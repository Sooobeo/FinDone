#!/usr/bin/env python3
"""Compile the approved standalone glossary catalog into an offline SQLite FTS5 pack."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Iterable

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.glossary_content import (
    DEFAULT_CATALOG,
    DEFAULT_INVENTORY,
    GlossaryContentError,
    canonical_json_bytes,
    load_catalog,
    parse_inventory,
    sha256_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_DIR = ROOT / "app" / "src" / "main" / "assets"
DEFAULT_DATABASE = DEFAULT_ASSET_DIR / "glossary.sqlite3"
DEFAULT_MANIFEST = DEFAULT_ASSET_DIR / "glossary-manifest.json"
SCHEMA_VERSION = 1
GLOSSARY_DB_VERSION = 1
APPLICATION_ID = 1179071315

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA page_size = 4096;

CREATE TABLE metadata(
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE categories(
    category_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    display_order INTEGER NOT NULL UNIQUE,
    term_count INTEGER NOT NULL CHECK(term_count >= 0)
) WITHOUT ROWID;

CREATE TABLE terms(
    term_id TEXT PRIMARY KEY NOT NULL,
    category_id TEXT NOT NULL REFERENCES categories(category_id),
    display_order INTEGER NOT NULL,
    canonical_name_en TEXT NOT NULL,
    canonical_name_ko TEXT NOT NULL,
    concept_type TEXT NOT NULL,
    one_line_definition_ko TEXT NOT NULL,
    core_definition_ko TEXT NOT NULL,
    practical_context_ko TEXT NOT NULL,
    why_it_matters_ko TEXT NOT NULL,
    example_ko TEXT NOT NULL,
    formula_latex TEXT NOT NULL,
    formula_notes_ko TEXT NOT NULL,
    jurisdictions_json TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    review_status TEXT NOT NULL,
    review_flags_json TEXT NOT NULL,
    UNIQUE(category_id, display_order)
);

CREATE TABLE aliases(
    term_id TEXT NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    label_type TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    PRIMARY KEY(term_id, label),
    UNIQUE(term_id, display_order)
) WITHOUT ROWID;

CREATE TABLE limitations(
    term_id TEXT NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL,
    body_ko TEXT NOT NULL,
    PRIMARY KEY(term_id, display_order)
) WITHOUT ROWID;

CREATE TABLE sources(
    source_code TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE term_sources(
    term_id TEXT NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    source_code TEXT NOT NULL REFERENCES sources(source_code),
    display_order INTEGER NOT NULL,
    PRIMARY KEY(term_id, source_code),
    UNIQUE(term_id, display_order)
) WITHOUT ROWID;

CREATE TABLE related_terms(
    term_id TEXT NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    related_term_id TEXT NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL,
    PRIMARY KEY(term_id, related_term_id),
    UNIQUE(term_id, display_order),
    CHECK(term_id <> related_term_id)
) WITHOUT ROWID;

CREATE INDEX terms_category_order_idx ON terms(category_id, display_order);
CREATE INDEX related_terms_reverse_idx ON related_terms(related_term_id, term_id);

CREATE VIRTUAL TABLE glossary_fts USING fts5(
    term_id UNINDEXED,
    category_id UNINDEXED,
    canonical_name_en,
    canonical_name_ko,
    aliases,
    definition_text,
    context_text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build_database(
    output: Path,
    *,
    inventory_path: Path = DEFAULT_INVENTORY,
    catalog_path: Path = DEFAULT_CATALOG,
    glossary_version: int = GLOSSARY_DB_VERSION,
    expected_term_count: int | None = 1_649,
) -> dict[str, Any]:
    inventory = parse_inventory(inventory_path, expected_term_count=expected_term_count)
    catalog = load_catalog(catalog_path, inventory=inventory)
    terms = catalog["terms"]
    by_id = {term["termId"]: term for term in terms}
    category_counts: dict[str, int] = {}
    for term in terms:
        category_counts[term["categoryId"]] = category_counts.get(term["categoryId"], 0) + 1

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=output.name + ".", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    database = sqlite3.connect(temporary)
    try:
        database.executescript(SCHEMA_SQL)
        database.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        database.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        database.executemany(
            "INSERT INTO metadata(key,value) VALUES (?,?)",
            (
                ("schema_version", str(SCHEMA_VERSION)),
                ("glossary_db_version", str(glossary_version)),
                ("inventory_sha256", inventory.sha256),
                ("catalog_sha256", sha256_bytes(canonical_json_bytes(catalog))),
                ("term_count", str(len(terms))),
                ("generator", "tools/build_glossary_db.py"),
                ("as_of_date", catalog["asOfDate"]),
            ),
        )
        database.executemany(
            "INSERT INTO categories(category_id,name,display_order,term_count) VALUES (?,?,?,?)",
            (
                (
                    category.category_id,
                    category.name,
                    category.display_order,
                    category_counts.get(category.category_id, 0),
                )
                for category in inventory.categories
            ),
        )
        database.executemany(
            "INSERT INTO sources(source_code,title,url) VALUES (?,?,?)",
            ((source.source_code, source.title, source.url) for source in inventory.sources),
        )
        inventory_by_id = {term.term_id: term for term in inventory.terms}
        for term in terms:
            identity = inventory_by_id[term["termId"]]
            database.execute(
                """INSERT INTO terms(
                       term_id,category_id,display_order,canonical_name_en,canonical_name_ko,
                       concept_type,one_line_definition_ko,core_definition_ko,
                       practical_context_ko,why_it_matters_ko,example_ko,formula_latex,
                       formula_notes_ko,jurisdictions_json,as_of_date,review_status,review_flags_json
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    term["termId"],
                    term["categoryId"],
                    identity.display_order,
                    term["canonicalNameEn"],
                    term["canonicalNameKo"],
                    term["conceptType"],
                    term["oneLineDefinitionKo"],
                    term["coreDefinitionKo"],
                    term["practicalContextKo"],
                    term["whyItMattersKo"],
                    term["exampleKo"],
                    term["formulaLatex"],
                    term["formulaNotesKo"],
                    _json(term["jurisdictions"]),
                    term["asOfDate"],
                    term["reviewStatus"],
                    _json(term["reviewFlags"]),
                ),
            )

        # Child rows are populated only after every term exists so source and
        # cross-term foreign keys remain enabled throughout compilation.
        for term in terms:
            labels: list[tuple[str, str]] = []
            for label_type, label in (
                ("preferred_en", term["canonicalNameEn"]),
                ("preferred_ko", term["canonicalNameKo"]),
            ):
                if label and all(existing[1].casefold() != label.casefold() for existing in labels):
                    labels.append((label_type, label))
            for label in term["aliases"]:
                if all(existing[1].casefold() != label.casefold() for existing in labels):
                    labels.append(("alias", label))
            database.executemany(
                "INSERT INTO aliases(term_id,label,label_type,display_order) VALUES (?,?,?,?)",
                (
                    (term["termId"], label, label_type, order)
                    for order, (label_type, label) in enumerate(labels)
                ),
            )
            database.executemany(
                "INSERT INTO limitations(term_id,display_order,body_ko) VALUES (?,?,?)",
                (
                    (term["termId"], order, body)
                    for order, body in enumerate(term["limitationsKo"])
                ),
            )
            database.executemany(
                "INSERT INTO term_sources(term_id,source_code,display_order) VALUES (?,?,?)",
                (
                    (term["termId"], source_code, order)
                    for order, source_code in enumerate(term["sourceCodes"])
                ),
            )
            valid_related = [
                related
                for related in term["relatedTermIds"]
                if related in by_id and related != term["termId"]
            ]
            database.executemany(
                "INSERT INTO related_terms(term_id,related_term_id,display_order) VALUES (?,?,?)",
                (
                    (term["termId"], related, order)
                    for order, related in enumerate(dict.fromkeys(valid_related))
                ),
            )
            database.execute(
                """INSERT INTO glossary_fts(
                       term_id,category_id,canonical_name_en,canonical_name_ko,aliases,
                       definition_text,context_text
                   ) VALUES (?,?,?,?,?,?,?)""",
                (
                    term["termId"],
                    term["categoryId"],
                    term["canonicalNameEn"],
                    term["canonicalNameKo"],
                    " ".join(term["aliases"]),
                    "\n".join((term["oneLineDefinitionKo"], term["coreDefinitionKo"])),
                    "\n".join(
                        (
                            term["practicalContextKo"],
                            term["whyItMattersKo"],
                            term["exampleKo"],
                            *term["limitationsKo"],
                        )
                    ),
                ),
            )

        database.commit()
        database.execute("PRAGMA optimize")
        database.execute("VACUUM")
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()
    validate_database(temporary, expected_terms=len(terms))
    os.replace(temporary, output)
    return build_manifest(
        output,
        inventory_sha256=inventory.sha256,
        catalog_sha256=sha256_bytes(canonical_json_bytes(catalog)),
        glossary_version=glossary_version,
        expected_terms=len(terms),
    )


