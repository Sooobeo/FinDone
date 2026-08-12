from __future__ import annotations

import json
import unittest
from unittest import mock

from tools.admin_import_glossary import call_import


class _Response:
    def __init__(self, value: object) -> None:
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class AdminGlossaryImportTest(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_opaque_secret_is_sent_only_as_apikey(self, urlopen: mock.Mock) -> None:
        urlopen.return_value = _Response({"status": "imported"})

        result = call_import(
            {"formatVersion": 1},
            base_url="https://project.supabase.co",
            secret_key="sb_secret_test-value",
            timeout_seconds=30,
        )

        self.assertEqual({"status": "imported"}, result)
        request = urlopen.call_args.args[0]
        self.assertEqual("sb_secret_test-value", request.headers["Apikey"])
        self.assertNotIn("Authorization", request.headers)


if __name__ == "__main__":
    unittest.main()
