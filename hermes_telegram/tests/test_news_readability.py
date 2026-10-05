from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.news import (
    NewsError, NewsResult, VerifiedArticle, eligible_finance_sentences,
    news_model_payload, render_news_article, render_news_messages, validate_summary,
)
from findone_hermes.word_levels import OXFORD_URL, WordLevels


NOW = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)
URL = "https://www.ecb.europa.eu/press/readability.en.html"
FIRST = "Interest rates influence liquidity and investor financing."
SECOND = "Bond maturity requires transparency about commodity investment and each amendment."
ARTICLE = VerifiedArticle("Financial markets update", URL, NOW, "ECB", FIRST + " " + SECOND)
# Small explicit registry fixtures exercise eligibility, rather than estimating
# a level from the generated word, its phrase, or its financial subject.
LEVELS = {"investor": "B2", "liquidity": "C1", "maturity": "C1",
          "transparency": "C1", "commodity": "C1", "amendment": "C1"}


def response():
    return {
        "summary": [{"en": FIRST, "ko": "금리는 유동성과 투자자 자금 조달에 영향을 줍니다."}],
        "vocabulary": [
            {"term": "investor", "meaning_ko": "투자자", "context": FIRST},
            {"term": "liquidity", "meaning_ko": "유동성", "context": FIRST},
        ],
        "concept_links": [],
    }


def newsletter(*, registry=True):
    return validate_summary(ARTICLE, response(), {},
                            word_levels=WordLevels(LEVELS) if registry else None)


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class Element:
    element_id: str
    domain_id: str = "FI"
    title: str = "금리와 채권"
    definition: str = "금리는 자금 조달 비용이다."
    intuition: str = "금리 변동과 채권 가격을 비교한다."
    core_relation: str = "금리와 채권"


class Content:
    def elements(self):
        return tuple(Element(f"FI-{index:02}") for index in range(1, 7))


class NewsReadabilityTests(unittest.TestCase):
    def test_single_article_sections_and_each_word_are_visibly_separated(self):
        article = replace(newsletter(), concept_links=(("FI-01", "금리와 채권 관계를 복습합니다."),))
        body = render_news_article(article)
        sections = body.split("\n\n")
        self.assertTrue(sections[0].startswith("📰"))
        for heading in ("🏛", "🇬🇧", "🇰🇷", "🔗", "📚", "🔎", "💾"):
            self.assertTrue(any(section.startswith(heading) for section in sections), heading)
        self.assertIn("모델 번역", body)
        self.assertIn("Oxford 5000", body)
        self.assertRegex(body, r"(?m)^1\. investor · B2\n   투자자$")
        self.assertRegex(body, r"(?m)^2\. liquidity · C1\n   유동성$")
        self.assertIn("투자자\n\n2. liquidity", body)
        self.assertEqual(body.count(URL), 1)
        self.assertIn("🔎 원문\n" + URL, body)
        self.assertIn("/word investor", body)
        self.assertIn("/vocab 5", body)
        self.assertIn("/words", body)
        self.assertLessEqual(utf16_length(body), 3000)

    def test_multiple_articles_each_get_their_own_bounded_message_and_original_link(self):
        first = replace(newsletter(), title="가" * 1900)
        second_url = "https://www.bis.org/press/readability.htm"
        second = replace(newsletter(), title="나" * 1900, url=second_url, source_name="BIS")
        messages = render_news_messages(NewsResult((first, second), ""))
        self.assertEqual(len(messages), 2)
        self.assertGreater(utf16_length("\n\n".join(messages)), 3000)
        for body, own_url, other_url in ((messages[0], URL, second_url), (messages[1], second_url, URL)):
            self.assertLessEqual(utf16_length(body), 3000)
            self.assertEqual(body.count("📰 FinDone"), 1)
            self.assertEqual(body.count(own_url), 1)
            self.assertNotIn(other_url, body)

    def test_utf16_limit_accepts_exact_boundary_and_rejects_one_more_emoji(self):
        article = newsletter()
        remaining = 3000 - utf16_length(render_news_article(article))
        at_limit = replace(article, title=article.title + "x" * remaining)
        body = render_news_article(at_limit)
        self.assertEqual(utf16_length(body), 3000)
        # Astral characters consume two Telegram UTF-16 units, even while the
        # Python code-point count still fits within the nominal limit.
        self.assertLess(len(body + "😀"), 3000)
        with self.assertRaises(NewsError):
            render_news_article(replace(at_limit, title=at_limit.title + "😀"))

    def test_empty_eligible_vocabulary_has_friendly_text_and_no_invented_level(self):
        result = response()
        result["vocabulary"] = []
        article = validate_summary(ARTICLE, result, {}, word_levels=WordLevels(LEVELS))
        body = render_news_article(article)
        self.assertIn("선별 기준에 맞는 어휘를 찾지 못했습니다.", body)
        self.assertNotRegex(body, r"\b(?:A1|A2|B1|B2|C1|C2)\b")
        self.assertNotRegex(body, r"(?m)^\d+\. ")
        self.assertIn(URL, body)
        self.assertIn(FIRST, body)

    def test_no_articles_preserves_the_existing_unavailable_message(self):
        message = "검증된 최신 금융 뉴스가 아직 없습니다."
        self.assertEqual(render_news_messages(NewsResult((), message)), [message])

    def test_without_registry_existing_vocabulary_survives_without_level_claims(self):
        article = newsletter(registry=False)
        self.assertEqual(len(article.vocabulary), 2)
        self.assertTrue(all(not word.level and not word.reference for word in article.vocabulary_evidence))
        body = render_news_article(article)
        self.assertIn("📚 기사 어휘", body)
        self.assertIn("1. investor\n", body)
        self.assertNotIn("Oxford 5000", body)
        self.assertNotRegex(body, r"\b(?:B2|C1|C2)\b")
        missing = response()
        missing["vocabulary"] = []
        with self.assertRaises(NewsError):
            validate_summary(ARTICLE, missing, {})


