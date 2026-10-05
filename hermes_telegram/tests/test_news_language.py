"""Public synthetic articles test professional selection and exact provenance."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import sys
import unittest
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.news_language import (
    LanguageCandidate, MAX_ARTICLE_CHARS, MAX_CONTEXT_CHARS, MAX_CONTEXT_WORDS,
    select_business_phrases, select_specialist_vocabulary,
)


class NewsLanguageTests(unittest.TestCase):
    def assert_source_bound(self, text, candidates):
        for candidate in candidates:
            with self.subTest(term=candidate.term):
                self.assertEqual(text[candidate.start:candidate.end], candidate.term)
                self.assertIn(candidate.context, text)
                self.assertIn(candidate.term, candidate.context)
                self.assertLessEqual(len(candidate.context), MAX_CONTEXT_CHARS)
                self.assertLessEqual(len(candidate.context.split()), MAX_CONTEXT_WORDS)
                self.assertRegex(candidate.candidate_id, r"^[0-9a-f]{24}$")
                self.assertRegex(candidate.meaning_ko, r"[가-힣]")

    def test_professional_insurance_terms_replace_easy_generic_words(self):
        text = ("Persistent weakness may weaken the market. "
                "The insurer improved its combined ratio and underwriting profit. "
                "Gross written premiums grew while reinsurance protected capital.")
        candidates = select_specialist_vocabulary(text)
        self.assertEqual([candidate.lemma for candidate in candidates],
                         ["combined ratio", "underwriting profit", "gross written premiums"])
        self.assertTrue(all(candidate.category == "insurance" for candidate in candidates))
        self.assert_source_bound(text, candidates)

    def test_generic_advanced_and_basic_words_do_not_trigger_fallback(self):
        self.assertEqual(select_specialist_vocabulary(
            "Persistent inflation may weaken robust banks and sustain higher interest rates."), ())
        self.assertEqual(select_business_phrases("Persistent inflation weakened the economy."), ())

    def test_named_multiword_terms_outrank_earlier_specialist_retrocession(self):
        text = "Retrocession expanded. Combined ratios improved. Underwriting profits rose."
        candidates = select_specialist_vocabulary(text, limit=2)
        self.assertEqual([candidate.lemma for candidate in candidates], ["combined ratio", "underwriting profit"])
        self.assert_source_bound(text, candidates)

    def test_basic_industry_labels_and_variants_never_fill_automatic_candidates(self):
        for text in (
            "The investment bank expanded.", "Investment banks raised capital.",
            "An exchange-traded fund launched.", "Exchange traded funds grew.",
            "The exchange‐traded fund launched.", "ETF assets rose.", "ETFs attracted investors.",
            "The hedge fund traded bonds.", "Hedge funds provided capital.",
            "Reinsurance protected capital.",
            "The prediction market attracted traders.", "Prediction markets expanded.",
            "The company's profit margin improved.", "Gross profit margins increased.",
            "The bank's operating profit margin declined.", "Net profit margins rose.",
        ):
            with self.subTest(text=text):
                self.assertEqual(select_specialist_vocabulary(text), ())

    def test_basic_labels_do_not_pad_sparse_specialist_results(self):
        text = ("Investment banks hired hedge funds to trade ETFs. "
                "Prediction markets expanded as profit margins improved. "
                "Reinsurance protected the insurer's combined ratio. "
                "Retrocession protected the reinsurer's capital.")
        candidates = select_specialist_vocabulary(text, limit=4)
        self.assertEqual([candidate.lemma for candidate in candidates], ["combined ratio", "retrocession"])
        self.assert_source_bound(text, candidates)

    def test_cap_is_enforced_and_equal_priority_follows_article_order(self):
        text = ("Net inflows rose. Assets under management grew. Capital adequacy improved. "
                "Broker-dealers expanded. Combined ratios fell. Credit spreads narrowed.")
        candidates = select_specialist_vocabulary(text, limit=100)
        self.assertEqual([candidate.lemma for candidate in candidates],
                         ["net inflows", "assets under management", "capital adequacy", "broker-dealer"])
        self.assertEqual(len(candidates), 4)

    def test_curated_variants_preserve_original_case_and_inflection(self):
        cases = (
            ("Gross Premiums Written increased.", "Gross Premiums Written", "gross written premiums"),
            ("The U.S. broker-dealers increased capital.", "broker-dealers", "broker-dealer"),
            ("The broker‐dealer increased capital.", "broker‐dealer", "broker-dealer"),
            ("The insurer's loss reserves increased.", "loss reserves", "loss reserve"),
            ("Term premia increased on bonds.", "Term premia", "term premium"),
            ("Non-performing loans declined.", "Non-performing loans", "non-performing loan"),
            ("Net stable funding ratios improved.", "Net stable funding ratios", "net stable funding ratio"),
        )
        for text, term, lemma in cases:
            with self.subTest(text=text):
                candidates = select_specialist_vocabulary(text)
                self.assertEqual(len(candidates), 1)
                self.assertEqual((candidates[0].term, candidates[0].lemma), (term, lemma))
                self.assertEqual(candidates[0].context, text)
                self.assert_source_bound(text, candidates)

    def test_horizontal_whitespace_is_preserved_without_normalizing_source(self):
        text = "The insurer's combined\u00a0\u00a0ratio and gross  written premiums improved."
        candidates = select_specialist_vocabulary(text)
        self.assertEqual([candidate.term for candidate in candidates],
                         ["combined\u00a0\u00a0ratio", "gross  written premiums"])
        self.assert_source_bound(text, candidates)

    def test_insurance_reserving_and_regulatory_terms_have_source_bound_context(self):
        for text, lemma in (
            ("Loss adjustment expenses declined at the insurer.", "loss adjustment expense"),
            ("Ceded premiums increased as catastrophe exposure grew.", "ceded premium"),
            ("Risk-based capital improved at the insurer.", "risk-based capital"),
            ("Unearned premium reserves increased at the insurer.", "unearned premium reserve"),
            ("Retrocession protected the reinsurer's capital.", "retrocession"),
            ("The bank improved its liquidity coverage ratio.", "liquidity coverage ratio"),
            ("Net interest margins declined at the bank.", "net interest margin"),
            ("Quantitative tightening affected funding markets.", "quantitative tightening"),
        ):
            with self.subTest(text=text):
                candidates = select_specialist_vocabulary(text)
                self.assertEqual([candidate.lemma for candidate in candidates], [lemma])
                self.assert_source_bound(text, candidates)

    def test_health_insurance_coding_and_revenue_management_have_primary_references(self):
        text = ("The insurer attributes higher costs to AI-assisted medical coding. "
                "Secondary diagnoses changed reimbursement categories. "
                "The hospital improved revenue-cycle management. "
                "It opposes autonomous coding.")
        candidates = select_specialist_vocabulary(text)
        self.assertEqual([candidate.lemma for candidate in candidates],
                         ["medical coding", "secondary diagnosis", "revenue cycle management",
                          "autonomous medical coding"])
        self.assertEqual([candidate.term for candidate in candidates],
                         ["medical coding", "Secondary diagnoses", "revenue-cycle management",
                          "autonomous coding"])
        self.assertEqual({urlsplit(candidate.reference).hostname for candidate in candidates},
                         {"www.cms.gov", "www.hfma.org"})
        self.assertTrue(all(candidate.category == "insurance" for candidate in candidates))
        self.assert_source_bound(text, candidates)

    def test_health_insurance_variants_preserve_surface_and_do_not_duplicate_nested_coding(self):
        for text, term, lemma in (
            ("A secondary diagnosis affected reimbursement.", "secondary diagnosis", "secondary diagnosis"),
            ("The hospital improved revenue‐cycle management.", "revenue‐cycle management", "revenue cycle management"),
            ("The hospital improved Revenue  Cycle Management.", "Revenue  Cycle Management", "revenue cycle management"),
            ("Autonomous medical coding processes insurer claims.", "Autonomous medical coding", "autonomous medical coding"),
            ("The insurer scrutinized autonomous coding.", "autonomous coding", "autonomous medical coding"),
        ):
            with self.subTest(text=text):
                candidates = select_specialist_vocabulary(text)
                self.assertEqual([(candidate.term, candidate.lemma) for candidate in candidates], [(term, lemma)])
                self.assertEqual(candidates[0].context, text)
                self.assert_source_bound(text, candidates)

    def test_health_insurance_terms_do_not_promote_basic_words_or_unlisted_forms(self):
        for text in (
            "The insurer disputed billing and premiums.",
            "The medical coder reviewed the patient record.",
            "The hospital improved its revenue cycle.",
            "The secondary diagnostician reviewed autonomous codings.",
        ):
            with self.subTest(text=text):
                self.assertEqual(select_specialist_vocabulary(text), ())

    def test_longest_named_reinsurance_term_excludes_its_nested_noun(self):
        for text, lemma in (
            ("Excess of loss reinsurance protected the insurer.", "excess of loss reinsurance"),
            ("Excess-of-loss reinsurance protected the insurer.", "excess of loss reinsurance"),
            ("Facultative reinsurance protected the insurer.", "facultative reinsurance"),
        ):
            with self.subTest(text=text):
                candidates = select_specialist_vocabulary(text)
                self.assertEqual([candidate.lemma for candidate in candidates], [lemma])
                self.assert_source_bound(text, candidates)

    def test_explicit_boundaries_do_not_match_substrings_or_unlisted_morphology(self):
        for text in (
            "The rereinsurance market grew.", "The reinsurance-linked investment grew.",
            "The combined ratioship changed.", "Net inflowingly funds grew.",
            "The broker-dealership expanded.", "The capital inadequacy was serious.",
            "The reinsured business grew.", "The company used yield-curveish models.",
            "가combined ratio나 improved.",
        ):
            with self.subTest(text=text):
                self.assertEqual(select_specialist_vocabulary(text), ())

    def test_first_exact_occurrence_is_used_and_canonical_lemma_is_deduplicated(self):
        text = "The combined ratio was 98.3%. Combined ratios later improved."
        candidates = select_specialist_vocabulary(text)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].context, "The combined ratio was 98.3%.")
        self.assertEqual(candidates[0].term, "combined ratio")
        self.assert_source_bound(text, candidates)

    def test_decimal_abbreviation_quotes_and_question_boundaries_keep_whole_context(self):
        text = 'The U.S. broker-dealer reported a combined ratio of 98.3%. "Did capital adequacy improve?" Yes!'
        candidates = select_specialist_vocabulary(text)
        contexts = {candidate.lemma: candidate.context for candidate in candidates}
        self.assertEqual(contexts["broker-dealer"], "The U.S. broker-dealer reported a combined ratio of 98.3%.")
        self.assertEqual(contexts["combined ratio"], contexts["broker-dealer"])
        self.assertEqual(contexts["capital adequacy"], '"Did capital adequacy improve?"')
        self.assert_source_bound(text, candidates)

    def test_heading_fragments_and_cross_sentence_or_line_terms_are_not_candidates(self):
        for text in ("Combined ratio", "Combined. Ratio improved.",
                     "Combined\nratio improved.", "Combined ratio\nBusiness overview"):
            with self.subTest(text=text):
                self.assertEqual(select_specialist_vocabulary(text), ())
        text = "INSURANCE REVIEW\nThe combined ratio improved.\nCapital adequacy strengthened."
        candidates = select_specialist_vocabulary(text)
        self.assertEqual([candidate.context for candidate in candidates],
                         ["The combined ratio improved.", "Capital adequacy strengthened."])

    def test_oversized_context_is_omitted_whole_and_does_not_hide_later_valid_sentence(self):
        too_many_words = "Combined ratio " + "cost " * 40 + "rose."
        too_many_chars = "Combined ratio " + "x" * 701 + "."
        for prefix in (too_many_words, too_many_chars):
            text = prefix + " Underwriting profit increased."
            with self.subTest(prefix=prefix):
                candidates = select_specialist_vocabulary(text)
                self.assertEqual([candidate.lemma for candidate in candidates], ["underwriting profit"])
                self.assertEqual(candidates[0].context, "Underwriting profit increased.")
                self.assert_source_bound(text, candidates)

    def test_external_links_and_control_characters_do_not_become_article_context(self):
        for text in ("See https://example.com/combined ratio.", "The combined ratio\0 rose."):
            with self.subTest(text=text):
                self.assertEqual(select_specialist_vocabulary(text), ())

    def test_business_expressions_have_exact_surface_and_reusable_patterns(self):
        text = ("The insurer raised capital to shore up its balance sheet. "
                "Higher costs weighed heavily on profits. "
                "The company beat estimates and booked a loss on a bond sale.")
        candidates = select_business_phrases(text, limit=100)
        self.assertEqual([candidate.lemma for candidate in candidates], ["raise capital", "shore up", "weigh on"])
        self.assertEqual([candidate.term for candidate in candidates], ["raised capital", "shore up", "weighed heavily on"])
        self.assertTrue(all(candidate.category == "business_phrase" and candidate.reuse_pattern for candidate in candidates))
        self.assert_source_bound(text, candidates)

    def test_business_verb_variants_and_estimate_collocations_are_conservative(self):
        for text, term, lemma in (
            ("The insurer is raising capital.", "raising capital", "raise capital"),
            ("The bank is shoring up its reserves.", "shoring up", "shore up"),
            ("Costs are weighing on earnings.", "weighing on", "weigh on"),
            ("The company beats analysts' forecasts.", "beats analysts' forecasts", "beat estimates"),
            ("The company has beaten expectations.", "beaten expectations", "beat estimates"),
            ("The insurer booked losses.", "booked losses", "book a loss"),
            ("Profit margins remained under increasing pressure.", "under increasing pressure", "under pressure"),
            ("Profit margins remained under sustained pressure.", "under sustained pressure", "under pressure"),
        ):
            with self.subTest(text=text):
                candidates = select_business_phrases(text)
                self.assertEqual([(candidate.term, candidate.lemma) for candidate in candidates], [(term, lemma)])
                self.assert_source_bound(text, candidates)

    def test_literal_or_personal_phrase_senses_are_not_given_financial_glosses(self):
        for text in (
            "Bank staff shored up the wall.", "The insurer kept steam under pressure.",
            "Financial worries weighed on him.", "The ship shored up the wall.",
            "The athlete beat expectations.", "The diver was under pressure.",
        ):
            with self.subTest(text=text):
                self.assertEqual(select_business_phrases(text), ())

    def test_healthcare_and_business_opposition_preserve_actual_phrasal_verb(self):
        for text, term in (
            ("The hospital association pushed back on BCBSA's analysis.", "pushed back on"),
            ("The insurer pushes back on the proposed premium increase.", "pushes back on"),
            ("The company is pushing back on analysts’ claims.", "pushing back on"),
        ):
            with self.subTest(text=text):
                candidates = select_business_phrases(text)
                self.assertEqual([(candidate.term, candidate.lemma) for candidate in candidates],
                                 [(term, "push back on")])
                self.assertEqual(candidates[0].meaning_ko, "주장·방침에 이의를 제기하다")
                self.assertTrue(candidates[0].reuse_pattern)
                self.assertEqual(urlsplit(candidates[0].reference).hostname,
                                 "www.oxfordlearnersdictionaries.com")
                self.assert_source_bound(text, candidates)

    def test_push_back_opposition_excludes_physical_and_postponement_senses(self):
        for text in (
            "The insurer pushed back on the wall.",
            "The hospital staff pushed back on a wheelchair.",
            "The company pushed the meeting back.",
            "The insurer pushed back on a passenger's shoulder.",
        ):
            with self.subTest(text=text):
                self.assertEqual(select_business_phrases(text), ())

    def test_phrases_do_not_stem_or_reconstruct_unwritten_text(self):
        for text in (
            "The insurer will raise fresh capital.", "The bank shored its capital up.",
            "Costs weighed. On earnings the bank commented.", "The company is bookingly a loss.",
        ):
            with self.subTest(text=text):
                self.assertEqual(select_business_phrases(text), ())

    def test_glossary_references_are_primary_and_candidates_have_no_cefr_claim(self):
        text = ("Combined ratios improved. Assets under management grew. "
                "The broker-dealer strengthened capital adequacy.")
        candidates = select_specialist_vocabulary(text)
        self.assertEqual({urlsplit(candidate.reference).hostname for candidate in candidates},
                         {"content.naic.org", "www.cfainstitute.org", "www.sifma.org"})
        self.assertNotIn("level", {field.name for field in fields(LanguageCandidate)})
        self.assertNotIn("cefr", {field.name for field in fields(LanguageCandidate)})
        self.assertTrue(all(candidate.reference.startswith("https://") for candidate in candidates))

    def test_brokerage_succession_articles_have_professional_terms_and_business_idioms(self):
        text = ("The board approved a succession plan. "
                "A pure-play investment bank hired alternative asset managers. "
                "The bank got back on track after losses. "
                "The departing CEO risks becoming a lame duck. "
                "A deep-pocketed suitor could make a play for the bank's executive.")
        vocabulary = select_specialist_vocabulary(text)
        phrases = select_business_phrases(text)
        self.assertEqual([candidate.term for candidate in vocabulary],
                         ["succession plan", "pure-play", "alternative asset managers"])
        self.assertEqual([candidate.term for candidate in phrases],
                         ["back on track", "lame duck", "make a play for"])
        self.assert_source_bound(text, vocabulary + phrases)

    def test_prediction_market_articles_have_specialist_terms_and_actual_business_phrases(self):
        text = ("Prediction markets attracted traders. "
                "The exchange needs institutional liquidity. "
                "Event contracts determine settlement from a specified outcome. "
                "The exchange completed a block trade. "
                "The market is at an inflection point in its development. "
                "Institutional traders stayed on the sidelines.")
        vocabulary = select_specialist_vocabulary(text)
        phrases = select_business_phrases(text)
        self.assertEqual([candidate.lemma for candidate in vocabulary],
                         ["institutional liquidity", "event contract", "block trade"])
        self.assertEqual([candidate.term for candidate in phrases],
                         ["at an inflection point", "on the sidelines"])
        self.assertEqual({urlsplit(candidate.reference).hostname for candidate in vocabulary},
                         {"www.cftc.gov", "www.sec.gov"})
        self.assert_source_bound(text, vocabulary + phrases)

    def test_brokerage_business_lines_have_official_reference_and_exact_variants(self):
        for text, term, lemma in (
            ("Private credit financed an acquisition.", "Private credit", "private credit"),
            ("Investment banking fees increased.", "Investment banking fees", "investment banking fee"),
            ("Alternative asset management attracted capital.", "Alternative asset management", "alternative asset management"),
        ):
            with self.subTest(text=text):
                candidates = select_specialist_vocabulary(text)
                self.assertEqual([(candidate.term, candidate.lemma) for candidate in candidates], [(term, lemma)])
                self.assert_source_bound(text, candidates)

    def test_market_expansion_and_resource_commitment_phrases_are_supported(self):
        text = ("The insurer made a push into the Japanese market. "
                "The bank doubled down on wealth management. "
                "The insurer's capital is at stake.")
        phrases = select_business_phrases(text)
        self.assertEqual([candidate.term for candidate in phrases],
                         ["push into", "doubled down on", "at stake"])
        self.assert_source_bound(text, phrases)

    def test_new_idioms_reject_literal_mathematical_and_romantic_senses(self):
        for text in (
            "The bank's train got back on track.",
            "The asset chart has a graph at an inflection point.",
            "A bank employee made a play for his girlfriend.",
            "The bank staff pushed into the wall.",
        ):
            with self.subTest(text=text):
                self.assertEqual(select_business_phrases(text), ())

    def test_candidates_are_immutable_and_ids_are_deterministic_context_bound(self):
        text = "The combined ratio improved."
        first = select_specialist_vocabulary(text)[0]
        self.assertEqual(first, select_specialist_vocabulary(text)[0])
        changed = select_specialist_vocabulary("The combined ratio declined.")[0]
        self.assertNotEqual(first.candidate_id, changed.candidate_id)
        with self.assertRaises(FrozenInstanceError):
            first.term = "reinsurance"

    def test_zero_limit_empty_input_and_maximum_article_length(self):
        for selector in (select_specialist_vocabulary, select_business_phrases):
            self.assertEqual(selector("", limit=0), ())
            self.assertEqual(selector(""), ())
            self.assertEqual(selector("Combined ratio improved.", limit=0), ())
            self.assertEqual(selector(" " * MAX_ARTICLE_CHARS), ())

    def test_oversized_or_wrong_type_input_and_invalid_limits_are_rejected(self):
        for selector in (select_specialist_vocabulary, select_business_phrases):
            for text in ("a" * (MAX_ARTICLE_CHARS + 1), None, b"Combined ratio improved."):
                with self.subTest(selector=selector.__name__, text_type=type(text).__name__), self.assertRaises(ValueError):
                    selector(text)
            for limit in (-1, True, 1.5, "4", None):
                with self.subTest(selector=selector.__name__, limit=limit), self.assertRaises(ValueError):
                    selector("Combined ratio improved.", limit=limit)


if __name__ == "__main__":
    unittest.main()
