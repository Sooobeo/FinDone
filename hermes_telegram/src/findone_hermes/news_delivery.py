"""One-attempt direct delivery for the dedicated news profile's 08:00 cron.

Stdout contains only local symbolic status. Article bodies and credentials never
enter Hermes's cron delivery channel; each verified Telegram receipt is archived.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import sys
from typing import Mapping, Sequence
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import Settings
from .content import ContentRepository
from .jobs import KST, slot_is_due
from .model import model_from_env
from .news import NewsResult, NewsService, render_news_messages
from .news_archive import NewsArchive, archive_path
from .news_now import reserve_news_result
from .state import StateStore, utc_time
from .word_levels import WordLevels

_TOKEN = re.compile(r"[1-9][0-9]*:[A-Za-z0-9_-]{20,100}\Z")
_SLOT = "08:00"


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    sent_messages: int = 0
    error_code: str | None = None


class NewsDeliveryError(RuntimeError):
    def __init__(self, code: str, *, uncertain: bool = False):
        self.code, self.uncertain = code, uncertain
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NewsDeliveryError("telegram_send_uncertain", uncertain=True)


def _configuration(environment: Mapping[str, str]) -> tuple[Settings, str]:
    # An explicit routed profile is authoritative. Never read os.environ here.
    if environment.get("FINDONE_TELEGRAM_MODE", "").strip() != "news":
        raise NewsDeliveryError("news_configuration_failed")
    if not environment.get("STATE_DB_PATH", "").strip():
        raise NewsDeliveryError("news_configuration_failed")
    token = environment.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not _TOKEN.fullmatch(token):
        raise NewsDeliveryError("news_configuration_failed")
    try:
        return Settings.from_env(environment), token
    except Exception:
        raise NewsDeliveryError("news_configuration_failed") from None


def _messages(messages: Sequence[str]) -> list[str]:
    if isinstance(messages, (str, bytes)) or not isinstance(messages, (list, tuple)) or not 1 <= len(messages) <= 2:
        raise NewsDeliveryError("news_message_invalid")
    for body in messages:
        if (
            not isinstance(body, str) or not body.strip()
            or len(body.encode("utf-16-le")) // 2 > 3000
            or any(ord(char) < 32 and char not in "\n\r\t" for char in body)
        ):
            raise NewsDeliveryError("news_message_invalid")
    if len(set(messages)) != len(messages):
        raise NewsDeliveryError("news_message_invalid")
    return list(messages)


def _send_message(token: str, owner: int, body: str) -> tuple[str, str]:
    request = Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        json.dumps({"chat_id": owner, "text": body, "disable_web_page_preview": True}, ensure_ascii=False).encode("utf-8"),
        {"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise NewsDeliveryError("telegram_send_uncertain", uncertain=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise NewsDeliveryError("telegram_send_uncertain", uncertain=True)
        if payload.get("ok") is not True:
            raise NewsDeliveryError("telegram_send_failed")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise NewsDeliveryError("telegram_send_uncertain", uncertain=True)
        chat, message_id = result.get("chat"), result.get("message_id")
        if (
            not isinstance(chat, dict) or type(chat.get("id")) is not int
            or chat["id"] != owner or chat.get("type") != "private"
            or type(message_id) is not int or message_id <= 0
        ):
            raise NewsDeliveryError("telegram_send_uncertain", uncertain=True)
        return str(chat["id"]), str(message_id)
    except NewsDeliveryError:
        raise
    except Exception:
        # URLs in transport exceptions contain the BotFather credential.
        raise NewsDeliveryError("telegram_send_uncertain", uncertain=True) from None


def _deliver(token: str, owner: int, archive: NewsArchive,
             messages: list[str], *, article: bool, now: datetime) -> DeliveryResult:
    sent = 0
    for body in messages:
        try:
            chat_id, message_id = _send_message(token, owner, body)
            sent += 1
            recorded = archive.record_delivery(owner, chat_id, message_id, body, now=now)
            if article and not recorded:
                raise NewsDeliveryError("news_receipt_failed", uncertain=True)
        except NewsDeliveryError as error:
            return DeliveryResult("uncertain" if error.uncertain else "failed", sent, error.code)
        except Exception:
            # The API may have accepted the message before a receipt DB failure.
            return DeliveryResult("uncertain", sent, "news_receipt_failed")
    return DeliveryResult("delivered", sent)


def _finish(state: StateStore, owner: int, kind: str, date_key: str, slot: str,
            result: DeliveryResult, now: datetime) -> None:
    status = result.status if result.status in {"failed", "uncertain"} else "emitted"
    state.finish_job(owner, kind, date_key, slot, status=status, error_code=result.error_code, now=now)


def _record_completion(state: StateStore, owner: int, kind: str, date_key: str,
                       slot: str, result: DeliveryResult, now: datetime) -> DeliveryResult:
    try:
        _finish(state, owner, kind, date_key, slot, result, now)
        return result
    except Exception:
        # An existing claim stays consumed even when final bookkeeping fails.
        # Successful API sends cannot be reported as safely retryable failures.
        uncertain = result.status in {"delivered", "uncertain"} or bool(result.sent_messages)
        return DeliveryResult("uncertain" if uncertain else "failed", result.sent_messages, "news_job_record_failed")


def run_scheduled_news(environment: Mapping[str, str], *, now: datetime | None = None) -> DeliveryResult:
    """Prepare and send the 08:00 KST slot once, sharing the old cron claim key."""
    content = None
    try:
        settings, token = _configuration(environment)
        now = utc_time(now)
        if not slot_is_due("news", _SLOT, now):
            return DeliveryResult("not_due")
        owner, date_key = int(settings.user_id), now.astimezone(KST).date().isoformat()
        with StateStore(settings.state_db) as state:
            if not state.claim_job(owner, "news", date_key, _SLOT, now=now):
                return DeliveryResult("already_claimed")
            try:
                model = model_from_env(environment)
                if model is None:
                    result = NewsResult((), "뉴스 요약 모델이 아직 연결되지 않았습니다. 로컬 뉴스 설정을 확인해 주세요.")
                else:
                    content = ContentRepository(settings.content_db, settings.content_manifest)
                    levels = WordLevels.from_env(environment) if settings.news_focus == "general" else None
                    result = NewsService(content, state, model=model, word_levels=levels, focus=settings.news_focus).prepare(owner, now=now)
                result = reserve_news_result(state, owner, result, now=now)
                messages = _messages(render_news_messages(result))
                if result.articles and len(messages) != len(result.articles):
                    raise NewsDeliveryError("news_message_invalid")
                with NewsArchive(archive_path(environment)) as archive:
                    for article, body in zip(result.articles, messages):
                        archive.prepare_message(owner, article, body, now=now)
                    delivered = _deliver(token, owner, archive, messages, article=bool(result.articles), now=now)
                return _record_completion(state, owner, "news", date_key, _SLOT, delivered, now)
            except Exception:
                result = DeliveryResult("failed", error_code="news_processing_failed")
                return _record_completion(state, owner, "news", date_key, _SLOT, result, now)
    except Exception:
        return DeliveryResult("failed", error_code="news_configuration_failed")
    finally:
        if content is not None:
            try:
                content.close()
            except Exception:
                # Cleanup cannot expose a path or replace a confirmed receipt.
                pass


def send_prepared_news(environment: Mapping[str, str], messages: Sequence[str],
                       *, now: datetime | None = None) -> DeliveryResult:
    """Send already archived article bodies once; never synthesize or alter them."""
    try:
        settings, token = _configuration(environment)
        now = utc_time(now)
        bodies = _messages(messages)
        owner = int(settings.user_id)
        path = archive_path(environment)
        if not path.is_file():
            raise NewsDeliveryError("news_prepared_message_missing")
        with NewsArchive(path) as archive:
            for body in bodies:
                body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
                prepared = archive.connection.execute(
                    "SELECT 1 FROM news_prepared_messages WHERE user_id=? AND body_hash=?", (owner, body_hash),
                ).fetchone()
                if prepared is None:
                    raise NewsDeliveryError("news_prepared_message_missing")
            bundle = hashlib.sha256(json.dumps(bodies, ensure_ascii=False).encode("utf-8")).hexdigest()
            with StateStore(settings.state_db) as state:
                if not state.claim_job(owner, "news_prepared", "telegram", bundle, now=now):
                    return DeliveryResult("already_claimed")
                delivered = _deliver(token, owner, archive, bodies, article=True, now=now)
                return _record_completion(state, owner, "news_prepared", "telegram", bundle, delivered, now)
    except NewsDeliveryError as error:
        return DeliveryResult("uncertain" if error.uncertain else "failed", error_code=error.code)
    except Exception:
        return DeliveryResult("failed", error_code="news_processing_failed")


def main(environment: Mapping[str, str]) -> int:
    result = run_scheduled_news(environment)
    print("FinDone news delivery: " + result.status)
    if result.status in {"failed", "uncertain"}:
        print("FinDone news error: " + (result.error_code or "news_processing_failed"), file=sys.stderr)
        return 1
    return 0
