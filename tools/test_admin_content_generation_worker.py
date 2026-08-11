import json
import unittest
import uuid
from unittest import mock

from tools import admin_content_generation_worker as worker


BATCH_ID = "10000000-0000-0000-0000-000000000001"
FRAGMENT_ID = "20000000-0000-0000-0000-000000000002"


def context() -> worker.ElementContext:
    checklist = (
        "- 재무제표 검토에서 거래 후 균형을 확인할 때 사용한다.\n"
        "- 재무모델에서 자금조달 변화의 영향을 연결할 때 사용한다."
    )
    return worker.ElementContext(
        element_id="ACC-01",
        element={
            "element_id": "ACC-01",
            "domain_id": "ACC",
            "element_number": 1,
            "title": "회계등식",
            "topic_name": "회계",
            "subtopic_name": "기초",
            "mode": "CONCEPT",
            "core_relation": "자산은 부채와 자본의 합이다.",
            "scope_notes": "회계 거래가 재무상태표 항목에 미치는 영향을 다룬다.",
            "source_label": "기준서",
            "source_locator": "https://example.com/accounting",
            "spec_section_locator": "ACC.1",
            "display_order": 1,
            "is_active": True,
        },
        concept={
            "concept_id": "ACC-01-C01",
            "element_id": "ACC-01",
            "title": "회계등식",
            "definition_markdown": "회계등식은 기업의 자산이 채권자와 소유자가 제공한 재원으로 구성된다는 관계를 설명한다.",
            "intuition_markdown": "회사가 보유한 현금과 설비는 반드시 조달 원천이 있다. 은행에서 빌린 부분은 부채이고 주주가 납입하거나 영업으로 축적한 부분은 자본이므로 전체 자산과 연결된다.",
            "learning_notes_markdown": "### 거래 분석\n\n각 거래가 자산·부채·자본 중 어느 항목을 바꾸는지 순서대로 확인한다.",
            "checklist_markdown": checklist,
            "glossary_terms": ["자산", "부채", "자본"],
        },
        formula={
            "formula_id": "ACC-01-F01",
            "element_id": "ACC-01",
            "formula_key": "primary",
            "title": "회계등식",
            "expression_markdown": "$$A=L+E$$",
            "assumptions_markdown": "보고 시점의 인식된 잔액을 같은 측정 기준으로 비교한다.",
            "notes_markdown": checklist,
            "variables": [
                {"symbol": "A", "meaning": "자산"},
                {"symbol": "L", "meaning": "부채"},
                {"symbol": "E", "meaning": "자본"},
            ],
            "display_order": 0,
            "is_primary": True,
        },
        evidence=(
            {
                "source_fragment_id": FRAGMENT_ID,
                "source_version_id": "30000000-0000-0000-0000-000000000003",
                "source_id": "SRC-ACC",
                "source_label": "회계 기준",
                "source_locator": "https://example.com/accounting",
                "fragment_kind": "text",
                "locator": {"section": "1"},
                "content_excerpt": "자산은 기업이 통제하는 경제적 자원이며 부채와 자본을 통해 조달된다.",
            },
        ),
    )


def candidate(*, changed: bool = True, evidence: bool = True) -> dict:
    value = context()
    concept = {field: value.concept[field] for field in worker.ENTITY_FIELDS["concept"]}
    if changed:
        concept["definition_markdown"] = (
            "회계등식은 기업이 통제하는 자산과 그 자산을 조달한 부채 및 자본의 원천이 항상 연결된다는 구조를 설명한다."
        )
    return {
        "element": {field: value.element[field] for field in worker.ENTITY_FIELDS["element"]},
        "concept": concept,
        "formula": {field: value.formula[field] for field in worker.ENTITY_FIELDS["formula"]},
        "evidence": (
            [
                {
                    "entity_type": "concept",
                    "field_path": "definition_markdown",
                    "source_fragment_ids": [FRAGMENT_ID],
                    "rationale": "자산과 조달 원천의 관계를 직접 설명한다.",
                }
            ]
            if changed and evidence
            else []
        ),
        "confidence": 0.94,
        "risk_level": "low",
        "change_summary": "정의를 원문 근거에 맞춰 명확하게 정돈했다.",
    }


class FakeModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def generate(self, document, *, run_kind, run_number, idempotency_key):
        self.calls.append((document, run_kind, run_number, idempotency_key))
        payload = self.payloads.pop(0)
        body = worker.canonical_json_bytes(payload)
        return worker.ModelCallResult(
            payload=payload,
            response_id=f"resp-{len(self.calls)}",
            input_sha256="a" * 64,
            output_sha256=worker.sha256_bytes(body),
            input_tokens=100,
            output_tokens=50,
            duration_ms=25,
        )


