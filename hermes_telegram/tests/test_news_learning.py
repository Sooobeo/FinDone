"""Exercise news vocabulary commands with private DBs and no network calls."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.config import ConfigurationError, Settings
from findone_hermes.content import ContentRepository
from findone_hermes.model import ModelError
from findone_hermes.news import NewsletterArticle, NewsletterVocabulary, NewsletterPhrase
from findone_hermes.news_archive import NewsArchive, archive_path
from findone_hermes.news_learning import (
    handle_news_learning, record_news_learning_delivery, vocab_path,
)
from findone_hermes.vocab_state import VocabStore
from findone_hermes.wiki import WikiEntry, WikiError

ROOT = Path(__file__).resolve().parents[2]
OWNER = 123
OTHER_OWNER = 456
NOW = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
URL = "https://www.ecb.europa.eu/press/controller-fixture.en.html"
DATA = (
    ("yield", "채권 수익률", "Bond yield represents the return on a bond."),
    ("liquidity", "유동성", "Market liquidity allows investors to sell bonds quickly."),
    ("inflation", "물가 상승", "Inflation increases the general price level."),
    ("leverage", "차입 투자", "Leverage increases financial risk through borrowing."),
    ("duration", "금리 민감도", "Bond duration measures sensitivity to interest rate changes."),
    ("financing", "자금 조달", "Market financing provides funding for investment."),
    ("debt", "기업 채무", "Corporate debt creates fixed repayment obligations."),
)


def fixture_article(**overrides):
    return replace(NewsletterArticle(
        title="Public financial markets fixture", url=URL, published_at=NOW,
        source_name="ECB", english_summary=DATA[0][2], korean_summary="공개 테스트 금융 기사입니다.",
        vocabulary=tuple((term, meaning) for term, meaning, sentence in DATA),
        concept_links=(), source_text=" ".join(item[2] for item in DATA),
        vocabulary_evidence=tuple(NewsletterVocabulary(term, meaning, sentence, term, "B2")
                                  for term, meaning, sentence in DATA),
    ), **overrides)


class FakeLevels:
    def lookup(self, term):
        term = term.casefold()
        if term == "yields":
            return "yield", "B2"
        return (term, "B2") if term in {item[0] for item in DATA} else None


class FakeModel:
    def __init__(self):
        self.calls = []
        self.result = {"meaning_ko": "채권", "explanation_ko": "이 문장에서 거래 대상인 채권을 뜻합니다."}
        self.failure = None

    def complete_json(self, prompt, payload):
        self.calls.append((prompt, payload))
        if self.failure:
            raise self.failure
        return dict(self.result)


class NewsLearningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="findone-news-learning-")
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        self.environment = {
            "TELEGRAM_ALLOWED_USERS": str(OWNER), "FINDONE_TELEGRAM_MODE": "news",
            "FINDONE_REPO_ROOT": str(ROOT),
            "STATE_DB_PATH": str(directory / "news_state.sqlite3"),
            "FINDONE_NEWS_ARCHIVE_PATH": str(directory / "news_archive.sqlite3"),
            "FINDONE_VOCAB_DB_PATH": str(directory / "vocabulary.sqlite3"),
        }
        self.model = FakeModel()
        self.model_factory = patch("findone_hermes.news_learning.model_from_env", return_value=self.model)
        self.levels_patch = patch("findone_hermes.news_learning.WordLevels.from_env", return_value=FakeLevels())
        self.wiki_patch = patch("findone_hermes.news_learning.WikiSync.from_env", return_value=None)
        self.model_factory.start()
        self.levels_patch.start()
        self.wiki_factory = self.wiki_patch.start()
        self.addCleanup(self.model_factory.stop)
        self.addCleanup(self.levels_patch.stop)
        self.addCleanup(self.wiki_patch.stop)
        self.sequence = 0
        self.prepare_article()

    def prepare_article(self, *, message_id="100", snapshot=None, environment=None):
        environment = environment or self.environment
        owner = int(environment["TELEGRAM_ALLOWED_USERS"])
        snapshot = snapshot or fixture_article()
        body = f"Public article {message_id}\n{snapshot.title}\n{snapshot.source_text}\n{snapshot.url}"
        with NewsArchive(archive_path(environment)) as archive:
            article_id = archive.prepare_message(owner, snapshot, body, now=NOW)
            self.assertTrue(archive.record_delivery(owner, str(owner), message_id, body, now=NOW))
        return article_id

    def handle(self, text, *, submission_id=None, reply_id=None, now=NOW, environment=None):
        self.sequence += 1
        return handle_news_learning(
            environment or self.environment, text,
            submission_id=submission_id or str(self.sequence),
            reply_to_message_id=reply_id, now=now,
        )

    def save(self, term="yield", *, article_message="100", **kwargs):
        return self.handle("/word " + term, reply_id=article_message, **kwargs)

    def saved_words(self, owner=OWNER):
        with VocabStore(vocab_path(self.environment)) as store:
            return store.list_words(owner)

    def active_batch(self, owner=OWNER):
        with VocabStore(vocab_path(self.environment)) as store:
            return store.active_batch(owner)

    def answers(self, batch_id, owner=OWNER):
        with VocabStore(vocab_path(self.environment)) as store:
            return store.answers(owner, batch_id)

    def review(self, count=5, *, message_id="901", record=True, **kwargs):
        messages = self.handle(f"/vocab {count}", **kwargs)
        self.assertEqual(len(messages), 1)
        self.assertIn("문항 1/", messages[0])
        self.assertRegex(messages[0], r"복습 [1-9][0-9]*회")
        if record:
            self.assertTrue(record_news_learning_delivery(
                self.environment, chat_id="123", message_id=message_id, text=messages[0],
            ))
        return messages[0], self.active_batch()

    def test_word_save_requires_archived_reply_and_actual_article_occurrence(self):
        cases = (("/word yield", None), ("/word yield", "99999"), ("/word absent", "100"), ("/word", "100"))
        for text, reply_id in cases:
            with self.subTest(text=text, reply_id=reply_id):
                messages = self.handle(text, reply_id=reply_id)
                self.assertEqual(len(messages), 1)
                self.assertEqual(self.saved_words(), ())
        self.assertEqual(self.model.calls, [])

    def test_word_save_preserves_original_sentence_meaning_url_and_source(self):
        messages = self.save()
        self.assertEqual(len(messages), 1)
        for value in (DATA[0][0], DATA[0][1], DATA[0][2], URL):
            self.assertIn(value, messages[0])
        source = self.saved_words()[0].source
        self.assertEqual((source.term, source.lemma, source.sentence), ("yield", "yield", DATA[0][2]))
        self.assertEqual(source.meaning_ko, DATA[0][1])
        self.assertEqual((source.article_url, source.source_name), (URL, "ECB"))
        self.assertEqual(source.article_title, fixture_article().title)
        self.assertEqual(self.model.calls, [])

    def test_manual_basic_word_is_allowed_and_model_receives_only_exact_context(self):
        messages = self.save("bond")
        self.assertIn("채권", messages[0])
        self.assertEqual(len(self.model.calls), 1)
        payload = self.model.calls[0][1]
        self.assertEqual(payload, {"term": "Bond", "sentence": DATA[0][2], "article_title": fixture_article().title})
        source = self.saved_words()[0].source
        self.assertEqual((source.term, source.lemma, source.sentence), ("Bond", "bond", DATA[0][2]))
        self.assertEqual(source.meaning_ko, "채권")

    def test_manual_original_word_without_oxford_registry_uses_exact_context_and_model(self):
        self.assertNotIn("FINDONE_CEFR_WORDLIST_PATH", self.environment)
        with patch("findone_hermes.news_learning.WordLevels.from_env",
                   side_effect=AssertionError("An unconfigured registry must not be loaded")) as levels:
            messages = self.save("BOND")
        levels.assert_not_called()
        self.assertIn("채권", messages[0])
        source = self.saved_words()[0].source
        self.assertEqual((source.term, source.lemma, source.sentence), ("Bond", "bond", DATA[0][2]))
        self.assertEqual(source.meaning_ko, "채권")
        self.assertEqual(source.article_url, URL)
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(self.model.calls[0][1], {
            "term": "Bond", "sentence": DATA[0][2], "article_title": fixture_article().title,
        })

    def test_known_inflection_restores_surface_and_complete_original_sentence(self):
        sentence = "Bond yields represent returns on bonds."
        evidence = NewsletterVocabulary("yields", DATA[0][1], sentence, "yield", "B2")
        self.prepare_article(message_id="101", snapshot=fixture_article(
            source_text=sentence, vocabulary_evidence=(evidence,),
        ))
        self.save("yield", article_message="101")
        source = self.saved_words()[0].source
        self.assertEqual((source.term, source.lemma, source.sentence), ("yields", "yield", sentence))
        self.assertEqual(self.model.calls, [])

    def test_selected_professional_unicode_terms_preserve_us_sentence_without_oxford(self):
        for index, dash in enumerate(("\u2010", "\u2011"), 101):
            term = "broker" + dash + "dealers"
            sentence = f"The U.S. {term} reported assets under management of $8.5 billion."
            evidence = NewsletterVocabulary(term, "증권 중개·매매업자", sentence,
                                           "broker-dealer", "", "https://www.sifma.org/about", "capital_markets")
            self.prepare_article(message_id=str(index), snapshot=fixture_article(
                url=f"https://www.ecb.europa.eu/press/unicode-{index}.en.html",
                source_text=sentence, vocabulary_evidence=(evidence,), vocabulary=((term, evidence.meaning_ko),),
            ))
            with patch("findone_hermes.news_learning.WordLevels.from_env", side_effect=AssertionError("Selected professional evidence needs no Oxford lookup")):
                messages = self.save("broker-dealer", article_message=str(index))
            source = next(word.source for word in self.saved_words() if word.source.sentence == sentence)
            self.assertEqual((source.term, source.lemma, source.sentence), (term, "broker-dealer", sentence))
            self.assertIn(sentence, messages[0])
        self.assertEqual(self.model.calls, [])

    def test_selected_phrase_surface_and_curated_lemma_save_one_context_without_model(self):
        sentence = "The U.S. insurer raised capital to shore up its balance sheet."
        phrase = NewsletterPhrase("raised capital", "자본을 조달했다", sentence,
                                  "raise capital to + 동사", "https://dictionary.cambridge.org/dictionary/english/raise-money-funds-capital-etc",
                                  "재무 기반을 보강하기 위해 자본을 조달한 상황입니다.")
        self.prepare_article(message_id="101", snapshot=fixture_article(
            source_text=sentence, vocabulary=(), vocabulary_evidence=(), phrases=(phrase,),
        ))
        with patch("findone_hermes.news_learning.WordLevels.from_env", side_effect=AssertionError("Selected phrases need no Oxford lookup")):
            self.save("raised capital", article_message="101", submission_id="phrase-surface")
            first = self.saved_words()[0]
            self.save("raise capital", article_message="101", submission_id="phrase-lemma")
        self.assertEqual(len(self.saved_words()), 1)
        self.assertEqual(self.saved_words()[0].word_id, first.word_id)
        self.assertEqual((first.source.term, first.source.lemma, first.source.sentence),
                         ("raised capital", "raise capital", sentence))
        self.assertEqual(first.source.meaning_ko, phrase.meaning_ko)
        self.assertEqual(first.source.explanation_ko, phrase.explanation_ko)
        self.assertEqual(self.model.calls, [])

    def test_selected_source_sentence_can_end_with_an_abbreviation(self):
        sentence = "The broker‑dealer operates in the U.S."
        evidence = NewsletterVocabulary("broker‑dealer", "증권 중개·매매업자", sentence,
                                       "broker-dealer", "", "https://www.sifma.org/about", "capital_markets")
        self.prepare_article(message_id="101", snapshot=fixture_article(
            source_text=sentence, vocabulary_evidence=(evidence,),
        ))
        self.save("broker-dealer", article_message="101")
        self.assertEqual(self.saved_words()[0].source.sentence, sentence)
        self.assertEqual(self.model.calls, [])

    def test_manual_typographic_apostrophe_preserves_surface_and_uses_one_cached_meaning(self):
        sentence = "The issuer’s credit rating supports long-term borrowing."
        self.prepare_article(message_id="101", snapshot=fixture_article(
            source_text=sentence, vocabulary=(), vocabulary_evidence=(),
        ))
        self.model.result = {"meaning_ko": "발행인의", "explanation_ko": "이 문장에서 채권 발행인의 소유 관계를 나타냅니다."}
        self.save("issuer's", article_message="101", submission_id="plain-apostrophe")
        self.save("issuer’s", article_message="101", submission_id="curly-apostrophe")
        self.assertEqual(len(self.saved_words()), 1)
        source = self.saved_words()[0].source
        self.assertEqual((source.term, source.lemma, source.sentence), ("issuer’s", "issuer's", sentence))
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(self.model.calls[0][1]["term"], "issuer’s")
        self.assertEqual(self.model.calls[0][1]["sentence"], sentence)

    def test_unicode_professional_surface_is_kept_in_quiz_and_private_wiki_projection(self):
        term = "broker‑dealer"
        sentence = "The U.S. broker‑dealer’s revenue increased during the reporting period."
        evidence = NewsletterVocabulary(term, "증권 중개·매매업자", sentence,
                                       "broker-dealer", "", "https://www.sifma.org/about", "capital_markets")
        self.prepare_article(message_id="101", snapshot=fixture_article(
            source_text=sentence, vocabulary=((term, evidence.meaning_ko),), vocabulary_evidence=(evidence,),
        ))
        wiki = Mock(spec=["sync"])
        self.wiki_factory.return_value = wiki
        self.save("broker-dealer", article_message="101")
        wiki.sync.assert_called_once()
        entry = wiki.sync.call_args.args[0]
        self.assertEqual((entry.term, entry.lemma, entry.sentence), (term, "broker-dealer", sentence))
        question, batch = self.review(1)
        self.assertIn(term, question)
        self.assertIn(sentence, question)
        self.assertEqual(batch.items[0].source.term, term)
        self.assertEqual(batch.items[0].source.sentence, sentence)

    def test_invisible_or_nonenglish_request_characters_cannot_be_saved(self):
        for term in ("yield\u200b", "yi\u0435ld", "<yield>", "yield\nextra"):
            with self.subTest(term=term):
                self.save(term)
                self.assertEqual(self.saved_words(), ())
        self.assertEqual(self.model.calls, [])

    def test_same_word_with_earlier_different_sense_uses_its_paired_financial_evidence(self):
        earlier = "Drivers yield to pedestrians at a crossing."
        financial = "Investors measure yield when assessing the return on a bond."
        clause = "yield when assessing the return on a bond"
        evidence = NewsletterVocabulary("yield", "채권 수익률", clause, "yield", "B2")
        snapshot = fixture_article(source_text=earlier + " " + financial, vocabulary_evidence=(evidence,))
        self.prepare_article(message_id="101", snapshot=snapshot)
        messages = self.save("yield", article_message="101")
        source = self.saved_words()[0].source
        self.assertEqual(source.meaning_ko, "채권 수익률")
        self.assertEqual(source.sentence, financial)
        self.assertIn(financial, messages[0])
        self.assertNotIn(earlier, messages[0])
        self.assertEqual(self.model.calls, [])

    def test_evidence_crossing_sentence_boundary_is_not_saved_as_a_word_example(self):
        first = "Investors measure yield."
        second = "The bond supports funding."
        crossing = "yield. The bond"
        evidence = NewsletterVocabulary("yield", "채권 수익률", crossing, "yield", "B2")
        self.prepare_article(message_id="101", snapshot=fixture_article(
            source_text=first + " " + second, vocabulary_evidence=(evidence,),
        ))
        messages = self.save("yield", article_message="101")
        self.assertIn("문장을 찾지 못했습니다", messages[0])
        self.assertEqual(self.saved_words(), ())
        self.assertEqual(self.model.calls, [])

    def test_context_cache_and_submission_replay_never_change_first_meaning(self):
        self.save("bond", submission_id="save-basic")
        first = self.saved_words()[0]
        self.model.result = {"meaning_ko": "새로 변경한 뜻", "explanation_ko": "변경된 설명입니다."}
        self.assertEqual(self.save("bond", submission_id="save-basic"), [])
        messages = self.save("bond", submission_id="new-encounter", now=NOW + timedelta(hours=1))
        self.assertIn("이미 저장한 문맥", messages[0])
        current = self.saved_words()[0]
        self.assertEqual(current.source, first.source)
        self.assertEqual(current.word_id, first.word_id)
        self.assertEqual(current.due_at, first.due_at)
        self.assertEqual(len(self.model.calls), 1)

    def test_same_word_in_different_articles_creates_separate_source_records(self):
        self.save()
        other = fixture_article(title="Another public update", url="https://www.bis.org/press/controller-fixture.htm", source_name="BIS")
        self.prepare_article(message_id="101", snapshot=other)
        self.save(article_message="101")
        words = self.saved_words()
        self.assertEqual(len(words), 2)
        self.assertEqual({word.source.lemma for word in words}, {"yield"})
        self.assertEqual({word.source.article_url for word in words}, {URL, other.url})
        self.assertEqual(len({word.word_id for word in words}), 2)

    def test_other_owner_cannot_use_an_article_receipt_or_saved_word(self):
        self.save()
        other_environment = {**self.environment, "TELEGRAM_ALLOWED_USERS": "456"}
        messages = self.save(environment=other_environment)
        self.assertIn("기사 출처를 확인할 수 없습니다", messages[0])
        self.assertEqual(len(self.saved_words()), 1)
        self.assertEqual(self.saved_words(OTHER_OWNER), ())
        summary = self.handle("/words", environment=other_environment)
        self.assertIn("저장한 문맥: 0개", summary[0])

    def test_model_failure_or_invalid_translation_cannot_save_or_leak_details(self):
        for result in (
            {"meaning_ko": "English only", "explanation_ko": "영문 뜻 오류입니다."},
            {"meaning_ko": "채권 https://example.com", "explanation_ko": "링크가 섞인 응답입니다."},
            {"meaning_ko": "채권 银行业务", "explanation_ko": "중국어가 섞인 뜻입니다."},
            {"meaning_ko": "채권", "explanation_ko": "이 문장은 银行业务가 섞인 설명입니다."},
            {"meaning_ko": "채권", "explanation_ko": "의미 설명", "unexpected": "private-model-token"},
        ):
            with self.subTest(result=result):
                self.model.result = result
                messages = self.save("bond")
                self.assertIn("뜻을 확인하지 못했습니다", messages[0])
                self.assertNotIn("private-model-token", messages[0])
                self.assertEqual(self.saved_words(), ())
        self.model.failure = ModelError("private-provider-token")
        messages = self.save("bond")
        self.assertNotIn("private-provider-token", messages[0])
        self.assertEqual(self.saved_words(), ())

    def test_words_empty_counts_and_duplicate_summary(self):
        messages = self.handle("/words", submission_id="empty-summary")
        self.assertIn("저장한 문맥: 0개", messages[0])
        self.assertIn("복습 대기: 0개", messages[0])
        self.assertIn("진행 중인 문항: 0개", messages[0])
        self.assertEqual(self.handle("/words", submission_id="empty-summary"), [])
        self.save()
        messages = self.handle("/words")
        self.assertIn("저장한 문맥: 1개", messages[0])
        self.assertIn("복습 대기: 1개", messages[0])

    def test_empty_review_guides_article_word_save(self):
        messages = self.handle("/vocab 5")
        self.assertIn("아직 시험에 쓸 단어가 없습니다", messages[0])
        self.assertIn("/word", messages[0])
        self.assertIsNone(self.active_batch())

    def test_single_saved_word_has_four_provenance_grounded_choices_from_real_content(self):
        # Exclude the default fixture's other article vocabulary so the three
        # distractors must come from the real packaged finance concept titles.
        self.environment["FINDONE_NEWS_ARCHIVE_PATH"] = str(
            Path(self.environment["FINDONE_NEWS_ARCHIVE_PATH"]).with_name("single_word_archive.sqlite3")
        )
        single = fixture_article(vocabulary=(("yield", DATA[0][1]),), vocabulary_evidence=(fixture_article().vocabulary_evidence[0],))
        self.prepare_article(message_id="101", snapshot=single)
        self.save(article_message="101")
        question, batch = self.review(count=1)
        item = batch.items[0]
        settings = Settings.from_env(self.environment)
        with ContentRepository(settings.content_db, settings.content_manifest) as content:
            concepts = {element.element_id: element.title for element in content.elements()
                        if element.domain_id in {"FI", "CF", "IBT"}}
        self.assertEqual(len(item.choices), 4)
        self.assertEqual({choice.number for choice in item.choices}, {1, 2, 3, 4})
        for choice in item.choices:
            self.assertIn(f"{choice.number}. {choice.meaning_ko}", question)
            if choice.number != item.correct_number:
                self.assertIn(choice.source_id, concepts)
                self.assertEqual(choice.meaning_ko, concepts[choice.source_id])
        self.assertIn(DATA[0][2], question)
        self.assertNotIn("정답:", question)

    def test_review_count_validation_and_five_item_cap(self):
        for term, meaning, sentence in DATA:
            self.save(term)
        for text in ("/vocab 0", "/vocab 6", "/vocab 100", "/vocab 5 extra"):
            messages = self.handle(text)
            self.assertIn("1~5", messages[0])
            self.assertIsNone(self.active_batch())
        question, batch = self.review(5)
        self.assertEqual(len(batch.items), 5)
        self.assertIn("1/5", question)

    def test_review_prioritizes_due_words_over_a_correctly_reviewed_future_word(self):
        self.save("yield")
        question, first = self.review(1)
        self.handle(str(first.items[0].correct_number), reply_id="901")
        self.save("inflation", now=NOW - timedelta(hours=2))
        self.save("liquidity", now=NOW - timedelta(hours=1))
        question, batch = self.review(2, message_id="902")
        self.assertEqual([item.source.lemma for item in batch.items], ["inflation", "liquidity"])

    def test_pending_review_survives_reopen_without_shuffle_and_submission_replay_is_silent(self):
        self.save("yield")
        self.save("liquidity")
        question, first = self.review(2, submission_id="review-once")
        self.assertEqual(self.handle("/vocab 2", submission_id="review-once"), [])
        resumed = self.handle("/vocab 1", now=NOW + timedelta(days=1))
        self.assertEqual(resumed, [question])
        self.assertEqual(self.active_batch(), first)
        summary = self.handle("/words")
        self.assertIn("진행 중인 문항: 2개", summary[0])

    def test_question_receipt_requires_exact_body_and_can_be_replayed_without_remapping(self):
        self.save()
        question, batch = self.review(1, record=False)
        for index, text in enumerate((question + "\n", " " + question, "도움말 안내"), 902):
            self.assertFalse(record_news_learning_delivery(self.environment, chat_id="123", message_id=str(index), text=text))
        self.assertTrue(record_news_learning_delivery(self.environment, chat_id="123", message_id="901", text=question))
        self.assertTrue(record_news_learning_delivery(self.environment, chat_id="123", message_id="901", text=question))
        with self.assertRaises(ValueError):
            record_news_learning_delivery(self.environment, chat_id="123", message_id="901", text=question + " altered")
        with VocabStore(vocab_path(self.environment)) as store:
            self.assertEqual(store.question_delivery(OWNER, "901"), (batch.batch_id, 1))

    def test_question_receipts_require_news_profile_private_owner_and_owner_scoped_body(self):
        self.save()
        question, batch = self.review(1, record=False)
        other_environment = {**self.environment, "TELEGRAM_ALLOWED_USERS": "456"}
        self.assertFalse(record_news_learning_delivery(other_environment, chat_id="456", message_id="901", text=question))
        with self.assertRaises(ConfigurationError):
            record_news_learning_delivery(self.environment, chat_id="456", message_id="901", text=question)
        with self.assertRaises(ConfigurationError):
            record_news_learning_delivery({**self.environment, "FINDONE_TELEGRAM_MODE": "learning"}, chat_id="123", message_id="901", text=question)
        self.assertEqual(self.answers(batch.batch_id), ())

    def test_bare_answer_requires_successful_receipt_for_current_question(self):
        self.save()
        question, batch = self.review(1, record=False)
        before = self.saved_words()
        messages = self.handle(str(batch.items[0].correct_number))
        self.assertEqual(self.answers(batch.batch_id), ())
        self.assertEqual(self.saved_words(), before)
        self.assertTrue(messages)
        record_news_learning_delivery(self.environment, chat_id="123", message_id="901", text=question)
        feedback = self.handle(str(batch.items[0].correct_number), submission_id="bare-answer")
        self.assertIn("정답", feedback[0])
        self.assertEqual(len(self.answers(batch.batch_id)), 1)
        self.assertEqual(self.handle(str(batch.items[0].correct_number), submission_id="bare-answer"), [])

    def test_unknown_reply_cannot_fall_back_to_current_quiz(self):
        self.save()
        question, batch = self.review(1)
        messages = self.handle(str(batch.items[0].correct_number), reply_id="999999")
        self.assertIn("현재 단어시험 문항이 아닙니다", messages[0])
        self.assertEqual(self.answers(batch.batch_id), ())

    def test_old_question_reply_cannot_grade_next_question_and_next_bare_answer_needs_receipt(self):
        self.save("yield")
        self.save("liquidity")
        question, batch = self.review(2)
        feedback = self.handle(str(batch.items[0].correct_number), reply_id="901", submission_id="answer-first")
        self.assertEqual(len(self.answers(batch.batch_id)), 1)
        self.assertEqual(self.handle(str(batch.items[0].correct_number), reply_id="901", submission_id="answer-first"), [])
        old_reply = self.handle(str(batch.items[1].correct_number), reply_id="901")
        self.assertIn("예전 문항", old_reply[0])
        self.assertEqual(len(self.answers(batch.batch_id)), 1)
        self.handle(str(batch.items[1].correct_number))
        self.assertEqual(len(self.answers(batch.batch_id)), 1)
        self.assertTrue(record_news_learning_delivery(self.environment, chat_id="123", message_id="902", text=feedback[1]))
        self.handle(str(batch.items[1].correct_number), reply_id="902")
        self.assertEqual(len(self.answers(batch.batch_id)), 2)

    def test_reply_to_completed_batch_cannot_grade_a_new_active_batch(self):
        self.save()
        question, old = self.review(1)
        self.handle(str(old.items[0].correct_number), reply_id="901")
        new_question, new = self.review(1, message_id="902", now=NOW + timedelta(days=2))
        self.assertNotEqual(old.batch_id, new.batch_id)
        self.handle(str(new.items[0].correct_number), reply_id="901", now=NOW + timedelta(days=2))
        self.assertEqual(self.answers(new.batch_id), ())

    def test_multi_answer_input_does_not_grade_questions_the_user_has_not_seen(self):
        self.save("yield")
        self.save("liquidity")
        question, batch = self.review(2)
        self.handle(f"{batch.items[0].correct_number},{batch.items[1].correct_number}", reply_id="901")
        self.assertEqual(self.answers(batch.batch_id), ())

    def test_concurrent_bare_answers_bound_to_first_question_cannot_grade_unseen_second(self):
        self.save("yield")
        self.save("liquidity")
        question, batch = self.review(2)
        barrier = threading.Barrier(2)
        original = VocabStore.question_was_delivered

        def checked_together(store, owner, batch_id, ordinal):
            delivered = original(store, owner, batch_id, ordinal)
            self.assertEqual((batch_id, ordinal), (batch.batch_id, 1))
            self.assertTrue(delivered)
            # Both incoming messages have observed delivered Q1 before either
            # can acquire the backend's write transaction and grade an answer.
            barrier.wait(timeout=10)
            return delivered

        with patch.object(VocabStore, "question_was_delivered", new=checked_together), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(
                handle_news_learning, self.environment, str(batch.items[0].correct_number),
                submission_id=f"concurrent-{index}", now=NOW,
            ) for index in range(2)]
            results = [future.result(timeout=15) for future in futures]
        answers = self.answers(batch.batch_id)
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0].ordinal, 1)
        self.assertEqual(sum(word.correct_count + word.wrong_count for word in self.saved_words()), 1)
        with VocabStore(vocab_path(self.environment)) as store:
            self.assertEqual(store.next_item(OWNER, batch.batch_id).ordinal, 2)
            self.assertFalse(store.question_was_delivered(OWNER, batch.batch_id, 2))
        self.handle(str(batch.items[1].correct_number))
        self.assertEqual(len(self.answers(batch.batch_id)), 1)
        next_question = next(text for messages in results for text in messages if "문항 2/2" in text)
        self.assertTrue(record_news_learning_delivery(self.environment, chat_id="123", message_id="902", text=next_question))
        self.handle(str(batch.items[1].correct_number))
        self.assertEqual(len(self.answers(batch.batch_id)), 2)

    def test_wrong_answer_uses_saved_meaning_sentence_url_and_sets_short_review_delay(self):
        self.save()
        question, batch = self.review(1)
        wrong = next(choice.number for choice in batch.items[0].choices if choice.number != batch.items[0].correct_number)
        feedback = self.handle(str(wrong), reply_id="901")
        for value in ("오답", DATA[0][1], DATA[0][2], URL, "한국 시간"):
            self.assertIn(value, feedback[0])
        word = self.saved_words()[0]
        self.assertEqual(word.wrong_count, 1)
        self.assertEqual(word.correct_count, 0)
        self.assertEqual(datetime.fromisoformat(word.due_at), NOW + timedelta(minutes=10))

    def test_wiki_failure_keeps_word_and_words_resumes_typed_outbox_without_srs(self):
        unavailable = Mock(spec=["sync"])
        unavailable.sync.side_effect = WikiError("private-wiki-failure")
        self.wiki_factory.return_value = unavailable
        messages = self.save()
        self.assertIn("동기화 대기", messages[0])
        self.assertNotIn("private-wiki-failure", messages[0])
        before = self.saved_words()[0]
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertEqual(len(archive.pending_wiki(OWNER)), 1)
        available = Mock(spec=["sync"])
        self.wiki_factory.return_value = available
        self.handle("/words", now=NOW + timedelta(hours=1))
        available.sync.assert_called_once()
        entry = available.sync.call_args.args[0]
        self.assertIsInstance(entry, WikiEntry)
        self.assertEqual((entry.term, entry.sentence, entry.article_url), ("yield", DATA[0][2], URL))
        self.assertTrue({"due_at", "streak", "wrong_count", "correct_count", "user_id"}.isdisjoint(asdict(entry)))
        self.assertEqual(self.saved_words()[0], before)
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertEqual(archive.pending_wiki(OWNER), ())

    def test_words_rebuilds_missing_wiki_outbox_from_saved_source(self):
        self.save()
        word = self.saved_words()[0]
        with NewsArchive(archive_path(self.environment)) as archive:
            with archive.transaction() as connection:
                connection.execute("DELETE FROM news_wiki_outbox WHERE user_id=?", (OWNER,))
        available = Mock(spec=["sync"])
        self.wiki_factory.return_value = available
        self.handle("/words")
        available.sync.assert_called_once()
        self.assertEqual(available.sync.call_args.args[0].word_id, word.word_id)
        self.assertEqual(self.saved_words()[0], word)

    def test_duplicate_save_after_commit_before_outbox_recovers_once_without_response(self):
        with patch.object(NewsArchive, "queue_wiki", side_effect=WikiError("simulated outbox interruption")):
            with self.assertRaises(WikiError):
                self.save(submission_id="save-before-outbox")
        saved = self.saved_words()[0]
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertEqual(archive.pending_wiki(OWNER), ())
        available = Mock(spec=["sync"])
        self.wiki_factory.return_value = available
        self.assertEqual(self.save(submission_id="save-before-outbox"), [])
        available.sync.assert_called_once()
        entry = available.sync.call_args.args[0]
        self.assertIsInstance(entry, WikiEntry)
        self.assertEqual((entry.word_id, entry.meaning_ko, entry.sentence, entry.article_url),
                         (saved.word_id, saved.source.meaning_ko, saved.source.sentence, saved.source.article_url))
        self.assertEqual(self.saved_words(), (saved,))
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertEqual(archive.pending_wiki(OWNER), ())
            self.assertEqual(archive.wiki_status(OWNER, saved.word_id), "synced")
        self.assertEqual(self.save(submission_id="save-before-outbox"), [])
        available.sync.assert_called_once()
        self.assertEqual(self.saved_words(), (saved,))

    def test_words_only_syncs_the_current_owners_wiki_outbox(self):
        self.save()
        owner_word = self.saved_words()[0]
        other_environment = {**self.environment, "TELEGRAM_ALLOWED_USERS": "456"}
        self.prepare_article(environment=other_environment)
        self.save("liquidity", environment=other_environment)
        other_word = self.saved_words(OTHER_OWNER)[0]
        available = Mock(spec=["sync"])
        self.wiki_factory.return_value = available
        self.handle("/words")
        available.sync.assert_called_once()
        self.assertEqual(available.sync.call_args.args[0].word_id, owner_word.word_id)
        self.assertEqual(self.saved_words(OTHER_OWNER)[0], other_word)
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertEqual(archive.pending_wiki(OWNER), ())
            self.assertEqual(len(archive.pending_wiki(OTHER_OWNER)), 1)

    def test_learning_profile_and_colliding_archive_vocab_paths_are_rejected(self):
        with self.assertRaises(ConfigurationError):
            self.handle("/words", environment={**self.environment, "FINDONE_TELEGRAM_MODE": "learning"})
        with self.assertRaises(ConfigurationError):
            self.handle("/words", environment={**self.environment, "FINDONE_VOCAB_DB_PATH": self.environment["FINDONE_NEWS_ARCHIVE_PATH"]})


if __name__ == "__main__":
    unittest.main()
