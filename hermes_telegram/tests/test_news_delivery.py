"""Direct news delivery uses fake transport and real temporary receipt/slot DBs."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from findone_hermes import news_delivery as delivery
from findone_hermes.news import NewsletterArticle, NewsResult, render_news_messages
from findone_hermes.news_archive import NewsArchive, archive_path
from findone_hermes.state import StateStore

NOW = datetime(2026, 10, 4, 8, 0, tzinfo=timezone(timedelta(hours=9)))
OWNER = 123456
TOKEN = "123456:" + "fake_test_token_" * 2


class Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class NewsDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = {
            "FINDONE_TELEGRAM_MODE": "news", "TELEGRAM_ALLOWED_USERS": str(OWNER),
            "TELEGRAM_BOT_TOKEN": TOKEN, "STATE_DB_PATH": str(self.root / "state.sqlite3"),
            "FINDONE_NEWS_ARCHIVE_PATH": str(self.root / "archive.sqlite3"),
            "FINDONE_MODEL_BASE_URL": "http://127.0.0.1:11434/v1", "FINDONE_MODEL_NAME": "fake-model",
        }
        self.articles = tuple(
            NewsletterArticle(
                f"Synthetic article {ordinal}", f"https://www.ecb.europa.eu/test-{ordinal}.html",
                NOW - timedelta(days=1), "ECB", "Banks became more resilient.",
                "은행의 회복력이 높아졌습니다.", (), (), "Banks became more resilient.", (),
            ) for ordinal in (1, 2)
        )
        self.news_result = NewsResult(self.articles, "")
        self.content = Mock()
        self.service = Mock()
        self.service.prepare.return_value = self.news_result
        self.next_id = 100
        self.require_prepared = True
        self.opener = Mock()
        self.opener.open.side_effect = self.open_transport
        patches = (
            patch.object(delivery, "ContentRepository", return_value=self.content),
            patch.object(delivery, "model_from_env", return_value=object()),
            patch.object(delivery.WordLevels, "from_env", return_value=object()),
            patch.object(delivery, "NewsService", return_value=self.service),
            patch.object(delivery, "build_opener", return_value=self.opener),
        )
        self.content_factory, self.model_factory, self.levels_factory, self.service_factory, self.opener_factory = [item.start() for item in patches]
        for item in patches:
            self.addCleanup(item.stop)

    def open_transport(self, request, *, timeout):
        payload = json.loads(request.data)
        self.assertEqual(payload["chat_id"], OWNER)
        self.assertEqual(timeout, 20)
        if self.require_prepared:
            with closing(sqlite3.connect(archive_path(self.environment))) as connection:
                body_hash = hashlib.sha256(payload["text"].encode("utf-8")).hexdigest()
                self.assertIsNotNone(connection.execute(
                    "SELECT 1 FROM news_prepared_messages WHERE user_id=? AND body_hash=?", (OWNER, body_hash),
                ).fetchone(), "An article snapshot must be committed before transport")
        self.next_id += 1
        return Response({"ok": True, "result": {"chat": {"id": OWNER, "type": "private"}, "message_id": self.next_id}})

    def test_scheduled_articles_are_individual_messages_archived_before_send(self):
        result = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(result, delivery.DeliveryResult("delivered", 2))
        self.assertEqual(self.opener.open.call_count, 2)
        self.model_factory.assert_called_once_with(self.environment)
        self.levels_factory.assert_called_once_with(self.environment)
        self.content.close.assert_called_once()
        for call in self.opener.open.call_args_list:
            request = call.args[0]
            self.assertTrue(request.full_url.startswith("https://api.telegram.org/bot"))
            self.assertNotIn("parse_mode", json.loads(request.data))
            payload = json.loads(request.data)
            self.assertTrue(payload["entities"])
            encoded = payload["text"].encode("utf-16-le")
            first = payload["entities"][0]
            self.assertEqual(encoded[first["offset"] * 2:(first["offset"] + first["length"]) * 2].decode("utf-16-le"),
                             "📰 FinDone | 금융 영어 뉴스")
            self.assertLessEqual(len(json.loads(request.data)["text"].encode("utf-16-le")) // 2, 3000)
        with NewsArchive(archive_path(self.environment)) as archive:
            first = archive.lookup_delivery(OWNER, str(OWNER), "101")
            second = archive.lookup_delivery(OWNER, str(OWNER), "102")
            self.assertEqual(first.article.url, self.articles[0].url)
            self.assertEqual(second.article.url, self.articles[1].url)
        with StateStore(Path(self.environment["STATE_DB_PATH"])) as state:
            self.assertEqual(state.seen_news_urls(OWNER), {article.url for article in self.articles})
            self.assertEqual(tuple(state.connection.execute("SELECT kind,kst_date,slot,status FROM job_runs").fetchone()), ("news", "2026-10-04", "08:00", "emitted"))

    def test_same_slot_and_legacy_claim_never_replay_delivery(self):
        with StateStore(Path(self.environment["STATE_DB_PATH"])) as state:
            state.claim_job(OWNER, "news", NOW.date().isoformat(), "08:00", now=NOW)
            state.finish_job(OWNER, "news", NOW.date().isoformat(), "08:00", status="failed", now=NOW)
        self.assertEqual(delivery.run_scheduled_news(self.environment, now=NOW).status, "already_claimed")
        self.opener.open.assert_not_called()
        self.content_factory.assert_not_called()

    def test_transport_timeout_is_uncertain_and_no_article_or_slot_retries(self):
        self.opener.open.side_effect = TimeoutError("https://api.telegram.org/botPRIVATE_TOKEN/sendMessage")
        first = delivery.run_scheduled_news(self.environment, now=NOW)
        second = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(first, delivery.DeliveryResult("uncertain", 0, "telegram_send_uncertain"))
        self.assertEqual(second.status, "already_claimed")
        self.opener.open.assert_called_once()
        with StateStore(Path(self.environment["STATE_DB_PATH"])) as state:
            self.assertEqual(len(state.seen_news_urls(OWNER)), 2)
            self.assertEqual(tuple(state.connection.execute("SELECT status,error_code FROM job_runs").fetchone()), ("uncertain", "telegram_send_uncertain"))

    def test_failed_second_article_stops_without_retrying_first_or_second(self):
        outcomes = [Response({"ok": True, "result": {"chat": {"id": OWNER, "type": "private"}, "message_id": 101}}), TimeoutError("PRIVATE_TOKEN")]
        self.opener.open.side_effect = outcomes
        result = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(result, delivery.DeliveryResult("uncertain", 1, "telegram_send_uncertain"))
        self.assertEqual(self.opener.open.call_count, 2)
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertIsNotNone(archive.lookup_delivery(OWNER, str(OWNER), "101"))
            self.assertEqual(archive.connection.execute("SELECT COUNT(*) FROM news_message_receipts").fetchone()[0], 1)

    def test_clock_grace_is_bounded_without_opening_db_or_transport(self):
        for clock in (NOW - timedelta(seconds=1), NOW + timedelta(minutes=30, seconds=1)):
            with self.subTest(clock=clock):
                self.assertEqual(delivery.run_scheduled_news(self.environment, now=clock).status, "not_due")
        self.content_factory.assert_not_called()
        self.opener.open.assert_not_called()
        self.assertFalse(Path(self.environment["STATE_DB_PATH"]).exists())
        self.assertEqual(delivery.run_scheduled_news(self.environment, now=NOW + timedelta(minutes=30)).status, "delivered")

    def test_configuration_never_inherits_default_bot_credentials_or_owner(self):
        for changes in (
            {"FINDONE_TELEGRAM_MODE": "learning"}, {"FINDONE_TELEGRAM_MODE": ""},
            {"TELEGRAM_BOT_TOKEN": ""}, {"STATE_DB_PATH": ""},
            {"TELEGRAM_ALLOWED_USERS": "*"}, {"TELEGRAM_ALLOWED_USERS": "123456,789"},
            {"TELEGRAM_ALLOWED_USERS": "-123456"},
        ):
            with self.subTest(changes=changes), patch.dict(os.environ, self.environment):
                result = delivery.run_scheduled_news({**self.environment, **changes}, now=NOW)
                self.assertEqual(result.status, "failed")
        self.opener.open.assert_not_called()
        self.content_factory.assert_not_called()
        self.assertFalse(Path(self.environment["STATE_DB_PATH"]).exists())

    def test_no_model_sends_short_setup_notice_without_lexical_or_article_lookup(self):
        self.model_factory.return_value = None
        self.service.prepare.return_value = NewsResult((), "unused legacy notice")
        self.require_prepared = False
        result = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(result, delivery.DeliveryResult("delivered", 1))
        self.levels_factory.assert_not_called()
        self.content_factory.assert_not_called()
        self.service_factory.assert_not_called()
        body = json.loads(self.opener.open.call_args.args[0].data)["text"]
        self.assertIn("모델", body)
        self.assertNotIn("퀴즈", body)
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertEqual(archive.connection.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0], 0)
            self.assertEqual(archive.connection.execute("SELECT COUNT(*) FROM news_message_receipts").fetchone()[0], 0)

    def test_no_new_article_notice_is_sent_without_fake_archive_snapshot(self):
        self.service.prepare.return_value = NewsResult((), "오늘 검증된 신규 기사 없음")
        self.require_prepared = False
        self.assertEqual(delivery.run_scheduled_news(self.environment, now=NOW).status, "delivered")
        with NewsArchive(archive_path(self.environment)) as archive:
            self.assertEqual(archive.connection.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0], 0)

    def test_http_response_requires_positive_message_id_and_exact_private_owner(self):
        self.require_prepared = False
        for result in (
            {"chat": {"id": OWNER + 1, "type": "private"}, "message_id": 1},
            {"chat": {"id": OWNER, "type": "group"}, "message_id": 1},
            {"chat": {"id": str(OWNER), "type": "private"}, "message_id": 1},
            {"chat": {"id": OWNER, "type": "private"}, "message_id": 0},
            {"chat": {"id": OWNER, "type": "private"}, "message_id": True},
            {"chat": {"id": OWNER, "type": "private"}, "message_id": "1"},
        ):
            with self.subTest(result=result):
                self.opener.open.side_effect = None
                self.opener.open.return_value = Response({"ok": True, "result": result})
                with self.assertRaises(delivery.NewsDeliveryError) as error:
                    delivery._send_message(TOKEN, OWNER, "notice")
                self.assertTrue(error.exception.uncertain)

    def test_redirects_are_disabled_and_provider_errors_are_symbolic(self):
        with self.assertRaises(delivery.NewsDeliveryError) as error:
            delivery._NoRedirect().redirect_request(None, None, 302, "", {}, "https://untrusted.example")
        self.assertEqual(str(error.exception), "telegram_send_uncertain")
        self.opener.open.side_effect = None
        self.opener.open.return_value = Response({"ok": False, "description": "PRIVATE_TOKEN OWNER_ID"})
        with self.assertRaises(delivery.NewsDeliveryError) as error:
            delivery._send_message(TOKEN, OWNER, "notice")
        self.assertEqual(str(error.exception), "telegram_send_failed")
        self.assertNotIn("PRIVATE_TOKEN", str(error.exception))

    def test_oversized_article_body_is_not_sent_or_split(self):
        with patch.object(delivery, "render_news_messages", return_value=["😀" * 1501, "other"]):
            result = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(result.status, "failed")
        self.opener.open.assert_not_called()

    def test_prepared_preview_sends_only_exact_archived_bodies_once(self):
        bodies = render_news_messages(self.news_result)
        with NewsArchive(archive_path(self.environment)) as archive:
            for article, body in zip(self.articles, bodies):
                archive.prepare_message(OWNER, article, body, now=NOW)
        first = delivery.send_prepared_news(self.environment, bodies, now=NOW)
        second = delivery.send_prepared_news(self.environment, bodies, now=NOW)
        self.assertEqual(first, delivery.DeliveryResult("delivered", 2))
        self.assertEqual(second.status, "already_claimed")
        self.content_factory.assert_not_called()
        self.model_factory.assert_not_called()
        self.assertEqual(self.opener.open.call_count, 2)

    def test_unprepared_or_modified_preview_body_never_reaches_transport(self):
        with NewsArchive(archive_path(self.environment)) as archive:
            archive.prepare_message(OWNER, self.articles[0], "original body", now=NOW)
        for messages in (["unprepared body"], ["original body", "modified body"], ["original body", "original body"]):
            with self.subTest(messages=messages):
                self.assertEqual(delivery.send_prepared_news(self.environment, messages, now=NOW).status, "failed")
        self.opener.open.assert_not_called()

    def test_receipt_storage_failure_is_uncertain_after_successful_api_send(self):
        with patch.object(NewsArchive, "record_delivery", side_effect=RuntimeError("PRIVATE_SOURCE")):
            result = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(result, delivery.DeliveryResult("uncertain", 1, "news_receipt_failed"))
        self.opener.open.assert_called_once()

    def test_final_job_record_failure_preserves_consumed_claim_and_uncertainty(self):
        with patch.object(StateStore, "finish_job", side_effect=RuntimeError("PRIVATE_TOKEN")):
            first = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(first, delivery.DeliveryResult("uncertain", 2, "news_job_record_failed"))
        self.assertEqual(delivery.run_scheduled_news(self.environment, now=NOW).status, "already_claimed")
        self.assertEqual(self.opener.open.call_count, 2)

    def test_content_cleanup_exception_cannot_expose_private_error_or_resend(self):
        self.content.close.side_effect = RuntimeError("PRIVATE_SOURCE_PATH")
        first = delivery.run_scheduled_news(self.environment, now=NOW)
        self.assertEqual(first, delivery.DeliveryResult("delivered", 2))
        self.assertEqual(delivery.run_scheduled_news(self.environment, now=NOW).status, "already_claimed")
        self.assertEqual(self.opener.open.call_count, 2)

    def test_cli_stdout_contains_only_symbolic_status_not_messages_credentials_or_ids(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(delivery, "run_scheduled_news", return_value=delivery.DeliveryResult("uncertain", error_code="telegram_send_uncertain")), patch.object(sys, "stdout", output), patch.object(sys, "stderr", errors):
            self.assertEqual(delivery.main(self.environment), 1)
        self.assertEqual(output.getvalue(), "FinDone news delivery: uncertain\n")
        self.assertEqual(errors.getvalue(), "FinDone news error: telegram_send_uncertain\n")
        self.assertNotIn(TOKEN, output.getvalue() + errors.getvalue())
        self.assertNotIn(str(OWNER), output.getvalue() + errors.getvalue())


BOOTSTRAP_PATH = Path(__file__).resolve().parents[1] / "hermes/scripts/_findone_bootstrap.py"
BOOTSTRAP_SPEC = importlib.util.spec_from_file_location("findone_news_delivery_bootstrap", BOOTSTRAP_PATH)
bootstrap = importlib.util.module_from_spec(BOOTSTRAP_SPEC)
BOOTSTRAP_SPEC.loader.exec_module(bootstrap)


class NewsWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.path = self.home / ".env"
        self.path.write_text(
            "FINDONE_TELEGRAM_MODE=news\nTELEGRAM_ALLOWED_USERS=123456\n"
            "TELEGRAM_BOT_TOKEN=literal-news-token\nFINDONE_MODEL_NAME=news-model\n"
            "FINDONE_CEFR_WORDLIST_PATH=/private/word-list.json\n"
            "FINDONE_NEWS_ARCHIVE_PATH=/private/archive.sqlite3\n"
            "FINDONE_VOCAB_DB_PATH=/private/vocabulary.sqlite3\n"
            "FINDONE_WIKI_VAULT=findone-news\n",
            encoding="utf-8",
        )
        self.file_patch = patch.object(bootstrap, "__file__", str(self.home / "scripts/_findone_bootstrap.py"))
        self.file_patch.start()
        self.addCleanup(self.file_patch.stop)

    def test_news_loader_uses_installed_profile_and_never_borrows_default_env(self):
        defaults = {"HERMES_HOME": "/wrong/default", "FINDONE_ENV_FILE": "/wrong/default/.env", "TELEGRAM_BOT_TOKEN": "wrong-default-token", "FINDONE_MODEL_NAME": "default-model", "FINDONE_MODEL_API_KEY": "default-key"}
        with patch.dict(os.environ, defaults, clear=True):
            environment = bootstrap.load_news_config_env()
            self.assertEqual(environment["TELEGRAM_BOT_TOKEN"], "literal-news-token")
            self.assertEqual(environment["FINDONE_MODEL_NAME"], "news-model")
            self.assertNotIn("FINDONE_MODEL_API_KEY", environment)
            self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "wrong-default-token")
        for key in ("FINDONE_CEFR_WORDLIST_PATH", "FINDONE_NEWS_ARCHIVE_PATH", "FINDONE_VOCAB_DB_PATH", "FINDONE_WIKI_VAULT"):
            self.assertIn(key, environment)

    def test_generic_learning_loader_still_excludes_bot_token(self):
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path)}, clear=True):
            bootstrap.load_config_env()
            self.assertNotIn("TELEGRAM_BOT_TOKEN", os.environ)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", bootstrap._read_config(self.path))

    def test_missing_news_profile_file_cannot_fall_back_to_process_credentials(self):
        self.path.unlink()
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "inherited-token", "TELEGRAM_ALLOWED_USERS": "123456"}):
            with self.assertRaises(FileNotFoundError):
                bootstrap.load_news_config_env()

    def test_news_wrapper_calls_direct_sender_with_explicit_mapping(self):
        sender = ModuleType("findone_hermes.news_delivery")
        sender.main = Mock(return_value=0)
        with patch.dict(sys.modules, {"findone_hermes.news_delivery": sender}):
            self.assertEqual(bootstrap.run_news_delivery(), 0)
        sender.main.assert_called_once_with(bootstrap.load_news_config_env())

    def test_malformed_or_duplicate_profile_token_is_rejected(self):
        for text in ('TELEGRAM_BOT_TOKEN="unterminated\n', "TELEGRAM_BOT_TOKEN=a\nTELEGRAM_BOT_TOKEN=b\n"):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    bootstrap.load_news_config_env()


if __name__ == "__main__":
    unittest.main()
