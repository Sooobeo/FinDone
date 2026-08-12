import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tools import train_concept_question_model as model
from tools import review_concept_question_model as review_command


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
            {"definition_to_term", "intuition_to_term", "core_relation_to_term"},
            {question.question_type for question in self.questions},
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
            self.assertIn(
                question["reviewStatus"],
                {"automated_pass", "needs_owner_review", "blocked", "owner_approved"},
            )

    def test_markdown_history_contains_runs_and_primary_references(self) -> None:
        history = json.loads(model.DEFAULT_ADMIN_REPORT.read_text(encoding="utf-8"))
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

    def test_owner_decisions_are_bound_to_exact_fingerprints(self) -> None:
        fingerprint = "a" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "type": "question",
                        "questionId": "ACC-01-definition_to_term-01",
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
            question_decisions[("ACC-01-definition_to_term-01", fingerprint)].decision,
        )
        self.assertEqual("approved", batch_decisions["b" * 64].decision)

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


if __name__ == "__main__":
    unittest.main()
