"""Separate private vocabulary storage with immutable context snapshots.

No FinDone learning or news-delivery tables are opened or migrated here. Existing
unrelated SQLite files are rejected before persistent metadata or schema changes.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import re
import threading
from typing import Any, Iterator

from .state import timestamp


@dataclass(frozen=True)
class VocabularySource:
    term: str
    lemma: str
    sense: str
    meaning_ko: str
    sentence: str
    article_url: str
    article_title: str
    article_id: str
    source_name: str
    published_at: str
    explanation_ko: str = ""


@dataclass(frozen=True)
class MeaningChoice:
    meaning_ko: str
    term: str = ""
    article_url: str = ""
    source_id: str = ""


@dataclass(frozen=True)
class SavedWord:
    word_id: str
    user_id: int
    source: VocabularySource
    saved_at: str
    last_seen_at: str
    due_at: str
    last_review_at: str | None
    streak: int
    correct_count: int
    wrong_count: int


@dataclass(frozen=True)
class VocabOption:
    number: int
    meaning_ko: str
    term: str
    article_url: str
    source_id: str


@dataclass(frozen=True)
class VocabItem:
    ordinal: int
    word_id: str
    source: VocabularySource
    choices: tuple[VocabOption, ...]
    correct_number: int


@dataclass(frozen=True)
class VocabBatch:
    batch_id: str
    user_id: int
    status: str
    created_at: str
    completed_at: str | None
    items: tuple[VocabItem, ...]
    duplicate: bool = False


@dataclass(frozen=True)
class VocabAnswer:
    ordinal: int
    chosen_number: int
    correct: bool
    submitted_at: str
    next_due_at: str
    explanation_ko: str
    example: str


@dataclass(frozen=True)
class AnswerResult:
    batch: VocabBatch
    answers: tuple[VocabAnswer, ...]
    next_item: VocabItem | None = None
    duplicate: bool = False


@dataclass(frozen=True)
class SaveResult:
    word: SavedWord
    created: bool
    duplicate: bool = False


@dataclass(frozen=True)
class WordSummary:
    total: int
    due: int
    correct_reviews: int
    wrong_reviews: int
    pending_count: int
    duplicate: bool = False


APPLICATION_ID = 0x46445642  # FDVB: FinDone Vocabulary
TABLES = {"vocab_words", "vocab_batches", "vocab_items", "vocab_answers", "vocab_submissions",
          "vocab_prepared_questions", "vocab_question_deliveries"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS vocab_words (
    user_id INTEGER NOT NULL CHECK(user_id > 0), word_id TEXT NOT NULL,
    lemma TEXT NOT NULL, article_url TEXT NOT NULL, sense TEXT NOT NULL,
    source_json TEXT NOT NULL,
    saved_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, due_at TEXT NOT NULL,
    last_review_at TEXT, streak INTEGER NOT NULL DEFAULT 0 CHECK(streak >= 0),
    correct_count INTEGER NOT NULL DEFAULT 0 CHECK(correct_count >= 0),
    wrong_count INTEGER NOT NULL DEFAULT 0 CHECK(wrong_count >= 0),
    PRIMARY KEY(user_id,word_id), UNIQUE(user_id,lemma,article_url,sense)
);
CREATE TABLE IF NOT EXISTS vocab_batches (
    user_id INTEGER NOT NULL CHECK(user_id > 0), batch_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','completed')),
    created_at TEXT NOT NULL, completed_at TEXT,
    PRIMARY KEY(user_id,batch_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_vocab_batch
    ON vocab_batches(user_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS vocab_items (
    user_id INTEGER NOT NULL, batch_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    word_id TEXT NOT NULL, snapshot_json TEXT NOT NULL,
    PRIMARY KEY(user_id,batch_id,ordinal),
    FOREIGN KEY(user_id,batch_id) REFERENCES vocab_batches(user_id,batch_id),
    FOREIGN KEY(user_id,word_id) REFERENCES vocab_words(user_id,word_id)
);
CREATE TABLE IF NOT EXISTS vocab_answers (
    user_id INTEGER NOT NULL, batch_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    chosen_number INTEGER NOT NULL CHECK(chosen_number BETWEEN 1 AND 4),
    correct INTEGER NOT NULL CHECK(correct IN (0,1)), submitted_at TEXT NOT NULL,
    next_due_at TEXT NOT NULL, explanation_ko TEXT NOT NULL, example TEXT NOT NULL,
    PRIMARY KEY(user_id,batch_id,ordinal),
    FOREIGN KEY(user_id,batch_id,ordinal) REFERENCES vocab_items(user_id,batch_id,ordinal)
);
CREATE TABLE IF NOT EXISTS vocab_submissions (
    user_id INTEGER NOT NULL CHECK(user_id > 0), action TEXT NOT NULL,
    submission_id TEXT NOT NULL, result_json TEXT NOT NULL, submitted_at TEXT NOT NULL,
    PRIMARY KEY(user_id,action,submission_id)
);
CREATE TABLE IF NOT EXISTS vocab_prepared_questions (
    user_id INTEGER NOT NULL, body_sha256 TEXT NOT NULL,
    batch_id TEXT NOT NULL, ordinal INTEGER NOT NULL, prepared_at TEXT NOT NULL,
    PRIMARY KEY(user_id,body_sha256),
    FOREIGN KEY(user_id,batch_id,ordinal) REFERENCES vocab_items(user_id,batch_id,ordinal)
);
CREATE TABLE IF NOT EXISTS vocab_question_deliveries (
    user_id INTEGER NOT NULL, chat_id TEXT NOT NULL, message_id TEXT NOT NULL,
    body_sha256 TEXT NOT NULL, batch_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY(user_id,message_id),
    FOREIGN KEY(user_id,body_sha256) REFERENCES vocab_prepared_questions(user_id,body_sha256),
    FOREIGN KEY(user_id,batch_id,ordinal) REFERENCES vocab_items(user_id,batch_id,ordinal)
);
CREATE INDEX IF NOT EXISTS user_vocab_due ON vocab_words(user_id,due_at);
CREATE TRIGGER IF NOT EXISTS immutable_vocab_source
    BEFORE UPDATE OF source_json ON vocab_words BEGIN
    SELECT RAISE(ABORT,'Vocabulary source snapshots are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_vocab_item
    BEFORE UPDATE OF snapshot_json ON vocab_items BEGIN
    SELECT RAISE(ABORT,'Vocabulary quiz snapshots are immutable'); END;
PRAGMA user_version=1;
"""


