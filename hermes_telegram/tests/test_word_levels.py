"""Synthetic lexical fixtures; no private vault or actual Oxford PDF is used.

Fixture grades exercise eligibility mechanics and make no claim about the real
Oxford classification of these words.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from findone_hermes.word_levels import OXFORD_URL, WordLevelError, WordLevels


class WordLevelsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "synthetic-word-list.json"
        self.entries = {
            "yield": "B2", "sustain": "C1", "strengthen": "C1",
            "coordinate": "B2", "robust": "C1", "endorse": "C1", "gradual": "B2",
        }

    def write(self, **overrides):
        document = {
            "schema_version": 1, "source_url": OXFORD_URL, "entries": self.entries,
            **overrides,
        }
        self.path.write_text(json.dumps(document), encoding="utf-8")
        return {"FINDONE_CEFR_WORDLIST_PATH": str(self.path)}

    def test_official_source_and_schema_are_required_for_local_cache(self):
        environment = self.write()
        loaded = WordLevels.from_env(environment)
        self.assertEqual(loaded.lookup("yield"), ("yield", "B2"))
        self.assertEqual(loaded.lookup("robust"), ("robust", "C1"))
        for overrides in (
            {"schema_version": 0}, {"schema_version": "1"},
            {"source_url": "https://example.com/unverified-word-list.pdf"},
            {"source_url": OXFORD_URL.replace("https://", "http://")},
            {"entries": ["yield", "robust"]}, {"entries": {}},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(WordLevelError):
                    WordLevels.from_env(self.write(**overrides))

    def test_boolean_schema_version_is_not_integer_version_one(self):
        with self.assertRaises(WordLevelError):
            WordLevels.from_env(self.write(schema_version=True))

    def test_relative_wordlist_path_is_rejected(self):
        with self.assertRaises(ValueError):
            WordLevels.from_env({"FINDONE_CEFR_WORDLIST_PATH": "relative.json"})

    def test_unsupported_grades_and_minimums_are_rejected(self):
        for grade in ("A1", "A2", "B1", "C2", "C3", "basic", "b2", "", None, 2):
            with self.subTest(grade=grade), self.assertRaises(WordLevelError):
                WordLevels({"yield": grade})
        for minimum in ("A1", "B1", "C2", "advanced", "c1", ""):
            with self.subTest(minimum=minimum), self.assertRaises(WordLevelError):
                WordLevels(self.entries, minimum=minimum)

    def test_abnormal_headwords_are_rejected_instead_of_becoming_new_grades(self):
        for lemma in ("", "../escape", "credit/spread", "company2", "a" * 81, "yield\n", "bad\0word", 123):
            with self.subTest(lemma=lemma), self.assertRaises(WordLevelError):
                WordLevels({lemma: "B2"})

    def test_default_minimum_retains_b2_and_c1_only_known_terms(self):
        levels = WordLevels(self.entries)
        self.assertEqual(levels.minimum, "B2")
        self.assertEqual(levels.lookup("yield"), ("yield", "B2"))
        self.assertEqual(levels.lookup("sustain"), ("sustain", "C1"))
        for term in ("and", "the", "bank", "cat", "unlistedfinancialjargon"):
            with self.subTest(term=term):
                self.assertIsNone(levels.lookup(term))

    def test_c1_minimum_drops_b2_basic_and_unknown_without_inventing_levels(self):
        levels = WordLevels(self.entries, minimum="C1")
        self.assertIsNone(levels.lookup("yields"))
        self.assertIsNone(levels.lookup("coordinate"))
        self.assertIsNone(levels.lookup("the"))
        self.assertIsNone(levels.lookup("unlistedfinancialjargon"))
        self.assertEqual(levels.lookup("sustained"), ("sustain", "C1"))

    def test_inflections_resolve_to_listed_lemmas_with_original_grades(self):
        levels = WordLevels(self.entries)
        for term, expected in (
            ("yields", ("yield", "B2")),
            ("sustained", ("sustain", "C1")),
            ("strengthening", ("strengthen", "C1")),
        ):
            with self.subTest(term=term):
                self.assertEqual(levels.lookup(term), expected)

    def test_candidates_preserve_exact_surface_context_and_deduplicate_lemmas(self):
        sentences = (
            "Yields were sustained while firms were strengthening reserves.",
            "Yield changes led firms to sustain momentum and coordinate funding.",
        )
        candidates = WordLevels(self.entries).candidates(sentences)
        self.assertEqual(len({word.lemma for word in candidates}), len(candidates))
        by_lemma = {word.lemma: word for word in candidates}
        self.assertEqual(by_lemma["yield"].term, "Yields")
        self.assertEqual(by_lemma["sustain"].term, "sustained")
        self.assertEqual(by_lemma["strengthen"].term, "strengthening")
        for candidate in candidates:
            self.assertIn(candidate.context, sentences)
            self.assertIn(candidate.term, candidate.context)
            self.assertEqual(candidate.reference, OXFORD_URL)

    def test_candidates_prefer_c1_then_source_order_and_are_bounded_to_four(self):
        sentences = (
            "Yields were sustained while firms were strengthening reserves.",
            "Coordinate robust banks to endorse gradual reforms.",
        )
        candidates = WordLevels(self.entries).candidates(sentences)
        self.assertEqual([word.lemma for word in candidates], ["sustain", "strengthen", "robust", "endorse"])
        self.assertTrue(all(word.level == "C1" for word in candidates))
        self.assertEqual(len(WordLevels(self.entries).candidates(sentences, limit=2)), 2)

    def test_candidate_limit_rejects_out_of_range_or_noninteger_values(self):
        levels = WordLevels(self.entries)
        sentence = ("Yields were sustained while firms were strengthening reserves.",)
        self.assertEqual(levels.candidates(sentence, limit=0), ())
        for limit in (99, -1, True, False, "4", 1.5, None):
            with self.subTest(limit=limit), self.assertRaises(WordLevelError):
                levels.candidates(sentence, limit=limit)

    def test_explicit_mapping_never_inherits_process_path_or_minimum(self):
        environment = self.write()
        with patch.dict(os.environ, {**environment, "FINDONE_VOCAB_MIN_LEVEL": "C1"}):
            with self.assertRaises(WordLevelError):
                WordLevels.from_env({})
            loaded = WordLevels.from_env(environment)
            self.assertEqual(loaded.minimum, "B2")
            self.assertEqual(loaded.lookup("yield"), ("yield", "B2"))
        with patch.dict(os.environ, {"FINDONE_VOCAB_MIN_LEVEL": "B2"}):
            loaded = WordLevels.from_env({**environment, "FINDONE_VOCAB_MIN_LEVEL": "C1"})
            self.assertEqual(loaded.minimum, "C1")
            self.assertIsNone(loaded.lookup("yield"))

    def test_cache_size_limit_prevents_unbounded_local_load(self):
        self.path.write_bytes(b" " * 2_000_001)
        with self.assertRaises(WordLevelError):
            WordLevels.from_env({"FINDONE_CEFR_WORDLIST_PATH": str(self.path)})


if __name__ == "__main__":
    unittest.main()
