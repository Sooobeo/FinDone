#!/usr/bin/env python3
"""Import a verified FinDone admin snapshot through the Supabase RPC.

This utility is for the one-time bootstrap import.  It never embeds credentials:
``SUPABASE_URL`` and ``SUPABASE_SECRET_KEY`` must be supplied by the operator's
environment or secret manager.  Normal content editing happens through the
authenticated Admin web application after this import.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import admin_export_content as exporter

RPC_PATH = "/rest/v1/rpc/import_content_snapshot"
MAX_RESPONSE_BYTES = 1024 * 1024


class SupabaseImportError(RuntimeError):
    """Raised when the bootstrap RPC cannot be called safely."""


def normalize_supabase_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SupabaseImportError("SUPABASE_URL must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise SupabaseImportError("A remote Supabase project must use HTTPS")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise SupabaseImportError("SUPABASE_URL must not include a path, query, or fragment")
    return url


def snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    if snapshot.get("exportFormat") != exporter.EXPORT_FORMAT:
        raise SupabaseImportError("Unsupported or missing admin export format")
    content = snapshot.get("content")
    tables = snapshot.get("tables")
    if not isinstance(content, dict) or not isinstance(tables, dict):
        raise SupabaseImportError("Snapshot content and tables must be objects")
    required = (
        "domains",
        "sources",
        "elements",
        "concept_cards",
        "formula_cards",
        "element_sources",
    )
    if any(not isinstance(tables.get(name), list) for name in required):
        raise SupabaseImportError("Snapshot is missing a required table array")
    database_sha256 = content.get("databaseSha256")
    if not isinstance(database_sha256, str) or len(database_sha256) != 64:
        raise SupabaseImportError("Snapshot database SHA-256 is invalid")
    return {
        "databaseSha256": database_sha256,
        "contentDbVersion": content.get("contentDbVersion"),
        "schemaVersion": content.get("schemaVersion"),
        "rowCounts": {name: len(tables[name]) for name in required},
    }


def load_snapshot(path: Path | None) -> dict[str, Any]:
    if path is None:
        return exporter.build_export()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SupabaseImportError(f"Could not read snapshot: {path}") from error
    if not isinstance(value, dict):
        raise SupabaseImportError("Snapshot must be a JSON object")
    return value


def call_import_rpc(
    *,
    base_url: str,
    secret_key: str,
    snapshot: dict[str, Any],
    allow_overwrite: bool,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    url = normalize_supabase_url(base_url) + RPC_PATH
    secret = secret_key.strip()
    if not secret:
        raise SupabaseImportError("SUPABASE_SECRET_KEY is missing")
    payload = json.dumps(
        {
            "p_snapshot": snapshot,
            "p_allow_overwrite": allow_overwrite,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "apikey": secret,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        body = error.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
        raise SupabaseImportError(
            f"Supabase import failed with HTTP {error.code}: {body[:1000]}"
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise SupabaseImportError(f"Could not reach the Supabase import RPC: {error}") from error
    if len(body) > MAX_RESPONSE_BYTES:
        raise SupabaseImportError("Supabase import response exceeded the safety limit")
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SupabaseImportError("Supabase import returned invalid JSON") from error
    if not isinstance(result, dict):
        raise SupabaseImportError("Supabase import returned an unexpected response")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap verified app content into Supabase.")
    parser.add_argument("--snapshot", type=Path, help="Existing canonical export JSON")
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    snapshot = load_snapshot(args.snapshot)
    summary = snapshot_summary(snapshot)
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    base_url = os.environ.get("SUPABASE_URL", "")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")
    result = call_import_rpc(
        base_url=base_url,
        secret_key=secret_key,
        snapshot=snapshot,
        allow_overwrite=args.allow_overwrite,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SupabaseImportError as error:
        print(f"Admin import stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
