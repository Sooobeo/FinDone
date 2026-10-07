"""Test the pre-authentication guard against Hermes' actual async hook shape."""

from __future__ import annotations

import asyncio
from enum import Enum
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


class Platform(Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"


_PLUGIN_PATH = Path(__file__).resolve().parents[1] / "hermes" / "plugin" / "__init__.py"
_SPEC = importlib.util.spec_from_file_location("findone_test_plugin", _PLUGIN_PATH)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)


class Adapter:
    def __init__(self, *, failure=None, success=True, username="hermes_engnews_bot", message_id="auto"):
        self.sent = []
        self.failure = failure
        self.success = success
        self.username = username
        self.message_id = message_id

    def _current_bot_username(self):
        return self.username

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append((chat_id, content, reply_to))
        if self.failure:
            raise self.failure
        message_id = str(7000 + len(self.sent)) if self.message_id == "auto" else self.message_id
        return SimpleNamespace(success=self.success, message_id=message_id)


def make_event(**overrides):
    source = SimpleNamespace(
        platform=overrides.pop("platform", Platform.TELEGRAM),
        user_id=overrides.pop("user_id", "123456"),
        chat_id=overrides.pop("chat_id", "123456"),
        chat_type=overrides.pop("chat_type", "dm"),
    )
    fields = {"text": "2,4", "message_id": "456", "source": source}
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_gateway(adapter):
    return SimpleNamespace(
        adapters={Platform.TELEGRAM: adapter},
        _delivery_adapter_for=Mock(return_value=adapter),
    )


class HermesPluginTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.adapter = Adapter()
        self.gateway = make_gateway(self.adapter)
        self.handler = Mock(return_value=["first part", "second part"])
        service = ModuleType("findone_hermes.gateway")
        service.handle_message = self.handler
        self.news_handler = Mock(return_value=["current news"])
        news_service = ModuleType("findone_hermes.news_now")
        news_service.run_news_now = self.news_handler
        self.news_learning_handler = Mock(return_value=["vocab reply"])
        news_learning = ModuleType("findone_hermes.news_learning")
        news_learning.handle_news_learning = self.news_learning_handler
        self.news_learning_receipt = Mock(return_value=False)
        news_learning.record_news_learning_delivery = self.news_learning_receipt
        self.news_receipt = Mock()
        news_archive = ModuleType("findone_hermes.news_archive")
        news_archive.record_news_delivery = self.news_receipt
        secret_scope = ModuleType("agent.secret_scope")
        self.secret_get = Mock(side_effect=lambda name, default=None: os.environ.get(name, default))
        secret_scope.get_secret = self.secret_get
        self.news_environment = {
            "TELEGRAM_ALLOWED_USERS": "123456",
            "FINDONE_TELEGRAM_MODE": "news",
            "FINDONE_MODEL_BASE_URL": "http://news-profile.example/v1",
            "FINDONE_MODEL_NAME": "news-profile-model",
            "FINDONE_MODEL_API_KEY": "profile-model-key",
            "STATE_DB_PATH": "news-profile-state.sqlite3",
        }
        self.scope_get = Mock(return_value=self.news_environment)
        secret_scope.current_secret_scope = self.scope_get
        self.env_patch = patch.dict(
            os.environ,
            {"TELEGRAM_ALLOWED_USERS": "123456", "FINDONE_TELEGRAM_MODE": "learning"},
        )
        self.service_patch = patch.dict(
            sys.modules,
            {
                "findone_hermes.gateway": service,
                "findone_hermes.news_now": news_service,
                "findone_hermes.news_learning": news_learning,
                "findone_hermes.news_archive": news_archive,
                "agent.secret_scope": secret_scope,
            },
        )
        self.env_patch.start()
        self.service_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(self.service_patch.stop)

    async def test_authorized_dm_uses_original_platform_adapter_and_skips(self):
        result = await plugin.pre_gateway_dispatch(make_event(), self.gateway, object())
        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "findone-handled")
        self.handler.assert_called_once_with(
            "telegram", "123456", "123456", "dm", "2,4", submission_id="456", batch_id=None
        )
        self.assertEqual(
            self.adapter.sent,
            [("123456", "first part", "456"), ("123456", "second part", "456")],
        )
        self.gateway._delivery_adapter_for.assert_called_once()

    async def test_news_emphasis_keeps_exact_prepared_body_for_article_receipt(self):
        body = "📰 FinDone | 금융 영어 뉴스\n\nBanks & markets\n\n🔎 원문\nhttps://example.com/news"
        self.news_handler.return_value = [body]
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result["reason"], "findone-handled")
        self.assertIn("**Banks & markets**", self.adapter.sent[0][1])
        self.news_receipt.assert_called_once_with(
            self.news_environment, chat_id="123456", message_id="7001", text=body,
        )

    async def test_unauthorized_and_group_events_are_silent_before_service_import(self):
        for values in (
            {"user_id": "999999"},
            {"chat_id": "999999"},
            {"chat_type": "group", "chat_id": "-123456"},
            {"chat_type": "private"},
            {"chat_type": "channel"},
        ):
            with self.subTest(values=values):
                result = await plugin.pre_gateway_dispatch(make_event(**values), self.gateway)
                self.assertEqual(result["action"], "skip")
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_invalid_allowlist_cannot_fall_through(self):
        for allowed in ("", "*", "123456,999999", "0", "-123456", "１２３４５６"):
            with self.subTest(allowed=allowed), patch.dict(
                os.environ, {"TELEGRAM_ALLOWED_USERS": allowed}
            ):
                result = await plugin.pre_gateway_dispatch(make_event(), self.gateway)
                self.assertEqual(result["action"], "skip")
        self.handler.assert_not_called()

    async def test_other_platform_is_unaffected(self):
        self.assertIsNone(
            await plugin.pre_gateway_dispatch(make_event(platform=Platform.DISCORD), self.gateway)
        )
        self.handler.assert_not_called()

    async def test_reply_to_prior_bot_quiz_preserves_batch_reference(self):
        batch_id = "4f9392791c894b5188f6ab7f722fdd99"
        event = make_event(
            reply_to_is_own_message=True,
            reply_to_text=f"FinDone | quiz\n회차 ID: {batch_id}\nQ1. preserved snapshot",
        )
        result = await plugin.pre_gateway_dispatch(event, self.gateway)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(self.handler.call_args.kwargs["batch_id"], batch_id)

    async def test_other_authors_quoted_text_cannot_supply_batch_reference(self):
        event = make_event(
            reply_to_is_own_message=False,
            reply_to_text="회차 ID: 4f9392791c894b5188f6ab7f722fdd99",
        )
        await plugin.pre_gateway_dispatch(event, self.gateway)
        self.assertIsNone(self.handler.call_args.kwargs["batch_id"])

    async def test_missing_source_and_text_fail_closed(self):
        for event in (None, SimpleNamespace(source=None), make_event(text=None)):
            with self.subTest(event=event):
                if getattr(event, "text", "") is None:
                    self.handler.side_effect = TypeError("secret should never appear")
                result = await plugin.pre_gateway_dispatch(event, self.gateway)
                self.assertEqual(result["action"], "skip")

    async def test_handler_error_never_becomes_an_agent_turn_or_leaks_exception(self):
        self.handler.side_effect = RuntimeError("token-sensitive-value")
        with self.assertLogs("findone_hermes.plugin", level="WARNING") as logs:
            result = await plugin.pre_gateway_dispatch(make_event(), self.gateway)
        self.assertEqual(result["action"], "skip")
        self.assertNotIn("token-sensitive-value", "".join(logs.output))
        self.assertEqual(self.adapter.sent, [])

    async def test_logging_failure_cannot_escape_protected_telegram_scope(self):
        self.handler.side_effect = RuntimeError("private-detail")
        with patch.object(plugin._LOG, "warning", side_effect=RuntimeError("logger failed")):
            result = await plugin.pre_gateway_dispatch(make_event(), self.gateway)
        self.assertEqual(result["action"], "skip")

    async def test_missing_package_still_returns_skip(self):
        with patch.dict(sys.modules, {"findone_hermes.gateway": None}):
            result = await plugin.pre_gateway_dispatch(make_event(), self.gateway)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(self.adapter.sent, [])

    async def test_transport_exception_and_failed_result_do_not_retry(self):
        for adapter in (
            Adapter(failure=RuntimeError("possibly sent")),
            Adapter(success=False),
            Adapter(failure=asyncio.CancelledError()),
        ):
            with self.subTest(adapter=adapter):
                gateway = make_gateway(adapter)
                result = await plugin.pre_gateway_dispatch(make_event(), gateway)
                self.assertEqual(result["action"], "skip")
                self.assertEqual(len(adapter.sent), 1)

    async def test_registration_uses_exact_hook_name(self):
        context = SimpleNamespace(register_hook=Mock())
        plugin.register(context)
        context.register_hook.assert_called_once_with(
            "pre_gateway_dispatch", plugin.pre_gateway_dispatch
        )

    async def test_news_mode_never_imports_learning_even_for_quiz_commands(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}), patch.dict(
            sys.modules, {"findone_hermes.gateway": None}
        ):
            for text in ("/help", "/review", "/stats", "2,4"):
                with self.subTest(text=text):
                    result = await plugin.pre_gateway_dispatch(make_event(text=text), self.gateway)
                    self.assertEqual(result, {"action": "skip", "reason": "findone-handled"})
        self.handler.assert_not_called()
        self.assertEqual(len(self.adapter.sent), 4)
        for chat_id, content, reply_to in self.adapter.sent:
            self.assertEqual((chat_id, reply_to), ("123456", "456"))
            self.assertIn("뉴스 전용", content)
            self.assertIn("08:00(한국 시간)", content)
            self.assertIn("/now", content)

    async def test_news_mode_unauthorized_and_group_events_are_silent(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}), patch.dict(
            sys.modules, {"findone_hermes.gateway": None}
        ):
            for values in (
                {"user_id": "999999"},
                {"chat_id": "999999"},
                {"chat_type": "group", "chat_id": "-123456"},
            ):
                with self.subTest(values=values):
                    result = await plugin.pre_gateway_dispatch(make_event(**values), self.gateway)
                    self.assertEqual(result, {"action": "skip", "reason": "findone-unauthorized"})
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_invalid_mode_fails_closed_without_learning_dispatch(self):
        for mode in ("", "all", "NEWS", "learning,news"):
            with self.subTest(mode=mode), patch.dict(
                os.environ, {"FINDONE_TELEGRAM_MODE": mode}
            ):
                result = await plugin.pre_gateway_dispatch(make_event(), self.gateway)
                self.assertEqual(result, {"action": "skip", "reason": "findone-invalid-mode"})
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_mode_transport_failures_remain_closed_without_retry(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for adapter in (
                Adapter(failure=RuntimeError("possibly sent")),
                Adapter(success=False),
                Adapter(failure=asyncio.CancelledError()),
            ):
                with self.subTest(adapter=adapter):
                    gateway = make_gateway(adapter)
                    result = await plugin.pre_gateway_dispatch(make_event(), gateway)
                    self.assertEqual(result["action"], "skip")
                    self.assertEqual(len(adapter.sent), 1)
        self.handler.assert_not_called()

    async def test_news_profile_uses_scoped_owner_mode_and_receiving_bot(self):
        profile = {"TELEGRAM_ALLOWED_USERS": "777777", "FINDONE_TELEGRAM_MODE": "news"}
        self.secret_get.side_effect = lambda name, default=None: profile.get(name, default)
        receiving_adapter = Adapter()
        self.gateway._delivery_adapter_for.return_value = receiving_adapter
        with patch.dict(sys.modules, {"findone_hermes.gateway": None}):
            result = await plugin.pre_gateway_dispatch(
                make_event(user_id="777777", chat_id="777777", text="/review"), self.gateway
            )
        self.assertEqual(result, {"action": "skip", "reason": "findone-handled"})
        self.assertEqual(self.adapter.sent, [])
        self.assertEqual(len(receiving_adapter.sent), 1)
        self.assertEqual(receiving_adapter.sent[0][0], "777777")
        self.assertIn("뉴스 전용", receiving_adapter.sent[0][1])
        self.handler.assert_not_called()

    async def test_missing_receiving_adapter_never_uses_default_bot_or_learning(self):
        self.gateway._delivery_adapter_for.return_value = None
        for mode in ("learning", "news"):
            with self.subTest(mode=mode), patch.dict(
                os.environ, {"FINDONE_TELEGRAM_MODE": mode}
            ):
                result = await plugin.pre_gateway_dispatch(make_event(), self.gateway)
                self.assertEqual(
                    result, {"action": "skip", "reason": "findone-unavailable-adapter"}
                )
        self.assertEqual(self.adapter.sent, [])
        self.handler.assert_not_called()

    async def test_secret_scope_error_never_falls_back_to_default_owner(self):
        self.secret_get.side_effect = RuntimeError("unscoped private detail")
        with self.assertLogs("findone_hermes.plugin", level="WARNING") as logs:
            result = await plugin.pre_gateway_dispatch(make_event(), self.gateway)
        self.assertEqual(result, {"action": "skip", "reason": "findone-error"})
        self.assertNotIn("unscoped private detail", "".join(logs.output))
        self.assertEqual(self.adapter.sent, [])
        self.handler.assert_not_called()

    async def test_news_now_uses_only_profile_configuration_and_receiving_adapter(self):
        receiving_adapter = Adapter()
        self.gateway._delivery_adapter_for.return_value = receiving_adapter
        with patch.dict(
            os.environ,
            {"FINDONE_TELEGRAM_MODE": "news", "FINDONE_MODEL_NAME": "default-model"},
        ), patch.dict(sys.modules, {"findone_hermes.gateway": None}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result, {"action": "skip", "reason": "findone-handled"})
        self.news_handler.assert_called_once_with(self.news_environment, submission_id="456")
        self.assertIsNot(self.news_handler.call_args.args[0], self.news_environment)
        self.assertEqual(self.news_handler.call_args.args[0]["FINDONE_MODEL_NAME"], "news-profile-model")
        self.assertEqual(receiving_adapter.sent, [("123456", "current news", "456")])
        self.assertEqual(self.adapter.sent, [])
        self.handler.assert_not_called()

    async def test_news_now_addressed_to_current_bot_accepts_case_insensitive_handle(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(
                make_event(text=" /now@HERMES_ENGNEWS_BOT \n"), self.gateway
            )
        self.assertEqual(result["reason"], "findone-handled")
        self.news_handler.assert_called_once()
        self.assertEqual(len(self.adapter.sent), 1)
        self.handler.assert_not_called()

    async def test_news_now_for_another_or_unknown_bot_is_silent(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for username, text in (
                ("hermes_engnews_bot", "/now@learning_bot"),
                ("hermes_engnews_bot", "/now@learning_bot ignored"),
                ("", "/now@hermes_engnews_bot"),
            ):
                with self.subTest(username=username, text=text):
                    adapter = Adapter(username=username)
                    result = await plugin.pre_gateway_dispatch(make_event(text=text), make_gateway(adapter))
                    self.assertEqual(result, {"action": "skip", "reason": "findone-other-bot"})
                    self.assertEqual(adapter.sent, [])
        self.news_handler.assert_not_called()
        self.scope_get.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_now_arguments_and_similar_text_only_show_help(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for text in ("/now extra", "/now@hermes_engnews_bot extra", "/nowadays", "send /now", "/now\nextra"):
                with self.subTest(text=text):
                    result = await plugin.pre_gateway_dispatch(make_event(text=text), self.gateway)
                    self.assertEqual(result["reason"], "findone-handled")
        self.news_handler.assert_not_called()
        self.scope_get.assert_not_called()
        self.handler.assert_not_called()
        self.assertEqual(len(self.adapter.sent), 5)
        self.assertTrue(all("/now" in sent[1] for sent in self.adapter.sent))

    async def test_news_now_missing_message_id_cannot_start_backend_work(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for message_id in (None, "", " ", "not-a-telegram-message", 0, False):
                with self.subTest(message_id=message_id):
                    result = await plugin.pre_gateway_dispatch(
                        make_event(text="/now", message_id=message_id), self.gateway
                    )
                    self.assertEqual(result, {"action": "skip", "reason": "findone-missing-submission-id"})
        self.news_handler.assert_not_called()
        self.scope_get.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_now_unauthorized_or_group_cannot_start_backend_work(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for values in (
                {"user_id": "999999"},
                {"chat_id": "999999"},
                {"chat_type": "group", "chat_id": "-123456"},
            ):
                with self.subTest(values=values):
                    result = await plugin.pre_gateway_dispatch(make_event(text="/now", **values), self.gateway)
                    self.assertEqual(result["reason"], "findone-unauthorized")
        self.news_handler.assert_not_called()
        self.scope_get.assert_not_called()
        self.assertEqual(self.adapter.sent, [])
        self.handler.assert_not_called()

    async def test_learning_now_never_imports_or_calls_news_backend(self):
        with patch.dict(sys.modules, {"findone_hermes.news_now": None}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result["reason"], "findone-handled")
        self.handler.assert_called_once_with(
            "telegram", "123456", "123456", "dm", "/now", submission_id="456", batch_id=None
        )
        self.news_handler.assert_not_called()
        self.scope_get.assert_not_called()

    async def test_news_now_missing_scope_does_not_borrow_process_defaults(self):
        self.scope_get.return_value = None
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news", "FINDONE_MODEL_NAME": "default-model"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result, {"action": "skip", "reason": "findone-missing-news-scope"})
        self.news_handler.assert_not_called()
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_now_backend_error_is_sanitized_and_cannot_dispatch_agent(self):
        self.news_handler.side_effect = RuntimeError("private-model-key")
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}), self.assertLogs(
            "findone_hermes.plugin", level="WARNING"
        ) as logs:
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result, {"action": "skip", "reason": "findone-error"})
        self.assertNotIn("private-model-key", "".join(logs.output))
        self.news_handler.assert_called_once()
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_now_transport_failure_and_cancellation_never_retry(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for adapter, expected_reason in (
                (Adapter(failure=RuntimeError("possibly sent")), "findone-error"),
                (Adapter(success=False), "findone-delivery-failed"),
                (Adapter(failure=asyncio.CancelledError()), "findone-cancelled"),
            ):
                with self.subTest(expected_reason=expected_reason):
                    self.news_handler.reset_mock()
                    result = await plugin.pre_gateway_dispatch(make_event(text="/now"), make_gateway(adapter))
                    self.assertEqual(result, {"action": "skip", "reason": expected_reason})
                    self.news_handler.assert_called_once()
                    self.assertEqual(len(adapter.sent), 1)
        self.handler.assert_not_called()

    async def test_news_now_thread_cancellation_does_not_dispatch_agent(self):
        self.news_handler.side_effect = asyncio.CancelledError()
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result, {"action": "skip", "reason": "findone-cancelled"})
        self.news_handler.assert_called_once()
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_word_uses_normalized_reply_id_without_own_message_flag(self):
        receiving_adapter = Adapter()
        self.gateway._delivery_adapter_for.return_value = receiving_adapter
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}), patch.dict(
            sys.modules, {"findone_hermes.gateway": None}
        ):
            result = await plugin.pre_gateway_dispatch(
                make_event(
                    text="/word yield",
                    reply_to_message_id="321",
                    reply_to_is_own_message=False,
                    reply_to_text="forged article text and ID",
                    raw_message=SimpleNamespace(reply_to_message=SimpleNamespace(message_id=999)),
                ), self.gateway
            )
        self.assertEqual(result["reason"], "findone-handled")
        self.news_learning_handler.assert_called_once_with(
            self.news_environment, "/word yield", submission_id="456", reply_to_message_id="321"
        )
        self.assertIsNot(self.news_learning_handler.call_args.args[0], self.news_environment)
        self.assertEqual(receiving_adapter.sent, [("123456", "vocab reply", "456")])
        self.assertEqual(self.adapter.sent, [])
        self.news_handler.assert_not_called()
        self.news_receipt.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_vocabulary_commands_and_answers_route_only_to_news_backend(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}), patch.dict(
            sys.modules, {"findone_hermes.gateway": None}
        ):
            for text in ("/vocab 5", "/words", "/word", "1", "2", "3", "4"):
                with self.subTest(text=text):
                    self.news_learning_handler.reset_mock()
                    result = await plugin.pre_gateway_dispatch(make_event(text=text), self.gateway)
                    self.assertEqual(result["reason"], "findone-handled")
                    self.news_learning_handler.assert_called_once_with(
                        self.news_environment, text, submission_id="456", reply_to_message_id=None
                    )
        self.news_handler.assert_not_called()
        self.news_receipt.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_vocabulary_bot_suffix_is_checked_and_removed_before_backend(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(
                make_event(text="/vocab@HERMES_ENGNEWS_BOT 5"), self.gateway
            )
        self.assertEqual(result["reason"], "findone-handled")
        self.news_learning_handler.assert_called_once_with(
            self.news_environment, "/vocab 5", submission_id="456", reply_to_message_id=None
        )

    async def test_news_vocabulary_for_other_or_unknown_bot_is_silent(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for username, text in (
                ("hermes_engnews_bot", "/word@learning_bot yield"),
                ("hermes_engnews_bot", "/vocab@learning_bot 5"),
                ("hermes_engnews_bot", "/words@learning_bot"),
                ("", "/words@hermes_engnews_bot"),
            ):
                adapter = Adapter(username=username)
                result = await plugin.pre_gateway_dispatch(make_event(text=text), make_gateway(adapter))
                self.assertEqual(result["reason"], "findone-other-bot")
                self.assertEqual(adapter.sent, [])
        self.news_learning_handler.assert_not_called()
        self.scope_get.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_invalid_reply_ids_are_not_sent_as_article_references(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for reply_id in (None, "", " ", "fake", 0, False):
                with self.subTest(reply_id=reply_id):
                    self.news_learning_handler.reset_mock()
                    await plugin.pre_gateway_dispatch(
                        make_event(text="/word yield", reply_to_message_id=reply_id), self.gateway
                    )
                    self.assertIsNone(self.news_learning_handler.call_args.kwargs["reply_to_message_id"])

    async def test_news_vocabulary_authorization_and_submission_id_precede_backend(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for text in ("/word yield", "/vocab 5", "/words", "2"):
                for values, reason in (
                    ({"user_id": "999999"}, "findone-unauthorized"),
                    ({"chat_type": "group"}, "findone-unauthorized"),
                    ({"message_id": None}, "findone-missing-submission-id"),
                ):
                    with self.subTest(text=text, values=values):
                        result = await plugin.pre_gateway_dispatch(make_event(text=text, **values), self.gateway)
                        self.assertEqual(result["reason"], reason)
        self.news_learning_handler.assert_not_called()
        self.scope_get.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_vocabulary_missing_scope_never_borrows_default_settings(self):
        self.scope_get.return_value = None
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/words"), self.gateway)
        self.assertEqual(result["reason"], "findone-missing-news-scope")
        self.news_learning_handler.assert_not_called()
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_learning_receipt_uses_receiving_bot_message_id_exact_body_and_scope(self):
        receiving_adapter = Adapter()
        self.gateway._delivery_adapter_for.return_value = receiving_adapter
        self.news_learning_handler.return_value = ["prepared question one", "prepared question two"]
        self.news_learning_receipt.return_value = True
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news", "FINDONE_MODEL_NAME": "default-model"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), self.gateway)
        self.assertEqual(result["reason"], "findone-handled")
        self.assertEqual(self.news_learning_receipt.call_args_list, [
            call(self.news_environment, chat_id="123456", message_id="7001", text="prepared question one"),
            call(self.news_environment, chat_id="123456", message_id="7002", text="prepared question two"),
        ])
        self.assertIsNot(self.news_learning_receipt.call_args.args[0], self.news_environment)
        self.assertEqual(self.adapter.sent, [])
        self.news_receipt.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_learning_receipt_false_for_help_is_a_harmless_noop(self):
        self.news_learning_handler.return_value = ["word command help"]
        self.news_learning_receipt.return_value = False
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/word"), self.gateway)
        self.assertEqual(result["reason"], "findone-handled")
        self.assertEqual(self.adapter.sent, [("123456", "word command help", "456")])
        self.news_learning_receipt.assert_called_once_with(
            self.news_environment, chat_id="123456", message_id="7001", text="word command help"
        )

    async def test_news_learning_failed_send_never_creates_a_question_receipt(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for adapter, reason in (
                (Adapter(success=False), "findone-delivery-failed"),
                (Adapter(failure=RuntimeError("ambiguous question send")), "findone-error"),
                (Adapter(failure=asyncio.CancelledError()), "findone-cancelled"),
            ):
                with self.subTest(reason=reason):
                    result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), make_gateway(adapter))
                    self.assertEqual(result["reason"], reason)
                    self.assertEqual(len(adapter.sent), 1)
        self.news_learning_receipt.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_learning_missing_receipt_id_cannot_bind_or_send_remaining_questions(self):
        self.news_learning_handler.return_value = ["prepared question", "remaining question"]
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for message_id in (None, "", "invalid-id", 0, False):
                with self.subTest(message_id=message_id):
                    adapter = Adapter(message_id=message_id)
                    result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), make_gateway(adapter))
                    self.assertEqual(result["reason"], "findone-news-learning-receipt-unavailable")
                    self.assertEqual(adapter.sent, [("123456", "prepared question", "456")])
        self.news_learning_receipt.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_learning_receipt_error_is_sanitized_and_does_not_resend(self):
        self.news_learning_handler.return_value = ["prepared question", "remaining question"]
        self.news_learning_receipt.side_effect = RuntimeError("private-learning-receipt-token")
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}), self.assertLogs(
            "findone_hermes.plugin", level="WARNING"
        ) as logs:
            result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), self.gateway)
        self.assertEqual(result["reason"], "findone-error")
        self.assertEqual(self.adapter.sent, [("123456", "prepared question", "456")])
        self.assertNotIn("private-learning-receipt-token", "".join(logs.output))
        self.news_learning_receipt.assert_called_once()
        self.handler.assert_not_called()

    async def test_news_learning_receipt_cancellation_never_retries_or_dispatches_agent(self):
        self.news_learning_handler.return_value = ["prepared question", "remaining question"]
        self.news_learning_receipt.side_effect = asyncio.CancelledError()
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), self.gateway)
        self.assertEqual(result["reason"], "findone-cancelled")
        self.assertEqual(self.adapter.sent, [("123456", "prepared question", "456")])
        self.news_learning_receipt.assert_called_once()
        self.handler.assert_not_called()

    async def test_news_learning_receipts_are_not_used_for_news_help_now_or_learning_bot(self):
        result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), self.gateway)
        self.assertEqual(result["reason"], "findone-handled")
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for text in ("/help", "/now"):
                result = await plugin.pre_gateway_dispatch(make_event(text=text), self.gateway)
                self.assertEqual(result["reason"], "findone-handled")
        self.news_learning_receipt.assert_not_called()

    async def test_news_learning_receipt_authentication_precedes_every_backend_or_send(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5", user_id="999999"), self.gateway)
        self.assertEqual(result["reason"], "findone-unauthorized")
        self.news_learning_handler.assert_not_called()
        self.news_learning_receipt.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_learning_vocabulary_commands_never_import_news_services(self):
        with patch.dict(sys.modules, {"findone_hermes.news_learning": None, "findone_hermes.news_archive": None}):
            for text in ("/word yield", "/vocab 5", "/words", "2"):
                with self.subTest(text=text):
                    self.handler.reset_mock()
                    result = await plugin.pre_gateway_dispatch(make_event(text=text), self.gateway)
                    self.assertEqual(result["reason"], "findone-handled")
                    self.handler.assert_called_once_with(
                        "telegram", "123456", "123456", "dm", text, submission_id="456", batch_id=None
                    )
        self.news_learning_handler.assert_not_called()
        self.news_receipt.assert_not_called()
        self.scope_get.assert_not_called()

    async def test_news_vocabulary_backend_failure_and_cancellation_never_dispatch_agent(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            self.news_learning_handler.side_effect = RuntimeError("private-vocab-token")
            with self.assertLogs("findone_hermes.plugin", level="WARNING") as logs:
                result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), self.gateway)
            self.assertEqual(result["reason"], "findone-error")
            self.assertNotIn("private-vocab-token", "".join(logs.output))
            self.news_learning_handler.side_effect = asyncio.CancelledError()
            result = await plugin.pre_gateway_dispatch(make_event(text="/vocab 5"), self.gateway)
            self.assertEqual(result["reason"], "findone-cancelled")
        self.handler.assert_not_called()
        self.assertEqual(self.adapter.sent, [])

    async def test_news_now_records_each_successful_message_with_exact_body_and_profile(self):
        self.news_handler.return_value = ["first article body", "second article body"]
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result["reason"], "findone-handled")
        self.assertEqual(self.news_receipt.call_args_list, [
            call(self.news_environment, chat_id="123456", message_id="7001", text="first article body"),
            call(self.news_environment, chat_id="123456", message_id="7002", text="second article body"),
        ])
        self.assertIsNot(self.news_receipt.call_args.args[0], self.news_environment)
        self.news_learning_handler.assert_not_called()

    async def test_news_failed_send_never_records_an_article_receipt(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), make_gateway(Adapter(success=False)))
        self.assertEqual(result["reason"], "findone-delivery-failed")
        self.news_receipt.assert_not_called()

    async def test_news_receipt_cancellation_does_not_retry_delivery_or_dispatch_agent(self):
        self.news_handler.return_value = ["first article", "second article"]
        self.news_receipt.side_effect = asyncio.CancelledError()
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result["reason"], "findone-cancelled")
        self.assertEqual(self.adapter.sent, [("123456", "first article", "456")])
        self.news_receipt.assert_called_once()
        self.handler.assert_not_called()

    async def test_news_receipt_failure_warns_once_without_resending_article_or_private_error(self):
        self.news_handler.return_value = ["first article", "second article"]
        self.news_receipt.side_effect = RuntimeError("private-archive-token")
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}), self.assertLogs(
            "findone_hermes.plugin", level="WARNING"
        ) as logs:
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result["reason"], "findone-news-archive-failed")
        self.assertEqual(len(self.adapter.sent), 2)
        self.assertEqual(self.adapter.sent[0][1], "first article")
        self.assertIn("기사 연결", self.adapter.sent[1][1])
        self.assertNotIn("private-archive-token", "".join(logs.output))
        self.news_receipt.assert_called_once()
        self.handler.assert_not_called()

    async def test_news_receipt_requires_numeric_delivered_message_id(self):
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            for message_id in (None, "", "private-invalid-id", False, 0):
                with self.subTest(message_id=message_id):
                    adapter = Adapter(message_id=message_id)
                    result = await plugin.pre_gateway_dispatch(make_event(text="/now"), make_gateway(adapter))
                    self.assertEqual(result["reason"], "findone-news-archive-failed")
                    self.assertEqual(len(adapter.sent), 2)
        self.news_receipt.assert_not_called()
        self.handler.assert_not_called()

    async def test_news_receipt_failure_notice_transport_error_never_dispatches_agent(self):
        self.news_receipt.side_effect = RuntimeError("receipt failure")
        async def fail_notice(chat_id, content, reply_to=None, metadata=None):
            self.adapter.sent.append((chat_id, content, reply_to))
            if len(self.adapter.sent) == 2:
                raise RuntimeError("ambiguous notice delivery")
            return SimpleNamespace(success=True, message_id="7001")
        self.adapter.send = fail_notice
        with patch.dict(os.environ, {"FINDONE_TELEGRAM_MODE": "news"}):
            result = await plugin.pre_gateway_dispatch(make_event(text="/now"), self.gateway)
        self.assertEqual(result["reason"], "findone-error")
        self.assertEqual(len(self.adapter.sent), 2)
        self.news_receipt.assert_called_once()
        self.handler.assert_not_called()


