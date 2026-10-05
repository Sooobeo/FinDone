"""Exercise the private CLI boundary without installing OMW in CI."""
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from findone_hermes.wiki import WikiEntry, WikiError, WikiSync, _render


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cli = self.root / "omw.exe"
        self.cli.touch()
        self.home = self.root / "home"
        self.home.mkdir()
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.environment = {
            "FINDONE_WIKI_CLI_PATH": str(self.cli), "FINDONE_WIKI_HOME": str(self.home),
            "FINDONE_WIKI_VAULT": "findone-news", "FINDONE_WIKI_VAULT_PATH": str(self.vault),
        }
        self.syncer = WikiSync.from_env(self.environment)
        self.entry = WikiEntry(
            word_id="8e02b605a20f4140aa0e426346d23683", term="capital headroom",
            lemma="capital headroom", sense="bank regulatory capital surplus",
            meaning_ko="규제 최소 수준을 초과하는 자본 여력",
            sentence="Aggregate capital headroom has continued to increase.",
            article_url="https://www.ecb.europa.eu/example.html",
            article_title="Bank resilience", source_name="ECB",
            published_at="2026-10-02T15:00:00+02:00", explanation_ko="규제 기준보다 여유 있게 보유한 자본을 뜻한다.",
        )
        self.calls = []

    def fake_cli(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        arguments = argv[1:]
        if arguments[:2] == ["vault", "info"]:
            result = {"name": "findone-news", "path": str(self.vault), "mode": "wiki", "archived": False}
        elif arguments[:2] == ["page", "write"]:
            title = arguments[arguments.index("--title") + 1]
            slug = re.sub(r"[^a-z0-9가-힣]+", "-", title.strip().lower()).strip("-")
            relpath = f"wiki/concepts/{slug}.md"
            page = self.vault / relpath
            page.parent.mkdir(parents=True, exist_ok=True)
            body = Path(arguments[arguments.index("--body-file") + 1]).read_text(encoding="utf-8")
            page.write_text("---\ntype: concept\n---\n" + body, encoding="utf-8")
            result = {"relpath": relpath}
        elif arguments[:2] == ["visibility", "set"]:
            result = {"set": "private", "updated": [arguments[2]], "missing": [], "failed": []}
        else:
            self.fail(f"Unexpected CLI operation: {arguments[:2]}")
        return SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr="")

    def test_saved_context_is_private_indexed_and_does_not_export_review_state(self):
        with patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli):
            result = self.syncer.sync(self.entry)
        self.assertEqual(result.status, "synced")
        self.assertEqual(len(list((self.vault / "wiki/concepts").glob("*.md"))), 1)
        body = (self.vault / result.relpath).read_text(encoding="utf-8")
        for expected in (self.entry.term, self.entry.meaning_ko, self.entry.sentence, self.entry.article_url):
            self.assertIn(expected, body)
        for forbidden in ("user_id", "due_at", "correct_count", "wrong_count", "streak", "review:"):
            self.assertNotIn(forbidden, body)
        self.assertEqual([call[0][1:3] for call in self.calls], [["vault", "info"], ["page", "write"], ["visibility", "set"]])
        self.assertTrue(all(call[1]["shell"] is False for call in self.calls))
        self.assertIn("private", self.calls[-1][0])
        self.assertFalse(Path(self.calls[1][0][self.calls[1][0].index("--body-file") + 1]).exists())

    def test_private_page_preserves_original_unicode_surface_and_sentence(self):
        entry = replace(self.entry, term="broker‑dealer’s assets\u00a0under management",
                        lemma="broker-dealer's assets under management",
                        sentence="The U.S. broker‑dealer’s assets\u00a0under management increased.")
        with patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli):
            result = self.syncer.sync(entry)
        body = (self.vault / result.relpath).read_text(encoding="utf-8")
        self.assertIn("# " + entry.term, body)
        self.assertIn("> " + entry.sentence, body)
        self.assertIn(entry.lemma, body)

    def test_retry_does_not_create_a_second_page_and_recovers_privacy_indexing(self):
        with patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli):
            first = self.syncer.sync(self.entry)
            second = self.syncer.sync(self.entry)
        self.assertEqual(second.status, "already_synced")
        self.assertEqual(first.relpath, second.relpath)
        self.assertEqual(sum(call[0][1:3] == ["page", "write"] for call in self.calls), 1)
        self.assertEqual(sum(call[0][1:3] == ["visibility", "set"] for call in self.calls), 2)

    def test_same_term_in_distinct_contexts_uses_distinct_uuid_pages(self):
        second = replace(self.entry, word_id="c05b0bba7bf74b9e851f346333bdb050", sentence="A different source context.")
        with patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli):
            first_result = self.syncer.sync(self.entry)
            second_result = self.syncer.sync(second)
        self.assertNotEqual(first_result.relpath, second_result.relpath)
        self.assertEqual(len(list((self.vault / "wiki/concepts").glob("*.md"))), 2)

    def test_existing_unowned_or_changed_source_page_is_preserved(self):
        _, relpath, _, _ = _render(self.entry)
        page = self.vault / relpath
        page.parent.mkdir(parents=True)
        page.write_text("Existing user page", encoding="utf-8")
        with patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli):
            with self.assertRaises(WikiError):
                self.syncer.sync(self.entry)
        self.assertEqual(page.read_text(encoding="utf-8"), "Existing user page")
        self.assertEqual(len(self.calls), 1)

    def test_unexpected_vault_registration_prevents_any_page_write(self):
        response = SimpleNamespace(returncode=0, stdout=json.dumps({"path": str(self.root / "other"), "mode": "wiki"}), stderr="")
        with patch("findone_hermes.wiki.subprocess.run", return_value=response) as run:
            with self.assertRaises(WikiError):
                self.syncer.sync(self.entry)
        run.assert_called_once()

    def test_source_id_and_url_cannot_control_the_filename_or_cli(self):
        for entry in (
            replace(self.entry, word_id="../escape"),
            replace(self.entry, article_url="file:///private"),
            replace(self.entry, article_url="https://user:password@example.com/path"),
        ):
            with self.subTest(entry=entry), patch("findone_hermes.wiki.subprocess.run") as run:
                with self.assertRaises(WikiError):
                    self.syncer.sync(entry)
                run.assert_not_called()

    def test_long_terms_preserve_complete_uuid_without_cli_shell_expansion(self):
        long_entry = replace(self.entry, term="a" * 80)
        _, path, _, _ = _render(long_entry)
        self.assertIn(long_entry.word_id, path)
        self.assertLessEqual(len(Path(path).stem), 80)
        with patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli):
            self.syncer.sync(replace(self.entry, term="$(secret); `command`"))
        self.assertTrue(all(call[1]["shell"] is False for call in self.calls))

    def test_no_provider_or_telegram_secrets_are_in_cli_environment(self):
        secrets = {"TELEGRAM_BOT_TOKEN": "private-token", "FINDONE_MODEL_API_KEY": "private-key", "OMW_SERVE_TOKEN": "serve-key"}
        with patch.dict(os.environ, secrets), patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli):
            self.syncer.sync(self.entry)
        for _, kwargs in self.calls:
            for key in secrets:
                self.assertNotIn(key, kwargs["env"])
            self.assertEqual(kwargs["env"]["OMW_HOME"], str(self.home))

    def test_cli_failures_and_timeouts_are_redacted(self):
        for outcome in (
            SimpleNamespace(returncode=1, stdout="", stderr="private-token private-page"),
            subprocess.TimeoutExpired(["omw", "private-page"], 20, output="private-token"),
        ):
            with self.subTest(outcome=outcome):
                if isinstance(outcome, Exception):
                    context = patch("findone_hermes.wiki.subprocess.run", side_effect=outcome)
                else:
                    context = patch("findone_hermes.wiki.subprocess.run", return_value=outcome)
                with context, self.assertRaises(WikiError) as error:
                    self.syncer.sync(self.entry)
                self.assertNotIn("private-token", str(error.exception))
                self.assertNotIn("private-page", str(error.exception))

    def test_resolved_page_outside_vault_is_rejected_before_page_access(self):
        # Model the path returned by a junction/symlink without requiring the
        # Windows developer-mode privilege to create one in a unit test.
        _, relpath, _, _ = _render(self.entry)
        page = self.vault / relpath
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            return self.root / "outside.md" if path == page else original_resolve(path, *args, **kwargs)

        with patch("findone_hermes.wiki.subprocess.run", side_effect=self.fake_cli), patch.object(Path, "resolve", resolve):
            with self.assertRaises(WikiError):
                self.syncer.sync(self.entry)
        self.assertEqual(len(self.calls), 1)

    def test_configuration_is_explicit_and_repository_paths_are_rejected(self):
        self.assertIsNone(WikiSync.from_env({}))
        for changes in (
            {"FINDONE_WIKI_VAULT": "../elsewhere"},
            {"FINDONE_WIKI_HOME": "relative-home"},
            {"FINDONE_WIKI_CLI_PATH": ""},
            {"FINDONE_REPO_ROOT": str(self.root)},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(WikiError):
                    WikiSync.from_env({**self.environment, **changes})

    def test_cli_returned_path_cannot_escape_vault_and_temp_source_is_removed(self):
        def escaped_cli(argv, **kwargs):
            if argv[1:3] == ["page", "write"]:
                self.calls.append((argv, kwargs))
                return SimpleNamespace(returncode=0, stdout='{"relpath":"../../private"}', stderr="")
            return self.fake_cli(argv, **kwargs)
        with patch("findone_hermes.wiki.subprocess.run", side_effect=escaped_cli):
            with self.assertRaises(WikiError):
                self.syncer.sync(self.entry)
        self.assertEqual(len(self.calls), 2)
        arguments = self.calls[-1][0]
        self.assertFalse(Path(arguments[arguments.index("--body-file") + 1]).exists())


if __name__ == "__main__":
    unittest.main()
