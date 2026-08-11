import json
import unittest
from collections import Counter

from tools import train_concept_question_model as model


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

    def test_checked_in_question_bank_is_five_choice_bootstrap(self) -> None:
        bank = json.loads(model.DEFAULT_BANK.read_text(encoding="utf-8"))

        self.assertEqual(405, bank["questionCount"])
        self.assertEqual("bootstrap_not_reviewed", bank["releaseStatus"])
        self.assertEqual(405, len(bank["questions"]))
        for question in bank["questions"]:
            choices = question["choices"]
            self.assertEqual(["A", "B", "C", "D", "E"], [item["key"] for item in choices])
            self.assertEqual(5, len({item["text"] for item in choices}))
            self.assertEqual(1, sum(bool(item["isCorrect"]) for item in choices))
            self.assertEqual("bootstrap", question["reviewStatus"])

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


if __name__ == "__main__":
    unittest.main()
