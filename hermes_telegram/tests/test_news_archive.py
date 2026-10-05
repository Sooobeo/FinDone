"""Verify immutable article snapshots and private Telegram receipt binding."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.config import ConfigurationError, private_news_path
from findone_hermes.news import NewsletterArticle, NewsletterVocabulary
from findone_hermes.news_archive import (
    APPLICATION_ID, NewsArchive, NewsArchiveError, archive_path, record_news_delivery,
)
from findone_hermes.vocab_state import VocabularySource

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
OWNER = 123
OTHER_OWNER = 456
URL = "https://www.ecb.europa.eu/press/archive-fixture.en.html"
SENTENCE = "Bond yield represents the return on a bond."
FULL_TEXT = SENTENCE + " Market liquidity allows investors to sell bonds quickly. This final sentence is not in the visible summary."
BODY = "ECB financial markets update\n" + SENTENCE + "\n채권 수익률은 채권에서 얻는 수익률입니다.\n" + URL


def article(**overrides):
    return replace(NewsletterArticle(
        title="Financial markets update",
        url=URL,
        published_at=NOW,
        source_name="ECB",
        english_summary=SENTENCE,
        korean_summary="채권 수익률은 채권에서 얻는 수익률입니다.",
        vocabulary=(("yield", "채권 수익률"), ("liquidity", "유동성")),
        concept_links=(("채권", "공개 테스트 금융 개념"),),
        source_text=FULL_TEXT,
        vocabulary_evidence=(
            NewsletterVocabulary("yield", "채권 수익률", SENTENCE, "yield", "B2", "https://www.oxfordlearnersdictionaries.com/wordlists/oxford3000-5000"),
        ),
    ), **overrides)


def word_source(article_id: str, **overrides):
    return replace(VocabularySource(
        term="yield", lemma="yield", sense="bond return", meaning_ko="채권에서 얻는 수익률",
        sentence=SENTENCE, article_url=URL, article_title="Financial markets update",
        article_id=article_id, source_name="ECB", published_at=NOW.isoformat(),
        explanation_ko="이 원문에서 채권의 수익률을 뜻합니다.",
    ), **overrides)


class NewsArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="findone-news-archive-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "news_archive.sqlite3"
        self.environment = {
            "TELEGRAM_ALLOWED_USERS": str(OWNER),
            "FINDONE_REPO_ROOT": str(ROOT),
            "STATE_DB_PATH": str(self.directory / "news_state.sqlite3"),
            "CONTENT_DB_PATH": str(self.directory / "public_content.sqlite3"),
            "CONTENT_MANIFEST_PATH": str(self.directory / "public_manifest.json"),
            "FINDONE_NEWS_ARCHIVE_PATH": str(self.path),
        }
        self.archive = NewsArchive(self.path)
        self.addCleanup(self.archive.close)

    def prepare(self, *, owner=OWNER, snapshot=None, body=BODY):
        return self.archive.prepare_message(owner, snapshot or article(), body, now=NOW)

    def test_exact_prepared_body_binds_receipt_to_full_snapshot(self):
        article_id = self.prepare()
        self.assertTrue(self.archive.record_delivery(OWNER, "123", "41", BODY, now=NOW))
        saved = self.archive.lookup_delivery(OWNER, "123", "41")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.article_id, article_id)
        self.assertEqual(saved.article, article())
        self.assertIn("not in the visible summary", saved.article.source_text)

    def test_unknown_and_altered_body_cannot_bind_a_message(self):
        article_id = self.prepare()
        variants = (
            "뉴스 상태 안내",
            BODY + "\n",
            " " + BODY,
            BODY.replace("Bond yield", "Bond Yield"),
            BODY + "\n기사 ID: " + article_id,
            "기사 ID: " + article_id,
        )
        for index, body in enumerate(variants, 100):
            with self.subTest(body=body):
                self.assertFalse(self.archive.record_delivery(OWNER, "123", str(index), body, now=NOW))
                self.assertIsNone(self.archive.lookup_delivery(OWNER, "123", str(index)))

    def test_existing_receipt_is_idempotent_and_cannot_be_remapped(self):
        first = self.prepare()
        self.archive.record_delivery(OWNER, "123", "41", BODY, now=NOW)
        self.assertTrue(self.archive.record_delivery(OWNER, "123", "41", BODY, now=NOW + timedelta(days=1)))
        second_body = "A second financial update"
        self.prepare(snapshot=article(title="Second update", url=URL + "?edition=2"), body=second_body)
        with self.assertRaises(NewsArchiveError):
            self.archive.record_delivery(OWNER, "123", "41", second_body, now=NOW)
        self.assertEqual(self.archive.lookup_delivery(OWNER, "123", "41").article_id, first)

    def test_prepared_body_keeps_first_snapshot_when_metadata_changes(self):
        first = self.prepare()
        repeated = self.prepare(snapshot=article(source_text=FULL_TEXT + " Later source revision."))
        self.assertEqual(repeated, first)
        self.archive.record_delivery(OWNER, "123", "42", BODY, now=NOW)
        self.assertEqual(self.archive.lookup_delivery(OWNER, "123", "42").article.source_text, FULL_TEXT)

    def test_receipts_and_prepared_bodies_are_owner_isolated(self):
        first = self.prepare()
        self.assertFalse(self.archive.record_delivery(OTHER_OWNER, "456", "41", BODY, now=NOW))
        other_article = article(title="Other owner update", url="https://www.bis.org/press/archive-fixture.htm", source_name="BIS")
        second = self.prepare(owner=OTHER_OWNER, snapshot=other_article)
        self.archive.record_delivery(OWNER, "123", "41", BODY, now=NOW)
        self.archive.record_delivery(OTHER_OWNER, "456", "41", BODY, now=NOW)
        self.assertNotEqual(first, second)
        self.assertEqual(self.archive.lookup_delivery(OWNER, "123", "41").article_id, first)
        self.assertEqual(self.archive.lookup_delivery(OTHER_OWNER, "456", "41").article_id, second)
        self.assertIsNone(self.archive.lookup_delivery(OWNER, "456", "41"))
        self.assertIsNone(self.archive.lookup_delivery(OTHER_OWNER, "123", "41"))

    def test_private_owner_chat_and_positive_message_id_are_required(self):
        self.prepare()
        for chat_id, message_id in (("456", "41"), ("-123", "41"), ("123", "0"), ("123", ""), ("123", "article-id")):
            with self.subTest(chat_id=chat_id, message_id=message_id):
                with self.assertRaises(NewsArchiveError):
                    self.archive.record_delivery(OWNER, chat_id, message_id, BODY, now=NOW)
                self.assertIsNone(self.archive.lookup_delivery(OWNER, chat_id, message_id))

    def test_reopen_preserves_full_article_vocabulary_context_and_receipt(self):
        article_id = self.prepare()
        source = word_source(article_id)
        self.archive.record_delivery(OWNER, "123", "41", BODY, now=NOW)
        self.assertEqual(self.archive.cache_word(OWNER, source), source)
        self.archive.close()
        with NewsArchive(self.path) as reopened:
            self.assertEqual(reopened.lookup_delivery(OWNER, "123", "41").article, article())
            self.assertEqual(reopened.cached_word(OWNER, article_id, "yield"), source)
            choices = reopened.vocabulary_choices(OWNER)
            self.assertEqual({choice.meaning_ko for choice in choices}, {"채권 수익률", "유동성"})
            self.assertTrue(all(choice.article_url == URL and choice.source_id == article_id for choice in choices))

    def test_cache_keeps_first_word_value_and_other_owner_cannot_read_it(self):
        article_id = self.prepare()
        original = word_source(article_id)
        self.archive.cache_word(OWNER, original)
        changed = replace(original, meaning_ko="나중에 변경한 뜻", explanation_ko="새 설명으로 덮어쓰려는 값입니다.")
        self.assertEqual(self.archive.cache_word(OWNER, changed), original)
        self.assertEqual(self.archive.cached_word(OWNER, article_id, "yield"), original)
        self.assertIsNone(self.archive.cached_word(OTHER_OWNER, article_id, "yield"))
        self.assertEqual(self.archive.vocabulary_choices(OTHER_OWNER), ())

    def test_wiki_outbox_retry_preserves_pending_entry_and_survives_reopen(self):
        entry = {"word_id": "word-1", "term": "yield", "meaning_ko": "채권 수익률"}
        self.archive.queue_wiki(OWNER, "word-1", entry, now=NOW)
        self.archive.queue_wiki(OWNER, "word-1", {**entry, "meaning_ko": "변경된 뜻"}, now=NOW + timedelta(minutes=1))
        self.assertEqual(self.archive.pending_wiki(OWNER), (entry,))
        self.archive.close()
        with NewsArchive(self.path) as reopened:
            self.assertEqual(reopened.pending_wiki(OWNER), (entry,))
            reopened.mark_wiki_synced(OWNER, "word-1", now=NOW + timedelta(minutes=2))
            self.assertEqual(reopened.pending_wiki(OWNER), ())
            reopened.queue_wiki(OWNER, "word-1", entry, now=NOW + timedelta(minutes=3))
            self.assertEqual(reopened.pending_wiki(OWNER), ())

    def test_wiki_outbox_same_word_id_and_acknowledgments_are_owner_isolated(self):
        first = {"word_id": "same-word", "term": "yield", "meaning_ko": "채권 수익률"}
        second = {"word_id": "same-word", "term": "liquidity", "meaning_ko": "유동성"}
        self.archive.queue_wiki(OWNER, "same-word", first, now=NOW)
        self.archive.queue_wiki(OTHER_OWNER, "same-word", second, now=NOW)
        self.archive.mark_wiki_synced(OWNER, "same-word", now=NOW)
        self.assertEqual(self.archive.pending_wiki(OWNER), ())
        self.assertEqual(self.archive.pending_wiki(OTHER_OWNER), (second,))
        self.archive.mark_wiki_synced(OWNER, "unknown-word", now=NOW)
        self.assertEqual(self.archive.pending_wiki(OTHER_OWNER), (second,))

    def test_wiki_retry_batch_limit_does_not_consume_pending_entries(self):
        entries = tuple({"word_id": f"word-{index}", "term": "yield", "ordinal": index} for index in range(3))
        for index, entry in enumerate(entries):
            self.archive.queue_wiki(OWNER, entry["word_id"], entry, now=NOW + timedelta(minutes=index))
        self.assertEqual(self.archive.pending_wiki(OWNER, limit=2), entries[:2])
        self.assertEqual(self.archive.pending_wiki(OWNER, limit=3), entries)

    def test_unrelated_wrong_application_and_future_sqlite_are_unchanged(self):
        for index, (app_id, version, table) in enumerate((
            (0, 0, "learning_words"),
            (0, 0, "news_articles"),
            (0x564F4342, 1, "vocab_words"),
            (APPLICATION_ID, 1, "unrelated_data"),
            (APPLICATION_ID, 2, "news_articles"),
        )):
            with self.subTest(app_id=app_id, version=version, table=table):
                path = self.directory / f"protected-{index}.sqlite3"
                connection = sqlite3.connect(path)
                connection.execute(f"CREATE TABLE {table} (value TEXT)")
                connection.execute(f"INSERT INTO {table} VALUES ('public fixture')")
                connection.execute(f"PRAGMA application_id={app_id}")
                connection.execute(f"PRAGMA user_version={version}")
                connection.commit()
                connection.close()
                before = path.read_bytes()
                with self.assertRaises(NewsArchiveError):
                    NewsArchive(path)
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse(path.with_name(path.name + "-wal").exists())

    def test_telegram_size_limit_uses_utf16_units(self):
        self.prepare(body="😀" * 1500)
        with self.assertRaises(NewsArchiveError):
            self.prepare(body="😀" * 1501)

    def test_record_helper_uses_explicit_profile_owner_path_and_exact_body(self):
        article_id = self.prepare()
        wrong_profile_path = self.directory / "unrelated-profile.sqlite3"
        with patch.dict(os.environ, {
            "TELEGRAM_ALLOWED_USERS": str(OTHER_OWNER),
            "STATE_DB_PATH": "relative-invalid",
            "FINDONE_NEWS_ARCHIVE_PATH": str(wrong_profile_path),
        }):
            record_news_delivery(self.environment, chat_id="123", message_id="41", text=BODY)
        self.assertFalse(wrong_profile_path.exists())
        self.assertEqual(self.archive.lookup_delivery(OWNER, "123", "41").article_id, article_id)

    def test_record_helper_status_or_forged_body_creates_no_article_binding(self):
        article_id = self.prepare()
        for message_id, text in (("41", "오늘 소개할 신규 기사 없음"), ("42", "기사 ID: " + article_id)):
            record_news_delivery(self.environment, chat_id="123", message_id=message_id, text=text)
            self.assertIsNone(self.archive.lookup_delivery(OWNER, "123", message_id))

    def test_record_helper_rejects_wrong_chat_before_creating_any_archive(self):
        target = self.directory / "must-not-create.sqlite3"
        environment = {**self.environment, "FINDONE_NEWS_ARCHIVE_PATH": str(target)}
        with self.assertRaises(NewsArchiveError):
            record_news_delivery(environment, chat_id="456", message_id="41", text=BODY)
        self.assertFalse(target.exists())

    def test_private_news_path_requires_explicit_state_and_external_absolute_path(self):
        self.assertEqual(archive_path(self.environment), self.path.resolve())
        without_archive = {key: value for key, value in self.environment.items() if key != "FINDONE_NEWS_ARCHIVE_PATH"}
        self.assertEqual(archive_path(without_archive), self.path.resolve())
        without_state = {key: value for key, value in self.environment.items() if key != "STATE_DB_PATH"}
        with self.assertRaises(ConfigurationError):
            archive_path(without_state)
        with self.assertRaises(ConfigurationError):
            archive_path({**self.environment, "FINDONE_NEWS_ARCHIVE_PATH": "relative-archive.sqlite3"})

    def test_private_news_path_rejects_repository_state_and_content_collisions(self):
        targets = (
            ROOT,
            ROOT / "hermes_telegram" / "must-not-create.sqlite3",
            Path(self.environment["STATE_DB_PATH"]),
            Path(self.environment["CONTENT_DB_PATH"]),
            Path(self.environment["CONTENT_MANIFEST_PATH"]),
        )
        for target in targets:
            with self.subTest(target=target), self.assertRaises(ConfigurationError):
                private_news_path(
                    {**self.environment, "FINDONE_NEWS_ARCHIVE_PATH": str(target)},
                    "FINDONE_NEWS_ARCHIVE_PATH", "news_archive.sqlite3",
                )


if __name__ == "__main__":
    unittest.main()
