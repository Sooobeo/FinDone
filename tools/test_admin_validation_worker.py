import json
import unittest
from unittest import mock

from tools import admin_export_content as exporter
from tools import admin_validation_worker as worker

REVISION_ID = "10000000-0000-0000-0000-000000000001"
RUN_ID = "20000000-0000-0000-0000-000000000002"
JOB_ID = "30000000-0000-0000-0000-000000000003"
DISTRACTOR_ID = "40000000-0000-0000-0000-000000000004"


def revision(entity_type: str, entity_key: str, snapshot: dict) -> dict:
    return {
        "revision_id": REVISION_ID,
        "entity_type": entity_type,
        "entity_key": entity_key,
        "revision_number": 1,
        "operation": "update",
        "snapshot": snapshot,
        "content_hash": "a" * 64,
    }


def formula_snapshot() -> dict:
    return {
        "formula_id": "ACC-01-F01",
        "element_id": "ACC-01",
        "formula_key": "primary",
        "title": "회계등식",
        "expression_markdown": "핵심 식 $$A=L+E$$",
        "assumptions_markdown": "`$$code only`와 \\$100은 수식 구분자가 아니다.",
        "notes_markdown": "- 분개 검토에서 거래 후 균형을 확인할 때 쓴다.\n- 재무모델에서 자금조달 영향을 연결할 때 쓴다.",
        "variables": [{"symbol": "A", "meaning": "자산"}],
        "display_order": 0,
        "is_primary": True,
    }


class _Response:
    def __init__(self, value) -> None:
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int) -> bytes:
        return self.body[:size]


class _FakeClient:
    def __init__(
        self, revision_value: dict, *, select_error: Exception | None = None
    ) -> None:
        self.secret_key = "service-secret-value"
        self.revision_value = revision_value
        self.select_error = select_error
        self.rpc_calls: list[tuple[str, dict]] = []
        self.complete_error: Exception | None = None
        self.fail_response: dict = {"ok": True}
        self.claim = {
            "job_id": JOB_ID,
            "job_kind": "content_validation",
            "status": "running",
            "revision_id": REVISION_ID,
            "input": {"validationRunId": RUN_ID},
        }
        self.validation_run = {
            "validation_run_id": RUN_ID,
            "target_type": "revision",
            "revision_id": REVISION_ID,
            "status": "running",
            "validator_name": worker.VALIDATOR_NAME,
            "validator_version": worker.VALIDATOR_VERSION,
        }

    def rpc(self, name: str, payload: dict):
        self.rpc_calls.append((name, payload))
        if name == worker.CLAIM_RPC:
            return self.claim
        if name == worker.COMPLETE_RPC and self.complete_error is not None:
            raise self.complete_error
        if name == worker.FAIL_RPC:
            return self.fail_response
        return {"ok": True}

    def select_one(self, table: str, **_kwargs):
        if self.select_error is not None:
            raise self.select_error
        if table == "validation_runs":
            return self.validation_run
        if table == "content_revisions":
            return self.revision_value
        raise AssertionError(f"unexpected table {table}")


