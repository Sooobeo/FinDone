import json
import math
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tools import train_concept_question_model as model
from tools import experiment_concept_question_model_v3 as v3_experiment
from tools import generate_concept_question_preview_v3 as v3_preview
from tools import review_concept_question_model as review_command
from tools import validate_concept_question_reset as reset_validator


class ConceptQuestionModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = model._load_json_object(model.DEFAULT_CONFIG)
        cls.elements = model.load_elements()
        cls.assignments, cls.split = model.build_split(cls.elements, cls.config)
        cls.facts, cls.questions = model.build_facts_and_questions(
            cls.elements,
            cls.assignments,
        )

    def test_element_level_split_is_deterministic_and_has_no_leakage(self) -> None:
        assignments_again, split_again = model.build_split(self.elements, self.config)

        self.assertEqual(self.assignments, assignments_again)
        self.assertEqual(self.split["splitSha256"], split_again["splitSha256"])
        self.assertEqual(
            {"train": 95, "validation": 20, "test": 20},
            dict(Counter(self.assignments.values())),
        )
        question_splits = {
            question.element_id: question.split for question in self.questions
        }
        self.assertEqual(self.assignments, question_splits)

    def test_canonical_corpus_yields_three_questions_per_element(self) -> None:
        self.assertEqual(135, len(self.elements))
        self.assertEqual(405, len(self.facts))
        self.assertEqual(405, len(self.questions))
        self.assertEqual(
            {3},
            set(Counter(question.element_id for question in self.questions).values()),
        )
        self.assertEqual(
            {"term_to_definition", "term_to_intuition", "term_to_verbal_relation"},
            {question.question_type for question in self.questions},
        )
        self.assertEqual(
            0,
            sum(
                model.text_mentions_title(
                    fact.text,
                    next(item.title for item in self.elements if item.element_id == fact.element_id),
                )
                for fact in self.facts
            ),
        )
        self.assertEqual(
            0,
            sum(
                bool(model.FORMULA_CHOICE_RE.search(fact.text))
                for fact in self.facts
                if fact.fact_type == "verbal_relation"
            ),
        )

    def test_duplicate_title_alias_is_never_a_distractor(self) -> None:
        by_id = {element.element_id: index for index, element in enumerate(self.elements)}
        cf_wacc = by_id["CF-07"]
        eqv_wacc = by_id["EQV-13"]

        self.assertNotIn(
            eqv_wacc,
            model.eligible_candidate_indices(self.elements, cf_wacc),
        )
        self.assertNotIn(
            cf_wacc,
            model.eligible_candidate_indices(self.elements, eqv_wacc),
        )
        by_title = {element.title: index for index, element in enumerate(self.elements)}
        terminal_value = by_title["계속가치(Terminal Value)"]
        plain_terminal_value = by_title["계속가치"]
        self.assertNotIn(
            plain_terminal_value,
            model.eligible_candidate_indices(self.elements, terminal_value),
        )

    def test_definition_candidate_filter_requires_source_backed_role_compatibility(self) -> None:
        by_id = {element.element_id: index for index, element in enumerate(self.elements)}
        receivable_account = by_id["ACC-03"]
        subscription_metric = by_id["EQV-23"]
        secured_transaction = by_id["FI-07"]

        target_evidence = model.definition_role_evidence(self.elements[receivable_account])
        metric_evidence = model.definition_role_evidence(self.elements[subscription_metric])
        entity_evidence = model.definition_role_evidence(self.elements[secured_transaction])
        self.assertEqual({"financial_entity"}, {item.role_id for item in target_evidence})
        self.assertEqual({"quantitative_measure"}, {item.role_id for item in metric_evidence})
        self.assertEqual({"financial_entity"}, {item.role_id for item in entity_evidence})
        self.assertTrue(all(item.source_locator for item in target_evidence))
        self.assertTrue(all(len(item.source_sha256) == 64 for item in target_evidence))

        mismatch = model.candidate_filter_decision(
            self.elements,
            receivable_account,
            subscription_metric,
            "term_to_definition",
        )
        compatible = model.candidate_filter_decision(
            self.elements,
            receivable_account,
            secured_transaction,
            "term_to_definition",
        )
        self.assertFalse(mismatch.allowed)
        self.assertEqual("definition-role-mismatch", mismatch.reason_id)
        self.assertTrue(compatible.allowed)
        self.assertEqual("source-backed-role-match", compatible.reason_id)

    def test_definition_candidate_filter_keeps_unknowns_and_four_choice_capacity(self) -> None:
        target = self.elements[0]
        unknown = model.ElementRecord(
            element_id="TEST-UNKNOWN",
            domain_id=target.domain_id,
            domain_name=target.domain_name,
            title="근거 미확정 개념",
            mode=target.mode,
            definition="여러 금융 현상을 함께 살펴본다.",
            intuition=target.intuition,
            core_relation=target.core_relation,
            source_label=target.source_label,
            source_locator=target.source_locator,
        )
        probe_elements = [target, unknown]
        decision = model.candidate_filter_decision(
            probe_elements,
            0,
            1,
            "term_to_definition",
        )
        self.assertTrue(decision.allowed)
        self.assertEqual("insufficient-source-evidence", decision.reason_id)

        definition_questions = [
            question
            for question in self.questions
            if question.question_type == "term_to_definition"
        ]
        self.assertTrue(definition_questions)
        self.assertGreater(
            sum(
                not model.candidate_filter_decision(
                    self.elements,
                    question.element_index,
                    candidate_index,
                    question.question_type,
                ).allowed
                for question in definition_questions
                for candidate_index in range(len(self.elements))
            ),
            0,
        )
        for question in definition_questions:
            self.assertGreaterEqual(
                len(
                    model.eligible_candidate_indices(
                        self.elements,
                        question.element_index,
                        question.question_type,
                    )
                ),
                4,
            )

    def test_cross_concept_filter_rejects_facts_that_expose_target_term(self) -> None:
        by_id = {element.element_id: index for index, element in enumerate(self.elements)}
        target = by_id["ACC-03"]
        accrual = by_id["ACC-02"]

        decision = model.candidate_filter_decision(
            self.elements,
            target,
            accrual,
            "term_to_intuition",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("target-term-visible-in-candidate-fact", decision.reason_id)
        self.assertIn(
            "매출채권",
            model.display_fact_text(self.elements[accrual], "intuition"),
        )

    def test_reference_weight_profiles_are_normalized(self) -> None:
        weak = self.config["weakSupervisionProfiles"]
        retrieval = self.config["retrievalProfiles"]
        weak_keys = (
            "questionWord", "questionChar", "answerWord", "answerChar",
            "sameDomain", "sameMode",
        )
        retrieval_keys = weak_keys + ("questionSemantic", "answerSemantic")

        for profile in weak:
            self.assertAlmostEqual(1.0, sum(float(profile[key]) for key in weak_keys), places=8)
        for profile in retrieval:
            self.assertAlmostEqual(
                1.0,
                sum(float(profile[key]) for key in retrieval_keys),
                places=8,
            )
        self.assertEqual(60, self.config["fusionBaseline"]["rrfK"])
        self.assertEqual([0.1, 1.0, 10.0], self.config["pairwiseLogisticCValues"])

    def test_exception_profile_reviews_only_completely_unsupported_candidates(self) -> None:
        exception_profile = next(
            profile
            for profile in self.config["automatedReview"]["profiles"]
            if profile["id"] == "exception-only"
        )
        minimum = exception_profile["minimumSelectedCandidateSupport"]

        self.assertEqual(0.0, minimum)
        reason = model._candidate_support_review_reason(
            0.0,
            minimum,
            review_zero_support=self.config["automatedReview"]["reviewZeroCandidateSupport"],
        )
        self.assertIsNotNone(reason)
        self.assertEqual("candidate-never-supported", reason["id"])
        self.assertIsNone(
            model._candidate_support_review_reason(
                1 / 198,
                minimum,
                review_zero_support=True,
            )
        )
        self.assertIsNone(
            model._candidate_support_review_reason(
                0.0,
                minimum,
                review_zero_support=False,
            )
        )

    def test_v3_weak_supervision_has_exactly_two_strong_candidates(self) -> None:
        profile = next(
            item
            for item in self.config["weakSupervisionProfiles"]
            if item["id"] == self.config["canonicalWeakSupervisionProfile"]
        )
        context = v3_experiment.build_v3_feature_context(
            self.elements,
            self.questions,
            profile,
            self.config["fusionBaseline"]["rrfK"],
        )

        for row in context.weak_relevance:
            self.assertEqual(2, sum(int(value) == 3 for value in row))
            self.assertEqual(6, sum(int(value) >= 2 for value in row))

    def test_v3_generated_ratio_profiles_are_normalized_and_include_baseline(self) -> None:
        profiles = v3_experiment.fine_ratio_profiles(self.config["v3Experiment"])

        self.assertEqual(25, len(profiles))
        self.assertIn("ratio-s0.250-m0.250", {item["id"] for item in profiles})
        for profile in profiles:
            self.assertAlmostEqual(
                1.0,
                sum(float(profile[key]) for key in v3_experiment.RETRIEVAL_SIGNALS),
                places=8,
            )

    def test_v3_embedding_revision_pins_are_full_commits(self) -> None:
        pins = self.config["v3Experiment"]["embeddingRevisionPins"]

        self.assertEqual(5, len(pins))
        for revision in pins.values():
            self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_v3_selection_never_reads_test_metrics(self) -> None:
        def run(run_id: str, ndcg: float, test_ndcg: float) -> dict[str, object]:
            return {
                "stage": "probe",
                "embeddingId": "tfidf-word-char",
                "retrievalProfileId": run_id,
                "rankerFamily": "pairwise-logistic",
                "rankerId": run_id,
                "status": "completed",
                "validation": {
                    "ndcgAt2": ndcg,
                    "strongPrecisionAt2": ndcg,
                    "precisionAt2": ndcg,
                    "retrievalRecallAt20": 1.0,
                    "mrr": 1.0,
                },
                "test": {"ndcgAt2": test_ndcg},
            }

        selected = v3_experiment.select_validation_run(
            [run("validation-winner", 0.9, 0.0), run("test-winner", 0.8, 1.0)],
            {"tfidf-word-char": 0},
        )

        self.assertEqual("validation-winner", selected["rankerId"])

    def test_v3_output_policy_cannot_target_admin_or_question_bank(self) -> None:
        output, build = v3_experiment._output_policy(
            Path("docs/modeling/experiments"), Path("build/concept-model-v3")
        )
        self.assertTrue(str(output).startswith(str(model.ROOT / "docs" / "modeling")))
        self.assertTrue(str(build).startswith(str(model.ROOT / "build")))
        with self.assertRaises(model.ConceptModelError):
            v3_experiment._output_policy(Path("admin/data"), Path("build/probe"))

    def test_v3_source_anchors_have_evidence_and_cross_concept_capacity(self) -> None:
        raw_by_id = v3_preview.load_raw_elements()
        anchors = {
            element.element_id: v3_preview.extract_anchor_evidence(
                element, raw_by_id[element.element_id]
            )
            for element in self.elements
        }
        minimum_capacity = 999
        for question in self.questions:
            target = self.elements[question.element_index]
            capacity = 0
            for candidate_index in model.eligible_candidate_indices(
                self.elements, question.element_index, question.question_type
            ):
                candidate = self.elements[candidate_index]
                evidence = v3_preview.build_cross_concept_evidence(
                    target, candidate, anchors
                )
                if evidence is None:
                    continue
                capacity += 1
                self.assertTrue(evidence["sharedAnchorIds"])
                self.assertTrue(evidence["distinctAxis"]["targetEvidence"])
                self.assertTrue(evidence["distinctAxis"]["candidateEvidence"])
            minimum_capacity = min(minimum_capacity, capacity)

        self.assertGreaterEqual(minimum_capacity, 2)

    def test_v3_every_general_question_has_two_auto_safe_mutations(self) -> None:
        for question in self.questions:
            mutations = v3_preview.generate_mutations(
                question.correct_answer,
                base_fact_id=question.fact_id,
                target_element_id=question.element_id,
            )
            safe = [item for item in mutations if item["autoReviewPassed"]]
            self.assertGreaterEqual(len(safe), 2, question.question_id)
            for mutation in safe:
                self.assertNotEqual(question.correct_answer, mutation["text"])
                self.assertIn("→", mutation["changedClaim"])
                self.assertEqual(False, mutation["statementTruth"])
                self.assertTrue(mutation["sourceTruthText"])

    def test_v3_selected_mutation_lint_rejects_broken_boundaries(self) -> None:
        self.assertIn(
            "broken-korean-particle",
            v3_preview.selected_mutation_lint_reasons(
                "부채, 이자비용, 세율를 나누면 결과가 달라진다."
            ),
        )
        self.assertIn(
            "broken-comparative-ending",
            v3_preview.selected_mutation_lint_reasons(
                "현재가치가 투자액보다 작면 부가 줄어든다."
            ),
        )

    def test_v3_reference_exception_policy_records_exact_corpus_threshold(self) -> None:
        raw_by_id = v3_preview.load_raw_elements()
        anchors = {
            element.element_id: v3_preview.extract_anchor_evidence(
                element, raw_by_id[element.element_id]
            )
            for element in self.elements
        }

        policy = v3_preview.reference_gate_policy(anchors)
        corpus = policy["anchorCorpus"]
        frequencies = sorted(
            v3_preview.anchor_document_frequency(anchors).values()
        )
        expected_rank = math.ceil(0.75 * len(frequencies))

        self.assertEqual(expected_rank, corpus["nearestRank"])
        self.assertEqual(frequencies[expected_rank - 1], corpus["documentFrequencyP75"])
        self.assertEqual(
            "displayedSharedAnchorCount == 0",
            policy["softReviewFormulas"]["no-displayed-fact-anchor-overlap"],
        )
        self.assertEqual(540, policy["hardGateThresholds"]["questionCount"])
        self.assertEqual(5, policy["hardGateThresholds"]["choiceCount"])

    def test_v3_relation_metadata_uses_source_scoped_participant_ids(self) -> None:
        element = self.elements[0]
        metadata = v3_preview.relation_metadata(
            element=element,
            text=element.core_relation,
            anchor_ids=("cash", "assets"),
        )

        self.assertEqual(element.element_id, metadata["participantIds"][0])
        self.assertEqual(
            f"{element.element_id}:source-anchor:cash",
            metadata["participantIds"][1],
        )
        self.assertGreaterEqual(len(metadata["participantIds"]), 2)
        self.assertGreaterEqual(len(metadata["relationEdges"]), 1)
        self.assertEqual(
            "checked-in-source-anchor-v1",
            metadata["relationEvidence"]["participantPolicy"],
        )

        mutation = {
            "mutationRuleId": "increase-decrease-forward",
            "changedClaim": "증가 → 감소",
        }
        changed = v3_preview._attach_relation_mutation_metadata(
            mutation,
            metadata,
        )
        self.assertEqual(
            metadata["participantIds"],
            changed["participantIds"],
        )
        self.assertEqual(
            1,
            changed["changedRelation"]["changedBindingOrEdgeCount"],
        )
        self.assertEqual(
            "replace_edge_predicate",
            changed["changedRelation"]["operation"],
        )

    def test_v3_hard_gate_checks_answer_choice_key(self) -> None:
        question = {
            "questionId": "probe",
            "elementId": "ACC-01",
            "elementTitle": "표시되지 않는 대상",
            "questionType": "term_to_incorrect_statement",
            "answerChoiceKey": "B",
            "choices": [
                {
                    "key": "A",
                    "choiceSourceType": "target_mutation",
                    "sourceElementId": "ACC-01",
                    "text": "거짓 설명",
                    "isAnswer": True,
                    "statementTruth": False,
                    "baseFactId": "fact-1",
                    "mutationRuleId": "rule-1",
                    "changedClaim": "참 → 거짓",
                    "falsityRationale": "출처 주장 하나를 뒤집었다.",
                    "sourceTruthText": "참 설명",
                },
                *[
                    {
                        "key": key,
                        "choiceSourceType": "target_fact",
                        "sourceElementId": "ACC-01",
                        "text": f"참 설명 {key}",
                        "isAnswer": False,
                        "statementTruth": True,
                    }
                    for key in "BCDE"
                ],
            ],
        }

        self.assertIn(
            "answer-choice-key-mismatch",
            v3_preview.hard_gate_reasons(question),
        )

    def test_v3_every_element_has_four_name_masked_atomic_facts(self) -> None:
        raw_by_id = v3_preview.load_raw_elements()

        for element in self.elements:
            facts = v3_preview.build_atomic_facts(
                element,
                raw_by_id[element.element_id],
                v3_preview.extract_anchor_evidence(
                    element,
                    raw_by_id[element.element_id],
                ),
            )
            self.assertGreaterEqual(len(facts), 4, element.element_id)
            for fact in facts:
                self.assertFalse(
                    model.text_mentions_title(fact["text"], element.title),
                    f"{element.element_id}/{fact['factId']}",
                )

    def test_cli_relative_paths_are_resolved_and_reported_from_repo_root(self) -> None:
        relative = Path("build/concept-ci/probe.json")

        self.assertEqual(
            model.ROOT / "build" / "concept-ci" / "probe.json",
            model._resolve_repo_path(relative),
        )
        self.assertEqual("build/concept-ci/probe.json", model._report_path(relative))

    def test_selection_uses_validation_and_cost_policy_only(self) -> None:
        def run(
            embedding: str,
            family: str,
            ranker: str,
            ndcg: float,
            precision: float,
            test_ndcg: float,
        ) -> dict[str, object]:
            return {
                "embeddingId": embedding,
                "retrievalProfileId": "lexical-balanced",
                "rankerFamily": family,
                "rankerId": ranker,
                "modelBytes": 100,
                "validation": {
                    "ndcgAt4": ndcg,
                    "precisionAt4": precision,
                    "retrievalRecallAt20": 1.0,
                },
                # Deliberately inverted values: selection must never read these.
                "test": {"ndcgAt4": test_ndcg},
            }

        runs = [
            run("kure-v1", "xgboost", "dense-best", 0.960, 1.0, 1.0),
            run("tfidf-word-char", "xgboost", "tree", 0.959, 1.0, 0.99),
            run("tfidf-word-char", "pairwise-logistic", "linear-low", 0.952, 0.98, 0.0),
            run("tfidf-word-char", "pairwise-logistic", "linear-high", 0.955, 0.99, 0.0),
        ]
        selected = model.select_validation_run(
            runs,
            self.config["embeddingCandidates"],
            self.config["retrievalProfiles"],
            0.01,
        )

        self.assertEqual("linear-high", selected["rankerId"])
        self.assertEqual("tfidf-word-char", selected["embeddingId"])

    def test_checked_in_question_bank_is_five_choice_candidate(self) -> None:
        bank = json.loads(model.DEFAULT_BANK.read_text(encoding="utf-8"))

        self.assertEqual(2, bank["bankVersion"])
        self.assertEqual("2.0", bank["contractVersion"])
        self.assertEqual(405, bank["questionCount"])
        self.assertIn(bank["releaseStatus"], {"candidate", "release_ready"})
        self.assertEqual(405, len(bank["questions"]))
        self.assertRegex(bank["reviewInputSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(135, len(bank["elementFingerprints"]))
        self.assertEqual(405, len(bank["questionFingerprints"]))
        for question in bank["questions"]:
            choices = question["choices"]
            self.assertEqual(["A", "B", "C", "D", "E"], [item["key"] for item in choices])
            self.assertEqual(5, len({item["text"] for item in choices}))
            self.assertEqual(1, sum(bool(item["isCorrect"]) for item in choices))
            self.assertIn(question["questionType"], model.V2_QUESTION_TYPES)
            self.assertTrue(all(item.get("factId") for item in choices))
            if question["questionType"] == "term_to_verbal_relation":
                self.assertFalse(any(model.FORMULA_CHOICE_RE.search(item["text"]) for item in choices))
            self.assertIn(
                question["reviewStatus"],
                {"automated_pass", "needs_owner_review", "blocked", "owner_approved"},
            )

    def test_markdown_history_contains_runs_and_primary_references(self) -> None:
        history = json.loads(model.DEFAULT_ADMIN_REPORT.read_text(encoding="utf-8"))
        if not history["experiments"]:
            self.assertEqual(2, history["reportVersion"])
            self.assertEqual("2.0", history["contractVersion"])
            self.assertIsNone(history["latestExperimentId"])
            reset_state = reset_validator.validate_reset_state()
            self.assertEqual("awaiting_v2_implementation", reset_state["state"])
            self.assertFalse(reset_state["releaseReady"])
            return
        latest = history["experiments"][0]
        rendered = model._render_experiment_markdown(latest)

        self.assertEqual(0, latest["safety"]["ambiguousQuestionCount"])
        self.assertEqual([], latest["safety"]["ambiguousQuestionIds"])
        self.assertIn(latest["experimentId"], rendered)
        self.assertIn("전체 validation 실험 행렬", rendered)
        self.assertIn("cormack.uwaterloo.ca/cormacksigir09-rrf.pdf", rendered)
        self.assertIn("microsoft.com/en-us/research", rendered)
        completed = sum(run["status"] == "completed" for run in latest["rankerRuns"])
        self.assertGreater(completed, 0)
        for run in latest["rankerRuns"]:
            self.assertEqual(bool(run["testEvaluated"]), run["test"] is not None)
        self.assertEqual(1, sum(bool(run["testEvaluated"]) for run in latest["rankerRuns"]))
        review = latest["automatedReview"]
        self.assertEqual(405, review["autoPassedCount"] + review["ownerApprovedCount"] + review["needsOwnerReviewCount"] + review["blockedCount"])
        self.assertGreaterEqual(len(review["profileExperiments"]), 3)
        self.assertIn(
            review["selectedProfileId"],
            {item["profileId"] for item in review["profileExperiments"]},
        )

    def test_checked_in_review_artifacts_match_active_policy(self) -> None:
        history = json.loads(model.DEFAULT_ADMIN_REPORT.read_text(encoding="utf-8"))
        latest = next(
            experiment
            for experiment in history["experiments"]
            if experiment["experimentId"] == history["latestExperimentId"]
        )
        bank = json.loads(model.DEFAULT_BANK.read_text(encoding="utf-8"))
        active_policy = self.config["automatedReview"]["policyVersion"]

        self.assertEqual(
            model._sha256_file(model.DEFAULT_CONFIG),
            latest["dataset"]["configSha256"],
        )
        self.assertEqual(active_policy, latest["automatedReview"]["policyVersion"])
        self.assertEqual(active_policy, bank["automatedReviewPolicyVersion"])
        self.assertEqual(
            latest["automatedReview"]["reviewInputSha256"],
            bank["reviewInputSha256"],
        )
        self.assertEqual(
            latest["artifacts"]["questionBankSha256"],
            bank["bankSha256"],
        )
        bank_payload = dict(bank)
        bank_sha256 = bank_payload.pop("bankSha256")
        self.assertEqual(
            bank_sha256,
            model._sha256_bytes(model._stable_json_bytes(bank_payload)),
        )

    def test_owner_decisions_are_bound_to_exact_fingerprints(self) -> None:
        fingerprint = "a" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "type": "question",
                        "questionId": "ACC-01-term_to_definition-01",
                        "questionFingerprint": fingerprint,
                        "decision": "approved",
                        "reviewerId": "owner",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "batch",
                        "reviewInputSha256": "b" * 64,
                        "decision": "approved",
                        "reviewerId": "owner",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            question_decisions, batch_decisions = model.load_owner_decisions(path)

        self.assertEqual(
            "approved",
            question_decisions[("ACC-01-term_to_definition-01", fingerprint)].decision,
        )
        self.assertEqual("approved", batch_decisions["b" * 64].decision)

    def test_question_edits_apply_only_to_the_exact_pre_edit_fingerprint(self) -> None:
        question = {
            "questionId": "Q-1",
            "elementId": "ACC-01",
            "questionType": "term_to_definition",
            "stem": "old stem",
            "explanation": "old explanation",
            "difficulty": 1,
            "sourceFactIds": ["fact-1"],
            "choices": [
                {
                    "key": key,
                    "elementId": "ACC-01" if index == 0 else f"ACC-{index + 1:02d}",
                    "text": f"old-{key}",
                    "explanation": f"old explanation {key}",
                    "isCorrect": index == 0,
                }
                for index, key in enumerate(model.CHOICE_KEYS)
            ],
        }
        fingerprint = model._question_review_fingerprint(question)
        bank = {"questions": [question]}
        edit = {
            "questionId": "Q-1",
            "questionFingerprint": fingerprint,
            "elementId": "ACC-01",
            "stem": "new stem",
            "explanation": "new explanation",
            "choices": [
                {
                    "key": key,
                    "elementId": "ACC-01" if index == 0 else f"ACC-{index + 11:02d}",
                    "text": f"new-{key}",
                    "explanation": f"new explanation {key}",
                    "isCorrect": index == 0,
                }
                for index, key in enumerate(model.CHOICE_KEYS)
            ],
        }

        self.assertEqual(1, model._apply_question_edits(bank, {("Q-1", fingerprint): edit}))
        self.assertEqual("new stem", bank["questions"][0]["stem"])
        self.assertEqual("new-E", bank["questions"][0]["choices"][-1]["text"])
        second_fingerprint = model._question_review_fingerprint(bank["questions"][0])
        second_edit = {**edit, "questionFingerprint": second_fingerprint, "stem": "newer stem"}
        self.assertEqual(
            1,
            model._apply_question_edits(
                bank,
                {("Q-1", fingerprint): edit, ("Q-1", second_fingerprint): second_edit},
            ),
        )
        self.assertEqual("newer stem", bank["questions"][0]["stem"])
        self.assertEqual(0, model._apply_question_edits(bank, {("Q-1", "0" * 64): edit}))

    def test_owner_batch_command_rejects_unresolved_queue(self) -> None:
        experiment = {
            "automatedReview": {
                "reviewInputSha256": "c" * 64,
                "queue": [
                    {
                        "questionId": "Q-1",
                        "questionFingerprint": "d" * 64,
                        "severity": "review",
                    }
                ],
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(review_command.ReviewCommandError):
                review_command.approve_batch(
                    experiment,
                    Path(directory) / "decisions.jsonl",
                    "owner",
                    "",
                )

    def test_supabase_review_sync_keeps_only_current_fingerprint_and_is_idempotent(self) -> None:
        fingerprint = "e" * 64
        experiment = {
            "automatedReview": {
                "reviewInputSha256": "f" * 64,
                "queue": [
                    {
                        "questionId": "Q-1",
                        "questionFingerprint": fingerprint,
                        "severity": "review",
                    }
                ],
            }
        }
        remote = [
            {
                "concept_question_review_decision_id": "decision-1",
                "question_id": "Q-1",
                "question_fingerprint": fingerprint,
                "decision": "approved",
                "reviewer_id": "owner-id",
                "decided_at": "2026-08-12T00:00:00+00:00",
                "comment": "checked",
            },
            {
                "concept_question_review_decision_id": "stale-decision",
                "question_id": "Q-1",
                "question_fingerprint": "0" * 64,
                "decision": "rejected",
            },
        ]

        merged, added = review_command.merge_remote_question_decisions(
            experiment, [], remote
        )
        repeated, repeated_added = review_command.merge_remote_question_decisions(
            experiment, merged, remote
        )

        self.assertEqual(1, added)
        self.assertEqual("supabase-admin", merged[0]["source"])
        self.assertEqual("approved", merged[0]["decision"])
        self.assertEqual(0, repeated_added)
        self.assertEqual(merged, repeated)

        with_batch, batch_added = review_command.append_auto_batch_if_complete(
            experiment, merged
        )
        repeated_batch, repeated_batch_added = review_command.append_auto_batch_if_complete(
            experiment, with_batch
        )
        self.assertTrue(batch_added)
        self.assertEqual("batch", with_batch[-1]["type"])
        self.assertEqual("f" * 64, with_batch[-1]["reviewInputSha256"])
        self.assertFalse(repeated_batch_added)
        self.assertEqual(with_batch, repeated_batch)

        rejected_rows = [{**merged[0], "decision": "rejected"}]
        without_batch, rejected_batch_added = review_command.append_auto_batch_if_complete(
            experiment, rejected_rows
        )
        self.assertFalse(rejected_batch_added)
        self.assertEqual(rejected_rows, without_batch)


if __name__ == "__main__":
    unittest.main()
