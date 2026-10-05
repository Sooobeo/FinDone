"""Publisher-owned feeds and public, contextual finance article evidence.

Only normally served HTML/JSON-LD is inspected. Hidden application state,
subscription content, CAPTCHA workarounds and third-party mirrors are excluded.
The caller still verifies the feed date/title and independently bounds excerpts.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import html
from html.parser import HTMLParser
import json
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler


class PublisherSourceError(ValueError):
    pass


@dataclass(frozen=True)
class PublisherSource:
    # Deliberately matches news.FeedSource's fields without a circular import.
    name: str
    url: str
    hosts: frozenset[str]


# Public publisher responses checked 2026-10-03. Bloomberg's legacy
# feeds.bloomberg.com address redirects to this canonical publisher feed.
CNBC_FINANCE = PublisherSource(
    "CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    frozenset({"www.cnbc.com", "cnbc.com", "search.cnbc.com"}),
)
CNBC_HEALTH = PublisherSource(
    "CNBC", "https://www.cnbc.com/id/10000108/device/rss/rss.html",
    CNBC_FINANCE.hosts,
)
BLOOMBERG_MARKETS = PublisherSource(
    "Bloomberg", "https://www.bloomberg.com/feeds/markets/news.rss",
    frozenset({"www.bloomberg.com", "bloomberg.com", "feeds.bloomberg.com"}),
)
# Health insurers' claims and premium stories can be absent from Finance.
# The same securities/insurance topic filter excludes unrelated health stories.
PUBLISHER_SOURCES = (CNBC_FINANCE, BLOOMBERG_MARKETS, CNBC_HEALTH)
PUBLISHER_HOSTS = frozenset(host for source in PUBLISHER_SOURCES for host in source.hosts)
_ARTICLE_HOSTS = frozenset({"www.cnbc.com", "cnbc.com", "www.bloomberg.com", "bloomberg.com"})
MAX_BYTES = 2_000_000


def normalize_publisher_url(url: str, *, source: PublisherSource | None = None,
                            article: bool = False) -> str:
    """Permit original HTTPS URLs; a source constrains redirects to one publisher."""
    try:
        if not isinstance(url, str) or any(char.isspace() or ord(char) < 32 for char in url) or "\\" in url:
            raise ValueError
        parts = urlsplit(html.unescape(url))
        allowed = source.hosts if source is not None else PUBLISHER_HOSTS
        if (parts.scheme.lower() != "https" or parts.hostname not in allowed
                or parts.port not in {None, 443} or parts.username or parts.password
                or article and parts.hostname not in _ARTICLE_HOSTS):
            raise ValueError
        if article and (parts.path.startswith("/feeds/") or "/device/rss/" in parts.path):
            raise ValueError
        host = parts.hostname
        if host in {"cnbc.com", "bloomberg.com"}:
            host = "www." + host
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
        return urlunsplit(("https", host, parts.path or "/", urlencode(sorted(query)), ""))
    except (TypeError, ValueError):
        raise PublisherSourceError("publisher_url_invalid") from None


class PublisherRedirect(HTTPRedirectHandler):
    def __init__(self, source: PublisherSource):
        super().__init__()
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = normalize_publisher_url(urljoin(req.full_url, newurl), source=self.source)
        return super().redirect_request(req, fp, code, msg, headers, destination)


_COMPANIES = re.compile(
    r"\b(?:Morgan\s+Stanley|Goldman\s+Sachs|Charles\s+Schwab|Schwab|Robinhood|"
    r"Interactive\s+Brokers|Jefferies|Nomura|Daiwa\s+Securities|Raymond\s+James|"
    r"LPL\s+Financial|Stifel|Prudential|MetLife|AIG|Chubb|Allianz|AXA|"
    r"Zurich\s+Insurance|Travelers|Aflac|State\s+Farm|Swiss\s+Re|Munich\s+Re|"
    r"UnitedHealth(?:care)?|Cigna|Humana|Elevance\s+Health|Centene|"
    r"Molina\s+Healthcare|Aetna)\b", re.I,
)
_SECTORS = re.compile(
    r"\b(?:investment\s+bank(?:s|ing|ers)?|broker[- ]dealers?|"
    r"securities\s+(?:firms?|brokers?|brokerages?)|stock\s+brokers?|stockbrokers?|"
    r"(?:online|retail|discount|insurance)\s+brokers?|brokerages?|"
    r"insurance\s+(?:compan(?:y|ies)|groups?|sector|industry|carriers?)|"
    r"insurers?|reinsurers?|reinsurance|combined\s+ratio|"
    r"underwriting\s+(?:profits?|losses|income|margins?|business)|"
    r"claims\s+costs?|premium\s+(?:income|growth|revenue))\b", re.I,
)
_COMMENTARY = re.compile(r"\b(?:analysts?|strategists?)\b.{0,60}\b(?:on|say|says|predict|expect|upgrade|downgrade)\b", re.I)
_REAL_ESTATE = re.compile(r"\breal\s+estate\s+brokerages?\b", re.I)
_BUSINESS = re.compile(r"\b(?:earnings|revenues?|profits?|shares?|stock|CEO|insur\w*|claims|premiums?|combined\s+ratio)\b", re.I)


def _company_matches(value: str):
    matches = []
    for match in _COMPANIES.finditer(value):
        name = match.group().lower()
        if name == "prudential" and re.match(r"\s+(?:regulation|regulators?|rules|standards|supervision|policy)\b", value[match.end():], re.I):
            continue
        if name == "travelers" and not _BUSINESS.search(value[max(0, match.start() - 100):match.end() + 100]):
            continue
        matches.append(match)
    return matches


def topic_score(title: str, text: str) -> int:
    """Rank brokers, investment banks and insurers; generic banking scores zero.

    A passing analyst mention in a broad market story is insufficient. Headline
    company names or explicit sector language supply the required topic evidence.
    """
    if not isinstance(title, str) or not isinstance(text, str):
        raise PublisherSourceError("publisher_topic_invalid")
    title, text = title[:1000], text[:50_000]
    title_sector = list(_SECTORS.finditer(_REAL_ESTATE.sub("", title)))
    body_sector = list(_SECTORS.finditer(_REAL_ESTATE.sub("", text)))
    title_companies = _company_matches(title)
    if _COMMENTARY.search(title) and not title_sector:
        title_companies = []
    if not title_sector and not body_sector and not title_companies:
        return 0
    body_companies = _company_matches(text)
    return (5 * min(len(title_companies), 3) + 4 * min(len(title_sector), 3)
            + 2 * min(len(body_sector), 5) + min(len(body_companies), 3))


@dataclass(frozen=True)
class StructuredArticle:
    title: str
    url: str
    published_at: str
    text: str
    is_accessible_for_free: bool | None = None
    public_preview: bool = False
    access_blocked: bool = False


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _nodes(value):
    pending, visited = [value], 0
    while pending:
        node = pending.pop()
        visited += 1
        if visited > 1000:
            raise PublisherSourceError("publisher_metadata_invalid")
        if isinstance(node, list):
            pending.extend(reversed(node))
        elif isinstance(node, dict):
            yield node
            if isinstance(node.get("@graph"), (list, dict)):
                pending.append(node["@graph"])


def _restricted(node) -> bool:
    pending, visited = [node], 0
    while pending:
        current = pending.pop()
        visited += 1
        if visited > 1000:
            return True
        if isinstance(current, dict):
            if "isAccessibleForFree" in current:
                flag = current["isAccessibleForFree"]
                if flag is not True and flag != "true":
                    return True
            pending.extend(value for value in current.values() if isinstance(value, (list, dict)))
        elif isinstance(current, list):
            pending.extend(current)
    return False


_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})
_IGNORE = frozenset({"script", "style", "nav", "aside", "footer", "noscript", "template", "button"})
_GATE = re.compile(r"\b(?:are you a robot|unusual activity from your computer|verify you are human|"
                   r"subscribe to (?:read|continue)|sign in to (?:read|continue)|unlock this article)\b", re.I)


class _PublicParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.json_scripts, self.json_current = [], None
        self.paragraphs, self.current_paragraph = [], None
        self.visible = []
        self.preview = False
        self.invalid_metadata = False
        self.paywall = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        inherited = self.stack[-1] if self.stack else ("", False, False)
        style = attrs.get("style", "").replace(" ", "").lower()
        hidden = (inherited[2] or tag in _IGNORE or "hidden" in attrs
                  or attrs.get("aria-hidden", "").lower() == "true"
                  or "display:none" in style or "visibility:hidden" in style)
        classes = set(attrs.get("class", "").split())
        article = (inherited[1] or tag == "article" or attrs.get("itemprop") == "articleBody"
                   or bool(classes & {"ArticleBody-articleBody", "body-copy", "body-content", "story-body"}))
        if "ArticleBody-meteredPaywallPreview" in classes:
            self.preview = True
        if any("paywall" in value.lower() and "preview" not in value.lower() for value in classes):
            self.paywall = True
            hidden = True
        if any(value.lower() in {"hidden", "sr-only", "visually-hidden"} for value in classes):
            hidden = True
        if tag == "script" and attrs.get("type", "").lower().strip() == "application/ld+json":
            self.json_current = []
        if tag == "p" and article and not hidden:
            self.current_paragraph = []
        if tag not in _VOID:
            self.stack.append((tag, article, hidden))

    def handle_data(self, data):
        if self.json_current is not None:
            self.json_current.append(data)
        if self.stack and not self.stack[-1][2]:
            self.visible.append(data)
            if self.current_paragraph is not None:
                self.current_paragraph.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.json_current is not None:
            try:
                self.json_scripts.append(json.loads("".join(self.json_current), object_pairs_hook=_pairs))
            except (ValueError, RecursionError):
                self.invalid_metadata = True
            self.json_current = None
        if tag == "p" and self.current_paragraph is not None:
            paragraph = re.sub(r"\s+", " ", "".join(self.current_paragraph)).strip()
            if paragraph:
                self.paragraphs.append(paragraph)
            self.current_paragraph = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def _parser(document: str) -> _PublicParser:
    if not isinstance(document, str) or len(document.encode("utf-8")) > MAX_BYTES:
        raise PublisherSourceError("publisher_document_invalid")
    parser = _PublicParser()
    parser.feed(document)
    parser.close()
    return parser


def _structured(parser: _PublicParser, page_url: str) -> StructuredArticle | None:
    page_url = normalize_publisher_url(page_url, article=True)
    if parser.invalid_metadata:
        return None
    for script in parser.json_scripts:
        for node in _nodes(script):
            types = node.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if not any(kind in {"Article", "NewsArticle", "ReportageNewsArticle"} for kind in types if isinstance(kind, str)):
                continue
            title, published = node.get("headline"), node.get("datePublished")
            if not isinstance(title, str) or not title.strip() or len(title) > 600 or not isinstance(published, str) or not published.strip() or len(published) > 100:
                continue
            identity = node.get("url") or node.get("mainEntityOfPage") or page_url
            if isinstance(identity, dict):
                identity = identity.get("@id") or identity.get("url")
            try:
                identity = normalize_publisher_url(identity, article=True)
            except PublisherSourceError:
                continue
            if identity != page_url:
                continue
            blocked = parser.paywall or _restricted(node) or bool(_GATE.search(" ".join(parser.visible)))
            flag = node.get("isAccessibleForFree")
            free = True if flag is True or flag == "true" else False if blocked else None
            body = node.get("articleBody", "")
            body = body if isinstance(body, str) else ""
            # JSON-LD body is public metadata, but an explicit restriction always
            # wins over any body supplied alongside it. Never read hidden state.
            return StructuredArticle(html.unescape(title).strip(), identity, published.strip(),
                                     "" if blocked else re.sub(r"\s+", " ", body).strip(),
                                     free, parser.preview, blocked)
    return None


def extract_jsonld_article(document: str, page_url: str) -> StructuredArticle | None:
    """Return original NewsArticle metadata; restricted bodies are discarded."""
    return _structured(_parser(document), page_url)


def extract_publisher_article(document: str, page_url: str) -> StructuredArticle | None:
    """Prefer public article paragraphs to JSON-LD body, preserving preview status.

    CNBC presently exposes dates/title in JSON-LD and body in article paragraphs.
    A preview is evidence only for its visible text, never proof of completeness.
    HTTP failures must be rejected by the caller before reaching this parser.
    """
    parser = _parser(document)
    structured = _structured(parser, page_url)
    if structured is None or structured.access_blocked:
        return structured
    text = " ".join(parser.paragraphs)
    return replace(structured, text=text or structured.text)


def _blocked(parser: _PublicParser) -> bool:
    if parser.invalid_metadata or parser.paywall or _GATE.search(" ".join(parser.visible)):
        return True
    for script in parser.json_scripts:
        for node in _nodes(script):
            types = node.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if any(kind in {"Article", "NewsArticle", "ReportageNewsArticle"} for kind in types if isinstance(kind, str)) and _restricted(node):
                return True
    return False


def extract_html_article_body(document: str) -> str:
    """Extract public paragraphs only, refusing explicit gates/restricted articles."""
    parser = _parser(document)
    return "" if _blocked(parser) else " ".join(parser.paragraphs)


def article_coverage(document: str) -> str:
    """Label evidence conservatively; public HTML never proves full coverage."""
    parser = _parser(document)
    if _blocked(parser):
        return "restricted"
    return "public_excerpt" if parser.preview else "public_text"
