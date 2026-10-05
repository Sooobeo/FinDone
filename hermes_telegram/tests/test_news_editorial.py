"""Source-bound editorial integration with public synthetic articles and no LLM."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.news import NewsError, VerifiedArticle, render_news_article
from findone_hermes.news_editorial import (
    EDITORIAL_PROMPT, editorial_payload, evidence_sentences,
    prepare_editorial, validate_editorial, _provisional_claim,
)
from findone_hermes.news_language import select_business_phrases, select_specialist_vocabulary


DATE = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
SENTENCES = (
    "Goldman Sachs appointed a new banking leader on Friday.",
    "The board reviewed leadership risks after the previous executive retired.",
    "Alternative asset managers added institutional liquidity as the investment bank got back on track.",
    "The board approved a succession plan for the investment bank.",
    "Investors stayed on the sidelines while the bank assessed its strategy.",
    "Goldman Sachs reported revenues of $12 billion.",
    "The bank's profit margin rose to 12% after costs fell.",
)


def article(**overrides):
    values = dict(title="Bank updates leadership and institutional business",
                  url="https://www.cnbc.com/2026/10/02/public-fixture.html",
                  published_at=DATE, source_name="CNBC", text=" ".join(SENTENCES),
                  coverage="public_excerpt")
    values.update(overrides)
    return VerifiedArticle(**values)


def response():
    return {
        "summary": [
            {"role": "event", "sentence_id": "S1", "en": "Goldman Sachs selected a banking leader.",
             "ko": "Goldman Sachs가 은행 부문 책임자를 선임했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The board assessed leadership risks following the executive's retirement.",
             "ko": "이사회는 경영진 퇴임 이후 승계 위험을 검토했습니다."},
            {"role": "impact", "sentence_id": "S3", "en": "Alternative asset managers increased institutional liquidity as the bank recovered.",
             "ko": "은행이 회복하면서 대체자산 운용사들이 기관 거래 유동성을 늘렸습니다."},
        ],
        "vocabulary": [{"candidate_id": "V1", "meaning_ko": "대체자산 운용사"},
                       {"candidate_id": "V2", "meaning_ko": "기관투자자가 공급하는 거래 유동성"}],
        "phrases": [{"candidate_id": "P1", "meaning_ko": "정상 궤도로 돌아온",
                     "explanation_ko": "기사에서는 은행 사업의 회복을 나타냅니다."},
                    {"candidate_id": "P2", "meaning_ko": "참여하지 않고 관망하는",
                     "explanation_ko": "기사에서는 투자자들이 참여를 미루는 상황을 나타냅니다."}],
        "concept_links": [],
    }


class NewsEditorialTests(unittest.TestCase):
    def reject(self, value, source=None, payload=None):
        with self.assertRaises(NewsError):
            validate_editorial(source or article(), value, payload)

    def test_payload_contains_exact_evidence_and_only_available_professional_candidates(self):
        source = article()
        payload = editorial_payload(source)
        self.assertEqual(set(payload), {"article", "evidence_sentences", "vocabulary_candidates", "phrase_candidates"})
        self.assertEqual(payload["article"], {"title": source.title, "source_name": "CNBC",
                         "published_date": "2026-10-02", "coverage": "public_excerpt"})
        self.assertEqual(payload["evidence_sentences"],
                         [{"id": f"S{index}", "text": sentence} for index, sentence in enumerate(SENTENCES, 1)])
        for key, prefix, selected in (
            ("vocabulary_candidates", "V", select_specialist_vocabulary(source.text)),
            ("phrase_candidates", "P", select_business_phrases(source.text)),
        ):
            self.assertLessEqual(len(payload[key]), 4 if prefix == "V" else 3)
            for index, (item, candidate) in enumerate(zip(payload[key], selected), 1):
                self.assertEqual(item["candidate_id"], f"{prefix}{index}")
                self.assertEqual(item["term"], candidate.term)
                self.assertEqual(item["context"], candidate.context)
                self.assertEqual(item["reference"], candidate.reference)
                self.assertIn(item["context"], source.text)
                self.assertNotIn("level", item)

    def test_evidence_keeps_the_numeric_lead_and_later_business_context(self):
        opening = "Goldman Sachs reported revenues of $12 billion."
        filler = tuple("The company issued a routine public statement." for _ in range(7))
        late = "The board discussed succession after reviewing leadership risks."
        source = article(text=" ".join((opening, *filler, late, SENTENCES[2])))
        selected = evidence_sentences(source)
        self.assertEqual(selected[0], opening)
        self.assertIn(late, selected)
        self.assertIn(SENTENCES[2], selected)
        self.assertLessEqual(sum(map(len, selected)), 6000)
        self.assertTrue(all(sentence in source.text for sentence in selected))

    def test_evidence_preserves_abbreviations_decimals_and_quotes(self):
        one = "The U.S. broker-dealer reported revenues of $12.5 billion."
        two = '"The bank is back on track," the executive said.'
        self.assertEqual(evidence_sentences(article(text=one + " " + two)), (one, two))

    def test_incomplete_or_insufficient_evidence_is_rejected(self):
        for text in ("One complete banking sentence.", "A bank without terminal punctuation",
                     "One complete sentence. 끝 문장은 한국어입니다."):
            with self.subTest(text=text), self.assertRaises(NewsError):
                editorial_payload(article(text=text))

    def test_evidence_budget_does_not_cut_or_rewrite_original_sentences(self):
        sentences = tuple(f"The bank considered risk scenario {index} after " + "market " * 70 + "changes."
                          for index in range(35))
        source = article(text=" ".join(sentences))
        selected = evidence_sentences(source)
        self.assertGreaterEqual(len(selected), 2)
        self.assertLessEqual(len(selected), 28)
        self.assertLessEqual(sum(map(len, selected)), 6000)
        self.assertTrue(all(sentence in sentences for sentence in selected))

    def test_qualifications_and_counterviews_outrank_generic_statistics(self):
        lead = "The insurer estimated that AI contributed to additional costs."
        stats = tuple(f"Hospital revenue rose by {index}% after costs changed." for index in range(32))
        cautions = (
            "The insurer stopped short of attributing the entire increase to AI.",
            '"While multiple factors contribute to coding intensity, the findings suggest AI tools play a role," the insurer said.',
            "The American Hospital Association pushed back on the analysis.",
            '"The analysis lacks the context needed to assess patient access or spending," its spokesperson said.',
        )
        source = article(text=" ".join((lead, *stats, *cautions, *stats[:5])))
        selected = evidence_sentences(source)
        self.assertEqual(selected[0], lead)
        for sentence in cautions:
            self.assertIn(sentence, selected)
        self.assertLessEqual(len(selected), 28)
        self.assertLessEqual(sum(map(len, selected)), 6000)
        self.assertTrue(all(sentence in source.text for sentence in selected))

    def test_prompt_anchors_time_verb_completed_launch_and_partial_causality(self):
        for expected in (
            "discussed replacing", "빠르면 내년 CEO를 교체하는 방안을 논의했습니다",
            "Launched in", "출시했습니다", "contributed", "비용 증가에 기여했습니다",
            "entire", "qualifications and counterviews", "most specialized",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, EDITORIAL_PROMPT)

    def test_completed_may_launch_is_not_a_provisional_modal_claim(self):
        source = article(text="The insurer launched its billing platform in May. The board reviewed operating costs after its launch.")
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "The insurer introduced its billing platform in May.",
             "ko": "보험사는 May에 청구 플랫폼을 출시했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The board assessed operating expenses following the launch.",
             "ko": "이사회는 출시 이후 운영 비용을 검토했습니다."},
        ], "vocabulary": [], "phrases": [], "concept_links": []}
        validate_editorial(source, result)
        result["summary"][0]["ko"] = "보험사는 5월에 청구 플랫폼을 출시했습니다."
        self.reject(result, source)

    def test_insurance_and_retirement_plan_nouns_are_not_future_claims(self):
        for sentence in (
            "The insurer reported higher costs for its health plans.",
            "The provider reviewed health plans for employees.",
            "The company published accounts for pension plans.",
            "The group reported retirement plan costs.",
            "The insurer evaluated insurance plans for employees.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(_provisional_claim(sentence))
        for sentence in ("The bank plans to expand its business.",
                         "Plans for a leadership change remain under review.",
                         "The provider of health plans plans to expand next year."):
            with self.subTest(sentence=sentence):
                self.assertTrue(_provisional_claim(sentence))

    def test_actual_plans_to_and_plans_for_still_require_future_qualification(self):
        for opening in ("The bank plans to expand its business.",
                        "The bank's plans for expansion remain under review."):
            source = article(text=opening + " The board reviewed operating costs.")
            result = {"summary": [
                {"role": "event", "sentence_id": "S1", "en": "The bank is considering expansion.",
                 "ko": "은행은 사업 확대를 검토하고 있습니다."},
                {"role": "background", "sentence_id": "S2", "en": "The board assessed operating expenses.",
                 "ko": "이사회는 운영 비용을 검토했습니다."},
            ], "vocabulary": [], "phrases": [], "concept_links": []}
            with self.subTest(opening=opening):
                validate_editorial(source, result)
                completed = copy.deepcopy(result)
                completed["summary"][0].update(en="The bank completed its business expansion.",
                                              ko="은행은 사업 확대를 완료했습니다.")
                self.reject(completed, source)
                changed_ko = copy.deepcopy(result)
                changed_ko["summary"][0]["ko"] = "은행은 사업 확대를 완료했습니다."
                self.reject(changed_ko, source)

    def contribution_digest(self):
        source = article(text=(
            "The insurer estimated that AI-assisted medical coding contributed to $942 million in additional costs for its health plans. "
            "The insurer reviewed hospital billing practices."))
        payload = editorial_payload(source)
        result = {"summary": [
            {"role": "event", "sentence_id": "S1",
             "en": "The insurer estimated that AI-assisted medical coding helped add $942 million in extra costs for its health plans.",
             "ko": "보험사는 AI 지원 의료 코딩이 건강보험 상품의 추가 비용 9억4200만 달러 증가에 기여했다고 추산했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The insurer reassessed hospital billing practices.",
             "ko": "보험사는 병원의 청구 관행을 재검토했습니다."},
        ], "vocabulary": [{"candidate_id": item["candidate_id"], "meaning_ko": item["reference_meaning_ko"]}
                           for item in payload["vocabulary_candidates"][:2]],
            "phrases": [{"candidate_id": item["candidate_id"], "meaning_ko": item["reference_meaning_ko"],
                         "explanation_ko": "원문에 제시된 용어 뜻을 설명합니다."}
                        for item in payload["phrase_candidates"][:1]], "concept_links": []}
        return source, result

    def test_partial_causal_contribution_and_health_plan_noun_are_valid(self):
        source, result = self.contribution_digest()
        validate_editorial(source, result)
        for en, ko in (
            ("The insurer estimated that AI-assisted medical coding contributed to $942 million in extra costs for its health plans.",
             "보험사는 AI 지원 의료 코딩이 건강보험 상품의 추가 비용 9억4200만 달러 증가에 기여했다고 추산했습니다."),
            ("The insurer estimated that AI-assisted medical coding partly caused $942 million in extra costs for its health plans.",
             "보험사는 AI 지원 의료 코딩이 건강보험 상품의 추가 비용 9억4200만 달러 발생에 일부 영향을 미쳤다고 추산했습니다."),
        ):
            changed = copy.deepcopy(result)
            changed["summary"][0].update(en=en, ko=ko)
            with self.subTest(en=en):
                validate_editorial(source, changed)

    def test_english_contribution_cannot_become_full_amount_causation(self):
        source, result = self.contribution_digest()
        for verb in ("added", "caused", "generated", "produced"):
            changed = copy.deepcopy(result)
            changed["summary"][0]["en"] = f"The insurer estimated that AI-assisted medical coding {verb} $942 million in extra costs for its health plans."
            with self.subTest(verb=verb):
                self.reject(changed, source)

    def test_korean_contribution_cannot_become_full_amount_causation(self):
        source, result = self.contribution_digest()
        for claim in ("추가 비용 9억4200만 달러를 발생시켰다고", "추가 비용 9억4200만 달러를 초래했다고",
                      "코딩 때문에 추가 비용 9억4200만 달러가 생겼다고"):
            changed = copy.deepcopy(result)
            changed["summary"][0]["ko"] = f"보험사는 AI 지원 의료 코딩이 건강보험 상품의 {claim} 추산했습니다."
            with self.subTest(claim=claim):
                self.reject(changed, source)

    def test_prepare_uses_one_mock_model_call_and_returns_bound_source_snapshots(self):
        source = article()
        model = Mock()
        model.complete_json.return_value = response()
        newsletter = prepare_editorial(source, model)
        model.complete_json.assert_called_once_with(EDITORIAL_PROMPT, editorial_payload(source))
        self.assertEqual(newsletter.title, source.title)
        self.assertEqual(newsletter.url, source.url)
        self.assertEqual(newsletter.source_text, source.text)
        self.assertEqual(newsletter.coverage, "public_excerpt")
        self.assertEqual([detail.role for detail in newsletter.summary_details], ["event", "background", "impact"])
        self.assertEqual([detail.evidence for detail in newsletter.summary_details], list(SENTENCES[:3]))
        self.assertEqual(newsletter.english_summary, " ".join(item["en"] for item in response()["summary"]))
        self.assertEqual(newsletter.concept_links, ())

    def test_vocabulary_and_phrase_surfaces_references_and_examples_are_program_bound(self):
        source = article()
        newsletter = validate_editorial(source, response())
        words = select_specialist_vocabulary(source.text)
        phrases = select_business_phrases(source.text)
        for saved, candidate in zip(newsletter.vocabulary_evidence, words[:2]):
            self.assertEqual((saved.term, saved.lemma, saved.context, saved.reference, saved.category),
                             (candidate.term, candidate.lemma, candidate.context, candidate.reference, candidate.category))
            self.assertEqual(saved.level, "")
        for saved, candidate in zip(newsletter.phrases, phrases[:2]):
            self.assertEqual((saved.term, saved.context, saved.reference, saved.reuse_pattern),
                             (candidate.term, candidate.context, candidate.reference, candidate.reuse_pattern))

    def test_generated_phrase_explanation_is_replaced_by_trusted_terminology(self):
        source = article(text=("Polymarket is at an inflection point in its institutional business. "
                               "The board reviewed expansion costs."))
        candidates = select_business_phrases(source.text)
        self.assertEqual(len(candidates), 1)
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "Polymarket reached a turning point in its institutional business.",
             "ko": "Polymarket은 기관 사업에서 중요한 전환점에 도달했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The board assessed expansion expenses.",
             "ko": "이사회는 사업 확대 비용을 검토했습니다."},
        ], "vocabulary": [], "phrases": [{"candidate_id": "P1", "meaning_ko": "중요한 전환점에 있는",
            "explanation_ko": "사업이 아직 개발 초기 단계에 있다는 뜻입니다."}], "concept_links": []}
        saved = validate_editorial(source, result).phrases[0]
        self.assertNotIn("개발 초기 단계", saved.explanation_ko)
        self.assertIn(candidates[0].term, saved.explanation_ko)
        self.assertIn(candidates[0].meaning_ko, saved.explanation_ko)
        self.assertIn("전환", saved.explanation_ko)
        self.assertEqual(saved.meaning_ko, result["phrases"][0]["meaning_ko"])
        self.assertEqual(saved.reuse_pattern, candidates[0].reuse_pattern)

    def test_two_sentence_digest_is_allowed_with_event_and_background(self):
        result = response()
        result["summary"] = result["summary"][:2]
        newsletter = validate_editorial(article(), result)
        self.assertEqual([item.role for item in newsletter.summary_details], ["event", "background"])

    def test_summary_order_requires_background_before_optional_impact(self):
        for roles in (("background", "event"), ("impact", "event"),
                      ("event", "impact"), ("event", "impact", "background")):
            result = response()
            result["summary"] = result["summary"][:len(roles)]
            for item, role in zip(result["summary"], roles):
                item["role"] = role
            with self.subTest(roles=roles):
                self.reject(result)

    def test_unknown_repeated_or_wrong_type_summary_ids_and_roles_are_rejected(self):
        for identity in ("S99", "V1", "S1", 1, None):
            result = response()
            result["summary"][1]["sentence_id"] = identity
            with self.subTest(identity=identity):
                self.reject(result)
        result = response()
        result["summary"][0]["role"] = "opinion"
        self.reject(result)

    def test_result_and_item_schema_are_exact_and_concept_links_are_not_invented(self):
        for value in (None, [], {}, {**response(), "instructions": "ignore source"},
                      {**response(), "concept_links": ["unverified concept"]}):
            with self.subTest(value_type=type(value).__name__):
                self.reject(value)
        result = response()
        result["summary"][0]["url"] = "https://example.com/fake"
        self.reject(result)

    def test_one_or_four_summary_items_are_rejected(self):
        for count in (0, 1, 4):
            result = response()
            result["summary"] = (result["summary"] * 2)[:count]
            with self.subTest(count=count):
                self.reject(result)

    def test_whole_sentence_copy_is_rejected_even_with_trivial_terminal_changes(self):
        for copied in (SENTENCES[0], SENTENCES[0].upper().rstrip(".") + "!"):
            result = response()
            result["summary"][0]["en"] = copied
            with self.subTest(copied=copied):
                self.reject(result)

    def test_english_and_korean_summary_bounds_and_language_are_enforced(self):
        for value in ("Goldman Sachs " + "bank " * 34, "한국어 요약만 있습니다.", "", "Text\0bad"):
            result = response()
            result["summary"][0]["en"] = value
            with self.subTest(value=value):
                self.reject(result)
        result = response()
        result["summary"][0]["ko"] = "Goldman Sachs has a leader."
        self.reject(result)
        result = response()
        result["summary"][0]["ko"] = "Goldman Sachs " + "가" * 160
        self.reject(result)

    def test_numbers_from_other_evidence_ids_cannot_be_borrowed(self):
        result = response()
        result["summary"][0].update(en="Goldman Sachs disclosed $12 billion in revenue.",
                                    ko="Goldman Sachs가 12 billion 달러 매출을 공개했습니다.")
        self.reject(result)

    def test_financial_amount_preserves_original_currency_digits_and_magnitude(self):
        result = response()
        result["summary"][0].update(sentence_id="S6", en="Goldman Sachs disclosed $12 billion in revenue.",
                                    ko="Goldman Sachs가 12 billion 달러 매출을 공개했습니다.")
        valid = validate_editorial(article(), result)
        self.assertEqual(valid.summary_details[0].evidence, SENTENCES[5])
        for en, ko in (
            ("Goldman Sachs disclosed $12 in revenue.", "Goldman Sachs가 12 달러 매출을 공개했습니다."),
            ("Goldman Sachs disclosed $12 million in revenue.", "Goldman Sachs가 12 million 달러 매출을 공개했습니다."),
            ("Goldman Sachs disclosed EUR 12 billion in revenue.", "Goldman Sachs가 12 billion 유로 매출을 공개했습니다."),
            ("Goldman Sachs disclosed $13 billion in revenue.", "Goldman Sachs가 13 billion 달러 매출을 공개했습니다."),
            ("Goldman Sachs disclosed $12 billion in revenue.", "Goldman Sachs가 매출을 공개했습니다."),
            ("Goldman Sachs disclosed $12 billion in revenue.", "Goldman Sachs가 12 million 달러 매출을 공개했습니다."),
        ):
            changed = copy.deepcopy(result)
            changed["summary"][0].update(en=en, ko=ko)
            with self.subTest(en=en, ko=ko):
                self.reject(changed)

    def number_digest(self, amount, translated, *, en_amount=None, qualifier="", ko_qualifier="", year="2023"):
        sentences = list(SENTENCES)
        sentences[5] = f"Goldman Sachs reported revenues of {qualifier}{amount} in {year}."
        source = article(text=" ".join(sentences))
        result = response()
        result["summary"][0].update(
            sentence_id="S6", en=f"Goldman Sachs disclosed {qualifier}{en_amount or amount} in revenue in {year}.",
            ko=f"Goldman Sachs가 {year}년 매출 {ko_qualifier}{translated}를 공개했습니다.")
        return source, result

    def test_korean_financial_magnitudes_convert_exactly_using_decimal_values(self):
        for amount, translated in (
            ("$12 billion", "120억 달러"), ("$1 trillion", "1조 달러"),
            ("$0.5 million", "50만 달러"), ("EUR 12.5 billion", "125억 유로"),
            ("GBP 0.125 million", "12.5만 파운드"), ("KRW 1 trillion", "1조 원"),
            ("$1,200 million", "12억 달러"), ("$0.1 million", "10만 달러"),
            ("$942 million", "9억4200만 달러"), ("$942.003 million", "9억 4200만 3천 달러"),
            ("-$942 million", "-9억4200만 달러"),
        ):
            source, result = self.number_digest(amount, translated)
            with self.subTest(amount=amount):
                newsletter = validate_editorial(source, result)
                self.assertIn(translated, newsletter.korean_summary)
                self.assertLessEqual(len(render_news_article(newsletter).encode("utf-16-le")) // 2, 3000)

    def test_korean_scale_currency_unit_and_invented_amount_errors_are_rejected(self):
        for amount, translated in (
            ("$12 million", "120억 달러"), ("$12 billion", "12억 달러"),
            ("$12 billion", "120억 유로"), ("$12 billion", "120억"),
            ("$12 billion", "120 달러"), ("$12 billion", "120"),
            ("$0.5 million", "500만 달러"), ("12 billion", "120억 달러"),
            ("$12 billion", "120억 달러와 1억 달러"),
            ("$12 billion", "USD 120억 유로"),
            ("$942 million", "9억420만 달러"), ("$942 million", "9억4200만 유로"),
            ("$942 million", "4200만9억 달러"),
            ("-$942 million", "9억4200만 달러"),
        ):
            source, result = self.number_digest(amount, translated)
            with self.subTest(amount=amount, translated=translated):
                self.reject(result, source)

    def test_english_numeric_literal_units_and_currency_remain_strict(self):
        for en_amount in ("$120억", "$12000 million", "$12", "12 billion", "EUR 12 billion"):
            source, result = self.number_digest("$12 billion", "120억 달러", en_amount=en_amount)
            with self.subTest(en_amount=en_amount):
                self.reject(result, source)

    def test_converted_financial_spans_do_not_hide_changed_years_or_extra_dates(self):
        source, result = self.number_digest("$12 billion", "120억 달러")
        for year in ("2024", "2023년과 2024"):
            changed = copy.deepcopy(result)
            changed["summary"][0]["ko"] = f"Goldman Sachs가 {year}년 매출 120억 달러를 공개했습니다."
            with self.subTest(year=year):
                self.reject(changed, source)

    def test_basis_points_and_percentages_are_distinct_dimensions(self):
        for amount, translated in (("12 basis points", "12bps"), ("12 percent", "12퍼센트")):
            source, result = self.number_digest(amount, translated)
            validate_editorial(source, result)
            changed = copy.deepcopy(result)
            changed["summary"][0]["ko"] = changed["summary"][0]["ko"].replace(translated, "12%" if "basis" in amount else "12bps")
            self.reject(changed, source)

    def test_quantity_bounds_and_approximations_survive_korean_conversion(self):
        for qualifier, translated, korean_before in (
            ("over ", "120억 달러 이상", ""),
            ("more than ", "120억 달러를 넘는 금액", ""),
            ("at least ", "120억 달러", "최소 "),
            ("up to ", "120억 달러", "최대 "),
            ("nearly ", "120억 달러", "거의 "),
            ("close to ", "120억 달러", "약 "),
        ):
            source, result = self.number_digest("$12 billion", translated, qualifier=qualifier, ko_qualifier=korean_before)
            with self.subTest(qualifier=qualifier):
                validate_editorial(source, result)
                missing = copy.deepcopy(result)
                missing["summary"][0]["ko"] = "Goldman Sachs가 2023년 매출 120억 달러를 공개했습니다."
                self.reject(missing, source)
                wrong = copy.deepcopy(result)
                wrong["summary"][0]["ko"] = "Goldman Sachs가 2023년 매출 최대 120억 달러를 공개했습니다."
                if qualifier != "up to ":
                    self.reject(wrong, source)

    def test_two_currencies_bind_to_their_own_amount_and_repeated_amounts_are_counted(self):
        source, result = self.number_digest("$12 billion and EUR 2 million", "120억 달러와 200만 유로")
        validate_editorial(source, result)
        changed = copy.deepcopy(result)
        changed["summary"][0]["ko"] = "Goldman Sachs가 2023년 매출 120억 유로와 200만 달러를 공개했습니다."
        self.reject(changed, source)
        source, result = self.number_digest("$12 billion and $12 billion", "120억 달러와 120억 달러")
        validate_editorial(source, result)
        changed = copy.deepcopy(result)
        changed["summary"][0]["ko"] = "Goldman Sachs가 2023년 매출 120억 달러를 공개했습니다."
        self.reject(changed, source)

    def test_korean_160_character_limit_and_non_currency_syllables(self):
        result = response()
        base = "Goldman Sachs의 새 은행 부문 책임자 선임 소식에 관한 위원회 설명입니다. "
        result["summary"][0]["ko"] = base + "설명" * ((160 - len(base)) // 2)
        result["summary"][0]["ko"] += "가" * (160 - len(result["summary"][0]["ko"]))
        self.assertEqual(len(result["summary"][0]["ko"]), 160)
        newsletter = validate_editorial(article(), result)
        self.assertLessEqual(len(render_news_article(newsletter).encode("utf-16-le")) // 2, 3000)
        result["summary"][0]["ko"] += "가"
        self.reject(result)

    def test_percentage_is_preserved_in_both_languages(self):
        result = response()
        result["summary"][0].update(sentence_id="S7", en="The bank's profit margin reached 12% as costs declined.",
                                    ko="비용이 줄면서 은행의 이익률이 12%에 도달했습니다.")
        validate_editorial(article(), result)
        result["summary"][0]["ko"] = "비용이 줄면서 은행의 이익률이 12에 도달했습니다."
        self.reject(result)

    def test_known_company_identity_is_preserved_in_english_and_korean(self):
        for key, text in (
            ("en", "Morgan Stanley selected a banking leader."),
            ("en", "The company selected a banking leader."),
            ("ko", "Morgan Stanley가 은행 부문 책임자를 선임했습니다."),
            ("ko", "골드만삭스가 은행 부문 책임자를 선임했습니다."),
        ):
            result = response()
            result["summary"][0][key] = text
            with self.subTest(key=key, text=text):
                self.reject(result)

    def test_live_fixture_prediction_platform_identity_cannot_be_swapped(self):
        source = article(text="Polymarket hired an institutional trading executive. The exchange reviewed its expansion strategy.")
        result = response()
        result["summary"] = [
            {"role": "event", "sentence_id": "S1", "en": "Polymarket appointed an institutional executive.",
             "ko": "Polymarket이 기관 부문 책임자를 선임했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The exchange assessed its expansion strategy.",
             "ko": "거래소는 사업 확장 전략을 검토했습니다."},
        ]
        result["vocabulary"] = result["phrases"] = []
        validate_editorial(source, result)
        for field, changed_text in (
            ("en", "Kalshi appointed an institutional executive."),
            ("ko", "Kalshi가 기관 부문 책임자를 선임했습니다."),
            ("ko", "폴리마켓이 기관 부문 책임자를 선임했습니다."),
        ):
            changed = copy.deepcopy(result)
            changed["summary"][0][field] = changed_text
            with self.subTest(field=field, changed_text=changed_text):
                self.reject(changed, source)

    def company_context_digest(self):
        source = article(text=("Polymarket hired a new executive. "
                               "Polymarket's board reviewed expansion costs. "
                               "Polymarket assigned Mantil to build its institutional business."))
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "Polymarket appointed a new executive.",
             "ko": "Polymarket은 새 임원을 선임했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The board assessed expansion expenses.",
             "ko": "이사회는 사업 확대 비용을 검토했습니다."},
            {"role": "impact", "sentence_id": "S3", "en": "Mantil was assigned to develop the institutional business.",
             "ko": "Mantil에게 기관 사업 확대를 맡겼습니다."},
        ], "vocabulary": [], "phrases": [], "concept_links": []}
        return source, result

    def test_background_and_impact_can_omit_a_previously_identified_company(self):
        source, result = self.company_context_digest()
        newsletter = validate_editorial(source, result)
        self.assertIn("Polymarket", newsletter.summary_details[0].en)
        self.assertNotIn("Polymarket", newsletter.summary_details[1].en)
        self.assertNotIn("Polymarket", newsletter.summary_details[2].en)
        self.assertIn("Polymarket", newsletter.summary_details[2].evidence)

    def test_context_company_omission_never_allows_an_introduced_company(self):
        source, result = self.company_context_digest()
        for index in (1, 2):
            changed = copy.deepcopy(result)
            changed["summary"][index].update(
                en="Morgan Stanley assessed expansion expenses.", ko="Morgan Stanley가 사업 확대 비용을 검토했습니다.")
            with self.subTest(index=index):
                self.reject(changed, source)

    def test_event_identity_and_english_to_korean_identity_stay_exact(self):
        source, result = self.company_context_digest()
        omitted_event = copy.deepcopy(result)
        omitted_event["summary"][0].update(en="The platform appointed a new executive.", ko="플랫폼은 새 임원을 선임했습니다.")
        self.reject(omitted_event, source)
        for index, translated in ((1, "Polymarket이 사업 확대 비용을 검토했습니다."),
                                  (2, "Morgan Stanley가 기관 사업 확대를 맡았습니다."),
                                  (0, "Kalshi가 새 임원을 선임했습니다.")):
            changed = copy.deepcopy(result)
            changed["summary"][index]["ko"] = translated
            with self.subTest(index=index, translated=translated):
                self.reject(changed, source)

    def test_event_company_anaphor_can_use_verified_title_identity(self):
        source = article(title="Goldman Sachs and Morgan Stanley leadership updates", text=(
            "The bank's board reviewed its leadership risks. "
            "The executive had retired from the banking business."))
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "Goldman Sachs reassessed its leadership risks.",
             "ko": "Goldman Sachs는 경영진 관련 위험을 재검토했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The executive previously retired from the banking business.",
             "ko": "해당 임원은 앞서 은행 사업 부문에서 퇴임했습니다."},
        ], "vocabulary": [], "phrases": [], "concept_links": []}
        newsletter = validate_editorial(source, result)
        self.assertIn("Goldman Sachs", newsletter.summary_details[0].en)
        self.assertNotIn("Morgan Stanley", newsletter.english_summary)
        for title in ("Bank leadership update", "Morgan Stanley leadership update"):
            with self.subTest(title=title):
                self.reject(result, replace(source, title=title))

    def test_title_context_does_not_erase_event_sentence_identity_requirement(self):
        source = article(title="Goldman Sachs and Morgan Stanley leadership updates")
        result = response()
        validate_editorial(source, result)
        result["summary"][0].update(en="Morgan Stanley selected a banking leader.",
                                    ko="Morgan Stanley는 은행 부문 책임자를 선임했습니다.")
        self.reject(result, source)

    def test_health_insurance_carrier_identity_is_preserved(self):
        for company in ("UnitedHealth Group", "UnitedHealthcare", "Cigna", "Humana",
                        "Elevance Health", "Centene", "Molina Healthcare", "Aetna"):
            source = article(text=f"{company} launched a claims platform. The board reviewed operating costs.")
            result = {"summary": [
                {"role": "event", "sentence_id": "S1", "en": f"{company} introduced its claims platform.",
                 "ko": f"{company}가 보험금 청구 플랫폼을 출시했습니다."},
                {"role": "background", "sentence_id": "S2", "en": "The board assessed operating expenses.",
                 "ko": "이사회는 운영 비용을 검토했습니다."},
            ], "vocabulary": [], "phrases": [], "concept_links": []}
            with self.subTest(company=company):
                validate_editorial(source, result)
                changed = copy.deepcopy(result)
                changed["summary"][0]["ko"] = "보험사가 보험금 청구 플랫폼을 출시했습니다."
                self.reject(changed, source)

    def test_insurer_summary_keeps_numeric_event_and_original_specialist_context(self):
        source = article(title="Synthetic Chubb insurance earnings", text=(
            "Chubb reported underwriting profit of $2 billion as claims costs declined. "
            "Lower catastrophe losses improved the combined ratio during the reporting period. "
            "The insurer raised capital to shore up its balance sheet."))
        payload = editorial_payload(source)
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "Chubb earned $2 billion from underwriting as claim expenses fell.",
             "ko": "Chubb는 보험금 비용 감소 속에 보험영업이익 $2 billion을 기록했습니다."},
            {"role": "background", "sentence_id": "S2", "en": "Reduced catastrophe losses strengthened the period's combined ratio.",
             "ko": "재해 손실 감소가 해당 기간 합산비율을 개선했습니다."},
        ], "vocabulary": [{"candidate_id": "V1", "meaning_ko": "보험영업이익"},
                           {"candidate_id": "V2", "meaning_ko": "합산비율"}],
            "phrases": [{"candidate_id": "P1", "meaning_ko": "자본을 조달했다", "explanation_ko": "보험사가 재무 기반 보강을 위해 자금을 조달한 상황입니다."}],
            "concept_links": []}
        newsletter = validate_editorial(source, result, payload)
        self.assertEqual([word.category for word in newsletter.vocabulary_evidence], ["insurance", "insurance"])
        self.assertEqual([word.level for word in newsletter.vocabulary_evidence], ["", ""])
        self.assertEqual(newsletter.summary_details[0].evidence, payload["evidence_sentences"][0]["text"])
        self.assertIn("$2 billion", newsletter.english_summary)
        self.assertTrue(all(word.context in source.text for word in newsletter.vocabulary_evidence))

    def test_may_can_be_paraphrased_as_could_without_losing_korean_uncertainty(self):
        source = article(text=("Morgan Stanley may cut costs if market conditions deteriorate. "
                               "The bank reviewed its costs after trading volumes declined."))
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "Morgan Stanley could reduce costs if market conditions worsen.",
             "ko": "시장 여건이 나빠지면 Morgan Stanley가 비용을 줄일 수 있습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The bank reassessed expenses following lower trading volumes.",
             "ko": "은행은 거래량 감소 이후 비용을 재검토했습니다."},
        ], "vocabulary": [], "phrases": [], "concept_links": []}
        validate_editorial(source, result)
        for en, ko in (
            ("Morgan Stanley will reduce costs when market conditions worsen.", "시장 여건이 나빠지면 Morgan Stanley는 비용을 줄입니다."),
            (result["summary"][0]["en"], "시장 여건이 나빠지면 Morgan Stanley는 비용을 줄입니다."),
        ):
            changed = copy.deepcopy(result)
            changed["summary"][0].update(en=en, ko=ko)
            with self.subTest(en=en, ko=ko):
                self.reject(changed, source)

    def test_invalid_model_response_is_not_automatically_retried(self):
        model = Mock()
        model.complete_json.return_value = {"provider_error": "synthetic"}
        with self.assertRaises(NewsError):
            prepare_editorial(article(), model)
        model.complete_json.assert_called_once()

    def test_korean_summary_meaning_and_phrase_explanation_reject_mixed_chinese_text(self):
        for section, field in (("summary", "ko"), ("vocabulary", "meaning_ko"), ("phrases", "explanation_ko")):
            result = response()
            result[section][0][field] += " 银行业务"
            with self.subTest(section=section, field=field):
                self.reject(result)

    def test_provisional_discussions_cannot_turn_into_completed_changes(self):
        source = article(text="Goldman Sachs reportedly discussed a possible leadership succession. The board reviewed risks after the executive retired.")
        result = response()
        result["summary"] = [
            {"role": "event", "sentence_id": "S1", "en": "Goldman Sachs reportedly considered a leadership change.",
             "ko": "Goldman Sachs가 경영진 교체를 검토한 것으로 보도됐습니다."},
            result["summary"][1],
        ]
        result["vocabulary"] = result["phrases"] = []
        validate_editorial(source, result)
        for en, ko in (
            ("Goldman Sachs completed a leadership change.", "Goldman Sachs가 경영진 교체를 완료했습니다."),
            ("Goldman Sachs reportedly considered a leadership change.", "Goldman Sachs가 경영진 교체를 완료했습니다."),
        ):
            changed = copy.deepcopy(result)
            changed["summary"][0].update(en=en, ko=ko)
            with self.subTest(en=en, ko=ko):
                self.reject(changed, source)

    def test_supplied_evidence_payload_cannot_substitute_unrelated_article_facts(self):
        payload = editorial_payload(article())
        payload["evidence_sentences"][0]["text"] = "Goldman Sachs reported revenue of $99 billion."
        result = response()
        result["summary"][0].update(en="Goldman Sachs disclosed $99 billion in revenue.",
                                    ko="Goldman Sachs가 99 billion 달러 매출을 공개했습니다.")
        self.reject(result, payload=payload)

    def test_learning_items_require_existing_unique_ids_from_the_right_candidate_pool(self):
        for key, identity in (("vocabulary", "V99"), ("vocabulary", "P1"),
                              ("phrases", "P99"), ("phrases", "V1"),
                              ("vocabulary", 1), ("phrases", None)):
            result = response()
            result[key][0]["candidate_id"] = identity
            with self.subTest(key=key, identity=identity):
                self.reject(result)
        for key in ("vocabulary", "phrases"):
            result = response()
            result[key][1]["candidate_id"] = result[key][0]["candidate_id"]
            with self.subTest(key=key):
                self.reject(result)

    def test_model_cannot_supply_learning_terms_contexts_references_or_levels(self):
        for key in ("vocabulary", "phrases"):
            for field, value in (("term", "fake term"), ("context", "fake sentence"),
                                 ("reference", "https://example.com/fake"), ("level", "C1")):
                result = response()
                result[key][0][field] = value
                with self.subTest(key=key, field=field):
                    self.reject(result)

    def test_learning_count_bounds_translation_and_explanation_schema_are_enforced(self):
        for key in ("vocabulary", "phrases"):
            result = response()
            result[key] = result[key] + [copy.deepcopy(result[key][0])]
            with self.subTest(key=key):
                self.reject(result)
            for meaning in ("English only", "뜻 99", "뜻 https://example.com", "가" * 101):
                result = response()
                result[key][0]["meaning_ko"] = meaning
                with self.subTest(key=key, meaning=meaning):
                    self.reject(result)
        result = response()
        del result["phrases"][0]["explanation_ko"]
        self.reject(result)

    def test_two_vocabulary_items_are_required_when_multiple_candidates_exist(self):
        self.assertGreaterEqual(len(editorial_payload(article())["vocabulary_candidates"]), 2)
        for count in (0, 1):
            result = response()
            result["vocabulary"] = result["vocabulary"][:count]
            with self.subTest(count=count):
                self.reject(result)

    def test_single_available_vocabulary_requires_exactly_one_grounded_item(self):
        source = article(text="The bank approved a succession plan. The board reviewed leadership risks after the executive retired.")
        payload = editorial_payload(source)
        self.assertEqual(len(payload["vocabulary_candidates"]), 1)
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "The bank adopted its succession plan.",
             "ko": "은행은 경영진 승계 계획을 승인했습니다."},
            response()["summary"][1],
        ], "vocabulary": [{"candidate_id": "V1", "meaning_ko": "경영진 승계 계획"}],
            "phrases": [], "concept_links": []}
        validate_editorial(source, result)
        result["vocabulary"] = []
        self.reject(result, source)

    def test_available_phrases_require_at_least_one_and_allow_up_to_two(self):
        result = response()
        result["phrases"] = result["phrases"][:1]
        validate_editorial(article(), result)
        result["phrases"] = []
        self.reject(result)
        source = article(text="The bank got back on track. The board reviewed its operating costs.")
        self.assertEqual(len(editorial_payload(source)["phrase_candidates"]), 1)
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "The bank returned to its normal course.",
             "ko": "은행은 정상 궤도로 돌아왔습니다."},
            {"role": "background", "sentence_id": "S2", "en": "The board assessed the bank's operating expenses.",
             "ko": "이사회는 은행의 운영 비용을 검토했습니다."},
        ], "vocabulary": [], "phrases": [response()["phrases"][0]], "concept_links": []}
        validate_editorial(source, result)
        result["phrases"] += [{"candidate_id": "P2", "meaning_ko": "지어낸 표현", "explanation_ko": "잘못된 표현입니다."}]
        self.reject(result, source)

    def test_empty_candidate_arrays_stay_empty_and_no_easy_words_are_added(self):
        source = article(text="Persistent inflation weakened the economy. Robust banks maintained stable interest rates.")
        payload = editorial_payload(source)
        self.assertEqual(payload["vocabulary_candidates"], [])
        self.assertEqual(payload["phrase_candidates"], [])
        result = {"summary": [
            {"role": "event", "sentence_id": "S1", "en": "Continued inflation left the economy weaker.",
             "ko": "지속된 물가 상승으로 경제가 약해졌습니다."},
            {"role": "background", "sentence_id": "S2", "en": "Resilient banks kept interest rates stable.",
             "ko": "견조한 은행들은 금리를 안정적으로 유지했습니다."},
        ], "vocabulary": [], "phrases": [], "concept_links": []}
        newsletter = validate_editorial(source, result, payload)
        self.assertEqual(newsletter.vocabulary, ())
        self.assertEqual(newsletter.phrases, ())
        result["vocabulary"] = [{"candidate_id": "V1", "meaning_ko": "쉬운 단어"}]
        self.reject(result, source, payload)

    def test_rendered_mobile_article_has_context_sections_professional_labels_and_one_message(self):
        newsletter = validate_editorial(article(), response())
        body = render_news_article(newsletter)
        self.assertIn("무슨 일이 있었나", body)
        self.assertIn("배경", body)
        self.assertIn("사업 영향·반응", body)
        self.assertIn("금융 전문 어휘", body)
        self.assertIn("중요한 비즈니스 구문", body)
        self.assertIn("공개된 본문 범위", body)
        self.assertIn("back on track", body)
        self.assertNotIn("C1", body)
        self.assertNotIn("S1", body)
        self.assertNotIn("V1", body)
        self.assertLessEqual(len(body.encode("utf-16-le")) // 2, 3000)
        with self.assertRaises(NewsError):
            render_news_article(replace(newsletter, title="🏦" * 1600))


if __name__ == "__main__":
    unittest.main()
