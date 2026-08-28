from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.admin_import_workbook import DEFAULT_SOURCE, EXPECTED_SOURCE_SHA256, build_workbook, write_workbook


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_ROOT = ROOT / "admin" / "content" / "workbook"


class AdminWorkbookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = json.loads((WORKBOOK_ROOT / "index.json").read_text(encoding="utf-8"))
        cls.units = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((WORKBOOK_ROOT / "units").glob("*.json"))
        }

    def test_index_has_expected_scope(self) -> None:
        self.assertEqual(self.index["schemaVersion"], 1)
        self.assertEqual(self.index["source"]["sha256"], EXPECTED_SOURCE_SHA256)
        self.assertEqual(self.index["stats"]["subjectCount"], 12)
        self.assertEqual(self.index["stats"]["unitCount"], 45)
        self.assertEqual(self.index["stats"]["questionCount"], 1350)
        self.assertEqual(len(self.index["subjects"]), 12)
        self.assertEqual(len(self.units), 45)

    def test_units_have_complete_unique_questions(self) -> None:
        indexed_ids = {
            unit["id"]
            for subject in self.index["subjects"]
            for unit in subject["units"]
        }
        self.assertEqual(indexed_ids, set(self.units))

        question_ids: set[str] = set()
        for unit_id, unit in self.units.items():
            self.assertEqual(unit["id"], unit_id)
            self.assertEqual(unit["sourceSha256"], self.index["source"]["sha256"])
            self.assertEqual(len(unit["questions"]), 30, unit_id)
            self.assertTrue(unit["theory"], unit_id)
            for question in unit["questions"]:
                self.assertNotIn(question["id"], question_ids)
                question_ids.add(question["id"])
                self.assertEqual(len(question["choices"]), 5, question["id"])
                self.assertIn(question["answerIndex"], range(5), question["id"])
                self.assertTrue(question["solution"], question["id"])
        self.assertEqual(len(question_ids), 1350)

    def test_generated_data_matches_source_byte_for_byte(self) -> None:
        self.assertTrue(DEFAULT_SOURCE.is_file(), f"Workbook source is missing: {DEFAULT_SOURCE}")
        source_bytes = DEFAULT_SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), EXPECTED_SOURCE_SHA256)
        rebuilt_index, rebuilt_units = build_workbook(source_bytes)
        self.assertEqual(rebuilt_index, self.index)
        self.assertEqual(rebuilt_units, self.units)

        with tempfile.TemporaryDirectory() as temporary_directory:
            generated_root = Path(temporary_directory) / "workbook"
            write_workbook(rebuilt_index, rebuilt_units, generated_root)
            self.assertEqual(
                (generated_root / "index.json").read_bytes(),
                (WORKBOOK_ROOT / "index.json").read_bytes(),
            )
            for unit_id in sorted(rebuilt_units):
                self.assertEqual(
                    (generated_root / "units" / f"{unit_id}.json").read_bytes(),
                    (WORKBOOK_ROOT / "units" / f"{unit_id}.json").read_bytes(),
                    unit_id,
                )


if __name__ == "__main__":
    unittest.main()
