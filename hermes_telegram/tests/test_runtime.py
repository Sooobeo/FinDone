from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from findone_hermes.config import ConfigurationError, Settings, content_paths, is_allowed
from findone_hermes.jobs import KST, run_job, slot_is_due
from findone_hermes.model import ModelError
from findone_hermes.state import StateStore


class ConfigurationTests(unittest.TestCase):
    def test_auth_denies_group_spoof_and_ambiguous_allowlist(self):
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "123"}):
            self.assertTrue(is_allowed("telegram", "123", "123", "dm"))
            for arguments in (("telegram", "123", "123", "group"), ("telegram", "123", "456", "dm"), ("telegram", "456", "123", "dm"), ("discord", "123", "123", "dm")):
                self.assertFalse(is_allowed(*arguments))
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "123,456"}):
            self.assertFalse(is_allowed("telegram", "123", "123", "dm"))

    def test_private_state_must_be_absolute_and_outside_checkout(self):
        root = Path(__file__).resolve().parents[2]
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "123", "STATE_DB_PATH": "local.sqlite3"}):
            with self.assertRaises(ConfigurationError):
                Settings.from_env()
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "123", "STATE_DB_PATH": str(root / "state.sqlite3")}):
            with self.assertRaises(ConfigurationError):
                Settings.from_env()

    def test_denied_gateway_never_opens_personal_database(self):
        from findone_hermes.gateway import handle_message
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "123"}), patch("findone_hermes.gateway.StateStore") as store:
            self.assertEqual([], handle_message("telegram", "456", "456", "dm", "2,4"))
            self.assertEqual([], handle_message("telegram", "123", "123", "group", "2,4"))
            store.assert_not_called()


class ScheduledJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db, manifest = content_paths()
        self.settings = Settings("123", Path(self.temp.name) / "state.sqlite3", db, manifest)

    def tearDown(self):
        self.temp.cleanup()

    def test_kst_slot_window_and_sunday_replacement(self):
        monday = datetime(2026, 10, 5, 12, 30, tzinfo=KST)
        self.assertTrue(slot_is_due("regular", "12:30", monday.astimezone(timezone.utc)))
        self.assertTrue(slot_is_due("regular", "12:30", monday + timedelta(minutes=30)))
        self.assertFalse(slot_is_due("regular", "12:30", monday + timedelta(minutes=31)))
        self.assertFalse(slot_is_due("regular", "12:30", monday - timedelta(seconds=1)))
        self.assertFalse(slot_is_due("regular", "08:00", monday))
        with self.assertRaises(ValueError):
            slot_is_due("regular", "12:30", monday.replace(tzinfo=None))
        self.assertFalse(slot_is_due("review", "20:30", monday.replace(hour=20)))
        sunday = datetime(2026, 10, 4, 20, 30, tzinfo=KST)
        self.assertTrue(slot_is_due("review", "20:30", sunday))

    def test_duplicate_slot_and_active_quiz_do_not_create_overlapping_batches(self):
        noon = datetime(2026, 10, 5, 12, 30, tzinfo=KST)
        self.assertTrue(run_job("regular", "12:30", self.settings, now=noon))
        self.assertEqual([], run_job("regular", "12:30", self.settings, now=noon))
        evening = noon.replace(hour=20)
        result = run_job("regular", "20:30", self.settings, now=evening)
        self.assertIn("미완료", "\n".join(result))
        state = StateStore(self.settings.state_db)
        try:
            self.assertEqual(1, state.connection.execute("SELECT COUNT(*) FROM quiz_batches").fetchone()[0])
        finally:
            state.close()

    def test_sunday_report_preserves_pending_batch_and_shared_slot_key(self):
        noon = datetime(2026, 10, 4, 12, 30, tzinfo=KST)
        run_job("regular", "12:30", self.settings, now=noon)
        report = run_job("regular", "20:30", self.settings, now=noon.replace(hour=20))
        self.assertIn("/review", "\n".join(report))
        self.assertEqual([], run_job("review", "20:30", self.settings, now=noon.replace(hour=20)))

    def test_stale_job_does_not_even_create_state(self):
        self.assertEqual([], run_job("regular", "12:30", self.settings, now=datetime(2026, 10, 5, 16, 0, tzinfo=KST)))
        self.assertFalse(self.settings.state_db.exists())

    def test_news_configuration_failure_does_not_block_quiz_or_retry_same_slot(self):
        morning = datetime(2026, 10, 5, 8, 0, tzinfo=KST)
        with patch.dict(os.environ, {"FINDONE_MODEL_BASE_URL": "https://example.com/v1", "FINDONE_MODEL_NAME": ""}):
            with self.assertRaises(ModelError):
                run_job("news", "08:00", self.settings, now=morning)
            self.assertEqual([], run_job("news", "08:00", self.settings, now=morning))
        self.assertTrue(run_job("regular", "12:30", self.settings, now=morning.replace(hour=12, minute=30)))

    def test_no_model_news_explicitly_reports_unavailable_without_delivery_rows(self):
        with patch.dict(os.environ, {"FINDONE_MODEL_BASE_URL": "", "FINDONE_MODEL_NAME": ""}):
            result = run_job("news", "08:00", self.settings, now=datetime(2026, 10, 5, 8, 0, tzinfo=KST))
        self.assertIn("모델이 설정되지", "\n".join(result))
        state = StateStore(self.settings.state_db)
        try:
            self.assertEqual(0, state.connection.execute("SELECT COUNT(*) FROM news_deliveries").fetchone()[0])
        finally:
            state.close()

    def test_gateway_answer_survives_restart_and_duplicate_replay(self):
        from findone_hermes.gateway import handle_message
        run_job("regular", "12:30", self.settings, now=datetime(2026, 10, 5, 12, 30, tzinfo=KST))
        env = {"TELEGRAM_ALLOWED_USERS": "123", "STATE_DB_PATH": str(self.settings.state_db)}
        with patch.dict(os.environ, env):
            result = handle_message("telegram", "123", "123", "dm", "1,1", submission_id="m1")
            self.assertIn("채점 결과", "\n".join(result))
            handle_message("telegram", "123", "123", "dm", "1,1", submission_id="m1")
            summary = handle_message("telegram", "123", "123", "dm", "/stats FI")
            self.assertTrue(summary)
        state = StateStore(self.settings.state_db)
        try:
            self.assertEqual(2, state.connection.execute("SELECT COUNT(*) FROM answers").fetchone()[0])
        finally:
            state.close()


if __name__ == "__main__":
    unittest.main()