class NewsVocabularyEligibilityTests(unittest.TestCase):
    def test_two_key_candidate_binds_exact_source_sentence_and_verified_level(self):
        result = response()
        result["vocabulary"] = [{"term": "liquidity", "meaning_ko": "유동성"},
                                {"term": "maturity", "meaning_ko": "만기"}]
        registry = WordLevels(LEVELS)
        supplied = news_model_payload(ARTICLE, Content(), registry)["vocabulary_candidates"]
        article = validate_summary(ARTICLE, result, {}, word_levels=registry)
        self.assertEqual(article.vocabulary, (("liquidity", "유동성"), ("maturity", "만기")))
        for word in article.vocabulary_evidence:
            candidate = next(item for item in supplied if item["term"] == word.term)
            self.assertEqual(word.context, candidate["context"])
            self.assertIn(word.context, ARTICLE.text)
            self.assertEqual((word.lemma, word.level), (candidate["lemma"], candidate["level"]))
            self.assertEqual(word.reference, OXFORD_URL)
        self.assertEqual(article.vocabulary_evidence[0].context, FIRST)
        self.assertEqual(article.vocabulary_evidence[1].context, SECOND)

    def test_two_key_known_word_outside_the_supplied_four_candidates_is_rejected(self):
        registry = WordLevels(LEVELS)
        supplied = news_model_payload(ARTICLE, Content(), registry)["vocabulary_candidates"]
        self.assertEqual(len(supplied), 4)
        self.assertIsNotNone(registry.lookup("amendment"))
        self.assertIn("amendment", ARTICLE.text)
        self.assertNotIn("amendment", {item["term"] for item in supplied})
        result = response()
        result["vocabulary"] = [{"term": "amendment", "meaning_ko": "수정안"}]
        with self.assertRaisesRegex(NewsError, "supplied source candidates"):
            validate_summary(ARTICLE, result, {}, word_levels=registry)

    def test_two_key_unknown_words_and_unlisted_phrase_are_filtered_without_level_claims(self):
        result = response()
        result["vocabulary"] = [{"term": term, "meaning_ko": "기사의 단어"}
                                for term in ("financing", "interest rates", "unfounded")]
        article = validate_summary(ARTICLE, result, {}, word_levels=WordLevels(LEVELS))
        self.assertEqual(article.vocabulary, ())
        self.assertEqual(article.vocabulary_evidence, ())
        body = render_news_article(article)
        self.assertIn("선별 기준에 맞는 어휘를 찾지 못했습니다.", body)
        self.assertNotRegex(body, r"\b(?:B2|C1|C2)\b")

    def test_two_key_vocabulary_without_registry_does_not_relax_existing_validation(self):
        result = response()
        for item in result["vocabulary"]:
            item.pop("context")
        with self.assertRaisesRegex(NewsError, "Invalid vocabulary entry"):
            validate_summary(ARTICLE, result, {})

    def test_basic_unknown_and_unlisted_phrase_are_filtered_but_verified_levels_survive(self):
        for term in ("rates", "financing", "interest rates"):
            with self.subTest(term=term):
                result = response()
                result["vocabulary"].append({"term": term, "meaning_ko": "기사의 단어", "context": FIRST})
                article = validate_summary(ARTICLE, result, {}, word_levels=WordLevels(LEVELS))
                self.assertEqual(article.vocabulary, (("investor", "투자자"), ("liquidity", "유동성")))
                evidence = article.vocabulary_evidence
                self.assertEqual([(word.lemma, word.level) for word in evidence],
                                 [("investor", "B2"), ("liquidity", "C1")])
                self.assertTrue(all(word.context == FIRST and word.reference == OXFORD_URL for word in evidence))
                self.assertNotIn("C2", render_news_article(article))

    def test_c1_threshold_filters_b2_without_promoting_its_level(self):
        article = validate_summary(ARTICLE, response(), {}, word_levels=WordLevels(LEVELS, minimum="C1"))
        self.assertEqual(article.vocabulary, (("liquidity", "유동성"),))
        self.assertEqual(article.vocabulary_evidence[0].level, "C1")
        self.assertNotIn("investor · C1", render_news_article(article))

    def test_eligible_term_still_requires_exact_original_context_and_occurrence(self):
        for context in ("Liquidity was invented by the model.", SECOND):
            result = copy.deepcopy(response())
            result["vocabulary"][1]["context"] = context
            with self.subTest(context=context), self.assertRaises(NewsError):
                validate_summary(ARTICLE, result, {}, word_levels=WordLevels(LEVELS))

    def test_model_candidates_are_four_bounded_exact_public_source_records(self):
        sentinel = "DO_NOT_COPY_PRIVATE_PROFILE_VALUE"
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": sentinel, "TELEGRAM_ALLOWED_USERS": sentinel}):
            payload = news_model_payload(ARTICLE, Content(), WordLevels(LEVELS))
        self.assertEqual(set(payload), {"article", "elements", "vocabulary_candidates"})
        self.assertEqual(set(payload["article"]), {"title", "url", "published_date", "source_name", "text"})
        self.assertEqual(payload["article"]["url"], URL)
        self.assertLessEqual(len(payload["article"]["text"]), 2000)
        self.assertEqual(len(payload["elements"]), 3)
        candidates = payload["vocabulary_candidates"]
        self.assertEqual(len(candidates), 4)
        self.assertEqual(len({candidate["lemma"] for candidate in candidates}), 4)
        original_sentences = eligible_finance_sentences(ARTICLE)
        for candidate in candidates:
            self.assertEqual(set(candidate), {"term", "lemma", "level", "context"})
            self.assertIn(candidate["context"], original_sentences)
            self.assertIn(candidate["context"], ARTICLE.text)
            self.assertIn(candidate["term"], candidate["context"])
            self.assertEqual(LEVELS[candidate["lemma"]], candidate["level"])
            self.assertIn(candidate["level"], ("B2", "C1"))
        self.assertNotIn(sentinel, json.dumps(payload))

    def test_payload_without_registry_preserves_its_original_shape(self):
        payload = news_model_payload(ARTICLE, Content())
        self.assertEqual(set(payload), {"article", "elements"})


if __name__ == "__main__":
    unittest.main()
