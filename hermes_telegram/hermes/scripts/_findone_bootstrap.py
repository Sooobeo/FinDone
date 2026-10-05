"""Load only FinDone's external configuration and invoke the installed package.

Hermes intentionally removes provider credentials from script-only cron child
environments. Read the local profile file explicitly without shell execution.
This module is copied with the wrappers into the real Hermes scripts directory.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

_CONFIG_KEYS = frozenset(
    {
        "FINDONE_REPO_ROOT",
        "CONTENT_DB_PATH",
        "CONTENT_MANIFEST_PATH",
        "STATE_DB_PATH",
        "TELEGRAM_ALLOWED_USERS",
        "FINDONE_QUIZ_COUNT",
        "FINDONE_MODEL_BASE_URL",
        "FINDONE_MODEL_NAME",
        "FINDONE_MODEL_API_KEY",
        "FINDONE_MODEL_TIMEOUT_SECONDS",
        "FINDONE_MODEL_REASONING_EFFORT",
        "FINDONE_MODEL_PRESENCE_PENALTY",
        "FINDONE_TELEGRAM_MODE",
        "FINDONE_NEWS_FOCUS",
        "FINDONE_CEFR_WORDLIST_PATH",
        "FINDONE_VOCAB_MIN_LEVEL",
        "FINDONE_NEWS_ARCHIVE_PATH",
        "FINDONE_VOCAB_DB_PATH",
        "FINDONE_VOCAB_STATE_PATH",
        "FINDONE_WIKI_CLI_PATH",
        "FINDONE_WIKI_HOME",
        "FINDONE_WIKI_VAULT",
        "FINDONE_WIKI_VAULT_PATH",
    }
)
_ASSIGNMENT = re.compile(r"(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*)\Z")


def _read_config(path: Path, *, include_bot_token: bool = False) -> dict[str, str]:
    settings = {}
    keys = _CONFIG_KEYS | {"TELEGRAM_BOT_TOKEN"} if include_bot_token else _CONFIG_KEYS
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT.fullmatch(line)
        if not match or match[1] not in keys:
            continue
        key, value = match.groups()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end + 1 :].strip() and not value[end + 1 :].lstrip().startswith("#")):
                raise ValueError("Invalid local configuration quoting")
            value = value[1:end]
        else:
            value = value.split(" #", 1)[0].strip()
        if key in settings:
            raise ValueError("Duplicate local configuration setting")
        # Values are literal: no ${...}, command substitution, or eval.
        settings[key] = value
    return settings


def load_config_env() -> None:
    configured_path = os.environ.get("FINDONE_ENV_FILE")
    if configured_path:
        path = Path(configured_path).expanduser()
    else:
        # The wrapper is installed in the real <profile>/scripts directory.
        # Its parent resolves POSIX, Windows, and named-profile homes even when
        # cron does not retain HERMES_HOME in its sanitized child environment.
        home = (
            Path(os.environ["HERMES_HOME"]).expanduser()
            if os.environ.get("HERMES_HOME")
            else Path(__file__).resolve().parents[1]
        )
        path = home / ".env"
    if not path.is_absolute():
        raise ValueError("FINDONE_ENV_FILE must be an absolute external path")
    path = path.resolve()
    if any((parent / ".git").exists() for parent in path.parents):
        raise ValueError("Local configuration must remain outside Git repositories")
    settings = _read_config(path)
    repo = os.environ.get("FINDONE_REPO_ROOT") or settings.get("FINDONE_REPO_ROOT")
    if repo and path.is_relative_to(Path(repo).expanduser().resolve()):
        raise ValueError("Local configuration must remain outside the repository")
    for key, value in settings.items():
        os.environ.setdefault(key, value)


def load_news_config_env() -> dict[str, str]:
    """Read this installed news wrapper's profile, without process-env fallbacks.

    HERMES_HOME/FINDONE_ENV_FILE may describe the multiplexer's default profile;
    the installed scripts directory is authoritative for dedicated news delivery.
    The token is returned only here and is never copied into the process env.
    """
    path = (Path(__file__).resolve().parents[1] / ".env").resolve()
    if any((parent / ".git").exists() for parent in path.parents):
        raise ValueError("Local configuration must remain outside Git repositories")
    settings = _read_config(path, include_bot_token=True)
    repo = settings.get("FINDONE_REPO_ROOT")
    if repo and path.is_relative_to(Path(repo).expanduser().resolve()):
        raise ValueError("Local configuration must remain outside the repository")
    return settings


def run_news_delivery() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        environment = load_news_config_env()
        from findone_hermes.news_delivery import main
        return main(environment)
    except Exception:
        print("FinDone news error: news_configuration_failed", file=sys.stderr)
        return 1


def run(kind: str, slot: str) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        load_config_env()
        from findone_hermes.jobs import main
    except Exception:
        print("FinDone: local configuration or package could not be loaded.", file=sys.stderr)
        return 1
    return main([kind, "--slot", slot])
