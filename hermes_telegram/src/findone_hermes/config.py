"""Environment-only configuration; never log credentials or Telegram identifiers."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping


class ConfigurationError(ValueError):
    pass


def absolute_path(value: str, name: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConfigurationError(f"{name} must be an absolute path")
    return path.resolve()


def repository_root(environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    value = environment.get("FINDONE_REPO_ROOT")
    return absolute_path(value, "FINDONE_REPO_ROOT") if value else Path(__file__).resolve().parents[3]


def content_paths(environment: Mapping[str, str] | None = None) -> tuple[Path, Path]:
    environment = os.environ if environment is None else environment
    assets = repository_root(environment) / "app" / "src" / "main" / "assets"
    db = absolute_path(environment["CONTENT_DB_PATH"], "CONTENT_DB_PATH") if environment.get("CONTENT_DB_PATH") else assets / "content.sqlite3"
    manifest = absolute_path(environment["CONTENT_MANIFEST_PATH"], "CONTENT_MANIFEST_PATH") if environment.get("CONTENT_MANIFEST_PATH") else db.with_name("content-manifest.json")
    return db, manifest


def allowed_user(environment: Mapping[str, str] | None = None) -> str:
    environment = os.environ if environment is None else environment
    value = environment.get("TELEGRAM_ALLOWED_USERS", "").strip()
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ConfigurationError("TELEGRAM_ALLOWED_USERS must contain exactly one numeric user ID")
    return value


def private_news_path(environment: Mapping[str, str], key: str, filename: str) -> Path:
    """Resolve profile-owned news data without inheriting a different profile."""
    if not environment.get("STATE_DB_PATH", "").strip():
        raise ConfigurationError("News features require an explicit STATE_DB_PATH")
    settings = Settings.from_env(environment)
    value = environment.get(key, "").strip()
    path = absolute_path(value, key) if value else settings.state_db.parent / filename
    path = path.resolve()
    root = repository_root(environment).resolve()
    if path == root or path.is_relative_to(root):
        raise ConfigurationError("Private news data must remain outside the repository")
    if path in {settings.state_db, settings.content_db.resolve(), settings.content_manifest.resolve()}:
        raise ConfigurationError("News databases cannot replace existing state or content")
    return path


def is_allowed(platform: str, user_id: str, chat_id: str, chat_type: str) -> bool:
    try:
        return platform.lower() == "telegram" and chat_type.lower() in {"dm", "private"} and str(user_id) == str(chat_id) == allowed_user()
    except ConfigurationError:
        return False


@dataclass(frozen=True)
class Settings:
    user_id: str
    state_db: Path
    content_db: Path
    content_manifest: Path
    quiz_count: int = 2
    news_focus: str = "general"

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> "Settings":
        # Routed Hermes profiles must pass their own mapping. An explicit mapping
        # is authoritative, including absent keys; never inherit another bot's env.
        environment = os.environ if environment is None else environment
        user_id = allowed_user(environment)
        db, manifest = content_paths(environment)
        if environment.get("STATE_DB_PATH"):
            state = absolute_path(environment["STATE_DB_PATH"], "STATE_DB_PATH")
        elif os.name == "nt":
            base = Path(environment.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            state = base / "FinDone" / "hermes" / "state.sqlite3"
        else:
            base = absolute_path(environment["XDG_DATA_HOME"], "XDG_DATA_HOME") if environment.get("XDG_DATA_HOME") else Path.home() / ".local" / "share"
            state = base / "findone-hermes" / "state.sqlite3"
        state = state.resolve()
        roots = {repository_root(environment).resolve()}
        # Also detect an editable/installed package pointed at another checkout.
        for ancestor in db.resolve().parents:
            if (ancestor / "AGENTS.md").exists() and ((ancestor / ".git").exists()):
                roots.add(ancestor)
                break
        if any(state == root or state.is_relative_to(root) for root in roots):
            raise ConfigurationError("STATE_DB_PATH must be outside the repository")
        if state in {db.resolve(), manifest.resolve()}:
            raise ConfigurationError("STATE_DB_PATH cannot replace content assets")
        try:
            count = int(environment.get("FINDONE_QUIZ_COUNT", "2"))
        except ValueError as error:
            raise ConfigurationError("FINDONE_QUIZ_COUNT must be 1 to 4") from error
        if count not in range(1, 5):
            raise ConfigurationError("FINDONE_QUIZ_COUNT must be 1 to 4")
        focus = environment.get("FINDONE_NEWS_FOCUS", "general").strip()
        if focus not in {"general", "securities_insurance"}:
            raise ConfigurationError("FINDONE_NEWS_FOCUS must be general or securities_insurance")
        return cls(user_id, state, db, manifest, count, focus)
