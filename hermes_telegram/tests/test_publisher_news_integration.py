"""Publisher focus integration with synthetic HTML and temporary private DBs."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.config import ConfigurationError, Settings
from findone_hermes import news_delivery, news_now
from findone_hermes.news import (
    FeedEntry, FeedSource, FetchedPage, NewsError, NewsResult, NewsService,
    NewsletterArticle, NewsletterPhrase, NewsletterSummary, NewsletterVocabulary,
    parse_publication, render_news_article, verify_article,
)
from findone_hermes.news_archive import NewsArchive, _article_from_data
from findone_hermes.news_sources import PUBLISHER_SOURCES

NOW = datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc)
SOURCES = tuple(FeedSource(item.name, item.url, item.hosts) for item in PUBLISHER_SOURCES)
CNBC, BLOOMBERG, HEALTH = SOURCES
URL = "https://www.cnbc.com/2026/09/29/synthetic-insurer.html"
TITLE = "Chubb reports improved insurance earnings"
DATE = "2026-09-29T15:30:00Z"
TEXT = ("Chubb increased underwriting profit as claims costs declined during the reporting period. "
        "The insurer raised capital to support future business growth and maintain financial flexibility. "
        "Management said lower costs supported stronger results across the insurance business.")


def html_article(*, title=TITLE, date=DATE, url=URL, canonical=None, restricted=False, preview=True):
    node = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": title,
            "datePublished": date, "url": url}
    if restricted:
        node["isAccessibleForFree"] = False
    body = '<p>' + TEXT + '</p>'
    if preview:
        body = '<div class="ArticleBody-meteredPaywallPreview">' + body + '</div>'
    return ('<html lang="en"><head><link rel="canonical" href="' + (canonical or url) + '">'
            '<script type="application/ld+json">' + json.dumps(node) + '</script></head>'
            '<body><div class="ArticleBody-articleBody">' + body + '</div></body></html>')


def feed(source, items):
    xml = '<rss><channel>' + ''.join(
        '<item><title>' + escape(title) + '</title><link>' + escape(url) + '</link>'
        '<pubDate>' + published + '</pubDate><description>RSS only; never a full article.</description></item>'
        for title, url, published in items
    ) + '</channel></rss>'
    return FetchedPage(xml, source.url, "application/xml")


def newsletter(article):
    return NewsletterArticle(article.title, article.url, article.published_at, article.source_name,
                             "The insurer reported improved results.", "보험사의 실적이 개선됐습니다.",
                             (), (), article.text, coverage=article.coverage)


class State:
    def seen_news_urls(self, owner):
        return set()


class PublisherIntegrationTests(unittest.TestCase):
    def test_focus_selects_only_publisher_feeds_without_institution_fallback(self):
        focused = NewsService(Mock(), State(), object(), focus="securities_insurance")
        self.assertEqual([(item.name, item.url) for item in focused.sources],
                         [(item.name, item.url) for item in SOURCES])
        self.assertEqual(NewsService(Mock(), State(), object()).focus, "general")

    def test_target_title_is_fetched_and_macro_or_passing_analyst_titles_are_not(self):
        generic = "https://www.cnbc.com/2026/10/03/synthetic-macro.html"
        commentary = "https://www.cnbc.com/2026/10/03/synthetic-commentary.html"
        fetched = []
        def fetcher(url):
            fetched.append(url)
            if url == CNBC.url:
                return feed(CNBC, [(TITLE, URL, DATE), ("Fed holds interest rates", generic, DATE),
                                   ("Morgan Stanley's Nike Analyst on quarterly earnings", commentary, DATE)])
            if url in {BLOOMBERG.url, HEALTH.url}:
                return feed(next(item for item in SOURCES if item.url == url), [])
            if url == URL:
                return FetchedPage(html_article(), URL)
            raise AssertionError("A non-target article must not be fetched")
        with patch("findone_hermes.news_editorial.prepare_editorial", side_effect=lambda article, model: newsletter(article)) as editorial:
            result = NewsService(Mock(), State(), object(), fetcher, focus="securities_insurance").prepare(123456, NOW)
        self.assertEqual([item.url for item in result.articles], [URL])
        self.assertEqual(fetched, [item.url for item in SOURCES] + [URL])
        self.assertEqual(result.articles[0].coverage, "public_excerpt")
        editorial.assert_called_once()

    def test_health_feed_adds_insurer_business_without_general_health_news(self):
        insurer = "https://www.cnbc.com/2026/10/01/synthetic-health-insurer.html"
        unrelated = "https://www.cnbc.com/2026/10/01/synthetic-drug-trial.html"
        title = "Health insurer reviews hospital claims costs"
        fetched = []
        def fetcher(url):
            fetched.append(url)
            if url == HEALTH.url:
                return feed(HEALTH, [(title, insurer, DATE),
                                    ("Drug maker announces new clinical trial", unrelated, DATE)])
            if url in {CNBC.url, BLOOMBERG.url}:
                return feed(next(item for item in SOURCES if item.url == url), [])
            if url == insurer:
                return FetchedPage(html_article(title=title, url=insurer), insurer)
            raise AssertionError("Unrelated healthcare article must not be fetched")
        with patch("findone_hermes.news_editorial.prepare_editorial", side_effect=lambda article, model: newsletter(article)) as editorial:
            result = NewsService(Mock(), State(), object(), fetcher, focus="securities_insurance").prepare(123456, NOW)
        self.assertEqual([item.url for item in result.articles], [insurer])
        self.assertEqual(fetched, [item.url for item in SOURCES] + [insurer])
        editorial.assert_called_once()

    def test_bloomberg_original_403_cannot_turn_rss_description_into_news(self):
        original = "https://www.bloomberg.com/news/articles/2026-10-02/synthetic-insurer"
        def fetcher(url):
            if url in {CNBC.url, HEALTH.url}:
                return feed(next(item for item in SOURCES if item.url == url), [])
            if url == BLOOMBERG.url:
                return feed(BLOOMBERG, [("Chubb insurance earnings rise", original, DATE)])
            raise HTTPError(url, 403, "Forbidden", None, None)
        with patch("findone_hermes.news_editorial.prepare_editorial") as editorial:
            result = NewsService(Mock(), State(), object(), fetcher, focus="securities_insurance").prepare(123456, NOW)
        self.assertEqual(result.articles, ())
        self.assertNotIn("RSS only", result.message)
        editorial.assert_not_called()

    def test_original_title_publication_date_identity_and_canonical_are_required(self):
        entry = FeedEntry(TITLE, URL, parse_publication(DATE), CNBC)
        accepted = verify_article(entry, FetchedPage(html_article(), URL))
        self.assertEqual((accepted.text, accepted.coverage), (TEXT, "public_excerpt"))
        for changes in (
            {"title": "Completely unrelated event headline"}, {"date": "2026-09-30T15:30:00Z"},
            {"url": "https://www.cnbc.com/2026/09/29/different-story.html"},
            {"canonical": "https://www.cnbc.com/2026/09/29/different-story.html"},
            {"canonical": "https://www.bloomberg.com/news/articles/different-story"},
            {"restricted": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                verify_article(entry, FetchedPage(html_article(**changes), URL))

    def test_preview_article_is_rendered_with_explicit_public_coverage_notice(self):
        article = verify_article(FeedEntry(TITLE, URL, parse_publication(DATE), CNBC), FetchedPage(html_article(), URL))
        body = render_news_article(newsletter(article))
        self.assertIn("공개된 본문 범위", body)
        self.assertIn(URL, body)
        self.assertLessEqual(len(body.encode("utf-16-le")) // 2, 3000)

    def test_malformed_jsonld_and_captcha_cannot_be_verified(self):
        entry = FeedEntry(TITLE, URL, parse_publication(DATE), CNBC)
        documents = (html_article().replace('"@context": "https://schema.org"', '"@context": invalid'),
                     html_article().replace('<body>', '<body><h1>Are you a robot?</h1>'))
        for source in documents:
            with self.subTest(source=source[:100]), self.assertRaises(ValueError):
                verify_article(entry, FetchedPage(source, URL))


class FocusConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = {"TELEGRAM_ALLOWED_USERS": "123456", "STATE_DB_PATH": str(self.root / "state.sqlite3"),
                            "FINDONE_NEWS_ARCHIVE_PATH": str(self.root / "archive.sqlite3"),
                            "FINDONE_TELEGRAM_MODE": "news", "TELEGRAM_BOT_TOKEN": "123456:" + "fake_test_token_" * 2}

    def test_explicit_focus_mapping_never_inherits_another_profiles_focus(self):
        with patch.dict(os.environ, {"FINDONE_NEWS_FOCUS": "securities_insurance"}):
            self.assertEqual(Settings.from_env(self.environment).news_focus, "general")
        with patch.dict(os.environ, {"FINDONE_NEWS_FOCUS": "general"}):
            self.assertEqual(Settings.from_env({**self.environment, "FINDONE_NEWS_FOCUS": "securities_insurance"}).news_focus,
                             "securities_insurance")
        with self.assertRaises(ConfigurationError):
            Settings.from_env({**self.environment, "FINDONE_NEWS_FOCUS": "markets"})

    def test_immediate_request_passes_profile_focus_to_news_service(self):
        environment = {**self.environment, "FINDONE_NEWS_FOCUS": "securities_insurance"}
        service, content = Mock(), Mock()
        service.prepare.return_value = NewsResult((), "오늘 소개할 신규 증권사·보험사 기사 없음")
        with patch.object(news_now, "ContentRepository", return_value=content), \
                patch.object(news_now, "model_from_env", return_value=object()), \
                patch.object(news_now.WordLevels, "from_env", return_value=object()), \
                patch.object(news_now, "NewsService", return_value=service) as factory:
            messages = news_now.run_news_now(environment, submission_id="synthetic-request", now=NOW)
        self.assertEqual(factory.call_args.kwargs["focus"], "securities_insurance")
        self.assertIsNone(factory.call_args.kwargs["word_levels"])
        self.assertIn("증권사·보험사", messages[0])
        content.close.assert_called_once()

    def test_scheduled_request_passes_profile_focus_to_news_service(self):
        environment = {**self.environment, "FINDONE_NEWS_FOCUS": "securities_insurance"}
        service, content = Mock(), Mock()
        service.prepare.return_value = NewsResult((), "오늘 소개할 신규 증권사·보험사 기사 없음")
        due = datetime(2026, 10, 4, 8, 0, tzinfo=timezone(timedelta(hours=9)))
        with patch.object(news_delivery, "ContentRepository", return_value=content), \
                patch.object(news_delivery, "model_from_env", return_value=object()), \
                patch.object(news_delivery.WordLevels, "from_env", return_value=object()), \
                patch.object(news_delivery, "NewsService", return_value=service) as factory, \
                patch.object(news_delivery, "_deliver", return_value=news_delivery.DeliveryResult("delivered", 1)):
            result = news_delivery.run_scheduled_news(environment, now=due)
        self.assertEqual(factory.call_args.kwargs["focus"], "securities_insurance")
        self.assertIsNone(factory.call_args.kwargs["word_levels"])
        self.assertEqual(result.status, "delivered")

    def test_new_article_context_and_phrases_survive_archive_receipt_roundtrip(self):
        details = (NewsletterSummary("event", "Chubb reported improved results.", "Chubb의 실적이 개선됐습니다.", TEXT.split('. ')[0] + '.'),)
        phrases = (NewsletterPhrase("raised capital", "자본을 조달했다", TEXT.split('. ')[1] + '.', "raise capital to + 동사", "https://example.test/reference", "사업 확대 목적의 자금 조달을 나타냅니다."),)
        vocabulary = (NewsletterVocabulary("underwriting profit", "보험영업이익", TEXT.split('. ')[0] + '.',
                                           "underwriting profit", "", "https://example.test/reference", "insurance"),)
        article = NewsletterArticle(TITLE, URL, parse_publication(DATE), "CNBC", details[0].en, details[0].ko,
                                    ((vocabulary[0].term, vocabulary[0].meaning_ko),), (), TEXT, vocabulary, details, phrases, "public_excerpt")
        body = render_news_article(article)
        with NewsArchive(self.root / "archive.sqlite3") as archive:
            archive.prepare_message(123456, article, body, now=NOW)
            self.assertTrue(archive.record_delivery(123456, "123456", "101", body, now=NOW))
            restored = archive.lookup_delivery(123456, "123456", "101").article
        self.assertEqual(restored, article)
        self.assertEqual(render_news_article(restored), body)

    def test_legacy_archive_snapshots_receive_compatible_defaults(self):
        legacy = newsletter(verify_article(FeedEntry(TITLE, URL, parse_publication(DATE), CNBC), FetchedPage(html_article(), URL)))
        payload = asdict(legacy)
        payload["published_at"] = legacy.published_at.isoformat()
        for field in ("summary_details", "phrases", "coverage"):
            payload.pop(field)
        restored = _article_from_data(payload)
        self.assertEqual(restored.summary_details, ())
        self.assertEqual(restored.phrases, ())
        self.assertEqual(restored.coverage, "full_article")


if __name__ == "__main__":
    unittest.main()
