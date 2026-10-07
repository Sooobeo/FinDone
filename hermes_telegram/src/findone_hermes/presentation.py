"""Telegram emphasis at the transport boundary, keeping receipt bodies intact."""
from __future__ import annotations

import re

_HEADING = re.compile(
    r"^(?:📝|📘|💡|❓|✍️|📋|✅|❌|📖|🔎|📊|📌|ℹ️|📚|🔁|⏭️|⏳|🌱|⚠️|"
    r"⏸️|📰|🧭|🔗|💼|🧠|🔤|📒|💾|↩️) "
)
_TERMS = ("📚 금융 전문 어휘", "📚 고급 어휘", "📚 기사 어휘", "💼 중요한 비즈니스 구문")


def emphasis_spans(text: str) -> list[tuple[int, int]]:
    """Return Python character spans; prose, links and answer choices stay plain."""
    spans = []
    position = 0
    article_title = False
    terms = False
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        if line:
            heading = bool(_HEADING.match(line)) or line in {
                "🇬🇧 원문 발췌 요약", "🇰🇷 한국어 · 모델 번역",
            }
            # The headline is the next nonempty line after the newsletter title.
            if heading or article_title:
                spans.append((position, position + len(line)))
            elif terms:
                term = re.match(r"\d+\. (.+?)(?: · .*)?$", line)
                if term:
                    spans.append((position + term.start(1), position + term.end(1)))
            article_title = line == "📰 FinDone | 금융 영어 뉴스"
            if heading:
                terms = line.startswith(_TERMS)
        position += len(raw_line)
    return spans


def telegram_entities(text: str) -> list[dict[str, str | int]]:
    """Telegram entity offsets count UTF-16 units, including emoji surrogates."""
    return [
        {"type": "bold", "offset": len(text[:start].encode("utf-16-le")) // 2,
         "length": len(text[start:end].encode("utf-16-le")) // 2}
        for start, end in emphasis_spans(text)
    ]


def hermes_markdown(text: str) -> str:
    """Hermes adapters consume standard Markdown and escape Telegram MarkdownV2."""
    for start, end in reversed(emphasis_spans(text)):
        # Do not create ambiguous nested delimiters in source-provided headlines.
        if "*" not in text[start:end]:
            text = text[:start] + "**" + text[start:end] + "**" + text[end:]
    return text
