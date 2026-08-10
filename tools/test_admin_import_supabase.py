import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import admin_export_content as exporter
from tools import admin_import_supabase as importer


class _Response:
    def __init__(self, value: dict[str, object]) -> None:
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size: int) -> bytes:
        return self.body


class AdminSupabaseImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = exporter.build_export()

    def test_summary_matches_packaged_content(self) -> None:
        summary = importer.snapshot_summary(self.snapshot)
        self.assertEqual(5, summary["contentDbVersion"])
        self.assertEqual(135, summary["rowCounts"]["elements"])
        self.assertEqual(174, summary["rowCounts"]["sources"])

    def test_remote_url_requires_https_and_no_path(self) -> None:
        with self.assertRaises(importer.SupabaseImportError):
            importer.normalize_supabase_url("http://example.supabase.co")
        with self.assertRaises(importer.SupabaseImportError):
            importer.normalize_supabase_url("https://example.supabase.co/rest")
        self.assertEqual(
            "http://127.0.0.1:54321",
            importer.normalize_supabase_url("http://127.0.0.1:54321/"),
        )

    def test_admin_env_url_is_used_when_process_url_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "SUPABASE_SECRET_KEY=must-not-be-loaded\n"
                "NEXT_PUBLIC_SUPABASE_URL='https://project.supabase.co'\n",
                encoding="utf-8",
            )
            self.assertEqual(
                "https://project.supabase.co",
                importer.resolve_supabase_url({}, [env_path]),
            )

    def test_process_url_takes_precedence_over_admin_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env.local"
            env_path.write_text(
                "NEXT_PUBLIC_SUPABASE_URL=https://file.supabase.co\n",
                encoding="utf-8",
            )
            self.assertEqual(
                "https://process.supabase.co",
                importer.resolve_supabase_url(
                    {"SUPABASE_URL": "https://process.supabase.co"},
                    [env_path],
                ),
            )

    @mock.patch("urllib.request.urlopen")
    def test_rpc_uses_secret_without_logging_it(self, urlopen: mock.Mock) -> None:
        urlopen.return_value = _Response({"status": "imported"})
        result = importer.call_import_rpc(
            base_url="https://project.supabase.co",
            secret_key="secret-test-value",
            snapshot=self.snapshot,
            allow_overwrite=False,
        )

        self.assertEqual({"status": "imported"}, result)
        request = urlopen.call_args.args[0]
        self.assertEqual(importer.RPC_PATH, request.full_url.removeprefix("https://project.supabase.co"))
        self.assertEqual("secret-test-value", request.headers["Apikey"])
        self.assertNotIn("Authorization", request.headers)
        payload = json.loads(request.data)
        self.assertFalse(payload["p_allow_overwrite"])
        self.assertEqual(exporter.EXPORT_FORMAT, payload["p_snapshot"]["exportFormat"])


if __name__ == "__main__":
    unittest.main()