class FakeSupabase:
    def __init__(self):
        self.secret_key = "supabase-secret"
        self.calls = []

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        if name == worker.ENQUEUE_RPC:
            return None
        if name == worker.CLAIM_RPC:
            return {
                "batch_id": BATCH_ID,
                "status": "running",
                "claimed_by": payload["p_worker_id"],
            }
        if name == worker.COMPLETE_RPC:
            return {
                "batchId": BATCH_ID,
                "status": "ready_for_review",
                "itemCount": len(payload["p_items"]),
            }
        if name == worker.FAIL_RPC:
            return {"batchId": BATCH_ID, "status": "queued", "retrying": True}
        return {"ok": True}


class CandidateValidationTest(unittest.TestCase):
    def test_changed_field_requires_allowed_fragment_and_passes_shared_validator(self):
        items, evidence_rows, errors = worker.validate_candidate(context(), candidate())

        self.assertEqual([], errors)
        self.assertEqual(1, len(items))
        self.assertEqual("concept", items[0]["entityType"])
        self.assertEqual(["definition_markdown"], items[0]["changedFields"])
        self.assertEqual(FRAGMENT_ID, evidence_rows[0]["sourceFragmentId"])
        self.assertEqual(0, items[0]["validationSummary"]["checksFailed"])

    def test_missing_field_evidence_is_rejected(self):
        items, evidence_rows, errors = worker.validate_candidate(
            context(), candidate(evidence=False)
        )

        self.assertTrue(any("has no source evidence" in error for error in errors))
        self.assertEqual([], evidence_rows)
        self.assertEqual(1, len(items))

    def test_invalid_first_output_is_repaired_automatically(self):
        model = FakeModel([candidate(evidence=False), candidate()])
        repairs = []

        bundle = worker.generate_element_candidate(
            model,
            BATCH_ID,
            context(),
            on_repair=lambda attempt, errors: repairs.append((attempt, errors)),
        )

        self.assertEqual(1, len(bundle.items))
        self.assertEqual(["generate", "repair"], [run["runKind"] for run in bundle.model_runs])
        self.assertEqual(1, repairs[0][0])
        self.assertIn("repair", model.calls[1][0])

    def test_unchanged_supported_baseline_produces_no_candidate_item(self):
        items, evidence_rows, errors = worker.validate_candidate(
            context(), candidate(changed=False)
        )
        self.assertEqual([], errors)
        self.assertEqual([], items)
        self.assertEqual([], evidence_rows)


class GenerationWorkerTest(unittest.TestCase):
    @mock.patch.object(worker, "load_element_contexts", return_value=[context()])
    def test_worker_persists_only_validated_candidate_and_progress(self, _load):
        client = FakeSupabase()
        model = FakeModel([candidate()])
        instance = worker.ContentGenerationWorker(
            client,
            model,
            "generation:test:1",
            "test-model",
        )

        result = instance.process_one()

        self.assertEqual("ready_for_review", result["status"])
        complete = next(payload for name, payload in client.calls if name == worker.COMPLETE_RPC)
        self.assertEqual(1, len(complete["p_items"]))
        self.assertEqual(1, len(complete["p_evidence"]))
        stages = [
            payload["p_processing_stage"]
            for name, payload in client.calls
            if name == worker.PROGRESS_RPC
        ]
        self.assertIn("local_schema_mapping", stages)
        self.assertIn("final_validation", stages)


class LocalRulesContentModelTest(unittest.TestCase):
    def test_explicit_json_field_is_mapped_without_network_or_tokens(self):
        document = worker.model_document(context())
        document["sourceEvidence"][0]["text"] = json.dumps(
            {
                "element_id": "ACC-01",
                "definition": (
                    "회계등식은 기업이 통제하는 자산과 이를 조달한 부채 및 자본의 원천이 "
                    "항상 연결된다는 구조를 설명한다."
                ),
            },
            ensure_ascii=False,
        )
        model = worker.LocalRulesContentModel()

        result = model.generate(
            document,
            run_kind="generate",
            run_number=1,
            idempotency_key=str(uuid.uuid4()),
        )

        self.assertTrue(result.response_id.startswith("local:"))
        self.assertEqual(0, result.input_tokens)
        self.assertEqual(0, result.output_tokens)
        self.assertNotEqual(
            context().concept["definition_markdown"],
            result.payload["concept"]["definition_markdown"],
        )
        self.assertEqual(FRAGMENT_ID, result.payload["evidence"][0]["source_fragment_ids"][0])

    def test_unstructured_prose_preserves_the_reviewed_baseline(self):
        document = worker.model_document(context())
        model = worker.LocalRulesContentModel()

        result = model.generate(
            document,
            run_kind="generate",
            run_number=1,
            idempotency_key=str(uuid.uuid4()),
        )

        self.assertEqual([], result.payload["evidence"])
        self.assertEqual(
            context().concept["definition_markdown"],
            result.payload["concept"]["definition_markdown"],
        )


if __name__ == "__main__":
    unittest.main()
