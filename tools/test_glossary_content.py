from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools import build_glossary_db
from tools.generate_glossary_content import apply_review_overrides
from tools.glossary_content import (
    GlossaryContentError,
    canonical_json_bytes,
    load_catalog,
    parse_inventory,
)


class GlossaryContentTest(unittest.TestCase):
    def test_inventory_has_stable_full_coverage(self) -> None:
        inventory = parse_inventory()
        self.assertEqual(21, len(inventory.categories))
        self.assertEqual(1_649, len(inventory.terms))
        self.assertEqual("FIN-01-001", inventory.terms[0].term_id)
        self.assertEqual("FIN-21-066", inventory.terms[-1].term_id)
        self.assertTrue(inventory.sources)

    def test_catalog_validation_rejects_missing_term(self) -> None:
        inventory = parse_inventory()
        sample = inventory.terms[0]
        catalog = {
            "formatVersion": 1,
            "inventorySha256": inventory.sha256,
            "terms": [
                {
                    "termId": sample.term_id,
                    "categoryId": sample.category_id,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_bytes(canonical_json_bytes(catalog))
            with self.assertRaisesRegex(GlossaryContentError, "coverage mismatch"):
                load_catalog(path, inventory=inventory)

    def test_review_overrides_change_copy_but_cannot_change_identity(self) -> None:
        catalog = {"terms": [{"termId": "FIN-01-001", "oneLineDefinitionKo": "before"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            path.write_bytes(canonical_json_bytes({
                "formatVersion": 1,
                "overrides": {"FIN-01-001": {"oneLineDefinitionKo": "after"}},
            }))
            apply_review_overrides(catalog, path)
            self.assertEqual("after", catalog["terms"][0]["oneLineDefinitionKo"])
            path.write_bytes(canonical_json_bytes({
                "formatVersion": 1,
                "overrides": {"FIN-01-001": {"termId": "FIN-01-999"}},
            }))
            with self.assertRaisesRegex(GlossaryContentError, "immutable"):
                apply_review_overrides(catalog, path)

    @unittest.skipUnless(build_glossary_db.DEFAULT_CATALOG.is_file(), "authored catalog not generated")
    def test_compiled_database_is_searchable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.sqlite3"
            second = Path(directory) / "second.sqlite3"
            first_manifest = build_glossary_db.build_database(first)
            second_manifest = build_glossary_db.build_database(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_manifest, second_manifest)
            database = sqlite3.connect(first)
            try:
                row = database.execute(
                    "SELECT term_id FROM glossary_fts WHERE glossary_fts MATCH ? LIMIT 1",
                    ('"Discounted"*',),
                ).fetchone()
                self.assertIsNotNone(row)
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
