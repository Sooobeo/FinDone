"""Hermes gateway interceptor; every Telegram path returns a skip directive.

Hermes invokes this hook before its own authorization, and hook exceptions
otherwise fall through to its agent. Keep even lazy imports inside the guard.
"""

from __future__ import annotations

import asyncio
import logging
import re

_LOG = logging.getLogger("findone_hermes.plugin")
_OWNER_ID = re.compile(r"[1-9][0-9]*\Z")
_NEWS_COMMAND = re.compile(r"/(now|word|vocab|words)(?:@([A-Za-z0-9_]+))?\Z")
_VOCAB_ANSWER = re.compile(r"[1-4]\Z")
_NEWS_HELP = (
    "FinDone 뉴스 전용 봇입니다. 뉴스는 매일 08:00(한국 시간)에 발송됩니다.\n"
    "/now — 지금 최신 뉴스를 보내기\n"
    "기사 메시지에 답장으로 /word yield — 기사 속 단어 저장\n"
    "/words — 저장한 단어장\n"
    "/vocab 5 — 저장한 단어로 퀴즈 5개\n"
    "단어 퀴즈 답은 1~4 중 하나를 보내세요."
)
_BATCH_ID = re.compile(
    r"^회차 ID:\s*([0-9a-fA-F]{32}|"
    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\s*$",
    re.MULTILINE,
)


def _skip(reason: str) -> dict[str, str]:
    return {"action": "skip", "reason": reason}


def _warn(message: str) -> None:
    try:
        _LOG.warning(message)
    except Exception:
        # A custom logger/handler must not turn a protected failure into dispatch.
        pass


