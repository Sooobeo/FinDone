#!/usr/bin/env python3
"""Build and validate queued FinDone content releases.

The worker projects immutable approved revisions onto the last stable SQLite
bundle (or the packaged v5 baseline), uploads the new private artifacts, and
finishes the job through service-role-only RPCs.  It never edits the checked-in
Android assets or the user's local learning database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sqlite3
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.admin_import_supabase import normalize_supabase_url, resolve_supabase_url


ROOT = Path(__file__).resolve().parents[1]
PACKAGED_DATABASE = ROOT / "app" / "src" / "main" / "assets" / "content.sqlite3"
PACKAGED_MANIFEST = ROOT / "app" / "src" / "main" / "assets" / "content-manifest.json"
RELEASE_BUCKET = "release-bundles"
CLAIM_RPC = "claim_ingestion_job"
COMPLETE_BUILD_RPC = "complete_release_build_job"
COMPLETE_VALIDATION_RPC = "complete_release_validation_job"
FAIL_RPC = "fail_release_job"
VALIDATOR_NAME = "findone-release-validator"
VALIDATOR_VERSION = "admin-v1"
SCHEMA_VERSION = 1
EXPECTED_DOMAIN_COUNTS = {
    "ACC": 12,
    "CF": 12,
    "INV": 9,
    "FI": 10,
    "DER": 10,
    "EQV": 64,
    "IBT": 18,
}
VERIFIED_TABLES = (
    "metadata",
    "domains",
    "elements",
    "concept_cards",
    "formula_cards",
    "sources",
    "element_sources",
    "knowledge_fts",
)
COPY_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "metadata": ("key", "value"),
    "domains": (
        "domain_id", "name", "description", "element_count", "display_order", "color_token",
    ),
    "sources": ("source_id", "label", "locator", "source_type", "notes"),
    "elements": (
        "element_id", "domain_id", "element_number", "title", "mode", "core_relation",
        "scope_notes", "source_label", "source_locator", "spec_section_locator", "display_order",
    ),
    "concept_cards": (
        "concept_id", "element_id", "title", "definition", "intuition", "scope_notes", "source_ids_json",
    ),
    "formula_cards": (
        "formula_id", "element_id", "title", "expression", "assumptions", "notes", "source_ids_json",
    ),
    "element_sources": ("element_id", "source_id", "ordinal"),
}

APP_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA page_size = 4096;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE domains (
    domain_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    element_count INTEGER NOT NULL CHECK (element_count > 0),
    display_order INTEGER NOT NULL UNIQUE,
    color_token TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY NOT NULL,
    label TEXT NOT NULL,
    locator TEXT NOT NULL,
    source_type TEXT NOT NULL,
    notes TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE elements (
    element_id TEXT PRIMARY KEY NOT NULL,
    domain_id TEXT NOT NULL REFERENCES domains(domain_id),
    element_number INTEGER NOT NULL CHECK (element_number > 0),
    title TEXT NOT NULL,
    mode TEXT NOT NULL,
    core_relation TEXT NOT NULL,
    scope_notes TEXT NOT NULL,
    source_label TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    spec_section_locator TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    UNIQUE (domain_id, element_number)
);

CREATE TABLE concept_cards (
    concept_id TEXT PRIMARY KEY NOT NULL,
    element_id TEXT NOT NULL UNIQUE REFERENCES elements(element_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    definition TEXT NOT NULL,
    intuition TEXT NOT NULL,
    scope_notes TEXT NOT NULL,
    source_ids_json TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE formula_cards (
    formula_id TEXT PRIMARY KEY NOT NULL,
    element_id TEXT NOT NULL UNIQUE REFERENCES elements(element_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    expression TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    notes TEXT NOT NULL,
    source_ids_json TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE element_sources (
    element_id TEXT NOT NULL REFERENCES elements(element_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (element_id, source_id)
) WITHOUT ROWID;

CREATE INDEX elements_domain_order_idx ON elements(domain_id, display_order);
CREATE INDEX element_sources_source_idx ON element_sources(source_id, element_id);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    element_id UNINDEXED,
    domain_id UNINDEXED,
    title,
    normalized_text,
    source_label,
    locator_text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_DATABASE_BYTES = 64 * 1024 * 1024


class ReleaseWorkerError(RuntimeError):
    """Raised when a release cannot be built or persisted safely."""


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    field_path: str | None = None
    details: dict[str, Any] | None = None

    def as_rpc(self) -> dict[str, Any]:
        return {
            "severity": "error",
            "code": self.code,
            "fieldPath": self.field_path,
            "message": self.message,
            "details": self.details or {},
        }


@dataclass(frozen=True)
class ValidationResult:
    checks_total: int
    checks_passed: int
    issues: tuple[ValidationIssue, ...]
    summary: dict[str, Any]

    @property
    def status(self) -> str:
        return "failed" if self.issues else "passed"

    @property
    def checks_failed(self) -> int:
        return len(self.issues)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _uuid(value: Any, label: str) -> str:
    try:
        result = str(uuid.UUID(str(value)))
    except (ValueError, AttributeError) as error:
        raise ReleaseWorkerError(f"{label} is not a canonical UUID") from error
    if result != str(value).lower():
        raise ReleaseWorkerError(f"{label} is not a canonical UUID")
    return result


def _text(snapshot: Mapping[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = snapshot.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ReleaseWorkerError(f"revision snapshot field {key} is invalid")
    return value


class SupabaseReleaseClient:
    def __init__(self, base_url: str, secret_key: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = normalize_supabase_url(base_url)
        self.secret_key = secret_key.strip()
        if not self.secret_key:
            raise ReleaseWorkerError("SUPABASE_SECRET_KEY is missing")
        self.timeout_seconds = timeout_seconds
        self.ssl_context = ssl.create_default_context()

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json; charset=utf-8",
        max_bytes: int = MAX_JSON_BYTES,
        extra_headers: Mapping[str, str] | None = None,
    ) -> bytes:
        headers = {"apikey": self.secret_key, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = content_type
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds, context=self.ssl_context
            ) as response:
                result = response.read(max_bytes + 1)
        except urllib.error.HTTPError as error:
            response = error.read(4096).decode("utf-8", errors="replace")
            raise ReleaseWorkerError(
                f"Supabase {method} {path.split('?', 1)[0]} failed with HTTP "
                f"{error.code}: {response[:1000]}"
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ReleaseWorkerError("Could not reach Supabase") from error
        if len(result) > max_bytes:
            raise ReleaseWorkerError("Supabase response exceeded its safety limit")
        return result

    def rpc(self, name: str, payload: Mapping[str, Any]) -> Any:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        raw = self._request("POST", f"/rest/v1/rpc/{name}", body=body)
        try:
            return json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReleaseWorkerError(f"{name} returned invalid JSON") from error

    def select(
        self,
        table: str,
        *,
        columns: Sequence[str],
        filters: Mapping[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        max_bytes: int = MAX_JSON_BYTES,
    ) -> list[dict[str, Any]]:
        query: dict[str, str] = {"select": ",".join(columns)}
        query.update(filters or {})
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = str(limit)
        raw = self._request(
            "GET",
            f"/rest/v1/{table}?{urllib.parse.urlencode(query)}",
            max_bytes=max_bytes,
        )
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReleaseWorkerError(f"{table} returned invalid JSON") from error
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise ReleaseWorkerError(f"{table} returned an unexpected response")
        return value

    def select_one(self, table: str, **kwargs: Any) -> dict[str, Any]:
        rows = self.select(table, limit=2, **kwargs)
        if len(rows) != 1:
            raise ReleaseWorkerError(f"Expected exactly one {table} row")
        return rows[0]

    @staticmethod
    def _storage_path(bucket: str, object_path: str) -> str:
        parts = [urllib.parse.quote(part, safe="") for part in object_path.split("/")]
        return "/storage/v1/object/" + urllib.parse.quote(bucket, safe="") + "/" + "/".join(parts)

    def upload(self, bucket: str, object_path: str, body: bytes, mime_type: str) -> None:
        self._request(
            "POST",
            self._storage_path(bucket, object_path),
            body=body,
            content_type=mime_type,
            max_bytes=1024 * 1024,
            extra_headers={"x-upsert": "true"},
        )

    def download(self, bucket: str, object_path: str, *, max_bytes: int) -> bytes:
        return self._request(
            "GET",
            self._storage_path(bucket, object_path),
            max_bytes=max_bytes,
            extra_headers={"Accept": "application/octet-stream"},
        )


def _rpc_object(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1 and isinstance(value[0], dict):
            return value[0]
    if isinstance(value, dict):
        return value
    raise ReleaseWorkerError(f"{label} RPC returned an unexpected response")


def _verify_base_database(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 1:
        raise ReleaseWorkerError("base content database is missing")
    database = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        if database.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ReleaseWorkerError("base SQLite integrity_check failed")
        if database.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise ReleaseWorkerError("base SQLite schema version is unsupported")
        table_names = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
        }
        if not set(VERIFIED_TABLES).issubset(table_names):
            raise ReleaseWorkerError("base SQLite is missing a required table")
    finally:
        database.close()


def _create_clean_database(base_path: Path, output_path: Path) -> None:
    """Copy canonical rows into a newly-created app schema, excluding DB history."""

    if output_path.exists():
        raise ReleaseWorkerError("clean release output already exists")
    source = sqlite3.connect(f"file:{base_path.as_posix()}?mode=ro", uri=True)
    output = sqlite3.connect(output_path)
    try:
        output.executescript(APP_SCHEMA_SQL)
        output.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        output.execute("PRAGMA application_id = 1179534414")
        for table, columns in COPY_TABLE_COLUMNS.items():
            names = ",".join(f'"{column}"' for column in columns)
            placeholders = ",".join("?" for _ in columns)
            rows = source.execute(f'SELECT {names} FROM "{table}"').fetchall()
            output.executemany(
                f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
                rows,
            )
        output.commit()
        if output.execute("PRAGMA foreign_key_check").fetchall():
            raise ReleaseWorkerError("clean baseline foreign-key projection failed")
    except Exception:
        output.rollback()
        raise
    finally:
        output.close()
        source.close()


def _update_exact(database: sqlite3.Connection, sql: str, values: Sequence[Any], label: str) -> None:
    cursor = database.execute(sql, tuple(values))
    if cursor.rowcount != 1:
        raise ReleaseWorkerError(f"{label} does not target exactly one packaged row")


def _apply_revision(database: sqlite3.Connection, revision: Mapping[str, Any]) -> str | None:
    operation = revision.get("operation")
    entity_type = revision.get("entity_type")
    snapshot = revision.get("snapshot")
    if operation not in {"insert", "update"} or not isinstance(snapshot, dict):
        raise ReleaseWorkerError("release contains an unsupported delete or malformed revision")

    if entity_type == "domain":
        if snapshot.get("is_active") is not True:
            raise ReleaseWorkerError("inactive domains cannot be projected to the app")
        domain_id = _text(snapshot, "domain_id")
        _update_exact(
            database,
            """UPDATE domains SET name=?, description=?, element_count=?, display_order=?, color_token=?
               WHERE domain_id=?""",
            (
                _text(snapshot, "name"),
                _text(snapshot, "description", allow_empty=True),
                int(snapshot.get("expected_element_count")),
                int(snapshot.get("display_order")),
                _text(snapshot, "color_token"),
                domain_id,
            ),
            domain_id,
        )
        return None

    if entity_type == "element":
        if snapshot.get("is_active") is not True:
            raise ReleaseWorkerError("inactive elements cannot be projected to the app")
        element_id = _text(snapshot, "element_id")
        _update_exact(
            database,
            """UPDATE elements SET domain_id=?, element_number=?, title=?, mode=?, core_relation=?,
               scope_notes=?, source_label=?, source_locator=?, spec_section_locator=?, display_order=?
               WHERE element_id=?""",
            (
                _text(snapshot, "domain_id"),
                int(snapshot.get("element_number")),
                _text(snapshot, "title"),
                _text(snapshot, "mode"),
                _text(snapshot, "core_relation", allow_empty=True),
                _text(snapshot, "scope_notes", allow_empty=True),
                _text(snapshot, "source_label", allow_empty=True),
                _text(snapshot, "source_locator", allow_empty=True),
                _text(snapshot, "spec_section_locator", allow_empty=True),
                int(snapshot.get("display_order")),
                element_id,
            ),
            element_id,
        )
        return element_id

    if entity_type == "concept":
        element_id = _text(snapshot, "element_id")
        _update_exact(
            database,
            """UPDATE concept_cards SET title=?, definition=?, intuition=?, scope_notes=?
               WHERE concept_id=? AND element_id=?""",
            (
                _text(snapshot, "title"),
                _text(snapshot, "definition_markdown"),
                _text(snapshot, "intuition_markdown"),
                _text(snapshot, "learning_notes_markdown"),
                _text(snapshot, "concept_id"),
                element_id,
            ),
            str(revision.get("entity_key")),
        )
        return element_id

    if entity_type == "formula":
        if snapshot.get("is_primary") is not True:
            raise ReleaseWorkerError("only the primary app formula can be released")
        element_id = _text(snapshot, "element_id")
        _update_exact(
            database,
            """UPDATE formula_cards SET title=?, expression=?, assumptions=?, notes=?
               WHERE formula_id=? AND element_id=?""",
            (
                _text(snapshot, "title"),
                _text(snapshot, "expression_markdown"),
                _text(snapshot, "assumptions_markdown", allow_empty=True),
                _text(snapshot, "notes_markdown", allow_empty=True),
                _text(snapshot, "formula_id"),
                element_id,
            ),
            str(revision.get("entity_key")),
        )
        return element_id

    if entity_type == "distractor":
        # The current Android schema generates concept choices deterministically and
        # has no distractor table. Keep the release build honest instead of silently
        # claiming that an unconsumed authoring record reached the app.
        raise ReleaseWorkerError("distractor revisions are not supported by Android schema v1")

    raise ReleaseWorkerError(f"unsupported release entity type: {entity_type}")


def _rebuild_fts(database: sqlite3.Connection) -> None:
    database.execute("DELETE FROM knowledge_fts")
    rows = database.execute(
        """SELECT e.element_id, e.domain_id, e.title, e.core_relation,
                  c.definition, c.intuition, c.scope_notes,
                  f.expression, f.assumptions, f.notes,
                  e.source_label, e.source_locator, e.spec_section_locator
           FROM elements e
           JOIN concept_cards c USING(element_id)
           JOIN formula_cards f USING(element_id)
           ORDER BY e.display_order"""
    ).fetchall()
    database.executemany(
        """INSERT INTO knowledge_fts(
               element_id, domain_id, title, normalized_text, source_label, locator_text
           ) VALUES (?, ?, ?, ?, ?, ?)""",
        (
            (
                row[0],
                row[1],
                row[2],
                "\n".join((row[0], row[2], *row[3:10])),
                row[10],
                f"{row[11]} {row[12]}",
            )
            for row in rows
        ),
    )


def validate_release_database(path: Path, manifest: Mapping[str, Any]) -> ValidationResult:
    issues: list[ValidationIssue] = []
    checks = 0

    def check(condition: bool, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            issues.append(ValidationIssue(code, message, details=details))

    check(path.is_file(), "database_missing", "content database artifact is missing")
    if not path.is_file():
        return ValidationResult(checks, checks - len(issues), tuple(issues), {})
    check(path.stat().st_size == manifest.get("byteSize"), "database_size", "database size differs from manifest")
    actual_sha = sha256_file(path)
    check(actual_sha == manifest.get("sha256"), "database_sha256", "database hash differs from manifest")

    database = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    row_counts: dict[str, int] = {}
    try:
        check(database.execute("PRAGMA integrity_check").fetchone() == ("ok",), "sqlite_integrity", "SQLite integrity_check failed")
        check(not database.execute("PRAGMA foreign_key_check").fetchall(), "sqlite_foreign_key", "SQLite foreign_key_check failed")
        check(database.execute("PRAGMA user_version").fetchone()[0] == manifest.get("schemaVersion"), "sqlite_schema", "SQLite schema version differs from manifest")
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        check(metadata.get("content_db_version") == str(manifest.get("contentDbVersion")), "metadata_version", "SQLite metadata content version differs")
        check(metadata.get("source_spec_sha256") == manifest.get("sourceSha256"), "metadata_source", "SQLite release fingerprint differs from manifest")
        for table in VERIFIED_TABLES:
            try:
                row_counts[table] = int(database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except sqlite3.DatabaseError:
                row_counts[table] = -1
            check(row_counts[table] == manifest.get("rowCounts", {}).get(table), "row_count", f"{table} row count differs from manifest", {"table": table})
        domain_counts = dict(database.execute("SELECT domain_id,COUNT(*) FROM elements GROUP BY domain_id"))
        check(domain_counts == EXPECTED_DOMAIN_COUNTS, "domain_counts", "domain element counts are not canonical")
        blank_rows = database.execute(
            """SELECT e.element_id FROM elements e
               JOIN concept_cards c USING(element_id)
               JOIN formula_cards f USING(element_id)
               WHERE trim(e.title)='' OR trim(c.definition)='' OR trim(c.intuition)=''
                  OR trim(c.scope_notes)='' OR trim(f.expression)=''"""
        ).fetchall()
        check(not blank_rows, "visible_content_blank", "a visible learning field is blank", {"sample": [row[0] for row in blank_rows[:3]]})
        malformed_fts = database.execute(
            """SELECT e.element_id FROM elements e
               JOIN concept_cards c USING(element_id)
               JOIN formula_cards f USING(element_id)
               JOIN knowledge_fts k USING(element_id)
               WHERE k.normalized_text <> e.element_id || char(10) || e.title || char(10) ||
                   e.core_relation || char(10) || c.definition || char(10) || c.intuition || char(10) ||
                   c.scope_notes || char(10) || f.expression || char(10) || f.assumptions || char(10) || f.notes"""
        ).fetchall()
        check(not malformed_fts, "fts_projection", "search projection differs from visible content")
    finally:
        database.close()
    return ValidationResult(
        checks_total=checks,
        checks_passed=checks - len(issues),
        issues=tuple(issues),
        summary={"databaseSha256": actual_sha, "databaseByteSize": path.stat().st_size, "rowCounts": row_counts},
    )


def build_release_bundle(
    base_database: Path,
    output_database: Path,
    output_manifest: Path,
    release: Mapping[str, Any],
    revisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _verify_base_database(base_database)
    content_version = int(release.get("content_version", 0))
    schema_version = int(release.get("schema_version", 0))
    if content_version < 1 or schema_version != SCHEMA_VERSION:
        raise ReleaseWorkerError("release version metadata is unsupported")
    release_id = _uuid(release.get("release_id"), "release_id")
    output_database.parent.mkdir(parents=True, exist_ok=True)
    _create_clean_database(base_database, output_database)

    release_identity = [
        {
            "revisionId": _uuid(item.get("revision_id"), "revision_id"),
            "entityType": item.get("entity_type"),
            "entityKey": item.get("entity_key"),
            "revisionNumber": item.get("revision_number"),
            "contentHash": item.get("content_hash"),
        }
        for item in sorted(revisions, key=lambda row: (str(row.get("entity_type")), str(row.get("entity_key"))))
    ]
    source_sha = sha256_bytes(canonical_json_bytes({"releaseId": release_id, "items": release_identity}))

    database = sqlite3.connect(output_database)
    try:
        database.execute("PRAGMA foreign_keys=ON")
        for revision in sorted(revisions, key=lambda row: (str(row.get("entity_type")), str(row.get("entity_key")))):
            _apply_revision(database, revision)
        _rebuild_fts(database)
        metadata_values = {
            "content_db_version": str(content_version),
            "schema_version": str(schema_version),
            "domain_count": "7",
            "element_count": "135",
            "generator": "tools/admin_release_worker.py",
            "source_spec": f"supabase-release:{release_id}",
            "source_spec_sha256": source_sha,
        }
        database.executemany(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)",
            metadata_values.items(),
        )
        database.commit()
        database.execute("PRAGMA optimize")
        database.execute("VACUUM")
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()

    row_counts: dict[str, int] = {}
    check_database = sqlite3.connect(f"file:{output_database.as_posix()}?mode=ro", uri=True)
    try:
        row_counts = {
            table: int(check_database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in VERIFIED_TABLES
        }
    finally:
        check_database.close()
    manifest: dict[str, Any] = {
        "manifestVersion": 1,
        "schemaVersion": schema_version,
        "contentDbVersion": content_version,
        "databaseAsset": "content.sqlite3",
        "sha256": sha256_file(output_database),
        "byteSize": output_database.stat().st_size,
        "sourceSpec": f"supabase-release:{release_id}",
        "sourceSha256": source_sha,
        "rowCounts": row_counts,
        "domainElementCounts": EXPECTED_DOMAIN_COUNTS,
        "buildMode": "clean-rebuild",
    }
    validation = validate_release_database(output_database, manifest)
    if validation.status != "passed":
        raise ReleaseWorkerError(validation.issues[0].message)
    output_manifest.write_bytes(canonical_json_bytes(manifest))
    return manifest


class ReleaseWorker:
    def __init__(self, client: SupabaseReleaseClient, worker_id: str) -> None:
        if WORKER_ID_RE.fullmatch(worker_id) is None:
            raise ReleaseWorkerError("worker id is invalid")
        self.client = client
        self.worker_id = worker_id

    def _claim(self) -> dict[str, Any] | None:
        return _rpc_object(
            self.client.rpc(
                CLAIM_RPC,
                {"p_worker_id": self.worker_id, "p_allowed_job_kinds": ["release_build", "release_validation"]},
            ),
            "claim",
        )

    def _base_database(self, directory: Path) -> Path:
        channel_rows = self.client.select(
            "release_channels",
            columns=("release_id",),
            filters={"channel": "eq.stable"},
            limit=1,
        )
        if not channel_rows:
            packaged_manifest = json.loads(PACKAGED_MANIFEST.read_text(encoding="utf-8"))
            if sha256_file(PACKAGED_DATABASE) != packaged_manifest.get("sha256"):
                raise ReleaseWorkerError("packaged baseline hash is invalid")
            return PACKAGED_DATABASE
        release_id = _uuid(channel_rows[0].get("release_id"), "stable release id")
        artifact = self.client.select_one(
            "release_artifacts",
            columns=("object_path", "sha256", "byte_size"),
            filters={"release_id": f"eq.{release_id}", "artifact_kind": "eq.content_database"},
        )
        body = self.client.download(RELEASE_BUCKET, str(artifact.get("object_path")), max_bytes=MAX_DATABASE_BYTES)
        if len(body) != int(artifact.get("byte_size", 0)) or sha256_bytes(body) != artifact.get("sha256"):
            raise ReleaseWorkerError("stable base artifact identity is invalid")
        result = directory / "base.sqlite3"
        result.write_bytes(body)
        return result

    def _release_revisions(self, release_id: str) -> list[dict[str, Any]]:
        items = self.client.select(
            "release_items",
            columns=("revision_id", "entity_type", "entity_key", "revision_number", "content_hash"),
            filters={"release_id": f"eq.{release_id}"},
            order="entity_type.asc,entity_key.asc",
        )
        if not items:
            raise ReleaseWorkerError("release contains no frozen approved revisions")
        ids = ",".join(str(item["revision_id"]) for item in items)
        revisions = self.client.select(
            "content_revisions",
            columns=("revision_id", "entity_type", "entity_key", "revision_number", "operation", "snapshot", "content_hash"),
            filters={"revision_id": f"in.({ids})"},
        )
        by_id = {str(row.get("revision_id")): row for row in revisions}
        result: list[dict[str, Any]] = []
        for item in items:
            revision = by_id.get(str(item.get("revision_id")))
            if revision is None or any(
                revision.get(key) != item.get(key)
                for key in ("entity_type", "entity_key", "revision_number", "content_hash")
            ):
                raise ReleaseWorkerError("frozen release item does not match its revision")
            result.append(revision)
        return result

    def _build(self, job: Mapping[str, Any]) -> dict[str, Any]:
        release_id = _uuid(job.get("release_id"), "release_id")
        release = self.client.select_one(
            "content_releases",
            columns=("release_id", "content_version", "version_name", "schema_version", "minimum_app_version", "status", "release_notes"),
            filters={"release_id": f"eq.{release_id}"},
        )
        if release.get("status") != "building":
            raise ReleaseWorkerError("claimed release is not building")
        revisions = self._release_revisions(release_id)
        with tempfile.TemporaryDirectory(prefix="findone-release-") as directory_name:
            directory = Path(directory_name)
            database_path = directory / "content.sqlite3"
            manifest_path = directory / "content-manifest.json"
            manifest = build_release_bundle(
                self._base_database(directory), database_path, manifest_path, release, revisions
            )
            database_body = database_path.read_bytes()
            manifest_body = manifest_path.read_bytes()
            database_object = f"{release_id}/content.sqlite3"
            manifest_object = f"{release_id}/content-manifest.json"
            self.client.upload(RELEASE_BUCKET, database_object, database_body, "application/x-sqlite3")
            self.client.upload(RELEASE_BUCKET, manifest_object, manifest_body, "application/json")
            return _rpc_object(
                self.client.rpc(
                    COMPLETE_BUILD_RPC,
                    {
                        "p_job_id": job["job_id"],
                        "p_worker_id": self.worker_id,
                        "p_manifest": manifest,
                        "p_manifest_sha256": sha256_bytes(manifest_body),
                        "p_manifest_byte_size": len(manifest_body),
                        "p_database_sha256": sha256_bytes(database_body),
                        "p_database_byte_size": len(database_body),
                        "p_database_object_path": database_object,
                        "p_manifest_object_path": manifest_object,
                        "p_output": {"builder": "admin-release-worker", "builderVersion": "admin-v1", "revisionCount": len(revisions)},
                    },
                ),
                "complete release build",
            ) or {}

    def _validate(self, job: Mapping[str, Any]) -> dict[str, Any]:
        release_id = _uuid(job.get("release_id"), "release_id")
        job_input = job.get("input")
        if not isinstance(job_input, dict):
            raise ReleaseWorkerError("release validation job input is invalid")
        validation_run_id = _uuid(job_input.get("validationRunId"), "validationRunId")
        release = self.client.select_one(
            "content_releases",
            columns=("release_id", "content_version", "schema_version", "manifest", "manifest_sha256", "database_sha256", "database_byte_size", "status"),
            filters={"release_id": f"eq.{release_id}"},
        )
        artifacts = self.client.select(
            "release_artifacts",
            columns=("artifact_kind", "object_path", "sha256", "byte_size"),
            filters={"release_id": f"eq.{release_id}"},
        )
        by_kind = {str(row.get("artifact_kind")): row for row in artifacts}
        database_artifact = by_kind.get("content_database")
        manifest_artifact = by_kind.get("manifest")
        if database_artifact is None or manifest_artifact is None:
            raise ReleaseWorkerError("release artifacts are incomplete")
        with tempfile.TemporaryDirectory(prefix="findone-validation-") as directory_name:
            directory = Path(directory_name)
            database_body = self.client.download(RELEASE_BUCKET, str(database_artifact["object_path"]), max_bytes=MAX_DATABASE_BYTES)
            manifest_body = self.client.download(RELEASE_BUCKET, str(manifest_artifact["object_path"]), max_bytes=1024 * 1024)
            database_path = directory / "content.sqlite3"
            database_path.write_bytes(database_body)
            issues: list[ValidationIssue] = []
            try:
                manifest = json.loads(manifest_body.decode("utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("manifest must be an object")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                manifest = {}
                issues.append(ValidationIssue("manifest_json", "release manifest is invalid JSON"))
            if sha256_bytes(manifest_body) != manifest_artifact.get("sha256") or sha256_bytes(manifest_body) != release.get("manifest_sha256"):
                issues.append(ValidationIssue("manifest_sha256", "release manifest hash is inconsistent"))
            if len(database_body) != int(database_artifact.get("byte_size", 0)) or len(database_body) != int(release.get("database_byte_size", 0)):
                issues.append(ValidationIssue("database_size", "release database size is inconsistent"))
            if sha256_bytes(database_body) != database_artifact.get("sha256") or sha256_bytes(database_body) != release.get("database_sha256"):
                issues.append(ValidationIssue("database_sha256", "release database hash is inconsistent"))
            if manifest != release.get("manifest"):
                issues.append(ValidationIssue("manifest_metadata", "stored release manifest differs from artifact"))
            database_result = validate_release_database(database_path, manifest)
            issues.extend(database_result.issues)
            checks_total = database_result.checks_total + 4
            checks_failed = len(issues)
            status = "failed" if issues else "passed"
            return _rpc_object(
                self.client.rpc(
                    COMPLETE_VALIDATION_RPC,
                    {
                        "p_job_id": job["job_id"],
                        "p_worker_id": self.worker_id,
                        "p_validation_run_id": validation_run_id,
                        "p_validation_status": status,
                        "p_checks_total": checks_total,
                        "p_checks_passed": checks_total - checks_failed,
                        "p_checks_failed": checks_failed,
                        "p_summary": {**database_result.summary, "validator": VALIDATOR_NAME, "validatorVersion": VALIDATOR_VERSION},
                        "p_issues": [issue.as_rpc() for issue in issues],
                        "p_output": {"validator": VALIDATOR_NAME, "validatorVersion": VALIDATOR_VERSION},
                    },
                ),
                "complete release validation",
            ) or {}

    def process_one(self) -> dict[str, Any] | None:
        job = self._claim()
        if job is None:
            return None
        job_id = _uuid(job.get("job_id"), "job_id")
        try:
            if job.get("status") != "running":
                raise ReleaseWorkerError("claim did not return a running job")
            if job.get("job_kind") == "release_build":
                return self._build(job)
            if job.get("job_kind") == "release_validation":
                return self._validate(job)
            raise ReleaseWorkerError("claim returned an unsupported job kind")
        except Exception as error:
            safe_message = str(error).replace(self.client.secret_key, "[redacted]")[:1000]
            terminal = _rpc_object(
                self.client.rpc(
                    FAIL_RPC,
                    {
                        "p_job_id": job_id,
                        "p_worker_id": self.worker_id,
                        "p_error_message": safe_message or error.__class__.__name__,
                        "p_output": {"failureType": error.__class__.__name__},
                    },
                ),
                "fail release job",
            )
            if terminal is not None and terminal.get("jobStatus") == "succeeded":
                return terminal
            raise ReleaseWorkerError("claimed release job failed safely") from error


def default_worker_id() -> str:
    hostname = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:48] or "host"
    return f"findone-release:{hostname}:{os.getpid()}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", default=default_worker_id())
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=2,
        help="Maximum jobs to claim in this run (a build queues its validation job)",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_jobs < 1 or args.max_jobs > 10:
        raise ReleaseWorkerError("--max-jobs must be between 1 and 10")
    client = SupabaseReleaseClient(
        base_url=resolve_supabase_url(),
        secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
        timeout_seconds=args.timeout,
    )
    worker = ReleaseWorker(client, args.worker_id)
    outcomes: list[dict[str, Any]] = []
    for _ in range(args.max_jobs):
        outcome = worker.process_one()
        if outcome is None:
            break
        outcomes.append(outcome)
    print(
        json.dumps(
            {"status": "processed" if outcomes else "idle", "jobs": outcomes},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReleaseWorkerError, ValueError, OSError, sqlite3.DatabaseError) as error:
        print(f"Release worker stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
