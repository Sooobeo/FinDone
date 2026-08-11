import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from tools import admin_source_ingestion_worker as source_worker
from tools import local_content_model as model


class LocalContentModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = model.load_model_config()

    def test_checked_in_golden_set_passes_every_field(self) -> None:
        result = model.evaluate_golden_set(self.config)

        self.assertEqual(result.case_count, result.passed_cases)
        self.assertEqual(result.field_assertion_count, result.passed_field_assertions)
        self.assertEqual(1.0, result.field_accuracy)

    def test_conflicting_structured_values_are_not_applied(self) -> None:
        baseline = model._golden_baseline()
        fragments = []
        for index, definition in enumerate(("첫 번째 정의", "두 번째 정의")):
            fragments.append(
                {
                    "sourceFragmentId": str(uuid.uuid4()),
                    "text": json.dumps(
                        {"element_id": "ACC-01", "definition": definition},
                        ensure_ascii=False,
                    ),
                }
            )
        result = model.transform_document(
            {"elementId": "ACC-01", "baseline": baseline, "sourceEvidence": fragments},
            self.config,
        )

        self.assertEqual(baseline["concept"]["definition_markdown"], result["concept"]["definition_markdown"])
        self.assertEqual([], result["evidence"])
        self.assertIn("충돌 필드 1개", result["change_summary"])

    def test_conflicting_aliases_inside_one_record_are_not_applied(self) -> None:
        baseline = model._golden_baseline()
        result = model.transform_document(
            {
                "elementId": "ACC-01",
                "baseline": baseline,
                "sourceEvidence": [
                    {
                        "sourceFragmentId": str(uuid.uuid4()),
                        "text": json.dumps(
                            {
                                "element_id": "ACC-01",
                                "definition": "첫 번째 정의",
                                "정의": "충돌하는 두 번째 정의",
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
            self.config,
        )

        self.assertEqual(baseline["concept"]["definition_markdown"], result["concept"]["definition_markdown"])
        self.assertEqual([], result["evidence"])

    def test_repair_restores_only_rejected_field(self) -> None:
        baseline = model._golden_baseline()
        document = {
            "elementId": "ACC-01",
            "baseline": baseline,
            "sourceEvidence": [
                {
                    "sourceFragmentId": str(uuid.uuid4()),
                    "text": json.dumps(
                        {
                            "element_id": "ACC-01",
                            "definition": "짧음",
                            "intuition": "검증 가능한 충분한 길이의 직관 설명을 새 값으로 제공한다.",
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        }
        candidate = model.transform_document(document, self.config)
        repaired = model.repair_candidate(
            document,
            candidate,
            ["concept.definition_markdown: too_short - definition is too short"],
        )

        self.assertEqual(baseline["concept"]["definition_markdown"], repaired["concept"]["definition_markdown"])
        self.assertNotEqual(baseline["concept"]["intuition_markdown"], repaired["concept"]["intuition_markdown"])
        self.assertTrue(all(item["field_path"] != "definition_markdown" for item in repaired["evidence"]))

    def test_uploaded_sqlite_table_reaches_the_local_content_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new-content.sqlite3"
            database = sqlite3.connect(path)
            database.execute("CREATE TABLE cards(element_id TEXT, definition TEXT)")
            database.execute(
                "INSERT INTO cards VALUES (?, ?)",
                ("ACC-01", "회계등식은 자산과 부채 및 자본의 조달 관계를 설명한다."),
            )
            database.commit()
            database.close()
            extracted = source_worker.extract_sqlite(path)

        baseline = model._golden_baseline()
        payload = model.transform_document(
            {
                "elementId": "ACC-01",
                "baseline": baseline,
                "sourceEvidence": [
                    {
                        "sourceFragmentId": str(uuid.uuid4()),
                        "text": extracted.fragments[0].text,
                    }
                ],
            },
            self.config,
        )

        self.assertEqual(
            "회계등식은 자산과 부채 및 자본의 조달 관계를 설명한다.",
            payload["concept"]["definition_markdown"],
        )


if __name__ == "__main__":
    unittest.main()