class ContentRevisionValidationTest(unittest.TestCase):
    def test_packaged_content_snapshots_all_pass(self) -> None:
        """Exercise the validator against the exact initial-import row mapping."""

        tables = exporter.build_export()["tables"]
        formulas_by_element = {
            row["element_id"]: row for row in tables["formula_cards"]
        }
        snapshots: list[tuple[str, str, dict]] = []

        for row in tables["domains"]:
            snapshots.append(
                (
                    "domain",
                    row["domain_id"],
                    {
                        "domain_id": row["domain_id"],
                        "name": row["name"],
                        "description": row["description"],
                        "expected_element_count": row["element_count"],
                        "display_order": row["display_order"],
                        "color_token": row["color_token"],
                        "is_active": True,
                    },
                )
            )

        for row in tables["elements"]:
            snapshots.append(
                (
                    "element",
                    row["element_id"],
                    {
                        "element_id": row["element_id"],
                        "domain_id": row["domain_id"],
                        "element_number": row["element_number"],
                        "title": row["title"],
                        "topic_name": "",
                        "subtopic_name": "",
                        "mode": row["mode"],
                        "core_relation": row["core_relation"],
                        "scope_notes": row["scope_notes"],
                        "source_label": row["source_label"],
                        "source_locator": row["source_locator"],
                        "spec_section_locator": row["spec_section_locator"],
                        "display_order": row["display_order"],
                        "is_active": True,
                    },
                )
            )

        for row in tables["concept_cards"]:
            snapshots.append(
                (
                    "concept",
                    row["concept_id"],
                    {
                        "concept_id": row["concept_id"],
                        "element_id": row["element_id"],
                        "title": row["title"],
                        "definition_markdown": row["definition"],
                        "intuition_markdown": row["intuition"],
                        "learning_notes_markdown": row["scope_notes"],
                        "checklist_markdown": formulas_by_element[row["element_id"]][
                            "notes"
                        ],
                        "glossary_terms": [],
                    },
                )
            )

        for row in tables["formula_cards"]:
            snapshots.append(
                (
                    "formula",
                    row["formula_id"],
                    {
                        "formula_id": row["formula_id"],
                        "element_id": row["element_id"],
                        "formula_key": "primary",
                        "title": row["title"],
                        "expression_markdown": row["expression"],
                        "assumptions_markdown": row["assumptions"],
                        "notes_markdown": row["notes"],
                        "variables": [],
                        "display_order": 0,
                        "is_primary": True,
                    },
                )
            )

        failures: list[str] = []
        for entity_type, entity_key, snapshot in snapshots:
            result = worker.validate_revision(
                revision(entity_type, entity_key, snapshot)
            )
            if result.status != "passed":
                issues = ", ".join(
                    f"{issue.field_path}:{issue.code}" for issue in result.issues
                )
                failures.append(f"{entity_type}:{entity_key} ({issues})")

        self.assertEqual(412, len(snapshots))
        self.assertEqual([], failures)

    def test_all_supported_entity_snapshots_pass(self) -> None:
        cases = [
            revision(
                "domain",
                "ACC",
                {
                    "domain_id": "ACC",
                    "name": "회계",
                    "description": "",
                    "expected_element_count": 12,
                    "display_order": 0,
                    "color_token": "research.accounting",
                    "is_active": True,
                },
            ),
            revision(
                "element",
                "ACC-01",
                {
                    "element_id": "ACC-01",
                    "domain_id": "ACC",
                    "element_number": 1,
                    "title": "회계등식",
                    "topic_name": "회계",
                    "subtopic_name": "기초",
                    "mode": "CONCEPT",
                    "core_relation": "A=L+E",
                    "scope_notes": "",
                    "source_label": "교재",
                    "source_locator": "p.1",
                    "spec_section_locator": "A.1",
                    "display_order": 1,
                    "is_active": True,
                },
            ),
            revision(
                "concept",
                "ACC-01-C01",
                {
                    "concept_id": "ACC-01-C01",
                    "element_id": "ACC-01",
                    "title": "회계등식",
                    "definition_markdown": "회계등식은 회사가 가진 자산의 재원이 부채와 자본으로 나뉜다는 기본 구조를 설명한다.",
                    "intuition_markdown": "회사의 재산은 어디선가 조달되어야 한다. 은행에서 빌리면 부채가 늘고 주주가 돈을 넣으면 자본이 늘어난다. 설비를 현금으로 사면 자산의 모양만 바뀐다.",
                    "learning_notes_markdown": "### 유형 A · 거래 후 잔액\n\n거래가 자산·부채·자본에 미치는 영향을 판단한다.",
                    "checklist_markdown": "- 분개 검토에서 거래 후 균형을 확인할 때 쓴다.\n- 재무모델에서 자금조달 영향을 연결할 때 쓴다.",
                    "glossary_terms": ["자산"],
                },
            ),
            revision("formula", "ACC-01-F01", formula_snapshot()),
            revision(
                "distractor",
                DISTRACTOR_ID,
                {
                    "distractor_id": DISTRACTOR_ID,
                    "element_id": "ACC-01",
                    "distractor_key": "assets-minus-liabilities",
                    "text": "A-L",
                    "explanation": "자본을 빠뜨림",
                    "misconception_type": "omission",
                    "difficulty": 2,
                    "display_order": 0,
                    "is_enabled": True,
                },
            ),
        ]

        for value in cases:
            with self.subTest(entity_type=value["entity_type"]):
                result = worker.validate_revision(value)
                self.assertEqual("passed", result.status, result.issues)
                self.assertGreater(result.checks_total, 0)
                self.assertEqual(result.checks_total, result.checks_passed)

    def test_invalid_stable_id_and_latex_delimiters_fail_with_field_paths(self) -> None:
        snapshot = formula_snapshot()
        snapshot["formula_id"] = "changed-id"
        snapshot["expression_markdown"] = "broken $$\\mathrm{FCFF}"
        result = worker.validate_revision(revision("formula", "ACC-01-F01", snapshot))

        self.assertEqual("failed", result.status)
        codes = {issue.code for issue in result.issues}
        self.assertIn("stable_id_invalid", codes)
        self.assertIn("revision_entity_key_mismatch", codes)
        self.assertIn("latex_delimiter_unclosed", codes)
        self.assertTrue(
            any(
                issue.field_path == "snapshot.expression_markdown"
                for issue in result.issues
            )
        )

    def test_markdown_code_spans_and_escaped_currency_are_not_math(self) -> None:
        markdown = "`$inline code` and \\$100\n```sh\necho '$HOME'\n```\n$$A=L+E$$"
        self.assertEqual([], worker.markdown_latex_issues(markdown, "snapshot.notes"))

    def test_markdown_scanner_matches_android_boundaries(self) -> None:
        accepted = "Price is $100 or $200\n    $indented-code\n\t$tab-code"
        self.assertEqual([], worker.markdown_latex_issues(accepted, "snapshot.notes"))

        invalid = "```text\n$code\n```oops\n$ a $\n\\(x+1\\)\n$x\n+y$"
        codes = {
            issue.code
            for issue in worker.markdown_latex_issues(invalid, "snapshot.notes")
        }
        self.assertIn("markdown_fence_unclosed", codes)

        inline_codes = {
            issue.code
            for issue in worker.markdown_latex_issues(
                "$ a $\n\\(x+1\\)\n$x\n+y$", "snapshot.notes"
            )
        }
        self.assertIn("latex_inline_spacing_invalid", inline_codes)
        self.assertIn("latex_delimiter_unsupported", inline_codes)
        self.assertIn("latex_delimiter_unclosed", inline_codes)

    def test_markdown_issue_collection_is_capped_during_scanning(self) -> None:
        issues = worker.markdown_latex_issues(
            "$$" + ("}" * 1000) + "$$", "snapshot.expression_markdown"
        )
        self.assertEqual(worker.MAX_ISSUES, len(issues))

    def test_snapshot_depth_and_control_characters_are_bounded(self) -> None:
        snapshot = formula_snapshot()
        snapshot["notes_markdown"] = "bad\u0000control"
        nested: dict = {}
        cursor = nested
        for _ in range(worker.MAX_JSON_DEPTH + 2):
            cursor["child"] = {}
            cursor = cursor["child"]
        snapshot["variables"] = [nested]
        result = worker.validate_revision(revision("formula", "ACC-01-F01", snapshot))
        codes = {issue.code for issue in result.issues}
        self.assertIn("snapshot_too_deep", codes)
        self.assertIn("control_character_invalid", codes)

    def test_glossary_and_formula_array_items_are_schema_checked(self) -> None:
        concept = {
            "concept_id": "ACC-01-C01",
            "element_id": "ACC-01",
            "title": "Accounting equation",
            "definition_markdown": "Definition",
            "intuition_markdown": "Intuition",
            "learning_notes_markdown": "Notes",
            "checklist_markdown": "Checklist",
            "glossary_terms": ["asset", "asset", None],
        }
        concept_result = worker.validate_revision(
            revision("concept", "ACC-01-C01", concept)
        )
        concept_codes = {issue.code for issue in concept_result.issues}
        self.assertIn("glossary_term_invalid", concept_codes)
        self.assertIn("glossary_term_duplicate", concept_codes)

        formula = formula_snapshot()
        formula["variables"] = [1, None, {"symbol": "", "meaning": []}]
        formula_result = worker.validate_revision(
            revision("formula", "ACC-01-F01", formula)
        )
        formula_codes = {issue.code for issue in formula_result.issues}
        self.assertIn("formula_variable_invalid", formula_codes)
        self.assertIn("formula_variable_symbol_invalid", formula_codes)
        self.assertIn("formula_variable_meaning_invalid", formula_codes)


