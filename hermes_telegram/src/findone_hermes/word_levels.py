"""Offline lexical eligibility from a locally cached official Oxford word list.

Levels describe listed headwords, not a model's estimate of a phrase or sense.
Unknown terms are never assigned an invented CEFR level.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping

from .config import absolute_path

OXFORD_URL = "https://www.oxfordlearnersdictionaries.com/external/pdf/wordlists/oxford-3000-5000/The_Oxford_5000.pdf"
_WORD = re.compile(r"[A-Za-z][A-Za-z -]{0,79}\Z")
_TOKEN = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z]+)*\b")
_LEVELS = {"B2": 2, "C1": 3}


class WordLevelError(ValueError):
    pass


@dataclass(frozen=True)
class AdvancedWord:
    term: str
    lemma: str
    level: str
    context: str
    reference: str = OXFORD_URL


class WordLevels:
    def __init__(self, entries: Mapping[str, str], *, minimum: str = "B2") -> None:
        if minimum not in _LEVELS or not entries:
            raise WordLevelError("A nonempty lexical list and supported minimum level are required")
        normalized = {}
        for lemma, level in entries.items():
            if not isinstance(lemma, str) or not _WORD.fullmatch(lemma) or level not in _LEVELS:
                raise WordLevelError("Invalid lexical eligibility entry")
            normalized[lemma.casefold()] = level
        self.entries, self.minimum = normalized, minimum

    @classmethod
    def from_env(cls, environment: Mapping[str, str]) -> "WordLevels":
        value = environment.get("FINDONE_CEFR_WORDLIST_PATH", "").strip()
        if not value:
            raise WordLevelError("The official local CEFR word list must be configured")
        path = absolute_path(value, "FINDONE_CEFR_WORDLIST_PATH")
        if path.stat().st_size > 2_000_000:
            raise WordLevelError("Lexical list exceeds its size limit")
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or type(data.get("schema_version")) is not int or data.get("schema_version") != 1
                or data.get("source_url") != OXFORD_URL or not isinstance(data.get("entries"), dict)):
            raise WordLevelError("Use the verified official lexical list format")
        return cls(data["entries"], minimum=environment.get("FINDONE_VOCAB_MIN_LEVEL", "B2").strip())

    def lookup(self, term: str) -> tuple[str, str] | None:
        surface = term.casefold().strip()
        forms = [surface]
        if surface.endswith("ies") and len(surface) > 4:
            forms.append(surface[:-3] + "y")
        if surface.endswith("s") and not surface.endswith("ss"):
            forms.extend((surface[:-1], surface[:-2] if surface.endswith("es") else ""))
        if surface.endswith("ied"):
            forms.append(surface[:-3] + "y")
        for suffix in ("ed", "ing"):
            if surface.endswith(suffix) and len(surface) > len(suffix) + 2:
                stem = surface[:-len(suffix)]
                forms.extend((stem, stem + "e"))
                if len(stem) > 2 and stem[-1] == stem[-2]:
                    forms.append(stem[:-1])
        for lemma in forms:
            level = self.entries.get(lemma)
            if level and _LEVELS[level] >= _LEVELS[self.minimum]:
                return lemma, level
        return None

    def candidates(self, sentences: tuple[str, ...], limit: int = 4) -> tuple[AdvancedWord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 4:
            raise WordLevelError("Candidate count must be between zero and four")
        found = {}
        for sentence in sentences:
            for match in _TOKEN.finditer(sentence):
                term = match.group()
                entry = self.lookup(term)
                if entry and entry[0] not in found:
                    lemma, level = entry
                    found[lemma] = AdvancedWord(term, lemma, level, sentence)
        # Prefer more advanced known headwords; retain article order for ties.
        return tuple(sorted(found.values(), key=lambda word: -_LEVELS[word.level])[:limit])
