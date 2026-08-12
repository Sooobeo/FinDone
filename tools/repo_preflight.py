#!/usr/bin/env python3
"""Read-only startup inspection and CI-parity verification for FinDone.

The startup phase detects repository state, release readiness, generated Admin
fixture drift, unsafe model report paths, and guardrail wiring. The verify
phase then executes the same commands used by GitHub Actions for the selected
scope. No external API or production credential is used.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALID_RELEASE_STATUSES = {"bootstrap_not_reviewed", "candidate", "release_ready"}
NON_RELEASE_SCOPES = ("admin", "model", "android")

ADMIN_PATTERNS = (
    "admin/**",
    "supabase/**",
    "tools/admin_*.py",
    "tools/test_admin_*.py",
    "tools/*glossary*.py",
    "content/glossary/**",
    "tools/validate_supabase_sql.py",
    "tools/requirements-source-worker.txt",
    "scripts/refresh_admin_content.ps1",
    ".github/workflows/admin-*.yml",
    "app/src/main/assets/content.sqlite3",
    "app/src/main/assets/content-manifest.json",
)
MODEL_PATTERNS = (
    "content/**",
    "finance_interview_app_final_spec.md",
    "tools/build_content_db.py",
    "tools/local_content_model.py",
    "tools/compile_app_content.py",
    "tools/test_local_content_model.py",
    "tools/test_build_content_db.py",
    "tools/train_concept_question_model.py",
    "tools/review_concept_question_model.py",
    "tools/test_train_concept_question_model.py",
    "tools/requirements-concept-model*.txt",
    "admin/data/concept-model-experiments.generated.json",
    "app/src/main/assets/content.sqlite3",
    "app/src/main/assets/content-manifest.json",
    ".github/workflows/local-content-model-evaluation.yml",
)
ANDROID_PATTERNS = (
    "app/**",
    "gradle/**",
    "build.gradle.kts",
    "settings.gradle.kts",
    "gradle.properties",
    "gradlew",
    "gradlew.bat",
    "content/**",
    "tools/build_content_db.py",
    "tools/compile_app_content.py",
    "tools/*glossary*.py",
)
GUARD_PATTERNS = (
    "AGENTS.md",
    "tools/repo_preflight.py",
    "tools/test_repo_preflight.py",
    "docs/operations/CODEX_PREFLIGHT.md",
    ".githooks/pre-commit",
    ".github/workflows/repository-preflight.yml",
)


class PreflightError(RuntimeError):
    """A repository invariant or selected verification command failed."""


@dataclass(frozen=True)
class Command:
    label: str
    argv: tuple[str, ...]
    cwd: Path = ROOT
    env: dict[str, str] | None = None


def _normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").removeprefix("./")


def _matches(path: str, patterns: Sequence[str]) -> bool:
    normalized = _normalize_path(path)
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
        elif fnmatch.fnmatchcase(normalized, pattern):
            return True
    return False


def scopes_for_path(path: str | Path) -> set[str]:
    normalized = _normalize_path(path)
    if _matches(normalized, GUARD_PATTERNS):
        return set(NON_RELEASE_SCOPES)
    scopes: set[str] = set()
    if _matches(normalized, ADMIN_PATTERNS):
        scopes.add("admin")
    if _matches(normalized, MODEL_PATTERNS):
        scopes.add("model")
    if _matches(normalized, ANDROID_PATTERNS):
        scopes.add("android")
    return scopes


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", "-C", str(ROOT), *args),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise PreflightError(f"Git command failed: git {' '.join(args)}\n{detail}")
    return result.stdout


def _path_lines(value: str) -> set[str]:
    return {_normalize_path(line.strip()) for line in value.splitlines() if line.strip()}


def changed_paths(mode: str) -> set[str]:
    if mode == "staged":
        return _path_lines(_git("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
    if mode == "head":
        return _path_lines(
            _git(
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "-r",
                "HEAD",
            )
        )
    if mode != "working":
        raise PreflightError(f"Unsupported change mode: {mode}")
    paths = _path_lines(_git("diff", "--name-only", "--diff-filter=ACMR"))
    paths.update(
        _path_lines(_git("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
    )
    paths.update(_path_lines(_git("ls-files", "--others", "--exclude-standard")))
    return paths


def _unstaged_paths() -> set[str]:
    paths = _path_lines(_git("diff", "--name-only", "--diff-filter=ACMR"))
    paths.update(_path_lines(_git("ls-files", "--others", "--exclude-standard")))
    return paths


def resolve_scopes(requested: Sequence[str], paths: Iterable[str]) -> tuple[set[str], bool]:
    values: set[str] = set()
    for item in requested:
        values.update(part.strip() for part in item.split(",") if part.strip())
    unknown = values - {"auto", "all", "admin", "model", "android", "release"}
    if unknown:
        raise PreflightError(f"Unknown preflight scope(s): {', '.join(sorted(unknown))}")

    release_requested = "release" in values
    scopes = values & set(NON_RELEASE_SCOPES)
    if "all" in values:
        scopes.update(NON_RELEASE_SCOPES)
    if "auto" in values:
        for path in paths:
            scopes.update(scopes_for_path(path))
    return scopes, release_requested


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise PreflightError(f"Required {label} is missing: {path.relative_to(ROOT)}")


def _release_status() -> str:
    manifest_path = ROOT / "app" / "src" / "main" / "assets" / "content-manifest.json"
    _require_path(manifest_path, "content manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"Content manifest is not valid UTF-8 JSON: {error}") from error
    status = manifest.get("conceptQuestionReleaseStatus")
    if status not in VALID_RELEASE_STATUSES:
        raise PreflightError(f"Invalid conceptQuestionReleaseStatus: {status!r}")
    return str(status)


def _assert_guardrail_wiring() -> None:
    contracts = {
        ROOT / "AGENTS.md": (
            "python tools/repo_preflight.py inspect",
            "python tools/repo_preflight.py verify",
        ),
        ROOT / ".githooks" / "pre-commit": (
            "repo_preflight.py",
            "verify --scope auto --changes staged",
        ),
        ROOT / ".github" / "workflows" / "admin-ci.yml": (
            "repo_preflight.py",
            "--scope admin",
        ),
        ROOT / ".github" / "workflows" / "local-content-model-evaluation.yml": (
            "repo_preflight.py",
            "--scope model",
        ),
    }
    for path, tokens in contracts.items():
        _require_path(path, "preflight contract file")
        text = path.read_text(encoding="utf-8")
        missing = [token for token in tokens if token not in text]
        if missing:
            raise PreflightError(
                f"Preflight wiring drift in {path.relative_to(ROOT)}; missing: {missing}"
            )


def _assert_local_markdown_links() -> None:
    markdown_paths = _path_lines(_git("ls-files", "*.md"))
    markdown_paths.update(
        _path_lines(_git("ls-files", "--others", "--exclude-standard", "*.md"))
    )
    link_pattern = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)")
    failures: list[str] = []
    for relative in sorted(markdown_paths):
        source = ROOT / relative
        if not source.is_file():
            continue
        for line_number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            for match in link_pattern.finditer(line):
                target = match.group("target").strip("<>")
                if (
                    not target
                    or target.startswith(("#", "/", "//"))
                    or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
                ):
                    continue
                local_part = unquote(target.split("#", 1)[0].split("?", 1)[0])
                if local_part and not (source.parent / local_part).resolve().exists():
                    failures.append(f"{relative}:{line_number} -> {target}")
    if failures:
        raise PreflightError(
            "Broken local Markdown link(s):\n- " + "\n- ".join(failures[:20])
        )


def _assert_model_path_contract() -> None:
    path = ROOT / "tools" / "train_concept_question_model.py"
    _require_path(path, "concept model trainer")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    class RootRelativeVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.function_name: str | None = None
            self.unsafe_lines: list[int] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            previous = self.function_name
            self.function_name = node.name
            self.generic_visit(node)
            self.function_name = previous

        def visit_Call(self, node: ast.Call) -> None:
            direct_root_relative = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "relative_to"
                and any(isinstance(argument, ast.Name) and argument.id == "ROOT" for argument in node.args)
            )
            if direct_root_relative and self.function_name != "_report_path":
                self.unsafe_lines.append(node.lineno)
            self.generic_visit(node)

    visitor = RootRelativeVisitor()
    visitor.visit(tree)
    if visitor.unsafe_lines:
        raise PreflightError(
            "Unsafe direct .relative_to(ROOT) found in the model trainer at line(s) "
            f"{', '.join(map(str, visitor.unsafe_lines))}. "
            "Use _report_path(...) so relative CLI paths work in CI."
        )


def _run_captured(argv: Sequence[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tuple(argv),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _assert_admin_fixtures_current() -> None:
    tracked_elements = ROOT / "admin" / "data" / "content-elements.generated.json"
    tracked_sources = ROOT / "admin" / "data" / "sources.generated.json"
    _require_path(tracked_elements, "Admin element fixture")
    _require_path(tracked_sources, "Admin source fixture")

    with tempfile.TemporaryDirectory(prefix="findone-preflight-") as temporary:
        temporary_root = Path(temporary)
        generated_elements = temporary_root / tracked_elements.name
        generated_sources = temporary_root / tracked_sources.name
        result = _run_captured(
            (
                sys.executable,
                str(ROOT / "tools" / "admin_export_content.py"),
                "--frontend-json",
                str(generated_elements),
                "--frontend-sources-json",
                str(generated_sources),
            )
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise PreflightError(f"Temporary Admin content export failed:\n{detail}")

        mismatches: list[str] = []
        for tracked, generated in (
            (tracked_elements, generated_elements),
            (tracked_sources, generated_sources),
        ):
            if tracked.read_bytes() != generated.read_bytes():
                mismatches.append(
                    f"{tracked.relative_to(ROOT)} "
                    f"(tracked={_sha256(tracked)[:12]}, generated={_sha256(generated)[:12]})"
                )
        if mismatches:
            raise PreflightError(
                "Generated Admin fixtures are stale:\n- "
                + "\n- ".join(mismatches)
                + "\nRun: python tools/admin_export_content.py "
                "--frontend-json admin/data/content-elements.generated.json "
                "--frontend-sources-json admin/data/sources.generated.json"
            )


def inspect_repository(
    scopes: set[str],
    *,
    release_requested: bool,
    change_mode: str,
    ci: bool,
) -> str:
    expected_root = Path(_git("rev-parse", "--show-toplevel").strip()).resolve()
    if expected_root != ROOT.resolve():
        raise PreflightError(f"Unexpected Git root: {expected_root}; expected {ROOT}")

    for relative in ("AGENTS.md", "tools/repo_preflight.py", ".githooks/pre-commit"):
        _require_path(ROOT / relative, "repository guardrail")
    _assert_guardrail_wiring()
    _assert_local_markdown_links()

    if change_mode == "staged":
        unstaged = _unstaged_paths()
        relevant_unstaged = sorted(
            path for path in unstaged if scopes_for_path(path).intersection(scopes)
        )
        if relevant_unstaged:
            raise PreflightError(
                "Staged verification cannot represent the commit while relevant unstaged "
                "files exist:\n- "
                + "\n- ".join(relevant_unstaged)
                + "\nStage the intended files or isolate the changes before committing."
            )

    if not ci:
        hooks_path = _git("config", "--get", "core.hooksPath", check=False).strip()
        if _normalize_path(hooks_path) != ".githooks":
            raise PreflightError(
                "Repository hooks are not active. Run: "
                "git config --local core.hooksPath .githooks"
            )

    status = _release_status()
    if release_requested and status != "release_ready":
        raise PreflightError(
            f"Release is blocked: concept question bank is {status!r}. "
            "Complete independent human review; do not bypass the Gradle gate."
        )
    if "admin" in scopes:
        _assert_admin_fixtures_current()
    if "model" in scopes:
        _assert_model_path_contract()
    return status


def _require_module(module: str, remediation: str) -> None:
    if importlib.util.find_spec(module) is None:
        raise PreflightError(f"Required Python module {module!r} is missing. Run: {remediation}")


def _command_display(command: Command) -> str:
    return " ".join(command.argv)


def _run_command(command: Command, index: int, total: int) -> None:
    print(f"[{index}/{total}] {command.label}")
    print(f"      $ {_command_display(command)}")
    environment = os.environ.copy()
    if command.env:
        environment.update(command.env)
    result = subprocess.run(command.argv, cwd=command.cwd, env=environment, check=False)
    if result.returncode != 0:
        raise PreflightError(
            f"{command.label} failed with exit code {result.returncode}: "
            f"{_command_display(command)}"
        )


def _npm_executable() -> str:
    executable = shutil.which("npm")
    if executable is None:
        raise PreflightError("npm is required for Admin verification but was not found on PATH")
    return executable


def _gradle_executable() -> str:
    candidate = ROOT / ("gradlew.bat" if os.name == "nt" else "gradlew")
    _require_path(candidate, "Gradle wrapper")
    return str(candidate)


def verification_commands(scopes: set[str], *, release_requested: bool) -> list[Command]:
    commands: list[Command] = []
    python = sys.executable
    if "admin" in scopes:
        _require_module("pglast", f"{python} -m pip install pglast==7.10")
        npm = _npm_executable()
        admin_environment = {"NEXT_PUBLIC_FINDONE_ADMIN_DEMO": "1"}
        commands.extend(
            (
                Command(
                    "Admin Python regression tests",
                    (
                        python,
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "tools",
                        "-p",
                        "test_admin*.py",
                        "-v",
                    ),
                ),
                Command(
                    "Glossary content regression tests",
                    (
                        python,
                        "-m",
                        "unittest",
                        "tools.test_glossary_content",
                        "-v",
                    ),
                ),
                Command("Supabase SQL syntax validation", (python, "tools/validate_supabase_sql.py")),
                Command("Admin dependency lock install", (npm, "ci"), ROOT / "admin", admin_environment),
                Command("Admin Vitest suite", (npm, "test"), ROOT / "admin", admin_environment),
                Command(
                    "Admin production build",
                    (npm, "run", "build"),
                    ROOT / "admin",
                    admin_environment,
                ),
            )
        )
    if "model" in scopes:
        _require_module(
            "numpy",
            f"{python} -m pip install -r tools/requirements-concept-model-core.txt",
        )
        _require_module(
            "sklearn",
            f"{python} -m pip install -r tools/requirements-concept-model-core.txt",
        )
        commands.extend(
            (
                Command(
                    "Local model regression tests",
                    (
                        python,
                        "-m",
                        "unittest",
                        "tools.test_local_content_model",
                        "tools.test_build_content_db",
                        "tools.test_train_concept_question_model",
                        "tools.test_repo_preflight",
                        "-v",
                    ),
                ),
                Command(
                    "Deterministic relative-path concept ranker",
                    (
                        python,
                        "tools/train_concept_question_model.py",
                        "--ranker",
                        "pairwise-logistic",
                        "--quiet",
                        "--split",
                        "build/concept-ci/split.json",
                        "--question-bank",
                        "build/concept-ci/question-bank.json",
                        "--build-dir",
                        "build/concept-ci",
                    ),
                ),
                Command(
                    "Deterministic app-content compile check",
                    (
                        python,
                        "tools/compile_app_content.py",
                        "--check",
                        "--benchmark-rounds",
                        "3",
                        "--report",
                        "build/local-content-model-report.json",
                    ),
                ),
            )
        )
    if "android" in scopes:
        gradle = _gradle_executable()
        commands.append(
            Command(
                "Android debug tests, lint, and assembly",
                (
                    gradle,
                    "testDebugUnitTest",
                    "lintDebug",
                    "assembleDebug",
                    "--console=plain",
                ),
            )
        )
    if release_requested:
        gradle = _gradle_executable()
        commands.append(
            Command(
                "Release concept-question gate",
                (gradle, ":app:verifyReleaseConceptQuestionBank", "--console=plain"),
            )
        )
    return commands


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inspect", "verify"))
    parser.add_argument(
        "--scope",
        action="append",
        default=None,
        help="auto, all, admin, model, android, or release; repeat or comma-separate",
    )
    parser.add_argument(
        "--changes",
        choices=("working", "staged", "head"),
        default="working",
        help="Git change set used by auto scope selection",
    )
    parser.add_argument("--ci", action="store_true", help="Skip clone-local hook activation check")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = changed_paths(args.changes)
    scopes, release_requested = resolve_scopes(args.scope or ["auto"], paths)
    printable_scopes = sorted(scopes | ({"release"} if release_requested else set()))

    print("FinDone repository preflight")
    print(f"  phase: {args.phase}")
    print(f"  changes: {args.changes} ({len(paths)} path(s))")
    print(f"  scopes: {', '.join(printable_scopes) if printable_scopes else 'core-only'}")
    status = inspect_repository(
        scopes,
        release_requested=release_requested,
        change_mode=args.changes,
        ci=args.ci,
    )
    release_note = "ready" if status == "release_ready" else f"blocked ({status})"
    print(f"  release: {release_note}")
    print("  inspection: passed")

    if args.phase == "inspect":
        return 0

    commands = verification_commands(scopes, release_requested=release_requested)
    for index, command in enumerate(commands, start=1):
        _run_command(command, index, len(commands))
    print(f"FinDone verification passed ({len(commands)} command(s)).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PreflightError, OSError, ValueError) as error:
        print(f"FinDone preflight failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
