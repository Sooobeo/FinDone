"""Immediate news requests using only the requesting bot's configuration.

Each Telegram message is claimed once, independently of calendar dates and the
08:00 schedule. URL reservations precede the transport handoff, just as for cron;
an interrupted or ambiguous send must never trigger an automatic duplicate.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping

from .config import ConfigurationError, Settings
from .content import ContentRepository
from .model import model_from_env
from .news import NewsResult, NewsService, render_news_messages
from .news_archive import NewsArchive, archive_path
from .state import StateStore, utc_time
from .word_levels import WordLevels

KST = timezone(timedelta(hours=9), "Asia/Seoul")
# Telegram message IDs are persistent identities rather than daily cron slots.
SUBMISSION_NAMESPACE = "telegram"


def reserve_news_result(state: StateStore, user_id: int, result: NewsResult,
                        *, now: datetime) -> NewsResult:
    """Keep only articles whose atomic URL reservation this caller wins.

    Another immediate request or the scheduled newsletter may finish preparing
    the same article concurrently. INSERT OR IGNORE prevents both from emitting
    it even when both started before either URL was visible as seen.
    """
    if not result.articles:
        return result
    reserved = tuple(article for article in result.articles
                     if state.record_news(user_id, article.url, article.published_at, sent_at=now))
    return NewsResult(reserved, "" if reserved else "오늘 소개할 신규 기사 없음")


def run_news_now(environment: Mapping[str, str], *, submission_id: str,
                 now: datetime | None = None) -> list[str]:
    """Prepare news immediately, once per authorized Telegram submission.

    Authorization of the incoming platform/chat is the plugin's responsibility;
    configuration still requires exactly one numeric owner and an explicit state
    path so a missing routed-profile value cannot select the learning bot's DB.
    """
    if (not isinstance(submission_id, str) or not submission_id.strip()
            or len(submission_id) > 200
            or any(ord(character) < 32 for character in submission_id)):
        raise ValueError("A persistent Telegram submission ID is required")
    if not environment.get("STATE_DB_PATH", "").strip():
        raise ConfigurationError("Immediate news requires an explicit STATE_DB_PATH")
    settings = Settings.from_env(environment)
    now = utc_time(now).astimezone(KST)
    owner = int(settings.user_id)
    with StateStore(settings.state_db) as state:
        if not state.claim_job(owner, "news_now", SUBMISSION_NAMESPACE, submission_id, now=now):
            return []
        content = None
        try:
            content = ContentRepository(settings.content_db, settings.content_manifest)
            model = model_from_env(environment)
            levels = WordLevels.from_env(environment) if model is not None and settings.news_focus == "general" else None
            result = NewsService(content, state, model=model, word_levels=levels, focus=settings.news_focus).prepare(owner, now=now)
            if model is None:
                result = NewsResult((), "뉴스 요약 모델이 아직 연결되지 않았습니다. 연결 후 /now로 다시 요청해 주세요.")
            result = reserve_news_result(state, owner, result, now=now)
            response = render_news_messages(result)
            if result.articles:
                with NewsArchive(archive_path(environment)) as archive:
                    for article, body in zip(result.articles, response):
                        archive.prepare_message(owner, article, body, now=now)
            state.finish_job(owner, "news_now", SUBMISSION_NAMESPACE, submission_id,
                             status="emitted", now=now)
            return response
        except Exception:
            # Symbolic code only: provider exceptions can include credentials.
            state.finish_job(owner, "news_now", SUBMISSION_NAMESPACE, submission_id,
                             status="failed", error_code="news_now_processing_failed", now=now)
            return ["뉴스를 준비하지 못했습니다. 로컬 뉴스 설정을 확인한 뒤 /now로 다시 요청해 주세요."]
        finally:
            if content is not None:
                content.close()
