import unittest

from tools import repo_preflight


class RepositoryPreflightTest(unittest.TestCase):
    def test_guard_files_select_every_non_release_scope(self) -> None:
        self.assertEqual(
            set(repo_preflight.NON_RELEASE_SCOPES),
            repo_preflight.scopes_for_path("AGENTS.md"),
        )

    def test_scope_mapping_covers_ci_sensitive_paths(self) -> None:
        self.assertEqual(
            {"admin"},
            repo_preflight.scopes_for_path("admin/data/sources.generated.json"),
        )
        self.assertEqual(
            {"model"},
            repo_preflight.scopes_for_path("tools/train_concept_question_model.py"),
        )
        self.assertEqual(
            {"admin", "model", "android"},
            repo_preflight.scopes_for_path("app/src/main/assets/content-manifest.json"),
        )

    def test_all_does_not_request_a_release_build(self) -> None:
        scopes, release_requested = repo_preflight.resolve_scopes(["all"], [])

        self.assertEqual(set(repo_preflight.NON_RELEASE_SCOPES), scopes)
        self.assertFalse(release_requested)

    def test_current_release_status_is_explicit_and_valid(self) -> None:
        self.assertIn(
            repo_preflight._release_status(),
            repo_preflight.VALID_RELEASE_STATUSES,
        )

    def test_generated_admin_fixtures_are_canonical(self) -> None:
        repo_preflight._assert_admin_fixtures_current()

    def test_guardrail_contracts_are_wired(self) -> None:
        repo_preflight._assert_guardrail_wiring()
        repo_preflight._assert_model_path_contract()

    def test_local_markdown_links_resolve(self) -> None:
        repo_preflight._assert_local_markdown_links()

    def test_android_development_suite_never_selects_release_tasks(self) -> None:
        commands = repo_preflight.verification_commands({"android"}, release_requested=False)
        gradle_arguments = commands[0].argv[1:]

        self.assertIn("testDebugUnitTest", gradle_arguments)
        self.assertIn("lintDebug", gradle_arguments)
        self.assertIn("assembleDebug", gradle_arguments)
        self.assertNotIn("test", gradle_arguments)
        self.assertFalse(any("Release" in argument for argument in gradle_arguments))


if __name__ == "__main__":
    unittest.main()
