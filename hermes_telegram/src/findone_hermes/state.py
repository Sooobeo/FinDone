"""Private SQLite state, immutable quiz snapshots, and atomic delivery reservations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterator


def utc_time(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required")
    return value.astimezone(timezone.utc)


def timestamp(now: datetime | None = None) -> str:
    return utc_time(now).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class ChoiceSnapshot:
    number: int
    key: str
    text: str
    explanation: str


@dataclass(frozen=True)
class QuizItem:
    ordinal: int
    domain_id: str
    element_id: str
    question_id: str
    concept_title: str
    definition: str
    intuition: str
    stem: str
    explanation: str
    choices: tuple[ChoiceSnapshot, ...]
    correct_number: int


@dataclass(frozen=True)
class QuizBatch:
    batch_id: str
    user_id: int
    chat_id: int
    kind: str
    status: str
    created_at: str
    sent_at: str | None
    delivery_status: str
    content_version: int
    items: tuple[QuizItem, ...]


@dataclass(frozen=True)
class GradedAnswer:
    ordinal: int
    chosen_number: int
    correct: bool
    attempt_kind: str
    submitted_at: str


@dataclass(frozen=True)
class GradeResult:
    batch: QuizBatch
    answers: tuple[GradedAnswer, ...]
    duplicate: bool = False


SCHEMA = """
CREATE TABLE IF NOT EXISTS quiz_batches (
    batch_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('regular','review')),
    status TEXT NOT NULL CHECK(status IN ('active','graded','skipped')),
    created_at TEXT NOT NULL, sent_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(delivery_status IN ('pending','emitted','uncertain')),
    content_version INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_user ON quiz_batches(user_id) WHERE status='active';
