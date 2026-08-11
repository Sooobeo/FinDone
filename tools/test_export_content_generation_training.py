import unittest

from tools import export_content_generation_training as exporter


class TrainingRecordTest(unittest.TestCase):
    def test_only_released_approved_item_becomes_grounded_record(self):
        record = exporter.build_training_record(
            {
                "batch_id": "batch",
                "status": "released",
                "release_id": "release",
                "model_name": "model",
                "prompt_version": "prompt-v1",
            },
            {
                "generation_item_id": "item",
                "element_id": "ACC-01",
                "entity_type": "concept",
                "entity_key": "ACC-01-C01",
                "baseline_snapshot": {"definition_markdown": "before"},
                "generated_snapshot": {"definition_markdown": "after"},
                "changed_fields": ["definition_markdown"],
                "change_summary": "approved improvement",
                "confidence": 0.9,
                "risk_level": "low",
                "revision_id": "revision",
            },
            [{
                "field_path": "definition_markdown",
                "source_fragment_id": "fragment",
                "rationale": "supports the change",
            }],
            {"fragment": {"locator": {"page": 1}, "content_text": "source quote"}},
        )

        self.assertEqual("findone-content-rule-feedback-v1", record["schema"])
        self.assertEqual("source quote", record["input"]["sourceEvidence"][0]["text"])
        self.assertEqual("after", record["idealOutput"]["generatedSnapshot"]["definition_markdown"])
        self.assertEqual("revision", record["metadata"]["revisionId"])

    def test_unreleased_or_unapproved_data_is_never_exported(self):
        with self.assertRaises(exporter.TrainingExportError):
            exporter.build_training_record(
                {"status": "ready_for_review"},
                {"revision_id": None},
                [],
                {},
            )


if __name__ == "__main__":
    unittest.main()
