from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.state import StateStore
from findone_hermes.vocab_state import APPLICATION_ID, SCHEMA, TABLES, VocabStore
from findone_hermes.vocabulary import (
    AnswerFormatError, MeaningChoice, NoActiveVocabError, VocabularyService, VocabularySource,
)

NOW = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
URL = "https://www.ecb.europa.eu/press/vocabulary.en.html"
DATA = (
    ("liquidity", "유동성", "자산을 빠르게 현금화하는 정도", "Market liquidity allows investors to sell bonds quickly."),
    ("yield", "채권수익률", "채권에서 얻는 수익률", "Bond yield represents the return on a bond."),
    ("inflation", "물가상승", "전반적인 물가 상승", "Inflation increases the general price level."),
    ("leverage", "차입투자", "차입으로 투자 규모를 확대하는 방식", "Leverage increases financial risk through borrowing."),
    ("duration", "금리민감도", "금리 변동에 대한 채권 가격의 민감도", "Bond duration measures sensitivity to interest rate changes."),
    ("financing", "자금조달", "투자에 필요한 자금을 조달하는 일", "Market financing provides funding for investment."),
    ("debt", "기업채무", "기업이 상환해야 하는 채무", "Corporate debt creates fixed repayment obligations."),
)


def source(index=0, **overrides):
    term, sense, meaning, sentence = DATA[index]
    return replace(VocabularySource(term, term, sense, meaning, sentence, URL,
                                    "Financial markets update", "ARTICLE-A", "ECB",
                                    "2026-10-02T15:00:00+02:00", "원문에 쓰인 금융 문맥을 기준으로 복습합니다."), **overrides)


