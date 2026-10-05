"""Read-only content access with the Android asset loader's integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3


class ContentIntegrityError(RuntimeError):
    """The packaged content cannot safely be used."""


@dataclass(frozen=True)
class Domain:
    domain_id: str
    name: str
    description: str


@dataclass(frozen=True)
class Element:
    element_id: str
    domain_id: str
    title: str
    definition: str
    intuition: str
    core_relation: str


@dataclass(frozen=True)
class Choice:
    key: str
    text: str
    explanation: str
    is_correct: bool


@dataclass(frozen=True)
class Question:
    question_id: str
    element_id: str
    domain_id: str
    stem: str
    explanation: str
    review_status: str
    choices: tuple[Choice, ...]


DOMAIN_COUNTS = {"ACC": 12, "CF": 12, "INV": 9, "FI": 10,
                 "DER": 10, "EQV": 64, "IBT": 18}
TABLES = {"metadata", "domains", "elements", "concept_cards", "formula_cards",
          "concept_questions", "concept_question_choices", "sources",
          "element_sources", "knowledge_fts"}
CANONICAL_COUNTS = {"domains": 7, "elements": 135, "concept_cards": 135,
                    "formula_cards": 135, "concept_questions": 405,
                    "concept_question_choices": 2025, "knowledge_fts": 135}
ELIGIBLE_STATUSES = ("automated_pass", "owner_approved")


class ContentRepository:
    def __init__(self, db_path: str | Path, manifest_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.manifest_path = Path(manifest_path).expanduser().resolve()
        self.connection: sqlite3.Connection | None = None
        try:
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self._validate_manifest()
            if self.db_path.stat().st_size != self.manifest["byteSize"]:
                raise ContentIntegrityError("Content database size mismatch")
            with self.db_path.open("rb") as asset:
                digest = hashlib.file_digest(asset, "sha256").hexdigest()
            if digest != self.manifest["sha256"].lower():
                raise ContentIntegrityError("Content database SHA-256 mismatch")
            self.connection = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True,
                                             check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA query_only = ON")
            self._validate_database()
            self._load()
        except ContentIntegrityError:
            self.close()
            raise
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            self.close()
            raise ContentIntegrityError("Content asset or manifest is invalid") from error

    def _validate_manifest(self) -> None:
        m = self.manifest
        if not isinstance(m, dict) or m.get("manifestVersion") != 1 or m.get("schemaVersion") != 2:
            raise ContentIntegrityError("Unsupported content manifest/schema version")
        if m.get("databaseAsset") != "content.sqlite3":
            raise ContentIntegrityError("Unsupported database asset name")
        for name in ("sha256", "sourceSha256", "conceptQuestionBankSha256"):
            if not isinstance(m.get(name), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", m[name]):
                raise ContentIntegrityError("Malformed content SHA-256")
        if any(type(m.get(key)) is not int or m[key] < 1 for key in ("contentDbVersion", "byteSize")):
            raise ContentIntegrityError("Invalid content version or size")
        counts = m.get("rowCounts")
        if not isinstance(counts, dict) or set(counts) != TABLES:
            raise ContentIntegrityError("Manifest table verification set is incomplete")
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ContentIntegrityError("Invalid manifest row count")
        if any(counts.get(key) != count for key, count in CANONICAL_COUNTS.items()):
            raise ContentIntegrityError("Manifest card/question/FTS invariant failed")
        if m.get("domainElementCounts") != DOMAIN_COUNTS:
            raise ContentIntegrityError("Manifest domain row counts are not canonical")
        if (m.get("conceptQuestionBankVersion") != 2
                or not isinstance(m.get("conceptQuestionModelVersion"), str)
                or not m["conceptQuestionModelVersion"].strip()
                or m.get("conceptQuestionReleaseStatus") not in
                {"bootstrap_not_reviewed", "candidate", "release_ready"}):
            raise ContentIntegrityError("Manifest question-bank invariant failed")

    def _validate_database(self) -> None:
        c = self.connection
        assert c is not None
        if [row[0] for row in c.execute("PRAGMA integrity_check")] != ["ok"]:
            raise ContentIntegrityError("SQLite integrity_check failed")
        if c.execute("PRAGMA user_version").fetchone()[0] != self.manifest["schemaVersion"]:
            raise ContentIntegrityError("Content schema version mismatch")
        for table, expected in self.manifest["rowCounts"].items():
            if c.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] != expected:
                raise ContentIntegrityError(f"Content table row count mismatch: {table}")
        if dict(c.execute("SELECT domain_id, COUNT(*) FROM elements GROUP BY domain_id")) != DOMAIN_COUNTS:
            raise ContentIntegrityError("Database domain row counts are not canonical")
        metadata = dict(c.execute("SELECT key, value FROM metadata"))
        metadata_checks = {"content_db_version": str(self.manifest["contentDbVersion"]),
                           "schema_version": str(self.manifest["schemaVersion"]),
                           "concept_question_bank_version": str(self.manifest["conceptQuestionBankVersion"]),
                           "concept_question_model_version": self.manifest["conceptQuestionModelVersion"],
                           "concept_question_release_status": self.manifest["conceptQuestionReleaseStatus"]}
        if any(metadata.get(key) != value for key, value in metadata_checks.items()):
            raise ContentIntegrityError("Database version/status metadata mismatch")
        for key, manifest_key in (("source_spec_sha256", "sourceSha256"),
                                  ("concept_question_bank_sha256", "conceptQuestionBankSha256")):
            if metadata.get(key, "").lower() != self.manifest[manifest_key].lower():
                raise ContentIntegrityError("Database content metadata hash mismatch")
        if c.execute("""SELECT COUNT(*) FROM concept_questions WHERE review_status NOT IN
                        ('automated_pass','needs_owner_review','blocked','owner_approved')""").fetchone()[0]:
            raise ContentIntegrityError("Database concept-question review status is invalid")
        if self.manifest["conceptQuestionReleaseStatus"] == "release_ready":
            if c.execute("""SELECT COUNT(*) FROM concept_questions WHERE review_status NOT IN
                            ('automated_pass','owner_approved')""").fetchone()[0]:
                raise ContentIntegrityError("Release-ready database contains ineligible questions")
            if c.execute("""SELECT COUNT(*) FROM (SELECT e.element_id FROM elements e
                            LEFT JOIN concept_questions q ON e.element_id=q.element_id
                            AND q.review_status IN ('automated_pass','owner_approved')
                            GROUP BY e.element_id HAVING COUNT(q.question_id)=0)""").fetchone()[0]:
                raise ContentIntegrityError("Release-ready database lacks eligible coverage")
        if c.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ContentIntegrityError("SQLite foreign_key_check failed")
        c.execute("SELECT COUNT(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'ROE'").fetchone()
        c.execute("SELECT bm25(knowledge_fts) FROM knowledge_fts WHERE knowledge_fts MATCH 'ROE' LIMIT 1").fetchone()
        if c.execute("""SELECT COUNT(*) FROM (
                        SELECT q.question_id FROM concept_questions q
                        LEFT JOIN concept_question_choices c ON c.question_id=q.question_id
                        GROUP BY q.question_id HAVING COUNT(c.choice_key)!=5
                        OR SUM(c.is_correct)!=1 OR COUNT(DISTINCT c.choice_key)!=5
                        OR SUM(CASE WHEN c.choice_key IN ('A','B','C','D','E') THEN 1 ELSE 0 END)!=5
                        OR SUM(CASE WHEN c.is_correct IN (0,1) THEN 0 ELSE 1 END)!=0)""").fetchone()[0]:
            raise ContentIntegrityError("Question must have five A-E choices and one correct answer")

    def _load(self) -> None:
        c = self.connection
        assert c is not None
        self._domains = tuple(Domain(*row) for row in c.execute(
            "SELECT domain_id,name,description FROM domains ORDER BY display_order"))
        self._elements = tuple(Element(*row) for row in c.execute("""
            SELECT e.element_id,e.domain_id,c.title,c.definition,c.intuition,e.core_relation
            FROM elements e JOIN concept_cards c ON c.element_id=e.element_id
            ORDER BY e.display_order"""))
        choices: dict[str, list[Choice]] = {}
        for row in c.execute("""SELECT question_id,choice_key,text,explanation,is_correct
                                FROM concept_question_choices ORDER BY question_id,choice_order"""):
            choices.setdefault(row[0], []).append(Choice(row[1], row[2], row[3], bool(row[4])))
        self._questions = tuple(Question(*row, tuple(choices[row[0]])) for row in c.execute("""
            SELECT q.question_id,q.element_id,e.domain_id,q.stem,q.explanation,q.review_status
            FROM concept_questions q JOIN elements e ON e.element_id=q.element_id
            WHERE q.review_status IN ('automated_pass','owner_approved') ORDER BY q.display_order"""))
        self._element_map = {item.element_id: item for item in self._elements}
        self._question_map = {item.question_id: item for item in self._questions}

    def domains(self) -> tuple[Domain, ...]:
        return self._domains

    def elements(self, domain_id: str | None = None) -> tuple[Element, ...]:
        return tuple(item for item in self._elements if domain_id is None or item.domain_id == domain_id.upper())

    def questions(self, element_id: str | None = None) -> tuple[Question, ...]:
        return tuple(item for item in self._questions if element_id is None or item.element_id == element_id.upper())

    def element(self, element_id: str) -> Element | None:
        return self._element_map.get(element_id.strip().upper())

    def question(self, question_id: str) -> Question | None:
        return self._question_map.get(question_id)

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> ContentRepository:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
