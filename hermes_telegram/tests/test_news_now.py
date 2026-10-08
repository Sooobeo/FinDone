from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.config import ConfigurationError, Settings
from findone_hermes.jobs import run_job
from findone_hermes.news import FetchedPage, SOURCES
from findone_hermes.news_now import KST, run_news_now
from findone_hermes.state import StateStore

ROOT = Path(__file__).resolve().parents[2]
SOURCE = SOURCES[1]
URL = "https://www.ecb.europa.eu/press/test.en.html"
TITLE = "ECB updates interest rates"
TEXT = ("The ECB held interest rates at 2.50%. Stable interest rates support market financing and economic activity. "
        "Financial markets remained stable during the reporting period.")
MIDNIGHT = datetime(2026, 10, 3, 0, 0, tzinfo=KST)


def fetch(url: str, *, article_url: str = URL) -> FetchedPage:
    if url == SOURCE.url:
        xml = (f"<rss><channel><item><title>{TITLE}</title><link>{article_url}</link>"
               "<pubDate>Fri, 02 Oct 2026 13:00:00 +0000</pubDate></item></channel></rss>")
        return FetchedPage(xml, SOURCE.url)
    if url == article_url:
        html = (f'<html lang="en"><head><meta property="article:published_time" content="2026-10-02">'
                f'<meta property="og:title" content="{TITLE}"><link rel="canonical" href="{article_url}">'
                f"</head><body><main><h1>{TITLE}</h1><p>{TEXT}</p></main></body></html>")
        return FetchedPage(html, article_url)
    # A single verifiable official source suffices despite other source outages.
    raise RuntimeError("private source exception")


class FakeModel:
    def __init__(self, *, barrier: threading.Barrier | None = None, invalid: bool = False):
        self.payloads = []
        self.barrier, self.invalid = barrier, invalid

    def complete_json(self, system, payload, *, response_schema=None):
        self.payloads.append(payload)
        if self.barrier is not None:
            self.barrier.wait(timeout=10)
        if self.invalid:
            return {"private provider exception": "credential"}
        return {
            "summary": [{"en": "The ECB held interest rates at 2.50%.", "ko": "ECB는 금리를 2.50%로 유지했습니다."}],
            "vocabulary": [
                {"term": "interest rates", "meaning_ko": "금리", "context": "The ECB held interest rates at 2.50%."},
                {"term": "financing", "meaning_ko": "자금 조달", "context": "Stable interest rates support market financing and economic activity."},
            ],
            "concept_links": [],
        }


class NewsNowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="findone-news-now-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "news.sqlite3"
        from findone_hermes.word_levels import OXFORD_URL
        levels = Path(self.temporary.name) / "levels.json"
        levels.write_text(json.dumps({"schema_version": 1, "source_url": OXFORD_URL,
                                      "entries": {"investor": "B2", "resilience": "C1"}}), encoding="utf-8")
        self.env = {
            "TELEGRAM_ALLOWED_USERS": "987654321",
            "FINDONE_REPO_ROOT": str(ROOT),
            "STATE_DB_PATH": str(self.path),
            "FINDONE_MODEL_BASE_URL": "http://127.0.0.1:11434/v1",
            "FINDONE_MODEL_NAME": "test-news-model",
            "FINDONE_CEFR_WORDLIST_PATH": str(levels),
        }

    def run_with_model(self, submission_id="message-1", *, now=MIDNIGHT, model=None):
        model = model or FakeModel()
        with patch("findone_hermes.news.fetch_official", side_effect=fetch), \
                patch("findone_hermes.news_now.model_from_env", return_value=model):
            return run_news_now(self.env, submission_id=submission_id, now=now), model

    def test_midnight_and_other_unscheduled_times_send_without_quiz_or_daily_claim(self):
        for index, now in enumerate((MIDNIGHT, MIDNIGHT + timedelta(hours=17, minutes=45))):
            with self.subTest(now=now):
                self.env["STATE_DB_PATH"] = str(Path(self.temporary.name) / f"news-{index}.sqlite3")
                messages, model = self.run_with_model(now=now)
                self.assertIn(URL, "\n".join(messages))
                self.assertEqual(len(model.payloads), 1)
                with StateStore(self.env["STATE_DB_PATH"]) as state:
                    self.assertEqual(state.connection.execute("SELECT COUNT(*) FROM quiz_batches").fetchone()[0], 0)
                    self.assertEqual(state.connection.execute("SELECT kind,slot,status FROM job_runs").fetchone()[:],
                                     ("news_now", "message-1", "emitted"))

    def test_same_message_replay_across_midnight_never_regenerates(self):
        first, model = self.run_with_model(now=MIDNIGHT - timedelta(minutes=1))
        repeated, _ = self.run_with_model(now=MIDNIGHT + timedelta(days=1), model=model)
        self.assertIn(URL, "\n".join(first))
        self.assertEqual(repeated, [])
        self.assertEqual(len(model.payloads), 1)
        with StateStore(self.path) as state:
            self.assertEqual(state.connection.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0], 1)
            self.assertEqual(len(state.seen_news_urls(987654321)), 1)

    def test_explicit_profile_mapping_never_reads_default_bot_configuration(self):
        default_state = Path(self.temporary.name) / "learning.sqlite3"
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "111111111", "FINDONE_REPO_ROOT": "relative-invalid",
                                     "STATE_DB_PATH": str(default_state), "FINDONE_QUIZ_COUNT": "99",
                                     "CONTENT_DB_PATH": "relative-invalid", "CONTENT_MANIFEST_PATH": "relative-invalid"}):
            settings = Settings.from_env(self.env)
            messages, _ = self.run_with_model()
        self.assertEqual(settings.user_id, "987654321")
        self.assertEqual(settings.quiz_count, 2)
        self.assertEqual(settings.state_db, self.path.resolve())
        self.assertIn(URL, "\n".join(messages))
        self.assertFalse(default_state.exists())

    def test_missing_or_multiple_owner_cannot_inherit_default_owner(self):
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "111111111"}):
            for value in ("", "987654321,111111111", "@owner"):
                scoped = {**self.env, "TELEGRAM_ALLOWED_USERS": value}
                with self.subTest(value=value), self.assertRaises(ConfigurationError):
                    run_news_now(scoped, submission_id="message-1", now=MIDNIGHT)
        self.assertFalse(self.path.exists())

    def test_explicit_news_state_path_is_required(self):
        scoped = {key: value for key, value in self.env.items() if key != "STATE_DB_PATH"}
        with patch.dict(os.environ, {"STATE_DB_PATH": str(self.path)}), self.assertRaises(ConfigurationError):
            run_news_now(scoped, submission_id="message-1", now=MIDNIGHT)
        self.assertFalse(self.path.exists())

    def test_missing_model_does_not_use_default_provider_or_fetch(self):
        scoped = {key: value for key, value in self.env.items() if not key.startswith("FINDONE_MODEL_")}
        with patch.dict(os.environ, {"FINDONE_MODEL_BASE_URL": "https://provider.invalid/v1",
                                     "FINDONE_MODEL_NAME": "default-paid-model", "FINDONE_MODEL_API_KEY": "secret"}), \
                patch("findone_hermes.news.fetch_official", side_effect=AssertionError("must not fetch")) as network:
            messages = run_news_now(scoped, submission_id="message-1", now=MIDNIGHT)
        self.assertIn("모델이 아직 연결되지 않았습니다", "\n".join(messages))
        self.assertIn("/now", "\n".join(messages))
        self.assertNotIn("퀴즈", "\n".join(messages))
        network.assert_not_called()
        with StateStore(self.path) as state:
            self.assertEqual(state.seen_news_urls(987654321), set())
            self.assertEqual(state.connection.execute("SELECT COUNT(*) FROM quiz_batches").fetchone()[0], 0)

    def test_fetch_and_model_validation_failures_send_safe_notice_without_article_claim(self):
        for index, broken_fetch in enumerate((True, False)):
            with self.subTest(fetch_failure=broken_fetch):
                scoped = {**self.env, "STATE_DB_PATH": str(Path(self.temporary.name) / f"failure-{index}.sqlite3")}
                with patch("findone_hermes.news.fetch_official", side_effect=RuntimeError("secret credential") if broken_fetch else fetch), \
                        patch("findone_hermes.news_now.model_from_env", return_value=FakeModel(invalid=True)):
                    messages = run_news_now(scoped, submission_id="message-1", now=MIDNIGHT)
                self.assertIn("검증하지 못해", "\n".join(messages))
                self.assertNotIn("credential", "\n".join(messages))
                with StateStore(scoped["STATE_DB_PATH"]) as state:
                    self.assertEqual(state.seen_news_urls(987654321), set())

    def test_invalid_model_configuration_is_recorded_failed_and_cannot_replay(self):
        scoped = {key: value for key, value in self.env.items() if key != "FINDONE_MODEL_BASE_URL"}
        notice = run_news_now(scoped, submission_id="message-1", now=MIDNIGHT)
        self.assertIn("로컬 뉴스 설정", "\n".join(notice))
        self.assertNotIn("FINDONE_MODEL_NAME", "\n".join(notice))
        self.assertEqual(run_news_now(self.env, submission_id="message-1", now=MIDNIGHT), [])
        with StateStore(self.path) as state:
            row = state.connection.execute("SELECT status,error_code FROM job_runs").fetchone()
            self.assertEqual(row[:], ("failed", "news_now_processing_failed"))
            self.assertEqual(state.seen_news_urls(987654321), set())

    def test_invalid_content_returns_safe_notice_and_records_failed_without_fetch(self):
        scoped = {**self.env, "CONTENT_MANIFEST_PATH": str(Path(self.temporary.name) / "private-manifest-missing.json")}
        with patch("findone_hermes.news.fetch_official") as network:
            notice = run_news_now(scoped, submission_id="message-1", now=MIDNIGHT)
        self.assertIn("로컬 뉴스 설정", "\n".join(notice))
        self.assertNotIn("private-manifest-missing", "\n".join(notice))
        network.assert_not_called()
        with StateStore(self.path) as state:
            self.assertEqual(state.connection.execute("SELECT status FROM job_runs").fetchone()[0], "failed")
            self.assertEqual(state.seen_news_urls(987654321), set())

    def test_submission_identity_and_aware_clock_are_required(self):
        for submission_id in ("", "\n", "private\nmessage", "x" * 201, None):
            with self.subTest(submission_id=submission_id), self.assertRaises(ValueError):
                run_news_now(self.env, submission_id=submission_id, now=MIDNIGHT)
        with self.assertRaises(ValueError):
            run_news_now(self.env, submission_id="message-1", now=datetime(2026, 10, 3))
        self.assertFalse(self.path.exists())

    def test_immediate_request_does_not_claim_the_daily_schedule(self):
        messages, _ = self.run_with_model()
        self.assertIn(URL, "\n".join(messages))
        another_url = "https://www.ecb.europa.eu/press/another-test.en.html"
        with patch("findone_hermes.news.fetch_official", side_effect=lambda url: fetch(url, article_url=another_url)), \
                patch("findone_hermes.model.model_from_env", return_value=FakeModel()), \
                patch("findone_hermes.jobs.QuizService", side_effect=AssertionError("news cannot create quiz")):
            self.assertEqual(run_job("news", "08:00", Settings.from_env(self.env), now=MIDNIGHT), [])
            scheduled = run_job("news", "08:00", Settings.from_env(self.env), now=MIDNIGHT + timedelta(hours=8))
        self.assertIn(another_url, "\n".join(scheduled))
        with StateStore(self.path) as state:
            kinds = {row[0] for row in state.connection.execute("SELECT kind FROM job_runs")}
            self.assertEqual(kinds, {"news", "news_now"})
            self.assertEqual(len(state.seen_news_urls(987654321)), 2)

    def test_concurrent_immediate_and_scheduled_news_can_emit_each_url_only_once(self):
        model = FakeModel(barrier=threading.Barrier(2))
        now = MIDNIGHT + timedelta(hours=8)
        with patch("findone_hermes.news.fetch_official", side_effect=fetch), \
                patch("findone_hermes.news_now.model_from_env", return_value=model), \
                patch("findone_hermes.model.model_from_env", return_value=model), \
                ThreadPoolExecutor(max_workers=2) as workers:
            immediate = workers.submit(run_news_now, self.env, submission_id="message-1", now=now)
            scheduled = workers.submit(run_job, "news", "08:00", Settings.from_env(self.env), now=now)
            results = (immediate.result(timeout=20), scheduled.result(timeout=20))
        self.assertEqual(sum(URL in "\n".join(messages) for messages in results), 1)
        self.assertEqual(len(model.payloads), 2)  # Both prepare before either reserves.
        with StateStore(self.path) as state:
            self.assertEqual(state.seen_news_urls(987654321), {URL})
            self.assertEqual(state.connection.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0], 2)
            self.assertEqual(state.connection.execute("SELECT COUNT(*) FROM quiz_batches").fetchone()[0], 0)

    def test_different_profile_state_does_not_share_article_or_message_claims(self):
        first, _ = self.run_with_model()
        self.env["STATE_DB_PATH"] = str(Path(self.temporary.name) / "other-news.sqlite3")
        other, _ = self.run_with_model()
        self.assertIn(URL, "\n".join(first))
        self.assertIn(URL, "\n".join(other))


if __name__ == "__main__":
    unittest.main()
