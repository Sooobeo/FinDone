"""Optional model controls use scoped configuration and validated request fields."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from findone_hermes.model import ModelClient, ModelError, model_from_env


class ModelPresencePenaltyTests(unittest.TestCase):
    SCOPED = {"FINDONE_MODEL_BASE_URL": "http://127.0.0.1:11434/v1",
              "FINDONE_MODEL_NAME": "public-test-model"}

    def request_body(self, client):
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"message": {
            "content": json.dumps({"summary": "공개 기사 요약"})}}]}).encode("utf-8")
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch("findone_hermes.model.build_opener", return_value=opener):
            self.assertEqual(client.complete_json("Return JSON.", {"article": "Public source."}),
                             {"summary": "공개 기사 요약"})
        return json.loads(opener.open.call_args.args[0].data)

    def test_explicit_finite_values_including_zero_and_boundaries_are_sent(self):
        for value in ("0", "-2", "2", "0.75", " -1.5 "):
            with self.subTest(value=value):
                client = model_from_env({**self.SCOPED, "FINDONE_MODEL_PRESENCE_PENALTY": value})
                self.assertEqual(client.presence_penalty, float(value))
                self.assertEqual(self.request_body(client)["presence_penalty"], float(value))

    def test_missing_and_empty_values_preserve_default_without_process_fallback(self):
        with patch.dict(os.environ, {"FINDONE_MODEL_PRESENCE_PENALTY": "1.5"}):
            for value in (None, "", " \t "):
                with self.subTest(value=value):
                    environment = self.SCOPED if value is None else {
                        **self.SCOPED, "FINDONE_MODEL_PRESENCE_PENALTY": value}
                    client = model_from_env(environment)
                    self.assertIsNone(client.presence_penalty)
                    self.assertNotIn("presence_penalty", self.request_body(client))
            self.assertIsNone(ModelClient(self.SCOPED["FINDONE_MODEL_BASE_URL"], "local").presence_penalty)

    def test_invalid_environment_values_raise_model_error_without_echoing_input(self):
        for value in ("nan", "inf", "-inf", "1e1000", "-2.001", "2.001", "true", "false",
                      "invalid-input-sentinel", True, False, None, []):
            with self.subTest(value=value), self.assertRaises(ModelError) as caught:
                model_from_env({**self.SCOPED, "FINDONE_MODEL_PRESENCE_PENALTY": value})
            self.assertEqual(str(caught.exception),
                             "Model presence penalty must be a finite number from -2 to 2")

    def test_direct_client_validation_rejects_booleans_wrong_types_and_nonfinite_values(self):
        for value in (True, False, "0", [], float("nan"), float("inf"), -2.1, 2.1, 10 ** 1000):
            with self.subTest(value=value), self.assertRaises(ModelError):
                ModelClient(self.SCOPED["FINDONE_MODEL_BASE_URL"], "local", presence_penalty=value)
        client = ModelClient(self.SCOPED["FINDONE_MODEL_BASE_URL"], "local", "", 30, "none", 0)
        body = self.request_body(client)
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["presence_penalty"], 0)

    def test_news_bootstrap_passes_this_profile_value_without_process_fallback(self):
        spec = importlib.util.spec_from_file_location("presence_test_bootstrap",
            PACKAGE_ROOT / "hermes/scripts/_findone_bootstrap.py")
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / "scripts").mkdir()
            (home / ".env").write_text(
                "FINDONE_MODEL_BASE_URL=http://127.0.0.1:11434/v1\n"
                "FINDONE_MODEL_NAME=public-test-model\nFINDONE_MODEL_PRESENCE_PENALTY=0\n", encoding="utf-8")
            with patch.object(bootstrap, "__file__", str(home / "scripts/_findone_bootstrap.py")), \
                    patch.dict(os.environ, {"FINDONE_MODEL_PRESENCE_PENALTY": "1.5"}, clear=True):
                configured = bootstrap.load_news_config_env()
                self.assertEqual(configured["FINDONE_MODEL_PRESENCE_PENALTY"], "0")
                self.assertEqual(model_from_env(configured).presence_penalty, 0)
                self.assertEqual(os.environ["FINDONE_MODEL_PRESENCE_PENALTY"], "1.5")


if __name__ == "__main__":
    unittest.main()