CREATE UNIQUE INDEX IF NOT EXISTS one_active_chat ON quiz_batches(chat_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS quiz_items (
    batch_id TEXT NOT NULL REFERENCES quiz_batches(batch_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL, domain_id TEXT NOT NULL, element_id TEXT NOT NULL,
    question_id TEXT NOT NULL, snapshot_json TEXT NOT NULL,
    PRIMARY KEY(batch_id, ordinal)
);
CREATE TABLE IF NOT EXISTS answers (
    batch_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    user_id INTEGER NOT NULL, chosen_number INTEGER NOT NULL CHECK(chosen_number BETWEEN 1 AND 5),
    correct INTEGER NOT NULL CHECK(correct IN (0,1)), submitted_at TEXT NOT NULL,
    attempt_kind TEXT NOT NULL CHECK(attempt_kind IN ('first','review')),
    PRIMARY KEY(batch_id,ordinal),
    FOREIGN KEY(batch_id,ordinal) REFERENCES quiz_items(batch_id,ordinal) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS submissions (
    user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, submission_id TEXT NOT NULL,
    batch_id TEXT NOT NULL REFERENCES quiz_batches(batch_id) ON DELETE CASCADE,
    PRIMARY KEY(user_id,chat_id,submission_id)
);
CREATE TABLE IF NOT EXISTS news_deliveries (
    user_id INTEGER NOT NULL, url TEXT NOT NULL, published_at TEXT NOT NULL,
    sent_at TEXT NOT NULL, PRIMARY KEY(user_id,url)
);
CREATE TABLE IF NOT EXISTS job_runs (
    user_id INTEGER NOT NULL, kind TEXT NOT NULL, kst_date TEXT NOT NULL, slot TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','emitted','failed','uncertain')),
    started_at TEXT NOT NULL, finished_at TEXT, error_code TEXT,
    PRIMARY KEY(user_id,kind,kst_date,slot)
);
CREATE INDEX IF NOT EXISTS user_answers ON answers(user_id,submitted_at);
PRAGMA user_version=1;
"""


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        repository = Path(__file__).resolve().parents[3]
        if (repository / ".git").exists() and self.path.is_relative_to(repository):
            raise ValueError("Learning state must be outside the repository")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None,
                                         check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        expected_tables = {"quiz_batches", "quiz_items", "answers", "submissions", "news_deliveries", "job_runs"}
        if version not in (0, 1):
            self.connection.close()
            raise ValueError("Unsupported learning state schema version")
        if (version == 0 and tables) or (version == 1 and tables != expected_tables):
            self.connection.close()
            raise ValueError("Existing database is not a FinDone Telegram learning state database")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)

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

    def batch(self, batch_id: str) -> QuizBatch | None:
        with self._lock:
            row = self.connection.execute("SELECT * FROM quiz_batches WHERE batch_id=?", (batch_id,)).fetchone()
            if row is None:
                return None
            items = []
            for item in self.connection.execute(
                    "SELECT snapshot_json FROM quiz_items WHERE batch_id=? ORDER BY ordinal", (batch_id,)):
                snapshot = json.loads(item[0])
                snapshot["choices"] = tuple(ChoiceSnapshot(**choice) for choice in snapshot["choices"])
                items.append(QuizItem(**snapshot))
            return QuizBatch(**dict(row), items=tuple(items))

    def active_batch(self, user_id: int, chat_id: int) -> QuizBatch | None:
        with self._lock:
            row = self.connection.execute("""SELECT batch_id FROM quiz_batches
                WHERE user_id=? AND chat_id=? AND status='active'""", (user_id, chat_id)).fetchone()
            return self.batch(row[0]) if row else None

    def latest_graded(self, user_id: int, chat_id: int) -> QuizBatch | None:
        with self._lock:
            row = self.connection.execute("""SELECT b.batch_id FROM quiz_batches b
                JOIN answers a ON a.batch_id=b.batch_id WHERE b.user_id=? AND b.chat_id=?
                AND b.status='graded' GROUP BY b.batch_id ORDER BY MAX(a.submitted_at) DESC,
                b.created_at DESC, b.rowid DESC LIMIT 1""", (user_id, chat_id)).fetchone()
            return self.batch(row[0]) if row else None

    def seen_question_ids(self, user_id: int) -> set[str]:
        with self._lock:
            return {row[0] for row in self.connection.execute("""SELECT DISTINCT i.question_id
                FROM quiz_items i JOIN quiz_batches b ON b.batch_id=i.batch_id WHERE b.user_id=?""", (user_id,))}

    def answer_rows(self, user_id: int) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.connection.execute("""SELECT a.*,i.domain_id,i.element_id,i.question_id
                FROM answers a JOIN quiz_items i ON i.batch_id=a.batch_id AND i.ordinal=a.ordinal
                WHERE a.user_id=? ORDER BY a.submitted_at,a.rowid""", (user_id,)))

    def graded_answers(self, batch_id: str) -> tuple[GradedAnswer, ...]:
        with self._lock:
            return tuple(GradedAnswer(row["ordinal"], row["chosen_number"], bool(row["correct"]),
                                     row["attempt_kind"], row["submitted_at"])
                         for row in self.connection.execute(
                             "SELECT * FROM answers WHERE batch_id=? ORDER BY ordinal", (batch_id,)))

    def insert_batch(self, batch: QuizBatch) -> None:
        """Called inside transaction so selection and activation stay atomic."""
        self.connection.execute("""INSERT INTO quiz_batches
            (batch_id,user_id,chat_id,kind,status,created_at,sent_at,delivery_status,content_version)
            VALUES (?,?,?,?,?,?,?,?,?)""", (batch.batch_id,batch.user_id,batch.chat_id,batch.kind,
            batch.status,batch.created_at,batch.sent_at,batch.delivery_status,batch.content_version))
        self.connection.executemany("""INSERT INTO quiz_items
            (batch_id,ordinal,domain_id,element_id,question_id,snapshot_json) VALUES (?,?,?,?,?,?)""",
            [(batch.batch_id,item.ordinal,item.domain_id,item.element_id,item.question_id,
              json.dumps(asdict(item), ensure_ascii=False, separators=(",", ":"))) for item in batch.items])

    def mark_batch_delivery(self, batch_id: str, status: str = "emitted", now: datetime | None = None) -> None:
        if status not in {"emitted", "uncertain"}:
            raise ValueError("Invalid delivery status")
        with self.transaction() as c:
            c.execute("UPDATE quiz_batches SET delivery_status=?,sent_at=? WHERE batch_id=?",
                      (status, timestamp(now) if status == "emitted" else None, batch_id))

    def claim_job(self, user_id: int, kind: str, kst_date: str, slot: str,
                  now: datetime | None = None) -> bool:
        with self.transaction() as c:
            result = c.execute("""INSERT OR IGNORE INTO job_runs
                (user_id,kind,kst_date,slot,status,started_at) VALUES (?,?,?,?,'running',?)""",
                (user_id,kind,kst_date,slot,timestamp(now)))
            return result.rowcount == 1

    def finish_job(self, user_id: int, kind: str, kst_date: str, slot: str,
                   status: str = "emitted", error_code: str | None = None,
                   now: datetime | None = None) -> None:
        if status not in {"emitted", "failed", "uncertain"}:
            raise ValueError("Invalid job status")
        # Error codes deliberately cannot contain URLs, exception bodies, or credentials.
        if error_code is not None and (len(error_code) > 80 or
                not all(character.isascii() and (character.isalnum() or character == "_") for character in error_code)):
            raise ValueError("A short symbolic error code is required")
        with self.transaction() as c:
            c.execute("""UPDATE job_runs SET status=?,finished_at=?,error_code=?
                WHERE user_id=? AND kind=? AND kst_date=? AND slot=? AND status='running'""",
                (status,timestamp(now),error_code,user_id,kind,kst_date,slot))

    def seen_news_urls(self, user_id: int) -> set[str]:
        with self._lock:
            return {row[0] for row in self.connection.execute(
                "SELECT url FROM news_deliveries WHERE user_id=?", (user_id,))}

    def record_news(self, user_id: int, url: str, published_at: str | datetime,
                    sent_at: str | datetime) -> bool:
        with self.transaction() as c:
            result = c.execute("""INSERT OR IGNORE INTO news_deliveries
                (user_id,url,published_at,sent_at) VALUES (?,?,?,?)""",
                (user_id,url,timestamp(published_at) if isinstance(published_at, datetime) else published_at,
                 timestamp(sent_at) if isinstance(sent_at, datetime) else sent_at))
            return result.rowcount == 1

    def delete_user(self, user_id: int) -> None:
        with self.transaction() as c:
            for table in ("news_deliveries", "job_runs"):
                c.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM quiz_batches WHERE user_id=?", (user_id,))

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
