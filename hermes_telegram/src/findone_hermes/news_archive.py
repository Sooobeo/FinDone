"""Private immutable articles and Telegram receipts for reply-based word saving."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Mapping
import uuid

from .config import Settings, private_news_path
from .news import NewsletterArticle, NewsletterVocabulary, NewsletterSummary, NewsletterPhrase, normalize_url
from .state import timestamp
from .vocab_state import MeaningChoice, VocabularySource, validate_user_id

APPLICATION_ID = 0x46444E41  # FDNA; cannot migrate a learning/vocabulary DB.
TABLES = {"news_articles", "news_prepared_messages", "news_message_receipts", "news_word_contexts", "news_wiki_outbox"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS news_articles (
 user_id INTEGER NOT NULL, article_id TEXT NOT NULL, snapshot_json TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(user_id,article_id)
);
CREATE TABLE IF NOT EXISTS news_prepared_messages (
 user_id INTEGER NOT NULL, body_hash TEXT NOT NULL, article_id TEXT NOT NULL,
 PRIMARY KEY(user_id,body_hash),
 FOREIGN KEY(user_id,article_id) REFERENCES news_articles(user_id,article_id)
);
CREATE TABLE IF NOT EXISTS news_message_receipts (
 user_id INTEGER NOT NULL, chat_id TEXT NOT NULL, message_id TEXT NOT NULL,
 article_id TEXT NOT NULL, delivered_at TEXT NOT NULL,
 PRIMARY KEY(user_id,chat_id,message_id),
 FOREIGN KEY(user_id,article_id) REFERENCES news_articles(user_id,article_id)
);
CREATE TABLE IF NOT EXISTS news_word_contexts (
 user_id INTEGER NOT NULL, article_id TEXT NOT NULL, lemma TEXT NOT NULL,
 source_json TEXT NOT NULL, PRIMARY KEY(user_id,article_id,lemma),
 FOREIGN KEY(user_id,article_id) REFERENCES news_articles(user_id,article_id)
);
CREATE TABLE IF NOT EXISTS news_wiki_outbox (
 user_id INTEGER NOT NULL, word_id TEXT NOT NULL, entry_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','synced')), updated_at TEXT NOT NULL,
 PRIMARY KEY(user_id,word_id)
);
"""


class NewsArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class ArchivedArticle:
    article_id: str
    article: NewsletterArticle


def _body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def archive_path(environment: Mapping[str, str]) -> Path:
    return private_news_path(environment, "FINDONE_NEWS_ARCHIVE_PATH", "news_archive.sqlite3")


def _article_data(article: NewsletterArticle) -> dict:
    payload = asdict(article)
    payload["published_at"] = article.published_at.isoformat()
    return payload


def _article_from_data(payload: dict) -> NewsletterArticle:
    values = dict(payload)
    values["published_at"] = datetime.fromisoformat(values["published_at"])
    values["vocabulary"] = tuple(tuple(item) for item in values["vocabulary"])
    values["concept_links"] = tuple(tuple(item) for item in values["concept_links"])
    values["vocabulary_evidence"] = tuple(NewsletterVocabulary(**item) for item in values.get("vocabulary_evidence", []))
    values["summary_details"] = tuple(NewsletterSummary(**item) for item in values.get("summary_details", []))
    values["phrases"] = tuple(NewsletterPhrase(**item) for item in values.get("phrases", []))
    return NewsletterArticle(**values)


