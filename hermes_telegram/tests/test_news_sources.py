"""Synthetic public publisher markup; no network or private fixture access."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from findone_hermes.news_sources import (
    BLOOMBERG_MARKETS, CNBC_FINANCE, CNBC_HEALTH, MAX_BYTES, PUBLISHER_SOURCES,
    PublisherRedirect, PublisherSourceError, article_coverage,
    extract_html_article_body, extract_jsonld_article, extract_publisher_article,
    normalize_publisher_url, topic_score,
)

URL = "https://www.cnbc.com/2026/10/03/synthetic-insurer.html"
TEXT = "The insurer increased underwriting profit as claims costs declined."


def metadata(**changes):
    return {"@context": "https://schema.org", "@type": "NewsArticle", "url": URL,
            "headline": "Synthetic insurer reports profit", "datePublished": "2026-10-03T10:00:00Z",
            **changes}


def document(node=None, body=None):
    node = metadata() if node is None else node
    body = f'<div class="ArticleBody-articleBody"><p>{TEXT}</p></div>' if body is None else body
    return '<html lang="en"><head><script type="application/ld+json">' + json.dumps(node) + '</script></head><body>' + body + '</body></html>'


class PublisherSourceTests(unittest.TestCase):
    def test_sources_are_exact_publisher_owned_endpoints(self):
        self.assertEqual(len(PUBLISHER_SOURCES), 3)
        self.assertEqual(CNBC_FINANCE.url, "https://www.cnbc.com/id/10000664/device/rss/rss.html")
        self.assertEqual(CNBC_HEALTH.url, "https://www.cnbc.com/id/10000108/device/rss/rss.html")
        self.assertEqual(BLOOMBERG_MARKETS.url, "https://www.bloomberg.com/feeds/markets/news.rss")
        for source in PUBLISHER_SOURCES:
            self.assertEqual(normalize_publisher_url(source.url, source=source), source.url)

    def test_urls_reject_external_hosts_credentials_ports_and_feed_as_article(self):
        for value in (
            "http://www.cnbc.com/story", "https://www.cnbc.com.attacker.test/story",
            "https://user:password@www.cnbc.com/story", "https://www.cnbc.com:8443/story",
            "https://www.cnbc.com/story\\next", URL + "\n", "https://localhost/story",
            CNBC_FINANCE.url, BLOOMBERG_MARKETS.url,
            "https://feeds.bloomberg.com/news/articles/story",
        ):
            with self.subTest(url=value), self.assertRaises(PublisherSourceError):
                normalize_publisher_url(value, article=True)
        self.assertEqual(normalize_publisher_url(URL + "?utm_source=rss&ref=a#part", article=True), URL + "?ref=a")

    def test_redirects_stay_with_one_publisher_and_https(self):
        request = Request("https://feeds.bloomberg.com/markets/news.rss")
        target = PublisherRedirect(BLOOMBERG_MARKETS).redirect_request(
            request, None, 302, "", {}, BLOOMBERG_MARKETS.url,
        )
        self.assertEqual(target.full_url, BLOOMBERG_MARKETS.url)
        for destination in (URL, "http://www.bloomberg.com/story", "https://mirror.example/story"):
            with self.subTest(destination=destination), self.assertRaises(PublisherSourceError):
                PublisherRedirect(BLOOMBERG_MARKETS).redirect_request(request, None, 302, "", {}, destination)

    def test_explicit_sector_headlines_and_company_business_get_positive_scores(self):
        for title in (
            "Goldman Sachs CEO succession planning faces a challenge",
            "Charles Schwab brokerage earnings increase", "Robinhood increases trading revenue",
            "Prudential reports higher insurance earnings", "MetLife increases premiums",
            "Chubb underwriting profit rises", "Allianz reports growth",
            "Travelers shares rise after earnings", "Investment banks face tougher competition",
            "Insurers reduce claims costs", "Broker-dealers increase capital",
        ):
            with self.subTest(title=title):
                self.assertGreater(topic_score(title, ""), 0)

    def test_generic_banking_macro_and_incidental_analyst_mentions_are_not_fallbacks(self):
        for title, text in (
            ("Fed holds interest rates", "Banks maintain capital and liquidity."),
            ("Inflation slows", "A Goldman Sachs analyst commented on the economy."),
            ("Morgan Stanley's Nike Analyst on quarterly earnings", "The retailer reported sales."),
            ("Prudential regulation of banks", "Capital ratios increased."),
            ("Travelers prepare for holidays", "Summer trips attract tourists."),
            ("Real estate brokerage expands", "Housing sales increased."),
        ):
            with self.subTest(title=title):
                self.assertEqual(topic_score(title, text), 0)

    def test_health_carrier_business_headlines_do_not_require_an_insurer_label(self):
        for title in (
            "UnitedHealth earnings beat estimates", "UnitedHealthcare reports stronger quarterly profit",
            "Cigna raises earnings forecast", "Humana quarterly revenue increases",
            "Elevance Health profit falls", "Centene shares rise after quarterly results",
            "Molina Healthcare cuts annual guidance", "Aetna reports larger quarterly losses",
        ):
            with self.subTest(title=title):
                self.assertGreater(topic_score(title, ""), 0)

    def test_general_medical_and_pharmacy_news_and_incidental_carriers_are_not_fallbacks(self):
        for title, text in (
            ("Pfizer reports promising drug trial results", "Cigna commented on the treatment."),
            ("Hospitals adopt a new cancer therapy", "UnitedHealthcare and Aetna sponsored research."),
            ("CVS Health expands pharmacy services", "The company reported higher pharmacy revenue."),
            ("Cigna analyst on Pfizer's new drug", "Pfizer reported clinical results."),
            ("Medical researchers develop a new diagnostic test", "The hospital expanded its laboratory."),
        ):
            with self.subTest(title=title):
                self.assertEqual(topic_score(title, text), 0)

    def test_headline_focus_ranks_above_generic_title_with_sector_body(self):
        strong = topic_score("Morgan Stanley investment banking earnings rise", TEXT)
        weaker = topic_score("Earnings news", "An insurer reported better underwriting profit.")
        self.assertGreater(strong, weaker)
        self.assertGreater(weaker, 0)

    def test_original_jsonld_metadata_and_visible_cnbc_body_are_kept(self):
        source = document()
        parsed = extract_publisher_article(source, URL)
        self.assertEqual((parsed.title, parsed.url, parsed.published_at),
                         (metadata()["headline"], URL, metadata()["datePublished"]))
        self.assertEqual(parsed.text, TEXT)
        self.assertEqual(extract_html_article_body(source), TEXT)
        self.assertEqual(extract_jsonld_article(source, URL).text, "")
        self.assertEqual(article_coverage(source), "public_text")

    def test_jsonld_graph_uses_newsarticle_and_exact_original_identity(self):
        graph = {"@graph": [{"@type": "WebPage", "headline": "Unrelated"}, metadata(articleBody=TEXT)]}
        parsed = extract_jsonld_article(document(graph, ""), URL)
        self.assertEqual(parsed.text, TEXT)
        for node in (metadata(url="https://www.bloomberg.com/news/articles/other"),
                     metadata(url="https://mirror.example/story"), metadata(headline=""), metadata(datePublished="")):
            with self.subTest(node=node):
                self.assertIsNone(extract_jsonld_article(document(node), URL))

    def test_cnbc_public_preview_is_labelled_without_claiming_full_article(self):
        body = '<div class="ArticleBody-articleBody"><div class="ArticleBody-meteredPaywallPreview"><p>' + TEXT + '</p></div></div>'
        source = document(body=body)
        parsed = extract_publisher_article(source, URL)
        self.assertTrue(parsed.public_preview)
        self.assertEqual(parsed.text, TEXT)
        self.assertEqual(article_coverage(source), "public_excerpt")

    def test_explicit_paywall_and_restricted_parts_discard_even_embedded_body(self):
        for changes in (
            {"isAccessibleForFree": False}, {"isAccessibleForFree": "false"},
            {"isAccessibleForFree": "unknown"},
            {"hasPart": {"@type": "WebPageElement", "isAccessibleForFree": False}},
        ):
            with self.subTest(changes=changes):
                source = document(metadata(articleBody="Hidden paid article", **changes))
                parsed = extract_publisher_article(source, URL)
                self.assertTrue(parsed.access_blocked)
                self.assertEqual(parsed.text, "")
                self.assertEqual(extract_html_article_body(source), "")
                self.assertEqual(article_coverage(source), "restricted")

    def test_captcha_and_signin_gates_are_not_article_evidence(self):
        for gate in ("Are you a robot?", "Unusual activity from your computer", "Sign in to continue"):
            with self.subTest(gate=gate):
                source = document(body=f'<h1>{gate}</h1><article><p>{TEXT}</p></article>')
                self.assertEqual(extract_html_article_body(source), "")
                self.assertTrue(extract_publisher_article(source, URL).access_blocked)

    def test_paywall_css_container_does_not_expose_paid_body(self):
        source = document(body='<article><p>Public introduction.</p><div class="Paywall-hiddenContent"><p>Paid body.</p></div></article>')
        self.assertEqual(extract_html_article_body(source), "")
        self.assertEqual(article_coverage(source), "restricted")
        self.assertTrue(extract_publisher_article(source, URL).access_blocked)

    def test_hidden_state_navigation_scripts_and_hidden_paragraphs_are_excluded(self):
        body = ('<nav><p>Navigation evidence</p></nav><article>'
                '<p>Visible <strong>source</strong> text.</p>'
                '<div hidden><p>Paid hidden text</p></div>'
                '<p aria-hidden="true">ARIA hidden text</p>'
                '<div style="display: none"><p>CSS hidden text</p></div>'
                '<script>{"articleBody":"Hidden serialized full article"}</script>'
                '<template><p>Template text</p></template></article>'
                '<footer><p>Footer text</p></footer>')
        self.assertEqual(extract_html_article_body(document(body=body)), "Visible source text.")

    def test_missing_malformed_and_duplicate_jsonld_never_supply_metadata(self):
        for raw in ("not json", '{"@type":"NewsArticle","isAccessibleForFree":false,"isAccessibleForFree":true}', "[]"):
            with self.subTest(raw=raw):
                source = f'<script type="application/ld+json">{raw}</script><article><p>{TEXT}</p></article>'
                self.assertIsNone(extract_jsonld_article(source, URL))
                if raw != "[]":
                    self.assertEqual(extract_html_article_body(source), "")
        with self.assertRaises(PublisherSourceError):
            extract_html_article_body("x" * (MAX_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
