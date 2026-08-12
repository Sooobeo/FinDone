# FinDone repository instructions

These instructions apply to every Codex task in this repository. Nested
`AGENTS.md` files may add area-specific rules but do not cancel this preflight.

## Mandatory startup preflight

Before the first command that can write files, install packages, generate
artifacts, run a build, commit, push, or change external state:

1. Preserve the user's existing work. Read `git status --short` and identify
   which files are already modified or untracked.
2. Select the intended scope: `admin`, `model`, `android`, or `release`. Use
   more than one `--scope` when needed; use `all` when uncertain.
3. Run the read-only repository inspection:

   ```text
   python tools/repo_preflight.py inspect --scope <scope> --changes working
   ```

4. Read every reported warning or failure before continuing. Do not work
   around a failed preflight. Fix its cause or explain the blocker.

Read-only file discovery needed to select a scope is allowed before this
command. The inspection may write only to an OS temporary directory and must
not regenerate tracked files in place.

## Mandatory verification before handoff

After implementation and before claiming completion, committing, or pushing,
run the exact relevant suite:

```text
python tools/repo_preflight.py verify --scope auto --changes working
```

If `auto` cannot see the intended area, pass explicit scopes. A check may be
skipped only when the environment genuinely cannot run it, and the final
briefing must name the skipped command and reason. Never describe unrun checks
as passing.

The tracked `.githooks/pre-commit` repeats verification against the staged
scope. Do not bypass it. If hooks are not active, enable them with:

```text
git config --local core.hooksPath .githooks
```

## Generated data and CI parity

- Never hand-edit `admin/data/*.generated.json`. Regenerate it with
  `tools/admin_export_content.py`; preflight compares a temporary canonical
  export byte-for-byte with the tracked fixtures.
- Model verification must execute the same relative-path CLI used by GitHub
  Actions. A successful import or unit test alone is insufficient.
- GitHub Actions must call `tools/repo_preflight.py`; do not duplicate a second
  command list that can drift from local verification.
- When a CI run failed on an old commit, do not merely rerun that run. Verify
  locally, commit and push the fix, then inspect the new run.
- Keep paths passed through CLIs independent of the caller's current working
  directory. Report paths with the repository-safe path helper rather than
  direct `Path.relative_to(ROOT)` calls.

## Release safety

- Always inspect the manifest status before any release Gradle task or release
  automation command.
- `bootstrap_not_reviewed` and `candidate` are valid development states but
  are not releasable. Do not attempt to bypass the release gate.
- Only `release_ready`, backed by the required independent human review, may
  proceed to release verification or APK publication.
- Bootstrap metrics are engineering diagnostics, not production accuracy or
  model generalization claims.

See `docs/operations/CODEX_PREFLIGHT.md` for the command matrix and remediation guide.
