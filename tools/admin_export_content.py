#!/usr/bin/env python3
"""Export the packaged FinDone content database for the Supabase admin system.

The exporter is intentionally read-only and deterministic.  It validates the
packaged manifest and SQLite database before emitting a canonical JSON snapshot
and optional spreadsheet-friendly CSV files.  The JSON snapshot is the handoff
format used by the initial Supabase import; it is not a replacement for review
or release validation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_DIR = ROOT / "app" / "src" / "main" / "assets"
DEFAULT_DATABASE = DEFAULT_ASSET_DIR / "content.sqlite3"
DEFAULT_MANIFEST = DEFAULT_ASSET_DIR / "content-manifest.json"
EXPORT_FORMAT = "findone-admin-content-v1"

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "domains": (
        "domain_id",
        "name",
        "description",
        "element_count",
        "display_order",
        "color_token",
    ),
    "sources": (
        "source_id",
        "label",
        "locator",
        "source_type",
        "notes",
    ),
    "elements": (
        "element_id",
        "domain_id",
        "element_number",
        "title",
        "mode",
        "core_relation",
        "scope_notes",
        "source_label",
        "source_locator",
        "spec_section_locator",
        "display_order",
    ),
    "concept_cards": (
        "concept_id",
        "element_id",
        "title",
        "definition",
        "intuition",
        "scope_notes",
        "source_ids_json",
    ),
    "formula_cards": (
        "formula_id",
        "element_id",
        "title",
        "expression",
        "assumptions",
        "notes",
        "source_ids_json",
    ),
    "element_sources": (
        "element_id",
        "source_id",
        "ordinal",
    ),
}

TABLE_ORDER_BY = {
    "domains": "display_order",
    "sources": "source_id",
    "elements": "display_order",
    "concept_cards": "element_id",
    "formula_cards": "element_id",
    "element_sources": "element_id, ordinal, source_id",
}

LEARNING_CONTENT_COLUMNS = (
    "domain_id",
    "domain_name",
    "element_id",
    "element_number",
    "title",
    "mode",
    "core_relation",
    "element_scope_notes",
    "definition_markdown",
    "intuition_markdown",
    "learning_notes_markdown",
    "formula_markdown",
    "assumptions_markdown",
    "checklist_markdown",
    "source_ids_json",
    "spec_section_locator",
)


class AdminExportError(ValueError):
    """Raised when the packaged content cannot be exported safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdminExportError(f"Could not read content manifest: {path}") from error
    if not isinstance(value, dict):
        raise AdminExportError("Content manifest must be a JSON object")
    return value