_BOOTSTRAP_PATH = _PLUGIN_PATH.parents[1] / "scripts" / "_findone_bootstrap.py"
_BOOTSTRAP_SPEC = importlib.util.spec_from_file_location("findone_test_bootstrap", _BOOTSTRAP_PATH)
bootstrap = importlib.util.module_from_spec(_BOOTSTRAP_SPEC)
_BOOTSTRAP_SPEC.loader.exec_module(bootstrap)


class CronWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".env"

    def write(self, content):
        self.path.write_text(content, encoding="utf-8")

    def test_model_timeout_is_loaded_from_profile_and_process_override_is_preserved(self):
        self.write("FINDONE_MODEL_TIMEOUT_SECONDS=90\n")
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path)}, clear=True):
            bootstrap.load_config_env()
            self.assertEqual(os.environ["FINDONE_MODEL_TIMEOUT_SECONDS"], "90")
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path), "FINDONE_MODEL_TIMEOUT_SECONDS": "60"}, clear=True):
            bootstrap.load_config_env()
            self.assertEqual(os.environ["FINDONE_MODEL_TIMEOUT_SECONDS"], "60")

    def test_reasoning_effort_is_loaded_from_profile_and_process_override_is_preserved(self):
        self.write("FINDONE_MODEL_REASONING_EFFORT=none\n")
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path)}, clear=True):
            bootstrap.load_config_env()
            self.assertEqual(os.environ["FINDONE_MODEL_REASONING_EFFORT"], "none")
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path), "FINDONE_MODEL_REASONING_EFFORT": "low"}, clear=True):
            bootstrap.load_config_env()
            self.assertEqual(os.environ["FINDONE_MODEL_REASONING_EFFORT"], "low")

    def test_explicit_load_only_imports_config_keys_and_preserves_process_overrides(self):
        self.write(
            "TELEGRAM_BOT_TOKEN=must-not-load\n"
            "FINDONE_MODEL_API_KEY='literal-$(does-not-execute)'\n"
            "TELEGRAM_ALLOWED_USERS=123456 # owner\n"
            "FINDONE_QUIZ_COUNT=3\n"
        )
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path), "FINDONE_QUIZ_COUNT": "2"}, clear=True):
            bootstrap.load_config_env()
            self.assertNotIn("TELEGRAM_BOT_TOKEN", os.environ)
            self.assertEqual(os.environ["FINDONE_MODEL_API_KEY"], "literal-$(does-not-execute)")
            self.assertEqual(os.environ["TELEGRAM_ALLOWED_USERS"], "123456")
            self.assertEqual(os.environ["FINDONE_QUIZ_COUNT"], "2")

    def test_windows_path_quoting_is_literal(self):
        self.write('FINDONE_REPO_ROOT="C:\\Users\\Learner\\FinDone" # checkout\n')
        self.assertEqual(bootstrap._read_config(self.path)["FINDONE_REPO_ROOT"], r"C:\Users\Learner\FinDone")

    def test_duplicate_or_malformed_used_setting_is_rejected(self):
        for content in (
            "TELEGRAM_ALLOWED_USERS=1\nTELEGRAM_ALLOWED_USERS=2\n",
            'FINDONE_MODEL_API_KEY="unterminated\n',
            'FINDONE_REPO_ROOT="/repo" extra-input\n',
        ):
            with self.subTest(content=content):
                self.write(content)
                with self.assertRaises(ValueError):
                    bootstrap._read_config(self.path)

    def test_relative_or_repository_configuration_is_rejected(self):
        self.write(f'FINDONE_REPO_ROOT="{self.temp.name}"\nTELEGRAM_ALLOWED_USERS=1\n')
        for path in ("relative.env", str(self.path)):
            with self.subTest(path=path), patch.dict(os.environ, {"FINDONE_ENV_FILE": path}, clear=True):
                with self.assertRaises(ValueError):
                    bootstrap.load_config_env()

    def test_config_in_git_repository_is_rejected_without_repo_setting(self):
        self.write("TELEGRAM_ALLOWED_USERS=1\n")
        (Path(self.temp.name) / ".git").mkdir()
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path)}, clear=True):
            with self.assertRaises(ValueError):
                bootstrap.load_config_env()

    def test_wrapper_uses_fixed_cli_args(self):
        self.write("TELEGRAM_ALLOWED_USERS=123456\n")
        jobs = ModuleType("findone_hermes.jobs")
        jobs.main = Mock(return_value=0)
        with patch.dict(os.environ, {"FINDONE_ENV_FILE": str(self.path)}, clear=True), patch.dict(
            sys.modules, {"findone_hermes.jobs": jobs}
        ):
            self.assertEqual(bootstrap.run("regular", "20:30"), 0)
        jobs.main.assert_called_once_with(["regular", "--slot", "20:30"])


if __name__ == "__main__":
    unittest.main()