def validate_database(path: Path, *, expected_terms: int = 1_649) -> dict[str, int]:
    database = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        if database.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise GlossaryContentError("Glossary SQLite integrity_check failed")
        if database.execute("PRAGMA foreign_key_check").fetchall():
            raise GlossaryContentError("Glossary SQLite foreign_key_check failed")
        if database.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise GlossaryContentError("Glossary SQLite schema version differs")
        row_counts = {
            table: int(database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in (
                "metadata",
                "categories",
                "terms",
                "aliases",
                "limitations",
                "sources",
                "term_sources",
                "related_terms",
                "glossary_fts",
            )
        }
        if row_counts["categories"] != 21 or row_counts["terms"] != expected_terms:
            raise GlossaryContentError("Glossary SQLite category/term coverage failed")
        if row_counts["glossary_fts"] != expected_terms:
            raise GlossaryContentError("Every glossary term needs one FTS row")
        missing_sources = database.execute(
            """SELECT term_id FROM terms
               WHERE NOT EXISTS(SELECT 1 FROM term_sources WHERE term_sources.term_id=terms.term_id)
               LIMIT 1"""
        ).fetchone()
        if missing_sources:
            raise GlossaryContentError(f"{missing_sources[0]} has no source")
        empty_required = database.execute(
            """SELECT term_id FROM terms WHERE
               length(trim(one_line_definition_ko)) < 18 OR
               length(trim(core_definition_ko)) < 35 OR
               length(trim(practical_context_ko)) < 18 OR
               length(trim(example_ko)) < 15 LIMIT 1"""
        ).fetchone()
        if empty_required:
            raise GlossaryContentError(f"{empty_required[0]} has incomplete authored copy")
        return row_counts
    finally:
        database.close()


def build_manifest(
    database_path: Path,
    *,
    inventory_sha256: str,
    catalog_sha256: str,
    glossary_version: int,
    expected_terms: int = 1_649,
) -> dict[str, Any]:
    row_counts = validate_database(database_path, expected_terms=expected_terms)
    body = database_path.read_bytes()
    return {
        "manifestVersion": 1,
        "schemaVersion": SCHEMA_VERSION,
        "glossaryDbVersion": glossary_version,
        "llmRuntimeUsed": False,
        "databaseAsset": "glossary.sqlite3",
        "sha256": sha256_bytes(body),
        "byteSize": len(body),
        "inventorySha256": inventory_sha256,
        "catalogSha256": catalog_sha256,
        "rowCounts": row_counts,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--glossary-version", type=int, default=GLOSSARY_DB_VERSION)
    args = parser.parse_args(argv)
    if args.glossary_version < 1:
        raise GlossaryContentError("glossary version must be positive")
    manifest = build_database(
        args.database,
        inventory_path=args.inventory,
        catalog_path=args.catalog,
        glossary_version=args.glossary_version,
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.manifest.with_suffix(args.manifest.suffix + ".tmp")
    temporary.write_bytes(canonical_json_bytes(manifest))
    os.replace(temporary, args.manifest)
    print(
        json.dumps(
            {
                "status": "built",
                "terms": manifest["rowCounts"]["terms"],
                "bytes": manifest["byteSize"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GlossaryContentError, OSError, sqlite3.DatabaseError) as error:
        print(f"Glossary build stopped: {error}", file=__import__("sys").stderr)
        raise SystemExit(1) from error