def choices():
    return tuple(MeaningChoice(value[2], value[0], URL, "ARTICLE-A") for value in DATA)


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="findone-vocabulary-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "vocabulary.sqlite3"
        self.store = VocabStore(self.path)
        self.service = VocabularyService(self.store, random.Random(12))

    def tearDown(self):
        self.store.close()

    def save(self, index=0, *, owner=101, submission_id=None, now=NOW, **overrides):
        return self.service.save_word(owner, source(index, **overrides),
                                      submission_id=submission_id or f"save-{index}", now=now)

    def review(self, *, owner=101, count=5, submission_id="review-1", now=NOW, pool=None):
        return self.service.review(owner, count, submission_id=submission_id,
                                   grounded_choices=choices() if pool is None else pool, now=now)

    def test_save_preserves_occurrence_sentence_meaning_and_original_url(self):
        result = self.save()
        self.assertTrue(result.created)
        self.assertFalse(result.duplicate)
        self.assertEqual(result.word.source.term, "liquidity")
        self.assertEqual(result.word.source.sentence, DATA[0][3])
        self.assertEqual(result.word.source.meaning_ko, DATA[0][2])
        self.assertEqual(result.word.source.article_url, URL)
        self.assertEqual(result.word.source.article_id, "ARTICLE-A")
        self.assertEqual(result.word.source.published_at, "2026-10-02T13:00:00+00:00")
        self.assertEqual(result.word.due_at, NOW.isoformat(timespec="microseconds"))
        self.assertEqual(self.service.summary(101, now=NOW).total, 1)
        self.assertEqual(self.service.summary(101, now=NOW).due, 1)

    def test_same_lemma_different_article_or_sense_is_stored_separately(self):
        original = self.save(1)
        different_sense = self.save(1, submission_id="sense-2", sense="수확량", meaning_ko="수확한 생산물의 양")
        different_article = self.save(1, submission_id="article-2", article_url="https://www.bis.org/press/yield.htm")
        same = self.save(1, submission_id="same-context", lemma="YIELD", article_url=URL + "?utm_source=rss#top")
        self.assertFalse(same.created)
        self.assertEqual(same.word.word_id, original.word.word_id)
        self.assertEqual(len({word.word.word_id for word in (original, different_sense, different_article)}), 3)
        self.assertEqual(len(self.store.list_words(101)), 3)

    def test_saved_source_changes_cannot_replace_snapshot_or_reset_srs(self):
        saved = self.save()
        batch = self.review(count=1)
        self.service.answer(101, str(batch.items[0].correct_number), submission_id="answer-1", now=NOW)
        graded = self.store.word(101, saved.word.word_id)
        changed = self.save(submission_id="save-again", now=NOW + timedelta(hours=1),
                            meaning_ko="새로 생성한 다른 뜻", sentence="Market liquidity is described differently today.")
        self.assertFalse(changed.created)
        self.assertEqual(changed.word.source, saved.word.source)
        self.assertEqual(changed.word.due_at, graded.due_at)
        self.assertEqual(changed.word.streak, 1)
        self.assertEqual(changed.word.correct_count, 1)
        self.assertEqual(changed.word.last_seen_at, (NOW + timedelta(hours=1)).isoformat(timespec="microseconds"))

    def test_save_submission_replay_survives_restart_and_does_not_save_other_input(self):
        original = self.save(submission_id="same-message")
        self.store.close()
        self.store = VocabStore(self.path)
        self.service = VocabularyService(self.store)
        repeated = self.save(1, submission_id="same-message", now=NOW + timedelta(days=2))
        self.assertTrue(repeated.duplicate)
        self.assertEqual(repeated.word.word_id, original.word.word_id)
        self.assertEqual(repeated.word.last_seen_at, original.word.last_seen_at)
        self.assertEqual(len(self.store.list_words(101)), 1)

    def test_review_uses_four_distinct_provenance_labelled_meanings_and_no_inference(self):
        self.save()
        batch = self.review(count=1)
        item = batch.items[0]
        self.assertEqual({choice.number for choice in item.choices}, {1, 2, 3, 4})
        self.assertEqual(len({choice.meaning_ko for choice in item.choices}), 4)
        self.assertEqual(item.choices[item.correct_number - 1].meaning_ko, DATA[0][2])
        known = {value[2] for value in DATA}
        self.assertTrue(all(choice.meaning_ko in known for choice in item.choices))
        self.assertTrue(all(choice.article_url or choice.source_id for choice in item.choices))

    def test_duplicate_unproven_and_ambiguous_distractors_do_not_create_fake_choices(self):
        self.save()
        invalid_pool = (
            MeaningChoice(DATA[1][2], "yield", URL),
            MeaningChoice(DATA[1][2].replace(" ", ""), "yield", URL),
            MeaningChoice("같은 단어의 다른 설명", "liquidity", URL),
            MeaningChoice("출처 없는 뜻", "unverified"),
            MeaningChoice("위험한 링크의 뜻", "unsafe", "https://attacker.invalid/article"),
        )
        self.assertIsNone(self.review(count=1, pool=invalid_pool))
        self.assertIsNone(self.store.active_batch(101))
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM vocab_items WHERE user_id=?", (101,)).fetchone()[0], 0)

    def test_finite_grounded_concept_fallback_can_provide_missing_distractors(self):
        self.save()
        pool = (MeaningChoice("금리와 채권", source_id="FI-01"),
                MeaningChoice("레버리지와 자본구조", source_id="CF-08"),
                MeaningChoice("순현재가치와 투자안 채택", source_id="CF-03"))
        batch = self.review(count=1, pool=pool)
        self.assertEqual(len(batch.items[0].choices), 4)
        self.assertEqual({choice.source_id for choice in batch.items[0].choices if not choice.article_url},
                         {"FI-01", "CF-08", "CF-03"})

    def test_saved_words_supply_their_own_grounded_distractor_pool(self):
        for index in range(4):
            self.save(index)
        batch = self.review(count=4, pool=())
        self.assertEqual(len(batch.items), 4)
        self.assertTrue(all(len(item.choices) == 4 for item in batch.items))

    def test_review_is_due_first_capped_at_five_and_reuses_pending_snapshots(self):
        self.save(0, now=NOW - timedelta(hours=1))
        first = self.review(count=1)
        self.service.answer(101, str(first.items[0].correct_number), submission_id="answer-first", now=NOW)
        for index in range(1, 7):
            self.save(index, now=NOW + timedelta(seconds=index))
        batch = self.review(count=5, submission_id="review-next", now=NOW + timedelta(minutes=1))
        self.assertEqual(len(batch.items), 5)
        self.assertTrue(all(item.source.term != "liquidity" for item in batch.items))
        reused = self.review(count=2, submission_id="review-pending", now=NOW + timedelta(days=2))
        self.assertEqual(reused, batch)
        repeated = self.review(count=5, submission_id="review-next", now=NOW + timedelta(days=2))
        self.assertTrue(repeated.duplicate)
        self.assertEqual(repeated.items, batch.items)
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM vocab_batches WHERE user_id=? AND status='active'", (101,)).fetchone()[0], 1)

    def test_sequential_answer_preserves_next_question_and_pending_across_restart(self):
        for index in range(3):
            self.save(index)
        batch = self.review(count=3)
        first = self.service.answer(101, str(batch.items[0].correct_number), submission_id="answer-1", now=NOW)
        self.assertEqual(len(first.answers), 1)
        self.assertEqual(first.next_item.ordinal, 2)
        self.assertEqual(first.batch.status, "active")
        self.store.close()
        self.store = VocabStore(self.path)
        self.service = VocabularyService(self.store)
        restored = self.store.active_batch(101)
        self.assertEqual(restored.items, batch.items)
        self.assertEqual(self.store.next_item(101, restored.batch_id).ordinal, 2)
        repeated = self.service.answer(101, "4", submission_id="answer-1", now=NOW + timedelta(hours=1))
        self.assertTrue(repeated.duplicate)
        self.assertEqual(repeated.answers, first.answers)
        self.assertEqual(repeated.next_item.ordinal, 2)
        self.assertEqual(len(self.store.answers(101, batch.batch_id)), 1)
        remaining = ",".join(str(item.correct_number) for item in batch.items[1:])
        finished = self.service.answer(101, remaining, submission_id="answer-rest", now=NOW)
        self.assertEqual(finished.batch.status, "completed")
        self.assertIsNone(finished.next_item)
        self.assertEqual(len(self.store.answers(101, batch.batch_id)), 3)

    def test_correct_and_wrong_feedback_has_korean_explanation_and_exact_original_example(self):
        self.save(owner=101)
        self.save(owner=202)
        correct_batch = self.review(owner=101, count=1)
        wrong_batch = self.review(owner=202, count=1)
        right = self.service.answer(101, str(correct_batch.items[0].correct_number), submission_id="answer", now=NOW)
        wrong_number = wrong_batch.items[0].correct_number % 4 + 1
        wrong = self.service.answer(202, str(wrong_number), submission_id="answer", now=NOW)
        self.assertTrue(right.answers[0].correct)
        self.assertFalse(wrong.answers[0].correct)
        for answer in (right.answers[0], wrong.answers[0]):
            self.assertIn(DATA[0][2], answer.explanation_ko)
            self.assertEqual(answer.example, DATA[0][3])
        self.assertEqual(datetime.fromisoformat(right.answers[0].next_due_at), NOW + timedelta(days=1))
        self.assertEqual(datetime.fromisoformat(wrong.answers[0].next_due_at), NOW + timedelta(minutes=10))
        self.assertEqual(self.service.summary(202, now=NOW + timedelta(minutes=10)).due, 1)
        self.assertEqual(self.service.summary(101, now=NOW + timedelta(minutes=10)).due, 0)

    def test_srs_progresses_one_three_seven_days_and_wrong_resets_to_ten_minutes(self):
        saved = self.save()
        clock = NOW
        for index, interval in enumerate((1, 3, 7)):
            batch = self.review(count=1, submission_id=f"review-{index}", now=clock)
            result = self.service.answer(101, str(batch.items[0].correct_number), submission_id=f"answer-{index}", now=clock)
            self.assertEqual(datetime.fromisoformat(result.answers[0].next_due_at), clock + timedelta(days=interval))
            clock += timedelta(days=interval)
        batch = self.review(count=1, submission_id="review-wrong", now=clock)
        self.service.answer(101, str(batch.items[0].correct_number % 4 + 1), submission_id="answer-wrong", now=clock)
        word = self.store.word(101, saved.word.word_id)
        self.assertEqual(word.streak, 0)
        self.assertEqual((word.correct_count, word.wrong_count), (3, 1))
        self.assertEqual(datetime.fromisoformat(word.due_at), clock + timedelta(minutes=10))
        next_batch = self.review(count=1, submission_id="review-recover", now=clock + timedelta(minutes=10))
        recovered = self.service.answer(101, str(next_batch.items[0].correct_number), submission_id="answer-recover", now=clock + timedelta(minutes=10))
        self.assertEqual(datetime.fromisoformat(recovered.answers[0].next_due_at), clock + timedelta(minutes=10, days=1))

    def test_invalid_answer_is_atomic_and_same_message_can_be_corrected(self):
        for index in range(3):
            self.save(index)
        batch = self.review(count=3)
        for text in ("0", "5", "1,2", "1,2,3,4", "one", "1\n2"):
            with self.subTest(text=text), self.assertRaises(AnswerFormatError):
                self.service.answer(101, text, submission_id="answer-message", now=NOW)
        self.assertEqual(self.store.answers(101, batch.batch_id), ())
        self.assertIsNone(self.store.receipt(101, "answer", "answer-message"))
        answers = ",".join(str(item.correct_number) for item in batch.items)
        result = self.service.answer(101, answers, submission_id="answer-message", now=NOW)
        self.assertTrue(all(answer.correct for answer in result.answers))

    def test_completed_batch_reference_cannot_grade_new_pending_review(self):
        self.save()
        old = self.review(count=1)
        self.service.answer(101, str(old.items[0].correct_number), submission_id="old-answer", now=NOW)
        new = self.review(count=1, submission_id="new-review")
        with self.assertRaises(NoActiveVocabError):
            self.service.answer(101, "1", submission_id="new-answer", batch_id=old.batch_id,
                                expected_ordinal=1, now=NOW)
        self.assertEqual(self.store.answers(101, new.batch_id), ())

    def test_exact_prepared_question_delivery_is_persistent_and_idempotent(self):
        self.save()
        batch = self.review(count=1)
        body = f"단어 복습\n회차 ID: {batch.batch_id}\nQ1. liquidity의 문맥상 뜻은?"
        self.assertFalse(self.store.record_question_delivery(101, "101", "501", body))
        self.store.prepare_question(101, batch.batch_id, 1, body)
        self.store.prepare_question(101, batch.batch_id, 1, body)
        self.assertFalse(self.store.record_question_delivery(101, "101", "502", body + " "))
        self.assertFalse(self.store.record_question_delivery(101, "101", "503", "저장 단어 수: 1"))
        self.assertIsNone(self.store.question_delivery(101, "502"))
        self.assertTrue(self.store.record_question_delivery(101, "101", "501", body))
        self.assertTrue(self.store.record_question_delivery(101, 101, 501, body))
        self.assertEqual(self.store.question_delivery(101, "501"), (batch.batch_id, 1))
        self.assertEqual(self.store.connection.execute(
            "SELECT COUNT(*) FROM vocab_question_deliveries WHERE user_id=?", (101,)).fetchone()[0], 1)
        self.store.close()
        self.store = VocabStore(self.path)
        self.service = VocabularyService(self.store)
        self.assertEqual(self.store.question_delivery(101, "501"), (batch.batch_id, 1))
        self.assertTrue(self.store.record_question_delivery(101, "101", "501", body))

    def test_question_receipts_are_owner_scoped_and_private_positive_ids_are_required(self):
        self.save()
        batch = self.review(count=1)
        body = f"{batch.batch_id}\nQ1 단어 복습"
        self.store.prepare_question(101, batch.batch_id, 1, body)
        with self.assertRaises(ValueError):
            self.store.prepare_question(202, batch.batch_id, 1, body)
        self.assertFalse(self.store.record_question_delivery(202, "202", "501", body))
        self.assertIsNone(self.store.question_delivery(202, "501"))
        for chat in ("202", "-101", "00101", True):
            with self.subTest(chat=chat), self.assertRaises(ValueError):
                self.store.record_question_delivery(101, chat, "501", body)
        for message in ("0", "-1", "001", True, "not-message", "1\n"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                self.store.record_question_delivery(101, "101", message, body)
        self.assertTrue(self.store.record_question_delivery(101, "101", "501", body))
        self.assertIsNone(self.store.question_delivery(202, "501"))

    def test_question_was_delivered_requires_exact_owner_batch_and_ordinal_receipt(self):
        self.save()
        self.save(1)
        batch = self.review(count=2)
        body = f"{batch.batch_id}\nQ1 단어 복습"
        self.assertFalse(self.store.question_was_delivered(101, batch.batch_id, 1))
        self.store.prepare_question(101, batch.batch_id, 1, body)
        self.assertFalse(self.store.question_was_delivered(101, batch.batch_id, 1))
        self.assertFalse(self.store.record_question_delivery(101, "101", "501", body + " "))
        self.assertFalse(self.store.question_was_delivered(101, batch.batch_id, 1))
        self.store.record_question_delivery(101, "101", "502", body)
        self.assertTrue(self.store.question_was_delivered(101, batch.batch_id, 1))
        self.assertFalse(self.store.question_was_delivered(202, batch.batch_id, 1))
        self.assertFalse(self.store.question_was_delivered(101, "unknown-batch", 1))
        self.assertFalse(self.store.question_was_delivered(101, batch.batch_id, 2))
        self.store.close()
        self.store = VocabStore(self.path)
        self.service = VocabularyService(self.store)
        self.assertTrue(self.store.question_was_delivered(101, batch.batch_id, 1))
        self.assertFalse(self.store.question_was_delivered(101, batch.batch_id, 2))
        for ordinal in (0, 6, True, "1"):
            with self.subTest(ordinal=ordinal), self.assertRaises(ValueError):
                self.store.question_was_delivered(101, batch.batch_id, ordinal)

    def test_human_review_number_is_persistent_owner_scoped_and_not_clock_based(self):
        self.save()
        first = self.review(count=1)
        self.save(owner=202)
        other = self.review(owner=202, count=1)
        self.assertEqual(first.created_at, other.created_at)
        self.assertEqual(self.store.review_number(101, first.batch_id), 1)
        self.assertEqual(self.store.review_number(202, other.batch_id), 1)
        self.service.answer(101, str(first.items[0].correct_number), submission_id="first-answer", now=NOW)
        second = self.review(count=1, submission_id="review-again")
        self.assertEqual(first.created_at, second.created_at)
        self.assertEqual(self.store.review_number(101, second.batch_id), 2)
        self.assertEqual(self.store.review_number(101, first.batch_id), 1)
        self.assertEqual(self.store.review_number(202, other.batch_id), 1)
        with self.assertRaises(ValueError):
            self.store.review_number(202, second.batch_id)
        with self.assertRaises(ValueError):
            self.store.review_number(101, "unknown-batch")
        self.store.close()
        self.store = VocabStore(self.path)
        self.service = VocabularyService(self.store)
        self.assertEqual(self.store.review_number(101, second.batch_id), 2)
        self.assertEqual(self.store.review_number(101, first.batch_id), 1)

    def test_reply_to_previous_question_cannot_grade_next_pending_question(self):
        self.save()
        self.save(1)
        batch = self.review(count=2)
        first_body = f"{batch.batch_id}\nQ1 단어 복습"
        self.store.prepare_question(101, batch.batch_id, 1, first_body)
        self.store.record_question_delivery(101, "101", "501", first_body)
        reference = self.store.question_delivery(101, "501")
        result = self.service.answer(101, str(batch.items[0].correct_number), submission_id="first-answer",
                                     batch_id=reference[0], expected_ordinal=reference[1], now=NOW)
        self.assertEqual(result.next_item.ordinal, 2)
        second_body = f"정답입니다.\n{batch.batch_id}\nQ2 단어 복습"
        self.store.prepare_question(101, batch.batch_id, 2, second_body)
        self.store.record_question_delivery(101, "101", "502", second_body)
        with self.assertRaisesRegex(ValueError, "old question"):
            self.service.answer(101, "1", submission_id="stale-answer", batch_id=reference[0],
                                expected_ordinal=reference[1], now=NOW)
        self.assertEqual(len(self.store.answers(101, batch.batch_id)), 1)
        self.assertIsNone(self.store.receipt(101, "answer", "stale-answer"))
        self.assertEqual(self.store.next_item(101, batch.batch_id).ordinal, 2)
        second = self.store.question_delivery(101, "502")
        finished = self.service.answer(101, str(batch.items[1].correct_number), submission_id="second-answer",
                                       batch_id=second[0], expected_ordinal=second[1], now=NOW)
        self.assertEqual(finished.batch.status, "completed")

    def test_same_question_receipt_or_prepared_body_cannot_be_remapped(self):
        self.save()
        self.save(1)
        batch = self.review(count=2)
        first_body = f"{batch.batch_id}\nQ1 단어 복습"
        second_body = f"{batch.batch_id}\nQ2 단어 복습"
        self.store.prepare_question(101, batch.batch_id, 1, first_body)
        self.store.record_question_delivery(101, "101", "501", first_body)
        with self.assertRaisesRegex(ValueError, "old question"):
            self.store.prepare_question(101, batch.batch_id, 2, second_body)
        self.service.answer(101, str(batch.items[0].correct_number), submission_id="first-answer", now=NOW)
        self.store.prepare_question(101, batch.batch_id, 2, second_body)
        with self.assertRaisesRegex(ValueError, "cannot be remapped"):
            self.store.record_question_delivery(101, "101", "501", second_body)
        with self.assertRaisesRegex(ValueError, "cannot be remapped"):
            self.store.record_question_delivery(101, "101", "501", "unknown fake body")
        with self.assertRaisesRegex(ValueError, "cannot be remapped"):
            self.store.prepare_question(101, batch.batch_id, 2, first_body)
        self.assertEqual(self.store.question_delivery(101, "501"), (batch.batch_id, 1))
        self.service.answer(101, str(batch.items[1].correct_number), submission_id="second-answer", now=NOW)
        self.assertFalse(self.store.record_question_delivery(101, "101", "504", first_body))
        self.assertTrue(self.store.record_question_delivery(101, "101", "501", first_body))
        new_batch = self.review(count=1, submission_id="new-review")
        with self.assertRaisesRegex(ValueError, "cannot be remapped"):
            self.store.prepare_question(101, new_batch.batch_id, 1, first_body)

    def test_concurrent_replies_to_same_ordinal_grade_only_that_question(self):
        self.save()
        self.save(1)
        batch = self.review(count=2)
        other_store = VocabStore(self.path)
        other = VocabularyService(other_store)
        def attempt(service, submission):
            try:
                return service.answer(101, str(batch.items[0].correct_number), submission_id=submission,
                                      batch_id=batch.batch_id, expected_ordinal=1, now=NOW)
            except ValueError as error:
                return str(error)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(attempt, self.service, "reply-a")
                second = workers.submit(attempt, other, "reply-b")
                results = (first.result(), second.result())
            self.assertEqual(sum(result == "old question" for result in results), 1)
            self.assertEqual(len(self.store.answers(101, batch.batch_id)), 1)
            self.assertEqual(self.store.next_item(101, batch.batch_id).ordinal, 2)
            self.assertEqual(self.service.summary(101, now=NOW).correct_reviews, 1)
        finally:
            other_store.close()

    def test_expected_ordinal_validation_and_submission_replay_do_not_advance_review(self):
        self.save()
        self.save(1)
        batch = self.review(count=2)
        for ordinal in (0, 6, True, "1"):
            with self.subTest(ordinal=ordinal), self.assertRaises(ValueError):
                self.service.answer(101, "1", submission_id="invalid-ordinal", expected_ordinal=ordinal, now=NOW)
        first = self.service.answer(101, str(batch.items[0].correct_number), submission_id="same-message",
                                    expected_ordinal=1, now=NOW)
        repeated = self.service.answer(101, "1", submission_id="same-message", expected_ordinal=1, now=NOW)
        self.assertTrue(repeated.duplicate)
        self.assertEqual(repeated.answers, first.answers)
        self.assertEqual(repeated.next_item.ordinal, 2)
        self.assertEqual(len(self.store.answers(101, batch.batch_id)), 1)

    def test_every_lookup_and_mutation_is_owner_scoped(self):
        saved = self.save()
        batch = self.review(count=1)
        self.assertIsNone(self.store.word(202, saved.word.word_id))
        self.assertIsNone(self.store.batch(202, batch.batch_id))
        self.assertIsNone(self.store.active_batch(202))
        self.assertEqual(self.store.answers(202, batch.batch_id), ())
        self.assertEqual(self.store.list_words(202), ())
        self.assertEqual(self.service.summary(202, now=NOW).total, 0)
        with self.assertRaises(NoActiveVocabError):
            self.service.answer(202, "1", submission_id="wrong-owner", batch_id=batch.batch_id, now=NOW)
        other = self.save(owner=202)
        self.assertNotEqual(other.word.word_id, saved.word.word_id)
        self.assertEqual(len(self.store.list_words(101)), 1)
        self.assertEqual(len(self.store.list_words(202)), 1)

    def test_words_summary_counts_due_reviews_and_pending_and_deduplicates_its_action(self):
        self.save()
        self.save(1)
        self.review(count=2)
        summary = self.service.summary(101, submission_id="words-message", now=NOW)
        self.assertEqual((summary.total, summary.due, summary.pending_count), (2, 2, 2))
        self.save(2)
        repeated = self.service.summary(101, submission_id="words-message", now=NOW)
        self.assertTrue(repeated.duplicate)
        self.assertEqual(repeated.total, 2)
        self.assertEqual(self.service.summary(101, now=NOW).total, 3)
        # Actions have separate receipt namespaces even with the same message ID.
        self.assertTrue(self.save(3, submission_id="words-message").created)

    def test_concurrent_same_submission_save_and_answer_have_one_effect(self):
        other_store = VocabStore(self.path)
        other = VocabularyService(other_store, random.Random(17))
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda service: service.save_word(101, source(), submission_id="same-save", now=NOW),
                                           (self.service, other)))
            self.assertEqual(sum(result.duplicate for result in results), 1)
            self.assertEqual(len(self.store.list_words(101)), 1)
            batch = self.review(count=1)
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda service: service.answer(101, str(batch.items[0].correct_number),
                                           submission_id="same-answer", now=NOW), (self.service, other)))
            self.assertEqual(sum(result.duplicate for result in results), 1)
            self.assertEqual(len(self.store.answers(101, batch.batch_id)), 1)
            self.assertEqual(self.store.list_words(101)[0].correct_count, 1)
        finally:
            other_store.close()

    def test_concurrent_review_commands_create_only_one_pending_batch(self):
        for index in range(3):
            self.save(index)
        other_store = VocabStore(self.path)
        other = VocabularyService(other_store)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(self.service.review, 101, 3, submission_id="review-a", grounded_choices=choices(), now=NOW)
                second = workers.submit(other.review, 101, 3, submission_id="review-b", grounded_choices=choices(), now=NOW)
                batches = (first.result(), second.result())
            self.assertEqual(batches[0].batch_id, batches[1].batch_id)
            self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM vocab_batches WHERE user_id=?", (101,)).fetchone()[0], 1)
        finally:
            other_store.close()

    def test_source_requires_real_occurrence_korean_meaning_and_official_link(self):
        for changes in ({"sentence": "This unrelated English sentence has no target term."},
                        {"meaning_ko": "invented English meaning"}, {"article_url": "https://attacker.invalid/article"},
                        {"published_at": "unverified-date"}, {"term": "liquidity; execute"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.save(submission_id="invalid-source", **changes)
        self.assertEqual(self.store.list_words(101), ())
        self.assertIsNone(self.store.receipt(101, "save_word", "invalid-source"))

    def test_invalid_owner_submission_count_and_naive_clock_fail_without_effect(self):
        for owner in (0, -1, True, "101"):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                self.service.save_word(owner, source(), submission_id="invalid", now=NOW)
        for submission in ("", "\n", "x" * 201, None):
            with self.subTest(submission=submission), self.assertRaises(ValueError):
                self.service.save_word(101, source(), submission_id=submission, now=NOW)
        for count in (0, 6, True, "5"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.review(count=count)
        with self.assertRaises(ValueError):
            self.save(now=NOW.replace(tzinfo=None))
        self.assertEqual(self.store.list_words(101), ())

    def test_schema_and_snapshots_are_separate_immutable_and_exportable(self):
        self.save()
        batch = self.review(count=1)
        self.assertEqual({row[0] for row in self.store.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}, TABLES)
        self.assertEqual(self.store.connection.execute("PRAGMA application_id").fetchone()[0], APPLICATION_ID)
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as connection:
            connection.execute("UPDATE vocab_words SET source_json='{}' WHERE user_id=?", (101,))
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as connection:
            connection.execute("UPDATE vocab_items SET snapshot_json='{}' WHERE user_id=? AND batch_id=?", (101, batch.batch_id))
        exported = self.service.export_words(101)
        self.assertEqual(exported[0].source.sentence, DATA[0][3])
        self.assertEqual(self.store.active_batch(101).items, batch.items)


class VocabularyDatabaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="findone-vocab-safety-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_learning_database_is_rejected_byte_for_byte_without_migration(self):
        path = self.directory / "learning.sqlite3"
        with StateStore(path) as learning:
            learning.claim_job(101, "news", "2026-10-03", "08:00", now=NOW)
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            VocabStore(path)
        self.assertEqual(path.read_bytes(), before)

    def test_unrelated_or_future_schema_is_rejected_before_changes(self):
        for version in (0, 99):
            path = self.directory / f"unrelated-{version}.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE notes(note TEXT)")
            connection.execute("INSERT INTO notes VALUES ('preserve this')")
            connection.execute(f"PRAGMA user_version={version}")
            connection.commit()
            connection.close()
            before = path.read_bytes()
            with self.subTest(version=version), self.assertRaises(ValueError):
                VocabStore(path)
            self.assertEqual(path.read_bytes(), before)

    def test_concurrent_first_use_publishes_one_complete_schema(self):
        for attempt in range(4):
            path = self.directory / f"concurrent-{attempt}.sqlite3"
            barrier = threading.Barrier(4)
            def initialize(owner):
                barrier.wait(timeout=10)
                with VocabStore(path) as store:
                    VocabularyService(store).save_word(owner, source(),
                                                       submission_id="first-save", now=NOW)
                    return store.connection.execute("PRAGMA application_id").fetchone()[0]
            with ThreadPoolExecutor(max_workers=4) as workers:
                identities = list(workers.map(initialize, (101, 202, 303, 404)))
            self.assertEqual(identities, [APPLICATION_ID] * 4)
            with VocabStore(path) as store:
                self.assertEqual({row[0] for row in store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}, TABLES)
                self.assertEqual(store.connection.execute("PRAGMA user_version").fetchone()[0], 1)
                for owner in (101, 202, 303, 404):
                    self.assertEqual(len(store.list_words(owner)), 1)

    def test_interrupted_initialization_rolls_back_all_ddl_and_can_retry(self):
        path = self.directory / "interrupted.sqlite3"
        broken = SCHEMA.replace("CREATE TABLE IF NOT EXISTS vocab_items", "CREATE INVALID vocab_items")
        with patch("findone_hermes.vocab_state.SCHEMA", broken), self.assertRaises(sqlite3.OperationalError):
            VocabStore(path)
        connection = sqlite3.connect(path)
        try:
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(connection.execute("PRAGMA application_id").fetchone()[0], 0)
        finally:
            connection.close()
        with VocabStore(path) as store:
            self.assertEqual(store.connection.execute("PRAGMA application_id").fetchone()[0], APPLICATION_ID)
            self.assertEqual(store.list_words(101), ())

    def test_relative_repository_and_symlink_into_repository_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            VocabStore("relative-vocabulary.sqlite3")
        target = ROOT / "hermes_telegram" / "must-not-create-vocabulary.sqlite3"
        with self.assertRaises(ValueError):
            VocabStore(target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
