"""Contextual news vocabulary and deterministic four-choice spaced review.

The caller supplies verified, published word meanings and their exact original
sentences. This service never generates meanings, examples, or distractors with
a model. Every operation and persisted receipt is scoped to one numeric owner.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta
import json
import random
import re
from typing import Sequence
import unicodedata
import uuid

from .news import normalize_url, parse_publication
from .state import timestamp, utc_time
from .vocab_state import (
    AnswerResult, MeaningChoice, SaveResult, SavedWord, VocabAnswer, VocabBatch,
    VocabItem, VocabOption, VocabStore, VocabularySource, WordSummary,
    validate_submission_id, validate_user_id,
)


class AnswerFormatError(ValueError):
    pass


class NoActiveVocabError(ValueError):
    pass


SRS_DAYS = (1, 3, 7, 14, 30, 60)
WRONG_REVIEW_DELAY = timedelta(minutes=10)
_DASHES = "-\u2010\u2011\u2012\u2013\u2014"
_APOSTROPHES = "'\u2018\u2019\u02bc"
_ENGLISH_PUNCTUATION = str.maketrans({**{char: "-" for char in _DASHES},
                                   **{char: "'" for char in _APOSTROPHES}})


def english_key(value: str) -> str:
    """Canonical identity only; never normalize the stored original surface."""
    return " ".join(unicodedata.normalize("NFKC", value).translate(_ENGLISH_PUNCTUATION).casefold().split())


def english_term_pattern(value: str) -> re.Pattern[str]:
    """Match English source spelling with common typographic punctuation."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 80
            or not re.fullmatch(r"[A-Za-z][A-Za-z \u00a0\u202f" + re.escape(_DASHES + _APOSTROPHES) + r"]*", value)):
        raise ValueError("Vocabulary terms must be bounded English text")
    pieces = []
    for char in english_key(value):
        if char == "-":
            pieces.append("[" + re.escape(_DASHES) + "]")
        elif char == "'":
            pieces.append("[" + re.escape(_APOSTROPHES) + "]")
        elif char == " ":
            pieces.append(r"[^\S\r\n]+")
        else:
            pieces.append(re.escape(char))
    return re.compile(r"(?<![A-Za-z])" + "".join(pieces) + r"(?![A-Za-z])", re.I)


def _text(value: str, limit: int, *, korean: bool = False) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 and char not in "\n\t\r" for char in value)):
        raise ValueError("Invalid vocabulary source text")
    cleaned = value.strip()
    if korean and (not re.search(r"[가-힣]", cleaned) or re.search(r"https?://|www\.", cleaned, re.I)):
        raise ValueError("A bounded Korean vocabulary meaning is required")
    return cleaned


def _key(value: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value).casefold())


def validated_source(source: VocabularySource) -> VocabularySource:
    """Validate supplied evidence without inventing or translating any content."""
    if not isinstance(source, VocabularySource):
        raise ValueError("A verified vocabulary source record is required")
    term = _text(source.term, 80)
    english_term_pattern(term)
    lemma = english_key(_text(source.lemma, 80))
    english_term_pattern(lemma)
    sentence = _text(source.sentence, 1600)
    if not english_term_pattern(term).search(sentence):
        raise ValueError("Vocabulary term is absent from its source sentence")
    sense = " ".join(_text(source.sense, 200).casefold().split())
    meaning = _text(source.meaning_ko, 200, korean=True)
    if isinstance(source.published_at, datetime):
        published = utc_time(source.published_at).isoformat()
    else:
        published = utc_time(parse_publication(_text(source.published_at, 100))).isoformat()
    explanation = _text(source.explanation_ko, 800, korean=True) if source.explanation_ko else ""
    return VocabularySource(term, lemma, sense, meaning, sentence, normalize_url(source.article_url),
                            _text(source.article_title, 500), _text(source.article_id, 160),
                            _text(source.source_name, 100), published, explanation)