def validate_user_id(user_id: int) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or not 0 < user_id < 2**63:
        raise ValueError("A positive numeric vocabulary owner is required")
    return user_id


def validate_submission_id(submission_id: str) -> str:
    if (not isinstance(submission_id, str) or not submission_id.strip()
            or len(submission_id) > 200 or any(ord(char) < 32 for char in submission_id)):
        raise ValueError("A persistent vocabulary submission ID is required")
    return submission_id


def _positive_message_id(message_id: str | int) -> str:
    value = str(message_id)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ValueError("A positive numeric question message ID is required")
    return value


def _question_hash(text: str) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
        raise ValueError("An exact bounded prepared question body is required")
    # No whitespace or Unicode normalization: only the prepared outbound body
    # can establish the receipt's binding to a particular question.
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source(value: dict[str, Any]) -> VocabularySource:
    return VocabularySource(**value)


def _word(row: sqlite3.Row) -> SavedWord:
    return SavedWord(row["word_id"], row["user_id"], _source(json.loads(row["source_json"])),
                     row["saved_at"], row["last_seen_at"], row["due_at"], row["last_review_at"],
                     row["streak"], row["correct_count"], row["wrong_count"])


class VocabStore:
    def __init__(self, path: str | Path):
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            raise ValueError("Vocabulary state requires an absolute external path")
        self.path = candidate.resolve()
        if any((ancestor / ".git").exists() for ancestor in (self.path, *self.path.parents)):
            raise ValueError("Vocabulary state must be outside Git repositories")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        try:
            self.connection.execute("PRAGMA foreign_keys=ON")
            # Serialize first use before inspecting schema metadata. DDL and
            # identity must become visible together, including to other processes.
            # executescript would implicitly commit this transaction.
            with self.transaction() as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                application = connection.execute("PRAGMA application_id").fetchone()[0]
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                if version not in (0, 1):
                    raise ValueError("Unsupported vocabulary schema version")
                if (version == 0 and (tables or application not in (0, APPLICATION_ID))
                        or version == 1 and (tables != TABLES or application != APPLICATION_ID)):
                    raise ValueError("Existing database is not FinDone vocabulary state")
                statement = ""
                for line in SCHEMA.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ""
                if statement.strip():
                    raise ValueError("Incomplete vocabulary schema")
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        except BaseException:
            self.connection.close()
            raise

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def word(self, user_id: int, word_id: str) -> SavedWord | None:
        validate_user_id(user_id)
        with self._lock:
            row = self.connection.execute("SELECT * FROM vocab_words WHERE user_id=? AND word_id=?",
                                          (user_id, word_id)).fetchone()
            return _word(row) if row else None

    def list_words(self, user_id: int) -> tuple[SavedWord, ...]:
        validate_user_id(user_id)
        with self._lock:
            return tuple(_word(row) for row in self.connection.execute(
                "SELECT * FROM vocab_words WHERE user_id=? ORDER BY saved_at,word_id", (user_id,)))

    def batch(self, user_id: int, batch_id: str) -> VocabBatch | None:
        validate_user_id(user_id)
        with self._lock:
            row = self.connection.execute("SELECT * FROM vocab_batches WHERE user_id=? AND batch_id=?",
                                          (user_id, batch_id)).fetchone()
            if row is None:
                return None
            items = []
            for item in self.connection.execute(
                    "SELECT snapshot_json FROM vocab_items WHERE user_id=? AND batch_id=? ORDER BY ordinal",
                    (user_id, batch_id)):
                value = json.loads(item[0])
                value["source"] = _source(value["source"])
                value["choices"] = tuple(VocabOption(**choice) for choice in value["choices"])
                items.append(VocabItem(**value))
            return VocabBatch(row["batch_id"], row["user_id"], row["status"], row["created_at"],
                              row["completed_at"], tuple(items))

    def active_batch(self, user_id: int) -> VocabBatch | None:
        validate_user_id(user_id)
        with self._lock:
            row = self.connection.execute("SELECT batch_id FROM vocab_batches WHERE user_id=? AND status='active'",
                                          (user_id,)).fetchone()
            return self.batch(user_id, row[0]) if row else None

    def answers(self, user_id: int, batch_id: str) -> tuple[VocabAnswer, ...]:
        validate_user_id(user_id)
        with self._lock:
            return tuple(VocabAnswer(row["ordinal"], row["chosen_number"], bool(row["correct"]),
                                     row["submitted_at"], row["next_due_at"], row["explanation_ko"], row["example"])
                         for row in self.connection.execute(
                             "SELECT * FROM vocab_answers WHERE user_id=? AND batch_id=? ORDER BY ordinal",
                             (user_id, batch_id)))

    def next_item(self, user_id: int, batch_id: str) -> VocabItem | None:
        batch = self.batch(user_id, batch_id)
        if batch is None or batch.status != "active":
            return None
        answered = {answer.ordinal for answer in self.answers(user_id, batch_id)}
        return next((item for item in batch.items if item.ordinal not in answered), None)

    def prepare_question(self, user_id: int, batch_id: str, ordinal: int, text: str) -> None:
        validate_user_id(user_id)
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 1 <= ordinal <= 5:
            raise ValueError("A vocabulary question ordinal from 1 to 5 is required")
        digest = _question_hash(text)
        with self.transaction() as connection:
            existing = connection.execute("""SELECT batch_id,ordinal FROM vocab_prepared_questions
                WHERE user_id=? AND body_sha256=?""", (user_id, digest)).fetchone()
            if existing is not None and (existing[0], existing[1]) != (batch_id, ordinal):
                raise ValueError("A prepared question body cannot be remapped")
            item = self.next_item(user_id, batch_id)
            if item is None or item.ordinal != ordinal:
                raise ValueError("old question")
            if existing is None:
                connection.execute("""INSERT INTO vocab_prepared_questions
                    (user_id,body_sha256,batch_id,ordinal,prepared_at) VALUES (?,?,?,?,?)""",
                    (user_id, digest, batch_id, ordinal, timestamp()))

    def record_question_delivery(self, user_id: int, chat_id: str | int,
                                 message_id: str | int, text: str) -> bool:
        validate_user_id(user_id)
        if str(chat_id) != str(user_id):
            raise ValueError("Question delivery must target the owner's private chat")
        message = _positive_message_id(message_id)
        digest = _question_hash(text)
        with self.transaction() as connection:
            existing = connection.execute("""SELECT body_sha256 FROM vocab_question_deliveries
                WHERE user_id=? AND message_id=?""", (user_id, message)).fetchone()
            if existing is not None:
                if existing[0] != digest:
                    raise ValueError("A question delivery receipt cannot be remapped")
                return True
            prepared = connection.execute("""SELECT p.batch_id,p.ordinal
                FROM vocab_prepared_questions p JOIN vocab_batches b
                ON b.user_id=p.user_id AND b.batch_id=p.batch_id
                WHERE p.user_id=? AND p.body_sha256=? AND b.status='active'""",
                (user_id, digest)).fetchone()
            if prepared is None:
                return False
            connection.execute("""INSERT INTO vocab_question_deliveries
                (user_id,chat_id,message_id,body_sha256,batch_id,ordinal,recorded_at) VALUES (?,?,?,?,?,?,?)""",
                (user_id, str(chat_id), message, digest, prepared[0], prepared[1], timestamp()))
            return True

    def question_delivery(self, user_id: int, message_id: str | int) -> tuple[str, int] | None:
        validate_user_id(user_id)
        message = _positive_message_id(message_id)
        with self._lock:
            row = self.connection.execute("""SELECT batch_id,ordinal FROM vocab_question_deliveries
                WHERE user_id=? AND message_id=?""", (user_id, message)).fetchone()
            return (row[0], row[1]) if row is not None else None

    def question_was_delivered(self, user_id: int, batch_id: str, ordinal: int) -> bool:
        """A prepared body alone does not make its question answerable."""
        validate_user_id(user_id)
        if (not isinstance(batch_id, str) or not batch_id.strip() or len(batch_id) > 200
                or isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 1 <= ordinal <= 5):
            raise ValueError("A specific vocabulary question is required")
        with self._lock:
            row = self.connection.execute("""SELECT 1 FROM vocab_question_deliveries d
                JOIN vocab_prepared_questions p ON p.user_id=d.user_id
                AND p.body_sha256=d.body_sha256 AND p.batch_id=d.batch_id AND p.ordinal=d.ordinal
                WHERE d.user_id=? AND d.chat_id=? AND d.batch_id=? AND d.ordinal=? LIMIT 1""",
                (user_id, str(user_id), batch_id, ordinal)).fetchone()
            return row is not None

    def review_number(self, user_id: int, batch_id: str) -> int:
        """Stable human review number within this owner's append-only history."""
        validate_user_id(user_id)
        if not isinstance(batch_id, str) or not batch_id.strip() or len(batch_id) > 200:
            raise ValueError("A specific vocabulary review is required")
        with self._lock:
            row = self.connection.execute("""SELECT
                (SELECT COUNT(*) FROM vocab_batches previous
                 WHERE previous.user_id=b.user_id AND previous.rowid<=b.rowid)
                FROM vocab_batches b WHERE b.user_id=? AND b.batch_id=?""",
                (user_id, batch_id)).fetchone()
            if row is None:
                raise ValueError("Vocabulary review does not belong to this owner")
            return row[0]

    def receipt(self, user_id: int, action: str, submission_id: str) -> dict[str, Any] | None:
        validate_user_id(user_id)
        validate_submission_id(submission_id)
        with self._lock:
            row = self.connection.execute(
                "SELECT result_json FROM vocab_submissions WHERE user_id=? AND action=? AND submission_id=?",
                (user_id, action, submission_id)).fetchone()
            return json.loads(row[0]) if row else None

    def put_receipt(self, user_id: int, action: str, submission_id: str,
                    result: dict[str, Any], submitted_at: str) -> None:
        """Call within a transaction that includes the corresponding operation."""
        validate_user_id(user_id)
        validate_submission_id(submission_id)
        self.connection.execute("""INSERT INTO vocab_submissions
            (user_id,action,submission_id,result_json,submitted_at) VALUES (?,?,?,?,?)""",
            (user_id, action, submission_id, json.dumps(result, ensure_ascii=False), submitted_at))

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> VocabStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