async def pre_gateway_dispatch(event=None, gateway=None, session_store=None, **kwargs):
    """Handle an authorized private DM and prevent any Telegram agent fallthrough."""
    del session_store, kwargs
    try:
        source = event.source
        platform = source.platform
        platform_name = getattr(platform, "value", platform)
        if platform_name != "telegram":
            return None

        # Hermes multiplexes profile credentials through a context-local scope;
        # os.environ would select the default profile's owner and bot mode.
        from agent.secret_scope import get_secret

        allowed = get_secret("TELEGRAM_ALLOWED_USERS", "").strip()
        user_id = str(source.user_id)
        chat_id = str(source.chat_id)
        chat_type = source.chat_type
        if (
            not _OWNER_ID.fullmatch(allowed)
            or user_id != allowed
            or chat_id != allowed
            or chat_type != "dm"
        ):
            return _skip("findone-unauthorized")

        submission_id = getattr(event, "message_id", None)
        mode = get_secret("FINDONE_TELEGRAM_MODE", "learning").strip()
        if mode not in ("learning", "news"):
            return _skip("findone-invalid-mode")
        # Route through the receiving profile's bot. A missing/disconnected
        # profile adapter must not borrow the default profile's connection.
        adapter = gateway._delivery_adapter_for(source)
        if adapter is None:
            return _skip("findone-unavailable-adapter")
        news_environment = None
        is_news_now = False
        if mode == "news":
            # A separate news profile must never import the learning service or
            # create/open its state DB. Vocabulary uses the news profile's DB.
            command_parts = event.text.strip().split(maxsplit=1)
            command = _NEWS_COMMAND.fullmatch(command_parts[0]) if command_parts else None
            if command and command[2]:
                # Hermes tracks BotFather renames here; never act on a command
                # addressed to another bot or an unknown receiving identity.
                recipient = adapter._current_bot_username()
                if not recipient or command[2].lower() != recipient.lower():
                    return _skip("findone-other-bot")
            is_news_now = bool(command and command[1] == "now" and len(command_parts) == 1)
            is_vocabulary = bool(command and command[1] != "now")
            is_vocab_answer = bool(_VOCAB_ANSWER.fullmatch(event.text.strip()))
            if is_news_now or is_vocabulary or is_vocab_answer:
                if submission_id is None or not _OWNER_ID.fullmatch(str(submission_id)):
                    return _skip("findone-missing-submission-id")
                from agent.secret_scope import current_secret_scope

                environment = current_secret_scope()
                if environment is None:
                    return _skip("findone-missing-news-scope")
                # Copy this profile's complete configuration before crossing
                # the thread boundary; process-global defaults belong to the
                # learning profile and must never supply news model settings.
                news_environment = dict(environment)
                if is_news_now:
                    from findone_hermes.news_now import run_news_now

                    replies = await asyncio.to_thread(
                        run_news_now,
                        news_environment,
                        submission_id=str(submission_id),
                    )
                else:
                    from findone_hermes.news_learning import handle_news_learning

                    # Telegram normalizes the reply ID here. Its own-message
                    # flag is not populated by this pinned adapter; the backend
                    # verifies this ID against the news profile's sent archive.
                    reply_id = getattr(event, "reply_to_message_id", None)
                    reply_id = str(reply_id) if reply_id is not None else None
                    if reply_id is not None and not _OWNER_ID.fullmatch(reply_id):
                        reply_id = None
                    text = event.text.strip()
                    if command:
                        text = "/" + command[1]
                        if len(command_parts) == 2:
                            text += " " + command_parts[1]
                    replies = await asyncio.to_thread(
                        handle_news_learning,
                        news_environment,
                        text,
                        submission_id=str(submission_id),
                        reply_to_message_id=reply_id,
                    )
            else:
                replies = [_NEWS_HELP]
        elif mode == "learning":
            # Lazy import ensures a broken package/config cannot disable the
            # guard and let the normal Hermes agent consume a learner's answer.
            from findone_hermes.gateway import handle_message

            batch_id = None
            if getattr(event, "reply_to_is_own_message", False):
                replied_text = getattr(event, "reply_to_text", None)
                match = _BATCH_ID.search(replied_text) if isinstance(replied_text, str) else None
                if match:
                    batch_id = match[1]
            replies = await asyncio.to_thread(
                handle_message,
                "telegram",
                user_id,
                chat_id,
                chat_type,
                event.text,
                submission_id=str(submission_id) if submission_id is not None else None,
                batch_id=batch_id,
            )
        for reply in replies:
            from findone_hermes.presentation import hermes_markdown

            result = await adapter.send(
                chat_id,
                hermes_markdown(reply),
                reply_to=str(submission_id) if submission_id is not None else None,
            )
            if not getattr(result, "success", False):
                # A transport error may be ambiguous. Never retry or fall through.
                _warn("FinDone Telegram reply delivery failed; dispatch blocked")
                return _skip("findone-delivery-failed")
            if is_news_now:
                receipt_failed = False
                delivered_id = getattr(result, "message_id", None)
                if delivered_id is None or not _OWNER_ID.fullmatch(str(delivered_id)):
                    receipt_failed = True
                else:
                    try:
                        from findone_hermes.news_archive import record_news_delivery

                        # Match the exact prepared body, never a user-visible ID
                        # or an arbitrary link copied from an incoming reply.
                        await asyncio.to_thread(
                            record_news_delivery,
                            news_environment,
                            chat_id=chat_id,
                            message_id=str(delivered_id),
                            text=reply,
                        )
                    except Exception:
                        receipt_failed = True
                if receipt_failed:
                    _warn("FinDone news article receipt failed; dispatch blocked")
                    notice = await adapter.send(
                        chat_id,
                        "기사 연결을 저장하지 못해 이 기사에서는 /word를 사용할 수 없습니다.",
                        reply_to=str(submission_id),
                    )
                    if not getattr(notice, "success", False):
                        return _skip("findone-delivery-failed")
                    return _skip("findone-news-archive-failed")
            elif news_environment is not None:
                delivered_id = getattr(result, "message_id", None)
                if delivered_id is None or not _OWNER_ID.fullmatch(str(delivered_id)):
                    _warn("FinDone news learning receipt ID unavailable; dispatch blocked")
                    return _skip("findone-news-learning-receipt-unavailable")
                from findone_hermes.news_learning import record_news_learning_delivery

                # The backend binds only an exact prepared question body; help
                # and status responses return False without creating a receipt.
                # Any error or cancellation stops here, after the one send.
                await asyncio.to_thread(
                    record_news_learning_delivery,
                    news_environment,
                    chat_id=chat_id,
                    message_id=str(delivered_id),
                    text=reply,
                )
        return _skip("findone-handled")
    except asyncio.CancelledError:
        # Returning the directive also protects shutdown/cancellation races from
        # becoming a normal agent turn; an ambiguous delivery is never retried.
        return _skip("findone-cancelled")
    except Exception:
        # Do not log exception text, inbound content, tokens, or personal IDs.
        _warn("FinDone Telegram handling failed; dispatch blocked")
        return _skip("findone-error")


def register(ctx):
    """Register only interception; no model-callable tool or injected prompt."""
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)