def _validated_choice(choice: MeaningChoice) -> MeaningChoice | None:
    """Accept only finite, provenance-labelled choices supplied by the caller."""
    if not isinstance(choice, MeaningChoice):
        return None
    try:
        meaning = _text(choice.meaning_ko, 200, korean=True)
        term = _text(choice.term, 80) if choice.term else ""
        url = normalize_url(choice.article_url) if choice.article_url else ""
        source_id = _text(choice.source_id, 160) if choice.source_id else ""
        if not url and not source_id:
            return None
        return MeaningChoice(meaning, term, url, source_id)
    except ValueError:
        return None


def _answer_numbers(text: str, remaining: int) -> tuple[int, ...]:
    if not isinstance(text, str) or not re.fullmatch(r"[1-4](?:\s*,\s*[1-4])*", text.strip()):
        raise AnswerFormatError("Answer with a number from 1 to 4 or comma-separated remaining answers")
    numbers = tuple(int(part.strip()) for part in text.strip().split(","))
    if len(numbers) not in {1, remaining}:
        raise AnswerFormatError("Provide one answer or one answer for each remaining question")
    return numbers


class VocabularyService:
    def __init__(self, store: VocabStore, rng=None):
        self.store = store
        self.random = rng if rng is not None else random.SystemRandom()

    def save_word(self, user_id: int, source: VocabularySource, *, submission_id: str,
                  now: datetime | None = None) -> SaveResult:
        validate_user_id(user_id)
        validate_submission_id(submission_id)
        stamp = timestamp(now)
        with self.store.transaction() as connection:
            receipt = self.store.receipt(user_id, "save_word", submission_id)
            if receipt is not None:
                word = self.store.word(user_id, receipt["word_id"])
                if word is None:
                    raise ValueError("Vocabulary receipt has no source snapshot")
                return SaveResult(word, receipt["created"], duplicate=True)
            source = validated_source(source)
            row = connection.execute("""SELECT word_id FROM vocab_words
                WHERE user_id=? AND lemma=? AND article_url=? AND sense=?""",
                (user_id, source.lemma, source.article_url, source.sense)).fetchone()
            created = row is None
            word_id = uuid.uuid4().hex if created else row[0]
            if created:
                connection.execute("""INSERT INTO vocab_words
                    (user_id,word_id,lemma,article_url,sense,source_json,saved_at,last_seen_at,due_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (user_id, word_id, source.lemma, source.article_url, source.sense,
                     json.dumps(asdict(source), ensure_ascii=False), stamp, stamp, stamp))
            else:
                # Refresh only the owner's explicit encounter. Never replace the
                # meaning/example snapshot or reset review counts and due dates.
                connection.execute("UPDATE vocab_words SET last_seen_at=? WHERE user_id=? AND word_id=?",
                                   (stamp, user_id, word_id))
            self.store.put_receipt(user_id, "save_word", submission_id,
                                   {"word_id": word_id, "created": created}, stamp)
            word = self.store.word(user_id, word_id)
            return SaveResult(word, created)

    def _choices(self, source: VocabularySource, pool: Sequence[MeaningChoice]) -> tuple[VocabOption, ...] | None:
        correct = MeaningChoice(source.meaning_ko, source.term, source.article_url, source.article_id)
        distractors, seen = [], {_key(correct.meaning_ko)}
        for value in pool:
            choice = _validated_choice(value)
            if choice is None or _key(choice.meaning_ko) in seen:
                continue
            # Other senses of the same lemma can overlap semantically. Use other
            # verified words/concepts rather than manufacture a distinction.
            if choice.term and _key(choice.term) in {_key(source.term), _key(source.lemma)}:
                continue
            seen.add(_key(choice.meaning_ko))
            distractors.append(choice)
        if len(distractors) < 3:
            return None
        selected = self.random.sample(distractors, 3) + [correct]
        self.random.shuffle(selected)
        return tuple(VocabOption(index, choice.meaning_ko, choice.term, choice.article_url, choice.source_id)
                     for index, choice in enumerate(selected, 1))

    def review(self, user_id: int, count: int = 5, *, submission_id: str,
               grounded_choices: Sequence[MeaningChoice] = (),
               now: datetime | None = None) -> VocabBatch | None:
        validate_user_id(user_id)
        validate_submission_id(submission_id)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 5:
            raise ValueError("Vocabulary review count must be 1 to 5")
        stamp = timestamp(now)
        with self.store.transaction() as connection:
            receipt = self.store.receipt(user_id, "review", submission_id)
            if receipt is not None:
                batch = self.store.batch(user_id, receipt["batch_id"]) if receipt["batch_id"] else None
                return replace(batch, duplicate=True) if batch else None
            active = self.store.active_batch(user_id)
            if active is not None:
                self.store.put_receipt(user_id, "review", submission_id, {"batch_id": active.batch_id}, stamp)
                return active
            words = sorted(self.store.list_words(user_id), key=lambda word: (
                word.due_at > stamp, word.due_at, -word.wrong_count, word.saved_at, word.word_id))
            own_choices = [MeaningChoice(word.source.meaning_ko, word.source.term,
                                          word.source.article_url, word.source.article_id) for word in words]
            pool = tuple(own_choices) + tuple(grounded_choices)
            items = []
            for word in words:
                choices = self._choices(word.source, pool)
                if choices is None:
                    continue
                correct = next(choice.number for choice in choices
                               if _key(choice.meaning_ko) == _key(word.source.meaning_ko))
                items.append(VocabItem(len(items) + 1, word.word_id, word.source, choices, correct))
                if len(items) == count:
                    break
            if not items:
                self.store.put_receipt(user_id, "review", submission_id, {"batch_id": None}, stamp)
                return None
            batch_id = "V-" + uuid.uuid4().hex[:12]
            connection.execute("""INSERT INTO vocab_batches
                (user_id,batch_id,status,created_at) VALUES (?,?,'active',?)""", (user_id, batch_id, stamp))
            connection.executemany("""INSERT INTO vocab_items
                (user_id,batch_id,ordinal,word_id,snapshot_json) VALUES (?,?,?,?,?)""",
                [(user_id, batch_id, item.ordinal, item.word_id, json.dumps(asdict(item), ensure_ascii=False))
                 for item in items])
            self.store.put_receipt(user_id, "review", submission_id, {"batch_id": batch_id}, stamp)
            return self.store.batch(user_id, batch_id)

    def answer(self, user_id: int, answer_text: str, *, submission_id: str,
               batch_id: str | None = None, expected_ordinal: int | None = None,
               now: datetime | None = None) -> AnswerResult:
        validate_user_id(user_id)
        validate_submission_id(submission_id)
        if expected_ordinal is not None and (isinstance(expected_ordinal, bool)
                or not isinstance(expected_ordinal, int) or not 1 <= expected_ordinal <= 5):
            raise ValueError("A vocabulary question ordinal from 1 to 5 is required")
        clock = utc_time(now)
        stamp = timestamp(clock)
        with self.store.transaction() as connection:
            receipt = self.store.receipt(user_id, "answer", submission_id)
            if receipt is not None:
                batch = self.store.batch(user_id, receipt["batch_id"])
                if batch is None:
                    raise ValueError("Vocabulary receipt has no quiz snapshot")
                answers = tuple(answer for answer in self.store.answers(user_id, batch.batch_id)
                                if answer.ordinal in receipt["ordinals"])
                return AnswerResult(batch, answers, self.store.next_item(user_id, batch.batch_id), duplicate=True)
            batch = self.store.batch(user_id, batch_id) if batch_id is not None else self.store.active_batch(user_id)
            if batch is None or batch.status != "active":
                raise NoActiveVocabError("No active vocabulary review belongs to this owner")
            graded = {answer.ordinal for answer in self.store.answers(user_id, batch.batch_id)}
            remaining = [item for item in batch.items if item.ordinal not in graded]
            if not remaining:
                raise NoActiveVocabError("No unanswered vocabulary question remains")
            # Compare while holding the same write transaction as grading. A
            # receipt for Q1 can never advance Q2, even with concurrent replies.
            if expected_ordinal is not None and remaining[0].ordinal != expected_ordinal:
                raise ValueError("old question")
            numbers = _answer_numbers(answer_text, len(remaining))
            targets = remaining[:1] if len(numbers) == 1 else remaining
            new_answers = []
            for item, number in zip(targets, numbers):
                word = self.store.word(user_id, item.word_id)
                if word is None:
                    raise ValueError("Vocabulary quiz has no saved word snapshot")
                correct = number == item.correct_number
                streak = word.streak + 1 if correct else 0
                delay = timedelta(days=SRS_DAYS[min(streak, len(SRS_DAYS)) - 1]) if correct else WRONG_REVIEW_DELAY
                next_due = timestamp(clock + delay)
                explanation = f"문맥상 뜻: {item.source.meaning_ko}."
                if item.source.explanation_ko:
                    explanation += "\n" + item.source.explanation_ko
                connection.execute("""INSERT INTO vocab_answers
                    (user_id,batch_id,ordinal,chosen_number,correct,submitted_at,next_due_at,explanation_ko,example)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (user_id, batch.batch_id, item.ordinal, number, int(correct),
                    stamp, next_due, explanation, item.source.sentence))
                connection.execute("""UPDATE vocab_words SET due_at=?,last_review_at=?,last_seen_at=?,streak=?,
                    correct_count=correct_count+?,wrong_count=wrong_count+? WHERE user_id=? AND word_id=?""",
                    (next_due, stamp, stamp, streak, int(correct), int(not correct), user_id, item.word_id))
                new_answers.append(VocabAnswer(item.ordinal, number, correct, stamp, next_due,
                                               explanation, item.source.sentence))
            if len(graded) + len(new_answers) == len(batch.items):
                connection.execute("""UPDATE vocab_batches SET status='completed',completed_at=?
                    WHERE user_id=? AND batch_id=?""", (stamp, user_id, batch.batch_id))
            self.store.put_receipt(user_id, "answer", submission_id,
                                   {"batch_id": batch.batch_id, "ordinals": [answer.ordinal for answer in new_answers]}, stamp)
            result_batch = self.store.batch(user_id, batch.batch_id)
            return AnswerResult(result_batch, tuple(new_answers), self.store.next_item(user_id, batch.batch_id))

    def summary(self, user_id: int, *, submission_id: str | None = None,
                now: datetime | None = None) -> WordSummary:
        validate_user_id(user_id)
        if submission_id is not None:
            validate_submission_id(submission_id)
        stamp = timestamp(now)
        with self.store.transaction() as connection:
            if submission_id is not None:
                receipt = self.store.receipt(user_id, "summary", submission_id)
                if receipt is not None:
                    return WordSummary(**receipt, duplicate=True)
            row = connection.execute("""SELECT COUNT(*) AS total,
                COALESCE(SUM(due_at <= ?),0) AS due, COALESCE(SUM(correct_count),0) AS correct_reviews,
                COALESCE(SUM(wrong_count),0) AS wrong_reviews FROM vocab_words WHERE user_id=?""",
                (stamp, user_id)).fetchone()
            active = self.store.active_batch(user_id)
            pending = len(active.items) - len(self.store.answers(user_id, active.batch_id)) if active else 0
            result = WordSummary(row["total"], row["due"], row["correct_reviews"], row["wrong_reviews"], pending)
            if submission_id is not None:
                self.store.put_receipt(user_id, "summary", submission_id,
                                       {key: value for key, value in asdict(result).items() if key != "duplicate"}, stamp)
            return result

    def export_words(self, user_id: int) -> tuple[SavedWord, ...]:
        return self.store.list_words(user_id)
