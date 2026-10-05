"""Private vocabulary projection through the official Oh My Wiki CLI.

Only immutable word/source fields enter a page. Quiz attempts, review schedules,
Telegram identity, and credentials stay in their separate private SQLite store.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time
from typing import Mapping
from urllib.parse import urlsplit
from uuid import UUID

from .config import absolute_path, repository_root


class WikiError(RuntimeError):
    """A private wiki operation failed; details never contain page/CLI content."""


@dataclass(frozen=True)
class WikiEntry:
    word_id: str
    term: str
    lemma: str
    sense: str
    meaning_ko: str
    sentence: str
    article_url: str
    article_title: str
    source_name: str
    published_at: str
    explanation_ko: str = ""


@dataclass(frozen=True)
class WikiSyncResult:
    status: str
    relpath: str


_CONFIG_KEYS = (
    "FINDONE_WIKI_CLI_PATH", "FINDONE_WIKI_HOME",
    "FINDONE_WIKI_VAULT", "FINDONE_WIKI_VAULT_PATH",
)
_PROCESS_KEYS = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME",
    "USERPROFILE", "LOCALAPPDATA", "APPDATA", "COMSPEC",
}


def _text(value: str, limit: int, *, optional: bool = False, preserve_spacing: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise WikiError("Invalid vocabulary source field")
    result = re.sub(r"[\r\n\t]", " ", value).strip() if preserve_spacing else " ".join(value.split())
    if (not result and not optional) or any(ord(char) < 32 for char in result):
        raise WikiError("Invalid vocabulary source field")
    return result.replace("<!--", "&lt;!--").replace("-->", "--&gt;")


def _render(entry: WikiEntry) -> tuple[str, str, str, str]:
    try:
        word_id = UUID(entry.word_id).hex
        published = datetime.fromisoformat(entry.published_at.replace("Z", "+00:00"))
        parts = urlsplit(entry.article_url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("invalid source URL")
    except (ValueError, TypeError, AttributeError) as error:
        raise WikiError("Invalid vocabulary identity or source") from error
    values = {
        "term": _text(entry.term, 80, preserve_spacing=True), "lemma": _text(entry.lemma, 80),
        "sense": _text(entry.sense, 300), "meaning": _text(entry.meaning_ko, 300),
        "sentence": _text(entry.sentence, 2500, preserve_spacing=True), "url": _text(entry.article_url, 2000),
        "article": _text(entry.article_title, 500), "source": _text(entry.source_name, 100),
        "explanation": _text(entry.explanation_ko, 1500, optional=True),
    }
    # OMW 2.54's title slug is limited to 80 characters. Keep the complete UUID
    # even for long terms, so separate contexts can never collide on a filename.
    title = f"{values['term'][:40]} {word_id}"
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", title.strip().lower()).strip("-")
    relpath = f"wiki/concepts/{slug}.md"
    fingerprint = hashlib.sha256(
        json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    marker = f"<!-- findone-word: {word_id}; source: {fingerprint} -->"
    lines = [
        marker, f"# {values['term']}", "", "## 문맥별 뜻", "",
        f"- 표제어: {values['lemma']}", f"- 의미 구분: {values['sense']}",
        f"- 한국어 뜻: {values['meaning']}", "", "## 기사 속 문장", "",
        f"> {values['sentence']}", "", "## 출처", "",
        f"- 기사: {values['article']}", f"- 기관: {values['source']}",
        f"- 발행일: {published.date().isoformat()}", f"- 원문: {values['url']}",
    ]
    if values["explanation"]:
        lines.extend(["", "## 문맥 설명", "", values["explanation"]])
    return title, relpath, marker, "\n".join(lines) + "\n"


@contextmanager
def _vault_lock(home: Path):
    # OS locks disappear on process exit; no stale lock reservation can prevent
    # an outbox retry. Serialize the canonical CLI's collision-suffixed writes.
    with (home / "findone-vocabulary.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + 3
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise WikiError("Private wiki is busy") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class WikiSync:
    cli_path: Path
    home: Path
    vault: str
    vault_path: Path

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> WikiSync | None:
        env = os.environ if environment is None else environment
        values = [env.get(key, "").strip() for key in _CONFIG_KEYS]
        if not any(values):
            return None
        if not all(values):
            raise WikiError("All private wiki configuration fields are required")
        try:
            cli = absolute_path(values[0], _CONFIG_KEYS[0])
            home = absolute_path(values[1], _CONFIG_KEYS[1])
            vault_path = absolute_path(values[3], _CONFIG_KEYS[3])
            root = repository_root(env).resolve()
            for path in (cli, home, vault_path):
                if path == root or path.is_relative_to(root):
                    raise WikiError("Private wiki paths must be outside the repository")
            if not cli.is_file() or not home.is_dir() or not vault_path.is_dir():
                raise WikiError("Private wiki installation or vault is unavailable")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", values[2]):
                raise WikiError("Invalid private wiki vault name")
            return cls(cli, home, values[2], vault_path)
        except WikiError:
            raise
        except Exception:
            raise WikiError("Invalid private wiki configuration") from None

    def _run(self, *arguments: str) -> dict:
        env = {key: value for key, value in os.environ.items() if key.upper() in _PROCESS_KEYS}
        env.update({"OMW_HOME": str(self.home), "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})
        try:
            result = subprocess.run(
                [str(self.cli_path), *arguments], shell=False, check=False,
                capture_output=True, text=True, encoding="utf-8", errors="strict",
                timeout=20, env=env,
            )
            if result.returncode or len(result.stdout) > 65536:
                raise WikiError("Private wiki CLI operation failed")
            payload = json.loads(result.stdout)
            if not isinstance(payload, dict):
                raise WikiError("Private wiki CLI returned invalid metadata")
            return payload
        except WikiError:
            raise
        except Exception:
            # Never relay stderr, args, source text, process env, or exception body.
            raise WikiError("Private wiki CLI operation failed") from None

    def sync(self, entry: WikiEntry) -> WikiSyncResult:
        title, relpath, marker, body = _render(entry)
        with _vault_lock(self.home):
            info = self._run("vault", "info", self.vault)
            try:
                matches = Path(info["path"]).resolve() == self.vault_path.resolve()
            except Exception:
                matches = False
            if not matches or info.get("mode") != "wiki" or info.get("archived", False):
                raise WikiError("Private wiki vault registration does not match configuration")
            page = self.vault_path / PurePosixPath(relpath)
            if not page.resolve().is_relative_to(self.vault_path.resolve()):
                raise WikiError("Private wiki page path escapes the vault")
            existed = page.exists()
            if existed:
                if not page.is_file() or marker not in page.read_text(encoding="utf-8"):
                    raise WikiError("Existing private wiki page belongs to different content")
            else:
                temporary_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w", encoding="utf-8", suffix=".md", prefix="findone-vocab-", delete=False,
                    ) as temporary:
                        temporary.write(body)
                        temporary_path = Path(temporary.name)
                    output = self._run(
                        "page", "write", "--layer", "concepts", "--title", title,
                        "--body-file", str(temporary_path), "--date",
                        datetime.fromisoformat(entry.published_at.replace("Z", "+00:00")).date().isoformat(),
                        "--tags", "findone,english,financial-vocabulary", "--index",
                        f"{entry.term}: {entry.meaning_ko}", "--vault", self.vault,
                    )
                    if output.get("relpath") != relpath:
                        raise WikiError("Private wiki CLI returned an unexpected page path")
                finally:
                    if temporary_path is not None:
                        temporary_path.unlink(missing_ok=True)
            # Explicit privacy plus incremental indexing also recovers a page
            # created before a timeout/crash. OMW's public-only serve is unused.
            output = self._run("visibility", "set", relpath, "private", "--vault", self.vault)
            if (
                output.get("set") != "private" or relpath not in output.get("updated", [])
                or output.get("missing") or output.get("failed")
            ):
                raise WikiError("Private wiki page could not be marked private")
            return WikiSyncResult("already_synced" if existed else "synced", relpath)
