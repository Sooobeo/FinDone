import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools import admin_export_content as exporter


class AdminContentExportTest(unittest.TestCase):
    def test_csv_export_neutralizes_spreadsheet_formula_prefixes(self) -> None:
        self.assertEqual("'=HYPERLINK(\"bad\")", exporter._csv_value('=HYPERLINK("bad")'))
        self.assertEqual("'+cmd", exporter._csv_value("+cmd"))
        self.assertEqual(-10, exporter._csv_value(-10))

    def test_packaged_content_exports_with_expected_relations(self) -> None:
        snapshot = exporter.build_export()
        tables = snapshot["tables"]

        self.assertEqual(exporter.EXPORT_FORMAT, snapshot["exportFormat"])
        self.assertEqual(7, len(tables["domains"]))
        self.assertEqual(135, len(tables["elements"]))
        self.assertEqual(135, len(tables["concept_cards"]))
        self.assertEqual(135, len(tables["formula_cards"]))
        self.assertEqual(174, len(tables["sources"]))
        self.assertEqual(309, len(tables["element_sources"]))
        self.assertEqual("ACC-01", tables["elements"][0]["element_id"])
        self.assertEqual("IBT-18", tables["elements"][-1]["element_id"])

        fixture = exporter.build_frontend_fixture(snapshot)
        self.assertEqual(135, len(fixture))
        self.assertEqual("ACC-01", fixture[0]["elementId"])
        self.assertEqual("calculation", fixture[0]["mode"])
        self.assertEqual("published", fixture[0]["status"])
        self.assertEqual("packaged-v5", fixture[0]["updatedAt"])

        source_fixture = exporter.build_frontend_sources_fixture(snapshot)
        self.assertEqual(174, len(source_fixture))
        self.assertTrue(all(row["status"] == "ready" for row in source_fixture))
        self.assertEqual(309, sum(row["linkedElements"] for row in source_fixture))

    def test_json_and_csv_outputs_are_deterministic_and_spreadsheet_safe(self) -> None:
        snapshot = exporter.build_export()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            csv_dir = root / "csv"

            exporter.write_json(snapshot, first)
            exporter.write_json(snapshot, second)
            exporter.write_csv_tables(snapshot, csv_dir)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(exporter.EXPORT_FORMAT, json.loads(first.read_text("utf-8"))["exportFormat"])
            with (csv_dir / "elements.csv").open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(135, len(rows))
            self.assertIn("자산", rows[0]["core_relation"])
            with (csv_dir / "learning_content.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as stream:
                learning_rows = list(csv.DictReader(stream))
            self.assertEqual(135, len(learning_rows))
            self.assertEqual("회계·재무제표", learning_rows[0]["domain_name"])
            self.assertIn("왜 중요한가", learning_rows[0]["intuition_markdown"])
            self.assertIn("$$", learning_rows[0]["formula_markdown"])


if __name__ == "__main__":
    unittest.main()
