#!/usr/bin/env python3
"""Verify the public stable glossary response and its signed offline artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any


MAX_METADATA_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_DATABASE_BYTES = 128 * 1024 * 1024
EXPECTED_APPLICATION_ID = 1_179_071_315
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERIFIED_TABLES = {
    "metadata", "categories", "terms", "aliases", "limitations",
    "sources", "term_sources", "related_terms", "glossary_fts",
}


class GlossaryReleaseVerificationError(RuntimeError):
    """Raised when a stable glossary artifact violates the app contract."""


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> urllib.request.Request | None:
        _https_url(urllib.parse.urljoin(request.full_url, new_url), "redirect URL")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _HttpsOnlyRedirectHandler(),
    )


def _https_url(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GlossaryReleaseVerificationError(f"{label} is missing")
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise GlossaryReleaseVerificationError(f"{label} must be an HTTPS URL")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value.lower()):
        raise GlossaryReleaseVerificationError(f"{label} is not a SHA-256 value")
    return value.lower()


def _fetch_bytes(url: str, maximum: int, timeout: float) -> bytes:
    request = urllib.request.Request(
        _https_url(url, "download URL"),
        headers={"Accept": "application/json, application/octet-stream", "User-Agent": "FinDone-Glossary-Verify/1.0"},
    )
    try:
        with _opener().open(
            request,
            timeout=timeout,
        ) as response:
            _https_url(response.geturl(), "final download URL")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > maximum:
                raise GlossaryReleaseVerificationError("response exceeds its safety limit")
            value = response.read(maximum + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(2048).decode("utf-8", errors="replace")
        raise GlossaryReleaseVerificationError(
            f"glossary endpoint returned HTTP {error.code}: {detail[:500]}"
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise GlossaryReleaseVerificationError(f"could not fetch glossary artifact: {error}") from error
    if len(value) > maximum:
        raise GlossaryReleaseVerificationError("response exceeds its safety limit")
    return value


def _download_database(
    url: str,
    destination: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
    timeout: float,
) -> None:
    request = urllib.request.Request(
        _https_url(url, "database URL"),
        headers={"Accept": "application/octet-stream", "User-Agent": "FinDone-Glossary-Verify/1.0"},
    )
    digest = hashlib.sha256()
    total = 0
    try:
        with _opener().open(
            request,
            timeout=timeout,
        ) as response, destination.open("wb") as output:
            _https_url(response.geturl(), "final database URL")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) != expected_bytes:
                raise GlossaryReleaseVerificationError("database Content-Length mismatch")
            while chunk := response.read(64 * 1024):
                total += len(chunk)
                if total > expected_bytes or total > MAX_DATABASE_BYTES:
                    raise GlossaryReleaseVerificationError("database exceeds its expected size")
                digest.update(chunk)
                output.write(chunk)
    except urllib.error.HTTPError as error:
        raise GlossaryReleaseVerificationError(
            f"database download returned HTTP {error.code}"
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise GlossaryReleaseVerificationError(f"could not download glossary database: {error}") from error
    if total != expected_bytes or digest.hexdigest() != expected_sha256:
        raise GlossaryReleaseVerificationError("database size or SHA-256 mismatch")


def verify_database(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    row_counts = manifest.get("rowCounts")
    if not isinstance(row_counts, dict) or set(row_counts) != VERIFIED_TABLES:
        raise GlossaryReleaseVerificationError("manifest rowCounts is invalid")
    database = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        if database.execute("pragma integrity_check").fetchone() != ("ok",):
            raise GlossaryReleaseVerificationError("SQLite integrity_check failed")
        if database.execute("pragma foreign_key_check").fetchall():
            raise GlossaryReleaseVerificationError("SQLite foreign_key_check failed")
        if database.execute("pragma application_id").fetchone() != (EXPECTED_APPLICATION_ID,):
            raise GlossaryReleaseVerificationError("SQLite application_id mismatch")
        if database.execute("pragma user_version").fetchone() != (manifest["schemaVersion"],):
            raise GlossaryReleaseVerificationError("SQLite schema version mismatch")
        for table, expected in row_counts.items():
            if table not in VERIFIED_TABLES or not isinstance(expected, int):
                raise GlossaryReleaseVerificationError("manifest contains an unsupported row-count table")
            actual = database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if actual != expected:
                raise GlossaryReleaseVerificationError(f"{table} row count mismatch")
        if database.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE lower(name) LIKE '%admin%' "
            "OR lower(coalesce(sql, '')) LIKE '%admin_reference%'"
        ).fetchone()[0]:
            raise GlossaryReleaseVerificationError("Admin-only schema leaked into the app database")
        if database.execute(
            "SELECT COUNT(*) FROM metadata WHERE lower(key) LIKE '%llm%' "
            "OR lower(value) LIKE '%openai%' OR lower(value) LIKE '%gemini%' "
            "OR lower(value) LIKE '%claude%'"
        ).fetchone()[0]:
            raise GlossaryReleaseVerificationError("runtime model metadata leaked into the app database")
        metadata = dict(database.execute("SELECT key, value FROM metadata"))
        if (
            metadata.get("inventory_sha256") != manifest.get("inventorySha256")
            or metadata.get("catalog_sha256") != manifest.get("catalogSha256")
            or metadata.get("glossary_db_version") != str(manifest.get("glossaryDbVersion"))
            or metadata.get("term_count") != str(row_counts.get("terms"))
        ):
            raise GlossaryReleaseVerificationError("SQLite metadata does not match the manifest")
        hit = database.execute(
            "SELECT term_id FROM glossary_fts WHERE glossary_fts MATCH ? LIMIT 1",
            ('"Discounted"*',),
        ).fetchone()
        if hit != ("FIN-09-003",):
            raise GlossaryReleaseVerificationError("stable glossary FTS smoke test failed")
        return {
            "terms": row_counts.get("terms"),
            "categories": row_counts.get("categories"),
            "sources": row_counts.get("sources"),
            "ftsRows": row_counts.get("glossary_fts"),
            "searchHit": hit[0],
        }
    finally:
        database.close()


def verify_release(endpoint: str, timeout: float) -> dict[str, Any]:
    metadata_bytes = _fetch_bytes(endpoint, MAX_METADATA_BYTES, timeout)
    try:
        release = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlossaryReleaseVerificationError("stable endpoint returned invalid JSON") from error
    if not isinstance(release, dict):
        raise GlossaryReleaseVerificationError("stable endpoint returned an unexpected value")
    if release.get("protocolVersion") != 1 or release.get("channel") != "stable":
        raise GlossaryReleaseVerificationError("unsupported stable release protocol")
    if release.get("llmRuntimeUsed") is not False:
        raise GlossaryReleaseVerificationError("stable release does not prohibit runtime LLM use")
    version = release.get("glossaryDbVersion")
    schema_version = release.get("schemaVersion")
    expected_bytes = release.get("databaseByteSize")
    if not isinstance(version, int) or version < 1 or schema_version != 1:
        raise GlossaryReleaseVerificationError("stable glossary version is invalid")
    if not isinstance(expected_bytes, int) or expected_bytes not in range(1, MAX_DATABASE_BYTES + 1):
        raise GlossaryReleaseVerificationError("stable database size is invalid")
    manifest_sha = _sha256(release.get("manifestSha256"), "manifestSha256")
    database_sha = _sha256(release.get("databaseSha256"), "databaseSha256")
    manifest_bytes = _fetch_bytes(_https_url(release.get("manifestUrl"), "manifest URL"), MAX_MANIFEST_BYTES, timeout)
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha:
        raise GlossaryReleaseVerificationError("manifest SHA-256 mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlossaryReleaseVerificationError("stable manifest is invalid JSON") from error
    if not isinstance(manifest, dict):
        raise GlossaryReleaseVerificationError("stable manifest is not an object")
    if (
        manifest.get("manifestVersion") != 1
        or manifest.get("schemaVersion") != schema_version
        or manifest.get("glossaryDbVersion") != version
        or manifest.get("llmRuntimeUsed") is not False
        or manifest.get("databaseAsset") != "glossary.sqlite3"
        or manifest.get("byteSize") != expected_bytes
        or _sha256(manifest.get("sha256"), "manifest database SHA-256") != database_sha
        or not _sha256(manifest.get("inventorySha256"), "inventorySha256")
        or not _sha256(manifest.get("catalogSha256"), "catalogSha256")
    ):
        raise GlossaryReleaseVerificationError("stable manifest does not match release metadata")
    with tempfile.TemporaryDirectory(prefix="findone-glossary-verify-") as directory:
        database_path = Path(directory) / "glossary.sqlite3"
        _download_database(
            _https_url(release.get("databaseUrl"), "database URL"),
            database_path,
            expected_bytes=expected_bytes,
            expected_sha256=database_sha,
            timeout=timeout,
        )
        database_summary = verify_database(database_path, manifest)
    return {
        "status": "verified",
        "channel": "stable",
        "glossaryDbVersion": version,
        "schemaVersion": schema_version,
        "databaseByteSize": expected_bytes,
        "databaseSha256": database_sha,
        "manifestSha256": manifest_sha,
        "llmRuntimeUsed": False,
        **database_summary,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("endpoint")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 600:
        raise GlossaryReleaseVerificationError("timeout must be between 0 and 600 seconds")
    print(json.dumps(verify_release(args.endpoint, args.timeout), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GlossaryReleaseVerificationError, OSError, sqlite3.DatabaseError) as error:
        print(f"Glossary release verification stopped: {error}", file=__import__("sys").stderr)
        raise SystemExit(1) from error