class NewsArchive:
    def __init__(self, path: Path):
        path = Path(path)
        if not path.is_absolute():
            raise NewsArchiveError("News archive requires an absolute private path")
        path = path.resolve()
        if any((parent / ".git").exists() for parent in path.parents):
            raise NewsArchiveError("News archive must remain outside Git repositories")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        try:
            # Serialize first use too: no other process can observe a partial
            # schema with a missing application ID between individual DDL calls.
            self.connection.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            app_id = self.connection.execute("PRAGMA application_id").fetchone()[0]
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if (version not in {0, 1} or app_id not in {0, APPLICATION_ID}
                    or version == 0 and tables
                    or version == 1 and (tables != TABLES or app_id != APPLICATION_ID)):
                raise NewsArchiveError("An unrelated or newer database cannot be used as a news archive")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    self.connection.execute(statement)
            self.connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            self.connection.execute("PRAGMA user_version=1")
            self.connection.commit()
            self.connection.execute("PRAGMA foreign_keys=ON")
        except BaseException:
            self.connection.rollback()
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def prepare_message(self, user_id: int, article: NewsletterArticle, text: str, *, now=None) -> str:
        validate_user_id(user_id)
        if not isinstance(text, str) or not text or len(text.encode("utf-16-le")) // 2 > 3000:
            raise NewsArchiveError("Each article must fit one Telegram message")
        normalize_url(article.url)
        payload = json.dumps(_article_data(article), ensure_ascii=False, sort_keys=True)
        article_id = uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(payload.encode()).hexdigest()).hex
        with self.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO news_articles VALUES (?,?,?,?)",
                               (user_id, article_id, payload, timestamp(now)))
            existing = connection.execute("SELECT article_id FROM news_prepared_messages WHERE user_id=? AND body_hash=?",
                                          (user_id, _body_hash(text))).fetchone()
            if existing and existing[0] != article_id:
                # The same visible message is already tied to an immutable snapshot.
                return existing[0]
            connection.execute("INSERT OR IGNORE INTO news_prepared_messages VALUES (?,?,?)",
                               (user_id, _body_hash(text), article_id))
        return article_id

    def record_delivery(self, user_id: int, chat_id: str, message_id: str, text: str, *, now=None) -> bool:
        validate_user_id(user_id)
        if chat_id != str(user_id) or not re.fullmatch(r"[1-9][0-9]*", str(message_id)):
            raise NewsArchiveError("A private owner delivery receipt is required")
        with self.transaction() as connection:
            prepared = connection.execute("SELECT article_id FROM news_prepared_messages WHERE user_id=? AND body_hash=?",
                                          (user_id, _body_hash(text))).fetchone()
            if not prepared:
                return False  # A status/help message is not an article.
            existing = connection.execute("SELECT article_id FROM news_message_receipts WHERE user_id=? AND chat_id=? AND message_id=?",
                                          (user_id, chat_id, str(message_id))).fetchone()
            if existing and existing[0] != prepared[0]:
                raise NewsArchiveError("An existing Telegram receipt cannot be remapped")
            connection.execute("INSERT OR IGNORE INTO news_message_receipts VALUES (?,?,?,?,?)",
                (user_id, chat_id, str(message_id), prepared[0], timestamp(now)))
        return True

    def lookup_delivery(self, user_id: int, chat_id: str, message_id: str) -> ArchivedArticle | None:
        validate_user_id(user_id)
        if chat_id != str(user_id) or not re.fullmatch(r"[1-9][0-9]*", str(message_id)):
            return None
        row = self.connection.execute("""SELECT a.article_id,a.snapshot_json FROM news_message_receipts r
            JOIN news_articles a ON a.user_id=r.user_id AND a.article_id=r.article_id
            WHERE r.user_id=? AND r.chat_id=? AND r.message_id=?""", (user_id, chat_id, str(message_id))).fetchone()
        return ArchivedArticle(row[0], _article_from_data(json.loads(row[1]))) if row else None

    def cached_word(self, user_id: int, article_id: str, lemma: str) -> VocabularySource | None:
        validate_user_id(user_id)
        row = self.connection.execute("SELECT source_json FROM news_word_contexts WHERE user_id=? AND article_id=? AND lemma=?",
                                      (user_id, article_id, lemma)).fetchone()
        return VocabularySource(**json.loads(row[0])) if row else None

    def cache_word(self, user_id: int, source: VocabularySource) -> VocabularySource:
        validate_user_id(user_id)
        from .vocabulary import validated_source
        source = validated_source(source)
        with self.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO news_word_contexts VALUES (?,?,?,?)",
                (user_id, source.article_id, source.lemma, json.dumps(asdict(source), ensure_ascii=False)))
        return self.cached_word(user_id, source.article_id, source.lemma)

    def vocabulary_choices(self, user_id: int) -> tuple[MeaningChoice, ...]:
        validate_user_id(user_id)
        result = []
        for row in self.connection.execute("SELECT article_id,snapshot_json FROM news_articles WHERE user_id=?", (user_id,)):
            article = _article_from_data(json.loads(row[1]))
            result.extend(MeaningChoice(meaning, term, article.url, row[0]) for term, meaning in article.vocabulary)
        return tuple(result)

    def queue_wiki(self, user_id: int, word_id: str, entry: dict, *, now=None) -> None:
        validate_user_id(user_id)
        with self.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO news_wiki_outbox VALUES (?,?,?,'pending',?)",
                               (user_id, word_id, json.dumps(entry, ensure_ascii=False), timestamp(now)))

    def pending_wiki(self, user_id: int, limit: int = 2) -> tuple[dict, ...]:
        validate_user_id(user_id)
        return tuple(json.loads(row[0]) for row in self.connection.execute(
            "SELECT entry_json FROM news_wiki_outbox WHERE user_id=? AND status='pending' ORDER BY updated_at LIMIT ?",
            (user_id, limit)))

    def mark_wiki_synced(self, user_id: int, word_id: str, *, now=None) -> None:
        validate_user_id(user_id)
        with self.transaction() as connection:
            connection.execute("UPDATE news_wiki_outbox SET status='synced',updated_at=? WHERE user_id=? AND word_id=?",
                               (timestamp(now), user_id, word_id))

    def wiki_status(self, user_id: int, word_id: str) -> str | None:
        validate_user_id(user_id)
        row = self.connection.execute("SELECT status FROM news_wiki_outbox WHERE user_id=? AND word_id=?",
                                      (user_id, word_id)).fetchone()
        return row[0] if row else None


def record_news_delivery(environment: Mapping[str, str], *, chat_id: str, message_id: str, text: str) -> None:
    settings = Settings.from_env(environment)
    if str(chat_id) != settings.user_id:
        raise NewsArchiveError("The article receipt must belong to the configured private owner")
    with NewsArchive(archive_path(environment)) as archive:
        archive.record_delivery(int(settings.user_id), str(chat_id), str(message_id), text)