class IdleClaimShapeTest(unittest.TestCase):
    def test_all_null_job_row_reads_as_an_idle_queue(self) -> None:
        empty = {"job_id": None, "status": None, "revision_id": None}
        rpc_object = worker.ContentValidationWorker._rpc_object
        self.assertIsNone(rpc_object(dict(empty), "claim"))
        self.assertIsNone(rpc_object([dict(empty)], "claim"))
        claimed = rpc_object({**empty, "status": "running"}, "claim")
        self.assertEqual("running", (claimed or {})["status"])


class ContentValidationWorkerTest(unittest.TestCase):
    def test_worker_claims_only_content_validation_and_completes_passed_run(
        self,
    ) -> None:
        client = _FakeClient(revision("formula", "ACC-01-F01", formula_snapshot()))
        outcome = worker.ContentValidationWorker(
            client, "validator:test:1"
        ).process_one()

        self.assertIsNotNone(outcome)
        self.assertEqual("passed", outcome.validation_status)
        claim_name, claim_payload = client.rpc_calls[0]
        self.assertEqual(worker.CLAIM_RPC, claim_name)
        self.assertEqual(["content_validation"], claim_payload["p_allowed_job_kinds"])
        complete_name, complete_payload = client.rpc_calls[-1]
        self.assertEqual(worker.COMPLETE_RPC, complete_name)
        self.assertEqual("passed", complete_payload["p_validation_status"])
        self.assertEqual([], complete_payload["p_issues"])

    def test_invalid_content_is_a_successful_job_with_failed_validation(self) -> None:
        snapshot = formula_snapshot()
        snapshot["expression_markdown"] = "$$unclosed"
        client = _FakeClient(revision("formula", "ACC-01-F01", snapshot))
        outcome = worker.ContentValidationWorker(
            client, "validator:test:2"
        ).process_one()

        self.assertEqual("failed", outcome.validation_status)
        complete_payload = client.rpc_calls[-1][1]
        self.assertEqual("failed", complete_payload["p_validation_status"])
        self.assertGreater(complete_payload["p_checks_failed"], 0)
        self.assertTrue(
            any(issue["severity"] == "error" for issue in complete_payload["p_issues"])
        )

    def test_infrastructure_failure_marks_claimed_job_failed_and_redacts_secret(
        self,
    ) -> None:
        client = _FakeClient(
            revision("formula", "ACC-01-F01", formula_snapshot()),
            select_error=RuntimeError("service-secret-value must not leak"),
        )
        with self.assertRaises(worker.ValidationWorkerError):
            worker.ContentValidationWorker(client, "validator:test:3").process_one()

        fail_name, fail_payload = client.rpc_calls[-1]
        self.assertEqual(worker.FAIL_RPC, fail_name)
        self.assertNotIn("service-secret-value", fail_payload["p_error_message"])
        self.assertIn("[redacted]", fail_payload["p_error_message"])

    def test_mismatched_validator_contract_fails_the_claimed_job(self) -> None:
        client = _FakeClient(revision("formula", "ACC-01-F01", formula_snapshot()))
        client.validation_run["validator_version"] = "unexpected-version"

        with self.assertRaises(worker.ValidationWorkerError):
            worker.ContentValidationWorker(
                client, "validator:test:version"
            ).process_one()

        fail_name, fail_payload = client.rpc_calls[-1]
        self.assertEqual(worker.FAIL_RPC, fail_name)
        self.assertIn("contract is inconsistent", fail_payload["p_error_message"])

    def test_lost_completion_response_reconciles_as_success(self) -> None:
        client = _FakeClient(revision("formula", "ACC-01-F01", formula_snapshot()))
        client.complete_error = TimeoutError("response lost after commit")
        client.fail_response = {
            "jobStatus": "succeeded",
            "validationRunId": RUN_ID,
            "validationStatus": "passed",
            "alreadyTerminal": True,
        }

        outcome = worker.ContentValidationWorker(
            client, "validator:test:reconcile"
        ).process_one()

        self.assertEqual("passed", outcome.validation_status)
        self.assertEqual(worker.COMPLETE_RPC, client.rpc_calls[-2][0])
        self.assertEqual(worker.FAIL_RPC, client.rpc_calls[-1][0])

    def test_idle_claim_returns_without_table_reads(self) -> None:
        client = _FakeClient(revision("formula", "ACC-01-F01", formula_snapshot()))
        client.claim = None
        self.assertIsNone(
            worker.ContentValidationWorker(client, "validator:test:4").process_one()
        )


class SupabaseRestClientTest(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_opaque_secret_key_is_sent_only_as_apikey(self, urlopen: mock.Mock) -> None:
        urlopen.return_value = _Response(None)
        client = worker.SupabaseRestClient(
            base_url="https://project.supabase.co",
            secret_key="secret-test-value",
        )
        client.rpc(
            worker.CLAIM_RPC,
            {
                "p_worker_id": "validator:test",
                "p_allowed_job_kinds": ["content_validation"],
            },
        )

        request = urlopen.call_args.args[0]
        self.assertEqual("secret-test-value", request.headers["Apikey"])
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("secret-test-value", request.full_url)
        self.assertNotIn(b"secret-test-value", request.data)
        self.assertTrue(request.full_url.endswith("/rest/v1/rpc/claim_ingestion_job"))

    def test_remote_supabase_url_requires_https(self) -> None:
        with self.assertRaises(worker.ValidationWorkerError):
            worker.SupabaseRestClient(
                base_url="http://example.supabase.co",
                secret_key="secret",
            )


if __name__ == "__main__":
    unittest.main()