def _read_table(
    database: sqlite3.Connection,
    table: str,
    columns: Sequence[str],
) -> list[dict[str, Any]]:
    projection = ", ".join(f'"{column}"' for column in columns)
    rows = database.execute(
        f'SELECT {projection} FROM "{table}" ORDER BY {TABLE_ORDER_BY[table]}'
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _validate_manifest_file(database_path: Path, manifest: dict[str, Any]) -> None:
    expected_asset = manifest.get("databaseAsset")
    if expected_asset != database_path.name:
        raise AdminExportError(
            f"Manifest expects {expected_asset!r}, not {database_path.name!r}"
        )
    if database_path.stat().st_size != manifest.get("byteSize"):
        raise AdminExportError("Content database byte size differs from the manifest")
    if sha256_file(database_path) != manifest.get("sha256"):
        raise AdminExportError("Content database SHA-256 differs from the manifest")


def _validate_tables(
    database: sqlite3.Connection,
    manifest: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
) -> None:
    integrity = database.execute("PRAGMA integrity_check").fetchone()
    if integrity != ("ok",):
        raise AdminExportError(f"SQLite integrity_check failed: {integrity}")
    foreign_key_errors = database.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise AdminExportError(f"SQLite foreign_key_check failed: {foreign_key_errors[:3]}")
    if database.execute("PRAGMA user_version").fetchone()[0] != manifest.get("schemaVersion"):
        raise AdminExportError("SQLite user_version differs from the manifest")

    expected_counts = manifest.get("rowCounts")
    if not isinstance(expected_counts, dict):
        raise AdminExportError("Manifest rowCounts is missing")
    for table, rows in tables.items():
        expected = expected_counts.get(table)
        if expected is None:
            if table != "element_sources":
                raise AdminExportError(f"Manifest does not declare {table} row count")
            continue
        if len(rows) != expected:
            raise AdminExportError(
                f"{table} row count differs: expected {expected}, found {len(rows)}"
            )

    elements = tables["elements"]
    concepts = tables["concept_cards"]
    formulas = tables["formula_cards"]
    sources = tables["sources"]
    links = tables["element_sources"]
    element_ids = {row["element_id"] for row in elements}
    source_ids = {row["source_id"] for row in sources}

    if len(element_ids) != len(elements):
        raise AdminExportError("Duplicate element_id found")
    if {row["element_id"] for row in concepts} != element_ids:
        raise AdminExportError("Concept cards are not exactly one per element")
    if {row["element_id"] for row in formulas} != element_ids:
        raise AdminExportError("Formula cards are not exactly one per element")
    if any(row["element_id"] not in element_ids for row in links):
        raise AdminExportError("element_sources contains an unknown element_id")
    if any(row["source_id"] not in source_ids for row in links):
        raise AdminExportError("element_sources contains an unknown source_id")

    linked_by_element: dict[str, list[str]] = {element_id: [] for element_id in element_ids}
    for row in links:
        linked_by_element[row["element_id"]].append(row["source_id"])
    for row in (*concepts, *formulas):
        try:
            declared = json.loads(row["source_ids_json"])
        except json.JSONDecodeError as error:
            raise AdminExportError(
                f"Invalid source_ids_json for {row['element_id']}"
            ) from error
        if declared != linked_by_element[row["element_id"]]:
            raise AdminExportError(
                f"Source ordering differs for {row['element_id']}"
            )

    actual_domain_counts = {
        domain_id: count
        for domain_id, count in database.execute(
            "SELECT domain_id, COUNT(*) FROM elements GROUP BY domain_id"
        )
    }
    if actual_domain_counts != manifest.get("domainElementCounts"):
        raise AdminExportError("Domain element counts differ from the manifest")


def build_export(
    database_path: Path = DEFAULT_DATABASE,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    """Return a validated, deterministic admin import snapshot."""

    database_path = database_path.resolve()
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    _validate_manifest_file(database_path, manifest)

    uri = f"file:{database_path.as_posix()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as database:
        tables = {
            table: _read_table(database, table, columns)
            for table, columns in TABLE_COLUMNS.items()
        }
        metadata = dict(database.execute("SELECT key, value FROM metadata ORDER BY key"))
        _validate_tables(database, manifest, tables)

    return {
        "exportFormat": EXPORT_FORMAT,
        "content": {
            "contentDbVersion": manifest["contentDbVersion"],
            "schemaVersion": manifest["schemaVersion"],
            "databaseSha256": manifest["sha256"],
            "databaseByteSize": manifest["byteSize"],
            "sourceSpec": manifest["sourceSpec"],
            "sourceSha256": manifest["sourceSha256"],
            "manifestSha256": sha256_file(manifest_path),
            "metadata": metadata,
        },
        "tables": tables,
    }


def write_json(snapshot: dict[str, Any], output_path: Path, *, compact: bool = False) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {
        "ensure_ascii": False,
        "sort_keys": True,
    }
    if compact:
        options["separators"] = (",", ":")
    else:
        options["indent"] = 2
    output_path.write_text(json.dumps(snapshot, **options) + "\n", encoding="utf-8")


def build_frontend_fixture(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the snapshot into the read-only Next.js demo grid contract."""

    tables = snapshot["tables"]
    domains = {row["domain_id"]: row for row in tables["domains"]}
    concepts = {row["element_id"]: row for row in tables["concept_cards"]}
    formulas = {row["element_id"]: row for row in tables["formula_cards"]}
    content_version = snapshot["content"]["contentDbVersion"]
    return [
        {
            "elementId": element["element_id"],
            "domainId": element["domain_id"],
            "domainName": domains[element["domain_id"]]["name"],
            "elementNumber": element["element_number"],
            "title": element["title"],
            "mode": "calculation" if element["mode"] == "calculation" else "concept",
            "coreRelation": element["core_relation"],
            "elementScopeNotes": element["scope_notes"],
            "definition": concepts[element["element_id"]]["definition"],
            "intuition": concepts[element["element_id"]]["intuition"],
            "scopeNotes": concepts[element["element_id"]]["scope_notes"],
            "formulaExpression": formulas[element["element_id"]]["expression"],
            "formulaAssumptions": formulas[element["element_id"]]["assumptions"],
            "formulaNotes": formulas[element["element_id"]]["notes"],
            "checklist": formulas[element["element_id"]]["notes"],
            "sourceLabel": element["source_label"],
            "sourceLocator": element["source_locator"],
            "specSectionLocator": element["spec_section_locator"],
            "status": "published",
            "issueCount": 0,
            "updatedAt": f"packaged-v{content_version}",
            "updatedBy": "초기 가져오기",
        }
        for element in tables["elements"]
    ]


def write_frontend_fixture(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_frontend_fixture(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_frontend_sources_fixture(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    tables = snapshot["tables"]
    linked_counts: dict[str, int] = {}
    domain_by_id = {row["domain_id"]: row for row in tables["domains"]}
    domain_by_element = {row["element_id"]: row["domain_id"] for row in tables["elements"]}
    domain_ids_by_source: dict[str, set[str]] = {}
    for row in tables["element_sources"]:
        linked_counts[row["source_id"]] = linked_counts.get(row["source_id"], 0) + 1
        domain_ids_by_source.setdefault(row["source_id"], set()).add(
            domain_by_element[row["element_id"]]
        )
    content_version = snapshot["content"]["contentDbVersion"]

    def kind(source_type: str) -> str:
        if source_type == "pdf":
            return "pdf"
        if source_type in {"web", "api", "license"}:
            return "url"
        return "document"

    return [
        {
            "id": source["source_id"],
            "label": source["label"],
            "kind": kind(source["source_type"]),
            "locator": source["locator"],
            "status": "ready",
            "linkedElements": linked_counts.get(source["source_id"], 0),
            "domains": [
                {
                    "id": domain_id,
                    "name": domain_by_id[domain_id]["name"],
                    "displayOrder": domain_by_id[domain_id]["display_order"],
                }
                for domain_id in sorted(
                    domain_ids_by_source.get(source["source_id"], set()),
                    key=lambda item: (domain_by_id[item]["display_order"], item),
                )
            ],
            "createdAt": f"packaged-v{content_version}",
        }
        for source in tables["sources"]
    ]


def write_frontend_sources_fixture(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_frontend_sources_fixture(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        # Spreadsheet applications may execute these prefixes as formulas.  CSV is an
        # interchange convenience only, so keep untrusted source text inert on open.
        return "'" + value
    return value


def write_csv_tables(snapshot: dict[str, Any], output_dir: Path) -> None:
    """Write normalized tables that can be opened by Excel or spreadsheet tools."""

    output_dir.mkdir(parents=True, exist_ok=True)
    tables = snapshot["tables"]
    for table, columns in TABLE_COLUMNS.items():
        path = output_dir / f"{table}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="raise")
            writer.writeheader()
            for row in tables[table]:
                writer.writerow({key: _csv_value(value) for key, value in row.items()})

    domains = {row["domain_id"]: row for row in tables["domains"]}
    concepts = {row["element_id"]: row for row in tables["concept_cards"]}
    formulas = {row["element_id"]: row for row in tables["formula_cards"]}
    learning_path = output_dir / "learning_content.csv"
    with learning_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LEARNING_CONTENT_COLUMNS)
        writer.writeheader()
        for element in tables["elements"]:
            concept = concepts[element["element_id"]]
            formula = formulas[element["element_id"]]
            writer.writerow(
                {
                    "domain_id": element["domain_id"],
                    "domain_name": domains[element["domain_id"]]["name"],
                    "element_id": element["element_id"],
                    "element_number": element["element_number"],
                    "title": element["title"],
                    "mode": element["mode"],
                    "core_relation": element["core_relation"],
                    "element_scope_notes": element["scope_notes"],
                    "definition_markdown": concept["definition"],
                    "intuition_markdown": concept["intuition"],
                    "learning_notes_markdown": concept["scope_notes"],
                    "formula_markdown": formula["expression"],
                    "assumptions_markdown": formula["assumptions"],
                    "checklist_markdown": formula["notes"],
                    "source_ids_json": concept["source_ids_json"],
                    "spec_section_locator": element["spec_section_locator"],
                }
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and export packaged FinDone content for the admin system."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", type=Path, help="Canonical JSON output path")
    parser.add_argument("--csv-dir", type=Path, help="Directory for spreadsheet CSV files")
    parser.add_argument(
        "--frontend-json",
        type=Path,
        help="Generated ConceptElement fixture for the Next.js demo grid",
    )
    parser.add_argument(
        "--frontend-sources-json",
        type=Path,
        help="Generated SourceItem fixture for the Next.js demo source list",
    )
    parser.add_argument("--compact", action="store_true", help="Write compact JSON")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        args.json is None
        and args.csv_dir is None
        and args.frontend_json is None
        and args.frontend_sources_json is None
    ):
        raise SystemExit("At least one output option is required")
    snapshot = build_export(args.database, args.manifest)
    if args.json is not None:
        write_json(snapshot, args.json, compact=args.compact)
    if args.csv_dir is not None:
        write_csv_tables(snapshot, args.csv_dir)
    if args.frontend_json is not None:
        write_frontend_fixture(snapshot, args.frontend_json)
    if args.frontend_sources_json is not None:
        write_frontend_sources_fixture(snapshot, args.frontend_sources_json)
    tables = snapshot["tables"]
    print(
        "Exported FinDone admin content: "
        f"{len(tables['domains'])} domains, "
        f"{len(tables['elements'])} elements, "
        f"{len(tables['sources'])} sources"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
