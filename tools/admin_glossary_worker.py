#!/usr/bin/env python3
"""Compile queued Admin glossary snapshots into verified offline release artifacts.

This worker is deterministic and contains no model/API authoring path. It receives the
already-authored Admin snapshot, builds SQLite FTS5, uploads private artifacts, and atomically
advances the independent glossary stable channel through service-role-only RPCs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.admin_import_supabase import resolve_supabase_url
from tools.admin_release_worker import ReleaseWorkerError, SupabaseReleaseClient, _rpc_object
from tools.build_glossary_db import build_database
from tools.glossary_content import canonical_json_bytes, sha256_bytes


RELEASE_BUCKET = "release-bundles"
CLAIM_RPC = "claim_glossary_compile_job"
COMPLETE_RPC = "complete_glossary_compile_job"
FAIL_RPC = "fail_glossary_compile_job"
TERM_ID_RE = re.compile(r"^FIN-(?:0[1-9]|1\d|2[01])-\d{3}$")
WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class GlossaryWorkerError(ReleaseWorkerError):
    """Raised when a glossary release cannot be compiled or published safely."""


def _list(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise GlossaryWorkerError(f"{label} must be an object array")
    return [dict(item) for item in value]


def _safe_cell(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text or "|" in text or "\n" in text or "\r" in text:
        raise GlossaryWorkerError(f"{label} cannot be represented in the release inventory")
    return text


def materialize_authoring_files(
    snapshot: Mapping[str, Any],
    directory: Path,
) -> tuple[Path, Path, int]:
    categories = _list(snapshot.get("categories"), "snapshot.categories")
    sources = _list(snapshot.get("sources"), "snapshot.sources")
    terms = _list(snapshot.get("terms"), "snapshot.terms")
    if len(categories) != 21 or not sources or not terms:
        raise GlossaryWorkerError("glossary compile snapshot coverage is incomplete")
    term_ids = [str(term.get("termId") or "") for term in terms]
    if len(term_ids) != len(set(term_ids)) or any(not TERM_ID_RE.fullmatch(term_id) for term_id in term_ids):
        raise GlossaryWorkerError("glossary compile snapshot has invalid or duplicate term IDs")

    by_category: dict[str, list[dict[str, Any]]] = {}
    for term in terms:
        by_category.setdefault(str(term.get("categoryId") or ""), []).append(term)
    markdown: list[str] = ["# FinDone glossary release snapshot", "", "## 0.1 Source code", ""]
    for source in sorted(sources, key=lambda item: str(item.get("sourceCode") or "")):
        code = _safe_cell(source.get("sourceCode"), "source code")
        title = _safe_cell(source.get("title"), f"{code} title")
        url = _safe_cell(source.get("url"), f"{code} URL")
        if not url.startswith("https://"):
            raise GlossaryWorkerError(f"{code} URL must use HTTPS")
        markdown.append(f"- **[{code}]** {title}: {url}")
    for category in sorted(categories, key=lambda item: int(item.get("displayOrder", -1))):
        category_id = _safe_cell(category.get("categoryId"), "category ID")
        category_name = _safe_cell(category.get("name"), f"category {category_id} name")
        markdown.extend(("", f"## {category_id}. {category_name}", "", "| ID | English | Korean | Aliases |", "|---|---|---|---|"))
        category_terms = sorted(
            by_category.get(category_id, []),
            key=lambda item: int(item.get("displayOrder", -1)),
        )
        for term in category_terms:
            term_id = _safe_cell(term.get("termId"), "term ID")
            canonical_en = _safe_cell(term.get("canonicalNameEn"), f"{term_id} English name")
            canonical_ko = _safe_cell(term.get("canonicalNameKo"), f"{term_id} Korean name")
            aliases_value = term.get("aliases")
            if not isinstance(aliases_value, list) or not all(isinstance(item, str) for item in aliases_value):
                raise GlossaryWorkerError(f"{term_id} aliases are invalid")
            aliases = " / ".join(_safe_cell(item, f"{term_id} alias") for item in aliases_value) or "—"
            markdown.append(f"| {term_id} | {canonical_en} | {canonical_ko} | {aliases} |")

    inventory_path = directory / "release-inventory.md"
    inventory_bytes = ("\n".join(markdown) + "\n").encode("utf-8")
    inventory_path.write_bytes(inventory_bytes)
    as_of_date = max((str(term.get("asOfDate") or "") for term in terms), default="")
    catalog = {
        "formatVersion": 1,
        "inventorySha256": sha256_bytes(inventory_bytes),
        "asOfDate": as_of_date,
        "generationModel": "admin-reviewed-static-glossary",
        "terms": terms,
    }
    catalog_path = directory / "release-catalog.json"
    catalog_path.write_bytes(canonical_json_bytes(catalog))
    return inventory_path, catalog_path, len(terms)


class GlossaryReleaseWorker:
    def __init__(self, client: SupabaseReleaseClient, worker_id: str) -> None:
        if not WORKER_ID_RE.fullmatch(worker_id):
            raise GlossaryWorkerError("worker ID contains unsupported characters")
        self.client = client
        self.worker_id = worker_id

    def process_one(self) -> dict[str, Any] | None:
        job = _rpc_object(
            self.client.rpc(CLAIM_RPC, {"p_worker_id": self.worker_id}),
            "claim glossary compile",
        )
        if job is None:
            return None
        job_id = str(job.get("jobId") or "")
        release_id = str(job.get("releaseId") or "")
        version = int(job.get("glossaryDbVersion") or 0)
        snapshot = job.get("snapshot")
        if not job_id or not release_id or version < 1 or not isinstance(snapshot, dict):
            raise GlossaryWorkerError("claimed glossary job is incomplete")
        try:
            with tempfile.TemporaryDirectory(prefix="findone-glossary-release-") as name:
                directory = Path(name)
                inventory_path, catalog_path, term_count = materialize_authoring_files(snapshot, directory)
                database_path = directory / "glossary.sqlite3"
                manifest_path = directory / "glossary-manifest.json"
                manifest = build_database(
                    database_path,
                    inventory_path=inventory_path,
                    catalog_path=catalog_path,
                    glossary_version=version,
                    expected_term_count=term_count,
                )
                manifest_bytes = canonical_json_bytes(manifest)
                manifest_path.write_bytes(manifest_bytes)
                database_bytes = database_path.read_bytes()
                object_prefix = f"glossary/{release_id}"
                database_object = f"{object_prefix}/glossary.sqlite3"
                manifest_object = f"{object_prefix}/glossary-manifest.json"
                self.client.upload(
                    RELEASE_BUCKET,
                    database_object,
                    database_bytes,
                    "application/x-sqlite3",
                )
                self.client.upload(
                    RELEASE_BUCKET,
                    manifest_object,
                    manifest_bytes,
                    "application/json",
                )
                completed = _rpc_object(
                    self.client.rpc(
                        COMPLETE_RPC,
                        {
                            "p_job_id": job_id,
                            "p_worker_id": self.worker_id,
                            "p_inventory_sha256": manifest["inventorySha256"],
                            "p_catalog_sha256": manifest["catalogSha256"],
                            "p_manifest_sha256": sha256_bytes(manifest_bytes),
                            "p_database_sha256": manifest["sha256"],
                            "p_database_byte_size": manifest["byteSize"],
                            "p_manifest_byte_size": len(manifest_bytes),
                            "p_database_object_path": database_object,
                            "p_manifest_object_path": manifest_object,
                            "p_term_count": term_count,
                            "p_output": {
                                "rowCounts": manifest["rowCounts"],
                                "manifestByteSize": len(manifest_bytes),
                                "compiler": "tools/admin_glossary_worker.py",
                                "llmRuntimeUsed": False,
                            },
                        },
                    ),
                    "complete glossary compile",
                )
                return completed or {
                    "jobId": job_id,
                    "releaseId": release_id,
                    "glossaryDbVersion": version,
                    "status": "published",
                }
        except Exception as error:
            safe_message = str(error).replace(self.client.secret_key, "[redacted]")[:1800]
            try:
                self.client.rpc(
                    FAIL_RPC,
                    {
                        "p_job_id": job_id,
                        "p_worker_id": self.worker_id,
                        "p_error_message": safe_message or error.__class__.__name__,
                    },
                )
            except Exception:
                pass
            raise GlossaryWorkerError("claimed glossary compile failed safely") from error


def default_worker_id() -> str:
    hostname = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:48] or "host"
    return f"findone-glossary:{hostname}:{os.getpid()}"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", default=default_worker_id())
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-jobs", type=int, default=1)
    args = parser.parse_args(argv)
    if args.max_jobs not in range(1, 11):
        raise GlossaryWorkerError("--max-jobs must be between 1 and 10")
    client = SupabaseReleaseClient(
        base_url=resolve_supabase_url(),
        secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
        timeout_seconds=args.timeout,
    )
    worker = GlossaryReleaseWorker(client, args.worker_id)
    outcomes: list[dict[str, Any]] = []
    for _ in range(args.max_jobs):
        outcome = worker.process_one()
        if outcome is None:
            break
        outcomes.append(outcome)
    print(json.dumps({"status": "processed" if outcomes else "idle", "jobs": outcomes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GlossaryWorkerError, ReleaseWorkerError, OSError, ValueError) as error:
        print(f"Glossary worker stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
