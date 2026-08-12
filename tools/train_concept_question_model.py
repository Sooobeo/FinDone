#!/usr/bin/env python3
"""Train and evaluate FinDone's offline five-choice distractor ranker.

The command is deliberately build-time only. It never calls an LLM API and it
does not place a model in the Android application. The resulting, validated
question bank is consumed by ``build_content_db.py``.

The first run uses weak supervision because no independent human-labelled test
set exists yet. Reports therefore remain ``bootstrap`` and release-blocked even
when regression metrics are high.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "content" / "model" / "concept-model-config.json"
DEFAULT_ELEMENTS = ROOT / "admin" / "data" / "content-elements.generated.json"
DEFAULT_LABELS = ROOT / "content" / "model" / "concept-review-labels.jsonl"
DEFAULT_OWNER_DECISIONS = ROOT / "content" / "model" / "concept-owner-decisions.jsonl"
DEFAULT_QUESTION_EDITS = ROOT / "content" / "model" / "concept-question-edits.jsonl"
DEFAULT_SPLIT = ROOT / "content" / "model" / "concept-split.json"
DEFAULT_BANK = ROOT / "content" / "model" / "concept-question-bank.generated.json"
DEFAULT_ADMIN_REPORT = ROOT / "admin" / "data" / "concept-model-experiments.generated.json"
DEFAULT_BUILD_DIR = ROOT / "build" / "concept-model"
DEFAULT_MARKDOWN_REPORT_DIR = ROOT / "docs" / "modeling" / "experiments"
REPORT_VERSION = 1
BANK_VERSION = 1
DOMAIN_ORDER = ("ACC", "CF", "INV", "FI", "DER", "EQV", "IBT")
CHOICE_KEYS = ("A", "B", "C", "D", "E")
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


class ConceptModelError(RuntimeError):
    """Raised when the model pipeline cannot produce a valid artifact."""


@dataclass(frozen=True)
class ElementRecord:
    element_id: str
    domain_id: str
    domain_name: str
    title: str
    mode: str
    definition: str
    intuition: str
    core_relation: str
    source_label: str
    source_locator: str

    @property
    def semantic_text(self) -> str:
        return "\n".join(
            (self.title, self.definition, self.intuition, self.core_relation)
        )


@dataclass(frozen=True)
class FactRecord:
    fact_id: str
    element_id: str
    domain_id: str
    fact_type: str
    text: str
    answer_text: str
    source_label: str
    source_locator: str
    review_status: str
    content_sha256: str


@dataclass(frozen=True)
class QuestionGroup:
    question_id: str
    element_index: int
    element_id: str
    domain_id: str
    question_type: str
    stem: str
    correct_answer: str
    fact_id: str
    split: str


@dataclass(frozen=True)
class HumanLabel:
    question_id: str
    candidate_element_id: str
    relevance: int
    reviewer_id: str
    review_status: str


@dataclass(frozen=True)
class OwnerQuestionDecision:
    question_id: str
    question_fingerprint: str
    decision: str
    reviewer_id: str
    reviewed_at: str
    comment: str


@dataclass(frozen=True)
class OwnerBatchDecision:
    review_input_sha256: str
    decision: str
    reviewer_id: str
    reviewed_at: str
    comment: str


@dataclass
class EmbeddingRun:
    candidate_id: str
    model_id: str
    status: str
    revision_requested: str
    revision_resolved: str | None
    dimensions: int | None
    encode_seconds: float | None
    artifact_bytes: int | None
    error: str | None
    cache_hit: bool = False
    matrix_cache_sha256: str | None = None
    query_candidate_similarity: np.ndarray | None = None
    answer_candidate_similarity: np.ndarray | None = None

    def report_dict(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "modelId": self.model_id,
            "status": self.status,
            "revisionRequested": self.revision_requested,
            "revisionResolved": self.revision_resolved,
            "dimensions": self.dimensions,
            "encodeSeconds": self.encode_seconds,
            "artifactBytes": self.artifact_bytes,
            "cacheHit": self.cache_hit,
            "matrixCacheSha256": self.matrix_cache_sha256,
            "error": self.error,
        }


@dataclass
class FeatureContext:
    elements: list[ElementRecord]
    questions: list[QuestionGroup]
    question_word_similarity: np.ndarray
    question_char_similarity: np.ndarray
    answer_word_similarity: np.ndarray
    answer_char_similarity: np.ndarray
    weak_relevance: np.ndarray


class ProgressBar:
    """Small terminal progress renderer matching the Admin stage model."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def update(self, percent: int, label: str, detail: str = "") -> None:
        if not self.enabled:
            return
        bounded = max(0, min(100, int(percent)))
        filled = int(bounded / 4)
        bar = "#" * filled + "-" * (25 - filled)
        suffix = f" · {detail}" if detail else ""
        print(f"[{bar}] {bounded:3d}%  {label}{suffix}", flush=True)


def _stable_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_path(path: Path) -> Path:
    """Resolve CLI paths consistently, independent of the caller's cwd."""
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _report_path(path: Path) -> str:
    """Render repo-local artifacts relatively without rejecting external paths."""
    resolved = _resolve_repo_path(path)
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value.rstrip())
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                )
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConceptModelError(f"Could not read JSON object: {path}") from error
    if not isinstance(value, dict):
        raise ConceptModelError(f"Expected a JSON object: {path}")
    return value


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).strip()


def normalized_key(value: str) -> str:
    return "".join(TOKEN_RE.findall(normalize_text(value).casefold()))


def _required_text(row: Mapping[str, Any], key: str, element_id: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not normalize_text(value):
        raise ConceptModelError(f"{element_id} has no usable {key}")
    return normalize_text(value)


def load_elements(path: Path = DEFAULT_ELEMENTS) -> list[ElementRecord]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConceptModelError(f"Could not read element catalogue: {path}") from error
    if not isinstance(raw, list):
        raise ConceptModelError("Element catalogue must be a JSON list")

    elements: list[ElementRecord] = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, Mapping):
            raise ConceptModelError("Each element catalogue entry must be an object")
        element_id = _required_text(row, "elementId", "unknown").upper()
        if element_id in seen:
            raise ConceptModelError(f"Duplicate element id: {element_id}")
        seen.add(element_id)
        domain_id = _required_text(row, "domainId", element_id).upper()
        if domain_id not in DOMAIN_ORDER:
            raise ConceptModelError(f"Unsupported domain for {element_id}: {domain_id}")
        elements.append(
            ElementRecord(
                element_id=element_id,
                domain_id=domain_id,
                domain_name=_required_text(row, "domainName", element_id),
                title=_required_text(row, "title", element_id),
                mode=_required_text(row, "mode", element_id),
                definition=_required_text(row, "definition", element_id),
                intuition=_required_text(row, "intuition", element_id),
                core_relation=_required_text(row, "coreRelation", element_id),
                source_label=_required_text(row, "sourceLabel", element_id),
                source_locator=_required_text(row, "sourceLocator", element_id),
            )
        )
    elements.sort(key=lambda item: (DOMAIN_ORDER.index(item.domain_id), item.element_id))
    if len(elements) != 135:
        raise ConceptModelError(f"Expected 135 canonical elements, found {len(elements)}")
    return elements


def content_fingerprint(elements: Sequence[ElementRecord]) -> str:
    return _sha256_bytes(_stable_json_bytes([asdict(item) for item in elements]))


def _largest_remainder_allocation(
    domain_counts: Mapping[str, int], total: int
) -> dict[str, int]:
    population = sum(domain_counts.values())
    if total < 0 or total > population:
        raise ConceptModelError("Invalid split allocation total")
    raw = {domain: count * total / population for domain, count in domain_counts.items()}
    result = {domain: math.floor(value) for domain, value in raw.items()}
    remaining = total - sum(result.values())
    order = sorted(
        domain_counts,
        key=lambda domain: (-(raw[domain] - result[domain]), DOMAIN_ORDER.index(domain)),
    )
    for domain in order[:remaining]:
        result[domain] += 1
    return result


def build_split(
    elements: Sequence[ElementRecord], config: Mapping[str, Any]
) -> tuple[dict[str, str], dict[str, Any]]:
    counts = config.get("splitCounts")
    if not isinstance(counts, Mapping):
        raise ConceptModelError("splitCounts is missing from model config")
    expected = {name: int(counts[name]) for name in ("train", "validation", "test")}
    if sum(expected.values()) != len(elements):
        raise ConceptModelError("Configured split counts do not cover every element")
    seed = int(config.get("splitSeed", 0))
    by_domain: dict[str, list[ElementRecord]] = defaultdict(list)
    for element in elements:
        by_domain[element.domain_id].append(element)
    domain_counts = {domain: len(by_domain[domain]) for domain in DOMAIN_ORDER}
    test_alloc = _largest_remainder_allocation(domain_counts, expected["test"])
    validation_alloc = _largest_remainder_allocation(domain_counts, expected["validation"])

    assignments: dict[str, str] = {}
    domain_summary: dict[str, dict[str, int]] = {}
    for domain in DOMAIN_ORDER:
        ordered = sorted(
            by_domain[domain],
            key=lambda item: hashlib.sha256(
                f"{seed}:{domain}:{item.element_id}".encode("utf-8")
            ).hexdigest(),
        )
        test_count = test_alloc[domain]
        validation_count = validation_alloc[domain]
        for item in ordered[:test_count]:
            assignments[item.element_id] = "test"
        for item in ordered[test_count : test_count + validation_count]:
            assignments[item.element_id] = "validation"
        for item in ordered[test_count + validation_count :]:
            assignments[item.element_id] = "train"
        domain_summary[domain] = dict(
            Counter(assignments[item.element_id] for item in ordered)
        )

    actual = Counter(assignments.values())
    if any(actual[name] != expected[name] for name in expected):
        raise ConceptModelError(f"Split count mismatch: expected={expected}, actual={dict(actual)}")
    manifest = {
        "splitVersion": str(config.get("splitVersion", "element-split-v1")),
        "splitSeed": seed,
        "contentFingerprint": content_fingerprint(elements),
        "counts": {name: actual[name] for name in ("train", "validation", "test")},
        "domainCounts": domain_summary,
        "elements": {
            name: sorted(element_id for element_id, split in assignments.items() if split == name)
            for name in ("train", "validation", "test")
        },
    }
    manifest["splitSha256"] = _sha256_bytes(_stable_json_bytes(manifest))
    return assignments, manifest


def build_facts_and_questions(
    elements: Sequence[ElementRecord], assignments: Mapping[str, str]
) -> tuple[list[FactRecord], list[QuestionGroup]]:
    fact_specs = (
        (
            "definition",
            "definition_to_term",
            "다음 설명에 가장 부합하는 금융 개념은 무엇인가?",
            lambda item: item.definition,
        ),
        (
            "intuition",
            "intuition_to_term",
            "다음 직관적 설명이 가리키는 금융 개념은 무엇인가?",
            lambda item: item.intuition,
        ),
        (
            "core_relation",
            "core_relation_to_term",
            "다음 핵심 관계와 직접 연결되는 금융 개념은 무엇인가?",
            lambda item: item.core_relation,
        ),
    )
    facts: list[FactRecord] = []
    questions: list[QuestionGroup] = []
    for element_index, element in enumerate(elements):
        for fact_type, question_type, prompt, getter in fact_specs:
            text = normalize_text(getter(element))
            fact_id = f"{element.element_id}:{fact_type}:01"
            fact_hash = _sha256_bytes(
                _stable_json_bytes(
                    {
                        "elementId": element.element_id,
                        "factType": fact_type,
                        "text": text,
                        "answer": element.title,
                        "source": element.source_locator,
                    }
                )
            )
            facts.append(
                FactRecord(
                    fact_id=fact_id,
                    element_id=element.element_id,
                    domain_id=element.domain_id,
                    fact_type=fact_type,
                    text=text,
                    answer_text=element.title,
                    source_label=element.source_label,
                    source_locator=element.source_locator,
                    review_status="reviewed",
                    content_sha256=fact_hash,
                )
            )
            questions.append(
                QuestionGroup(
                    question_id=f"{element.element_id}-{question_type}-01",
                    element_index=element_index,
                    element_id=element.element_id,
                    domain_id=element.domain_id,
                    question_type=question_type,
                    stem=f"{prompt}\n{text}",
                    correct_answer=element.title,
                    fact_id=fact_id,
                    split=assignments[element.element_id],
                )
            )
    if len(facts) != 405 or len(questions) != 405:
        raise ConceptModelError("The canonical corpus must yield 405 facts and questions")
    return facts, questions


def load_human_labels(path: Path = DEFAULT_LABELS) -> dict[tuple[str, str], HumanLabel]:
    if not path.exists():
        return {}
    result: dict[tuple[str, str], HumanLabel] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise ConceptModelError(f"Invalid label JSONL at line {line_number}") from error
            if not isinstance(raw, Mapping):
                raise ConceptModelError(f"Label line {line_number} is not an object")
            question_id = str(raw.get("questionId", "")).strip()
            candidate_id = str(raw.get("candidateElementId", "")).strip().upper()
            relevance = int(raw.get("relevance", -1))
            if not question_id or not candidate_id or relevance not in range(4):
                raise ConceptModelError(f"Malformed label at line {line_number}")
            label = HumanLabel(
                question_id=question_id,
                candidate_element_id=candidate_id,
                relevance=relevance,
                reviewer_id=str(raw.get("reviewerId", "anonymous")).strip() or "anonymous",
                review_status=str(raw.get("reviewStatus", "reviewer")).strip() or "reviewer",
            )
            key = (question_id, candidate_id)
            if key in result:
                raise ConceptModelError(f"Duplicate human label: {question_id}/{candidate_id}")
            result[key] = label
    return result


def load_owner_decisions(
    path: Path = DEFAULT_OWNER_DECISIONS,
) -> tuple[
    dict[tuple[str, str], OwnerQuestionDecision],
    dict[str, OwnerBatchDecision],
]:
    """Load append-only Owner decisions bound to exact review fingerprints."""
    if not path.exists():
        return {}, {}
    question_decisions: dict[tuple[str, str], OwnerQuestionDecision] = {}
    batch_decisions: dict[str, OwnerBatchDecision] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise ConceptModelError(
                    f"Invalid Owner decision JSONL at line {line_number}"
                ) from error
            if not isinstance(raw, Mapping):
                raise ConceptModelError(
                    f"Owner decision line {line_number} is not an object"
                )
            decision_type = str(raw.get("type", "question")).strip()
            decision = str(raw.get("decision", "")).strip()
            if decision not in {"approved", "rejected"}:
                raise ConceptModelError(
                    f"Owner decision line {line_number} has an invalid decision"
                )
            reviewer_id = str(raw.get("reviewerId", "owner")).strip() or "owner"
            reviewed_at = str(raw.get("reviewedAt", "")).strip()
            comment = str(raw.get("comment", "")).strip()
            if decision_type == "question":
                question_id = str(raw.get("questionId", "")).strip()
                fingerprint = str(raw.get("questionFingerprint", "")).strip()
                if not question_id or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                    raise ConceptModelError(
                        f"Owner question decision line {line_number} is malformed"
                    )
                question_decisions[(question_id, fingerprint)] = OwnerQuestionDecision(
                    question_id=question_id,
                    question_fingerprint=fingerprint,
                    decision=decision,
                    reviewer_id=reviewer_id,
                    reviewed_at=reviewed_at,
                    comment=comment,
                )
            elif decision_type == "batch":
                fingerprint = str(raw.get("reviewInputSha256", "")).strip()
                if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                    raise ConceptModelError(
                        f"Owner batch decision line {line_number} is malformed"
                    )
                batch_decisions[fingerprint] = OwnerBatchDecision(
                    review_input_sha256=fingerprint,
                    decision=decision,
                    reviewer_id=reviewer_id,
                    reviewed_at=reviewed_at,
                    comment=comment,
                )
            else:
                raise ConceptModelError(
                    f"Owner decision line {line_number} has an invalid type"
                )
    return question_decisions, batch_decisions


def _question_edit_value(raw: Mapping[str, Any], name: str, *, line_number: int) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConceptModelError(f"Question edit line {line_number} is missing {name}")
    return value.strip()


def load_question_edits(
    path: Path = DEFAULT_QUESTION_EDITS,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Load append-only Admin edits keyed by the exact pre-edit fingerprint."""
    if not path.exists():
        return {}
    result: dict[tuple[str, str], dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise ConceptModelError(
                    f"Invalid question edit JSONL at line {line_number}"
                ) from error
            if not isinstance(raw, Mapping) or str(raw.get("type", "question_edit")) != "question_edit":
                raise ConceptModelError(f"Question edit line {line_number} has an invalid type")
            question_id = _question_edit_value(raw, "questionId", line_number=line_number)
            if len(question_id) > 160 or not re.fullmatch(r"[A-Za-z0-9_-]+", question_id):
                raise ConceptModelError(f"Question edit line {line_number} has an invalid question id")
            fingerprint = _question_edit_value(raw, "questionFingerprint", line_number=line_number)
            if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                raise ConceptModelError(f"Question edit line {line_number} has an invalid fingerprint")
            element_id = _question_edit_value(raw, "elementId", line_number=line_number)
            if len(element_id) > 80 or not re.fullmatch(r"[A-Za-z0-9_-]+", element_id):
                raise ConceptModelError(f"Question edit line {line_number} has an invalid element id")
            stem = _question_edit_value(raw, "stem", line_number=line_number)
            explanation = _question_edit_value(raw, "explanation", line_number=line_number)
            if len(stem) > 20000 or len(explanation) > 20000:
                raise ConceptModelError(f"Question edit line {line_number} has text that is too long")
            comment = str(raw.get("comment", "")).strip()
            if len(comment) > 2000:
                raise ConceptModelError(f"Question edit line {line_number} has a comment that is too long")
            choices = raw.get("choices")
            if not isinstance(choices, list) or len(choices) != len(CHOICE_KEYS):
                raise ConceptModelError(f"Question edit line {line_number} must contain five choices")
            normalized_choices: list[dict[str, Any]] = []
            for expected_key, choice in zip(CHOICE_KEYS, choices, strict=True):
                if not isinstance(choice, Mapping):
                    raise ConceptModelError(f"Question edit line {line_number} has an invalid choice")
                key = str(choice.get("key", "")).strip()
                choice_element_id = str(choice.get("elementId", "")).strip()
                text = str(choice.get("text", "")).strip()
                choice_explanation = str(choice.get("explanation", "")).strip()
                is_correct = choice.get("isCorrect")
                if (
                    key != expected_key
                    or not choice_element_id
                    or len(choice_element_id) > 80
                    or not re.fullmatch(r"[A-Za-z0-9_-]+", choice_element_id)
                    or not text
                    or len(text) > 2000
                    or not choice_explanation
                    or len(choice_explanation) > 2000
                    or not isinstance(is_correct, bool)
                ):
                    raise ConceptModelError(f"Question edit line {line_number} has malformed choice {expected_key}")
                normalized_choices.append(
                    {
                        "key": key,
                        "elementId": choice_element_id,
                        "text": text,
                        "explanation": choice_explanation,
                        "isCorrect": is_correct,
                    }
                )
            correct_choices = [choice for choice in normalized_choices if choice["isCorrect"]]
            if len(correct_choices) != 1 or correct_choices[0]["elementId"] != element_id:
                raise ConceptModelError(
                    f"Question edit line {line_number} must keep exactly one correct choice for {element_id}"
                )
            result[(question_id, fingerprint)] = {
                "questionId": question_id,
                "questionFingerprint": fingerprint,
                "elementId": element_id,
                "stem": stem,
                "explanation": explanation,
                "choices": normalized_choices,
                "comment": comment,
            }
    return result


def _token_set(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(normalize_text(value))}


def title_alias_keys(value: str) -> set[str]:
    """Return conservative whole-title aliases, including parenthetical names."""
    normalized = normalize_text(value)
    keys = {normalized_key(normalized)}
    without_parenthetical = re.sub(r"\([^)]*\)", "", normalized).strip()
    if without_parenthetical:
        keys.add(normalized_key(without_parenthetical))
    for match in re.finditer(r"\(([^)]*)\)", normalized):
        parenthetical = normalized_key(match.group(1))
        if len(parenthetical) >= 2:
            keys.add(parenthetical)
    return {key for key in keys if key}


def eligible_candidate_indices(
    elements: Sequence[ElementRecord], answer_index: int
) -> list[int]:
    """Exclude the answer element and title aliases that would create two correct labels."""
    answer_keys = title_alias_keys(elements[answer_index].title)
    return [
        index
        for index, element in enumerate(elements)
        if index != answer_index and title_alias_keys(element.title).isdisjoint(answer_keys)
    ]


def _competition_ranks(
    values: Mapping[int, float],
    elements: Sequence[ElementRecord],
) -> dict[int, int]:
    """Return deterministic 1-based ranks while assigning equal values equal rank."""
    ordered = sorted(
        values.items(),
        key=lambda item: (-item[1], elements[item[0]].element_id),
    )
    ranks: dict[int, int] = {}
    previous_value: float | None = None
    previous_rank = 0
    for position, (candidate_index, value) in enumerate(ordered, start=1):
        if previous_value is None or not math.isclose(
            value, previous_value, rel_tol=1e-9, abs_tol=1e-12
        ):
            previous_rank = position
            previous_value = value
        ranks[candidate_index] = previous_rank
    return ranks


def build_feature_context(
    elements: list[ElementRecord],
    questions: list[QuestionGroup],
    weak_profile: Mapping[str, Any],
    rrf_k: int,
) -> FeatureContext:
    element_documents = [item.semantic_text for item in elements]
    train_questions = [item.stem for item in questions if item.split == "train"]
    fit_corpus = element_documents + train_questions
    word_vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=1,
        max_features=30_000,
        sublinear_tf=True,
        norm="l2",
    )
    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=1,
        max_features=50_000,
        sublinear_tf=True,
        norm="l2",
    )
    word_vectorizer.fit(fit_corpus)
    char_vectorizer.fit(fit_corpus)
    element_word = word_vectorizer.transform(element_documents)
    element_char = char_vectorizer.transform(element_documents)
    question_word = word_vectorizer.transform([item.stem for item in questions])
    question_char = char_vectorizer.transform([item.stem for item in questions])
    q_word = (question_word @ element_word.T).toarray().astype(np.float32)
    q_char = (question_char @ element_char.T).toarray().astype(np.float32)
    a_word = (element_word @ element_word.T).toarray().astype(np.float32)
    a_char = (element_char @ element_char.T).toarray().astype(np.float32)

    weak_weight_keys = (
        "questionWord",
        "questionChar",
        "answerWord",
        "answerChar",
        "sameDomain",
        "sameMode",
    )
    weak_weights = {key: float(weak_profile.get(key, -1.0)) for key in weak_weight_keys}
    if any(value < 0 for value in weak_weights.values()) or not math.isclose(
        sum(weak_weights.values()), 1.0, abs_tol=1e-6
    ):
        raise ConceptModelError(
            f"Weak-supervision profile {weak_profile.get('id')} must contain non-negative weights summing to 1"
        )
    if rrf_k <= 0:
        raise ConceptModelError("RRF k must be positive")

    weak = np.zeros((len(questions), len(elements)), dtype=np.int8)
    for question_index, question in enumerate(questions):
        scores: list[tuple[float, str, int]] = []
        answer_index = question.element_index
        answer = elements[answer_index]
        candidate_indices = eligible_candidate_indices(elements, answer_index)
        signal_values = {
            "questionWord": {
                index: float(q_word[question_index, index]) for index in candidate_indices
            },
            "questionChar": {
                index: float(q_char[question_index, index]) for index in candidate_indices
            },
            "answerWord": {
                index: float(a_word[answer_index, index]) for index in candidate_indices
            },
            "answerChar": {
                index: float(a_char[answer_index, index]) for index in candidate_indices
            },
            "sameDomain": {
                index: float(answer.domain_id == elements[index].domain_id)
                for index in candidate_indices
            },
            "sameMode": {
                index: float(answer.mode == elements[index].mode)
                for index in candidate_indices
            },
        }
        signal_ranks = {
            name: _competition_ranks(values, elements)
            for name, values in signal_values.items()
        }
        weak[question_index, :] = -1
        for candidate_index in candidate_indices:
            candidate = elements[candidate_index]
            score = sum(
                weak_weights[name] / (rrf_k + signal_ranks[name][candidate_index])
                for name in weak_weight_keys
            )
            scores.append((score, candidate.element_id, candidate_index))
        scores.sort(key=lambda item: (-item[0], item[1]))
        for rank, (_, _, candidate_index) in enumerate(scores):
            weak[question_index, candidate_index] = 3 if rank < 4 else 2 if rank < 8 else 1 if rank < 20 else 0

    return FeatureContext(
        elements=elements,
        questions=questions,
        question_word_similarity=q_word,
        question_char_similarity=q_char,
        answer_word_similarity=a_word,
        answer_char_similarity=a_char,
        weak_relevance=weak,
    )


def weak_supervision_sensitivity(
    elements: list[ElementRecord],
    questions: list[QuestionGroup],
    profiles: Sequence[Mapping[str, Any]],
    canonical_profile_id: str,
    rrf_k: int,
) -> tuple[FeatureContext, dict[str, Any]]:
    contexts: dict[str, FeatureContext] = {}
    for profile in profiles:
        profile_id = str(profile.get("id", "")).strip()
        if not profile_id or profile_id in contexts:
            raise ConceptModelError("Weak-supervision profile ids must be non-empty and unique")
        contexts[profile_id] = build_feature_context(elements, questions, profile, rrf_k)
    canonical = contexts.get(canonical_profile_id)
    if canonical is None:
        raise ConceptModelError(
            f"canonicalWeakSupervisionProfile does not exist: {canonical_profile_id}"
        )
    canonical_sets = [
        {
            index
            for index, relevance in enumerate(canonical.weak_relevance[question_index])
            if relevance == 3
        }
        for question_index in range(len(questions))
    ]
    comparisons: list[dict[str, Any]] = []
    all_agreements: list[float] = []
    for profile_id, context in contexts.items():
        profile_sets = [
            {
                index
                for index, relevance in enumerate(context.weak_relevance[question_index])
                if relevance == 3
            }
            for question_index in range(len(questions))
        ]
        agreements = [
            len(canonical_set & profile_set) / max(1, len(canonical_set | profile_set))
            for canonical_set, profile_set in zip(canonical_sets, profile_sets, strict=True)
        ]
        mean_agreement = round(float(np.mean(agreements)), 6)
        minimum_agreement = round(float(np.min(agreements)), 6)
        comparisons.append(
            {
                "profileId": profile_id,
                "meanTop4JaccardVsCanonical": mean_agreement,
                "minimumTop4JaccardVsCanonical": minimum_agreement,
                "changedQuestionCount": sum(value < 1.0 for value in agreements),
            }
        )
        if profile_id != canonical_profile_id:
            all_agreements.extend(agreements)
    return canonical, {
        "canonicalProfileId": canonical_profile_id,
        "fusionMethod": "reciprocal_rank_fusion",
        "rrfK": rrf_k,
        "profileCount": len(contexts),
        "comparisons": comparisons,
        "meanTop4JaccardAcrossAlternatives": round(float(np.mean(all_agreements)), 6)
        if all_agreements
        else 1.0,
        "minimumTop4JaccardAcrossAlternatives": round(float(np.min(all_agreements)), 6)
        if all_agreements
        else 1.0,
        "interpretation": "사람 라벨 전에는 최고 성능이 아니라 수동 약지도 가중치 변화에 대한 후보 안정성을 측정합니다.",
    }


def _directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def run_sentence_transformer(
    spec: Mapping[str, Any],
    context: FeatureContext,
    cache_root: Path,
    device: str,
) -> EmbeddingRun:
    candidate_id = str(spec.get("id", "unknown"))
    model_id = str(spec.get("model", ""))
    revision_requested = str(spec.get("revision", "main"))
    started = time.perf_counter()
    revision_resolved: str | None = None
    model_cache = cache_root / candidate_id
    try:
        from huggingface_hub import model_info
        from sentence_transformers import SentenceTransformer

        try:
            revision_resolved = model_info(model_id, revision=revision_requested).sha
        except Exception:
            revision_resolved = None
        revision = revision_resolved or revision_requested
        query_prefix = str(spec.get("queryPrefix", ""))
        passage_prefix = str(spec.get("passagePrefix", ""))
        matrix_identity = {
            "candidateId": candidate_id,
            "modelId": model_id,
            "revision": revision,
            "queryPrefix": query_prefix,
            "passagePrefix": passage_prefix,
            "questions": [item.stem for item in context.questions],
            "elements": [item.semantic_text for item in context.elements],
        }
        matrix_key = _sha256_bytes(_stable_json_bytes(matrix_identity))
        matrix_dir = model_cache / "findone-similarity-matrices"
        matrix_path = matrix_dir / f"{matrix_key}.npz"
        if matrix_path.is_file():
            with np.load(matrix_path, allow_pickle=False) as cached:
                query_candidate = np.asarray(cached["queryCandidate"], dtype=np.float32)
                answer_candidate = np.asarray(cached["answerCandidate"], dtype=np.float32)
                dimensions = int(np.asarray(cached["dimensions"]).item())
            expected_query_shape = (len(context.questions), len(context.elements))
            expected_answer_shape = (len(context.elements), len(context.elements))
            if query_candidate.shape != expected_query_shape or answer_candidate.shape != expected_answer_shape:
                raise ConceptModelError(f"Cached embedding matrix shape is invalid: {matrix_path}")
            return EmbeddingRun(
                candidate_id=candidate_id,
                model_id=model_id,
                status="completed",
                revision_requested=revision_requested,
                revision_resolved=revision_resolved,
                dimensions=dimensions,
                encode_seconds=round(time.perf_counter() - started, 3),
                artifact_bytes=_directory_bytes(model_cache),
                error=None,
                cache_hit=True,
                matrix_cache_sha256=_sha256_file(matrix_path),
                query_candidate_similarity=query_candidate,
                answer_candidate_similarity=answer_candidate,
            )
        model = SentenceTransformer(
            model_id,
            revision=revision,
            trust_remote_code=bool(spec.get("trustRemoteCode", False)),
            cache_folder=str(model_cache),
            device=device,
        )
        question_vectors = np.asarray(
            model.encode(
                [query_prefix + item.stem for item in context.questions],
                batch_size=16,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ),
            dtype=np.float32,
        )
        element_vectors = np.asarray(
            model.encode(
                [passage_prefix + item.semantic_text for item in context.elements],
                batch_size=16,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ),
            dtype=np.float32,
        )
        query_candidate = question_vectors @ element_vectors.T
        answer_candidate = element_vectors @ element_vectors.T
        matrix_dir.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=matrix_path.name + ".",
            suffix=".tmp",
            dir=matrix_dir,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as stream:
                np.savez_compressed(
                    stream,
                    queryCandidate=query_candidate,
                    answerCandidate=answer_candidate,
                    dimensions=np.asarray(element_vectors.shape[1], dtype=np.int32),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, matrix_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return EmbeddingRun(
            candidate_id=candidate_id,
            model_id=model_id,
            status="completed",
            revision_requested=revision_requested,
            revision_resolved=revision_resolved,
            dimensions=int(element_vectors.shape[1]),
            encode_seconds=round(time.perf_counter() - started, 3),
            artifact_bytes=_directory_bytes(model_cache),
            error=None,
            cache_hit=False,
            matrix_cache_sha256=_sha256_file(matrix_path),
            query_candidate_similarity=query_candidate,
            answer_candidate_similarity=answer_candidate,
        )
    except Exception as error:
        return EmbeddingRun(
            candidate_id=candidate_id,
            model_id=model_id,
            status="failed",
            revision_requested=revision_requested,
            revision_resolved=revision_resolved,
            dimensions=None,
            encode_seconds=round(time.perf_counter() - started, 3),
            artifact_bytes=_directory_bytes(model_cache),
            error=f"{type(error).__name__}: {str(error)[:500]}",
        )


def baseline_embedding_run(context: FeatureContext) -> EmbeddingRun:
    return EmbeddingRun(
        candidate_id="tfidf-word-char",
        model_id="tfidf-word-char",
        status="completed",
        revision_requested="feature-v1",
        revision_resolved="feature-v1",
        dimensions=None,
        encode_seconds=0.0,
        artifact_bytes=0,
        error=None,
        query_candidate_similarity=None,
        answer_candidate_similarity=None,
    )


def _candidate_features(
    context: FeatureContext,
    question_index: int,
    candidate_index: int,
    embedding: EmbeddingRun,
) -> np.ndarray:
    question = context.questions[question_index]
    answer = context.elements[question.element_index]
    candidate = context.elements[candidate_index]
    question_tokens = _token_set(question.stem)
    candidate_tokens = _token_set(candidate.title)
    overlap = len(question_tokens & candidate_tokens) / max(1, len(candidate_tokens))
    answer_key = normalized_key(answer.title)
    candidate_key = normalized_key(candidate.title)
    length_ratio = min(len(answer_key), len(candidate_key)) / max(
        1, max(len(answer_key), len(candidate_key))
    )
    acronym_pattern = re.compile(r"[A-Z][A-Z0-9]{1,}")
    answer_acronyms = set(acronym_pattern.findall(answer.title.upper()))
    candidate_acronyms = set(acronym_pattern.findall(candidate.title.upper()))
    acronym_match = float(bool(answer_acronyms & candidate_acronyms))
    embedding_query = (
        float(embedding.query_candidate_similarity[question_index, candidate_index])
        if embedding.query_candidate_similarity is not None
        else 0.0
    )
    embedding_answer = (
        float(embedding.answer_candidate_similarity[question.element_index, candidate_index])
        if embedding.answer_candidate_similarity is not None
        else 0.0
    )
    domain_one_hot = [float(candidate.domain_id == domain) for domain in DOMAIN_ORDER]
    return np.asarray(
        [
            float(context.question_word_similarity[question_index, candidate_index]),
            float(context.question_char_similarity[question_index, candidate_index]),
            float(context.answer_word_similarity[question.element_index, candidate_index]),
            float(context.answer_char_similarity[question.element_index, candidate_index]),
            embedding_query,
            embedding_answer,
            float(answer.domain_id == candidate.domain_id),
            float(answer.mode == candidate.mode),
            length_ratio,
            overlap,
            acronym_match,
            *domain_one_hot,
        ],
        dtype=np.float32,
    )


def _retrieval_weights(retrieval_profile: Mapping[str, Any]) -> dict[str, float]:
    signal_names = (
        "questionWord",
        "questionChar",
        "answerWord",
        "answerChar",
        "sameDomain",
        "sameMode",
        "questionSemantic",
        "answerSemantic",
    )
    weights = {name: float(retrieval_profile.get(name, -1.0)) for name in signal_names}
    if any(value < 0 for value in weights.values()) or not math.isclose(
        sum(weights.values()), 1.0, abs_tol=1e-6
    ):
        raise ConceptModelError(
            f"Retrieval profile {retrieval_profile.get('id')} weights must sum to 1"
        )
    return weights


def _effective_relevance(
    context: FeatureContext,
    question_index: int,
    candidate_index: int,
    human_labels: Mapping[tuple[str, str], HumanLabel],
) -> int:
    question = context.questions[question_index]
    candidate = context.elements[candidate_index]
    human = human_labels.get((question.question_id, candidate.element_id))
    return human.relevance if human is not None else int(
        context.weak_relevance[question_index, candidate_index]
    )


def retrieve_candidates(
    context: FeatureContext,
    embedding: EmbeddingRun,
    limit: int,
    retrieval_profile: Mapping[str, Any],
    rrf_k: int = 60,
) -> list[list[int]]:
    weights = _retrieval_weights(retrieval_profile)
    if embedding.query_candidate_similarity is None and (
        weights["questionSemantic"] > 0 or weights["answerSemantic"] > 0
    ):
        raise ConceptModelError("A semantic retrieval profile requires an embedding model")
    if rrf_k <= 0:
        raise ConceptModelError("RRF k must be positive")
    result: list[list[int]] = []
    for question_index, question in enumerate(context.questions):
        answer = context.elements[question.element_index]
        candidate_indices = eligible_candidate_indices(
            context.elements, question.element_index
        )
        signal_values: dict[str, dict[int, float]] = {
            "questionWord": {
                index: float(context.question_word_similarity[question_index, index])
                for index in candidate_indices
            },
            "questionChar": {
                index: float(context.question_char_similarity[question_index, index])
                for index in candidate_indices
            },
            "answerWord": {
                index: float(context.answer_word_similarity[question.element_index, index])
                for index in candidate_indices
            },
            "answerChar": {
                index: float(context.answer_char_similarity[question.element_index, index])
                for index in candidate_indices
            },
            "sameDomain": {
                index: float(answer.domain_id == context.elements[index].domain_id)
                for index in candidate_indices
            },
            "sameMode": {
                index: float(answer.mode == context.elements[index].mode)
                for index in candidate_indices
            },
        }
        if embedding.query_candidate_similarity is not None:
            signal_values["questionSemantic"] = {
                index: float(embedding.query_candidate_similarity[question_index, index])
                for index in candidate_indices
            }
            signal_values["answerSemantic"] = {
                index: float(
                    embedding.answer_candidate_similarity[question.element_index, index]
                )
                for index in candidate_indices
            }
        signal_ranks = {
            name: _competition_ranks(values, context.elements)
            for name, values in signal_values.items()
        }
        candidates = [
            (
                sum(
                    weight / (rrf_k + signal_ranks[name][candidate_index])
                    for name, weight in weights.items()
                    if weight > 0
                ),
                context.elements[candidate_index].element_id,
                candidate_index,
            )
            for candidate_index in candidate_indices
        ]
        candidates.sort(key=lambda item: (-item[0], item[1]))
        result.append([candidate_index for _, _, candidate_index in candidates[:limit]])
    return result


def _training_matrix(
    context: FeatureContext,
    embedding: EmbeddingRun,
    retrieved: Sequence[Sequence[int]],
    human_labels: Mapping[tuple[str, str], HumanLabel],
    split: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
    features: list[np.ndarray] = []
    labels: list[int] = []
    qids: list[int] = []
    question_indices: list[int] = []
    for question_index, question in enumerate(context.questions):
        if question.split != split:
            continue
        for candidate_index in retrieved[question_index]:
            features.append(
                _candidate_features(context, question_index, candidate_index, embedding)
            )
            labels.append(
                _effective_relevance(context, question_index, candidate_index, human_labels)
            )
            qids.append(question_index)
            question_indices.append(candidate_index)
    return (
        np.vstack(features),
        np.asarray(labels, dtype=np.int32),
        np.asarray(qids, dtype=np.int32),
        question_indices,
    )


def train_pairwise_logistic(
    context: FeatureContext,
    embedding: EmbeddingRun,
    retrieved: Sequence[Sequence[int]],
    human_labels: Mapping[tuple[str, str], HumanLabel],
    seed: int,
    max_pairs_per_question: int,
    c_value: float,
) -> Any:
    pair_features: list[np.ndarray] = []
    pair_labels: list[int] = []
    for question_index, question in enumerate(context.questions):
        if question.split != "train":
            continue
        candidates = list(retrieved[question_index])
        possible: list[tuple[str, int, int]] = []
        for left_position, left in enumerate(candidates):
            left_label = _effective_relevance(context, question_index, left, human_labels)
            for right in candidates[left_position + 1 :]:
                right_label = _effective_relevance(context, question_index, right, human_labels)
                if left_label == right_label:
                    continue
                higher, lower = (left, right) if left_label > right_label else (right, left)
                key = hashlib.sha256(
                    f"{seed}:{question.question_id}:{higher}:{lower}".encode("utf-8")
                ).hexdigest()
                possible.append((key, higher, lower))
        possible.sort()
        for _, higher, lower in possible[:max_pairs_per_question]:
            difference = _candidate_features(
                context, question_index, higher, embedding
            ) - _candidate_features(context, question_index, lower, embedding)
            pair_features.extend((difference, -difference))
            pair_labels.extend((1, 0))
    if not pair_features:
        raise ConceptModelError("No pairwise training examples were generated")
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=c_value,
            max_iter=1_000,
            random_state=seed,
            solver="lbfgs",
        ),
    )
    model.fit(np.vstack(pair_features), np.asarray(pair_labels, dtype=np.int8))
    return model


def train_xgboost_ranker(
    context: FeatureContext,
    embedding: EmbeddingRun,
    retrieved: Sequence[Sequence[int]],
    human_labels: Mapping[tuple[str, str], HumanLabel],
    seed: int,
    parameters: Mapping[str, Any],
) -> Any:
    try:
        from xgboost import XGBRanker
    except ImportError as error:
        raise ConceptModelError("xgboost is not installed") from error
    train_x, train_y, train_qid, _ = _training_matrix(
        context, embedding, retrieved, human_labels, "train"
    )
    validation_x, validation_y, validation_qid, _ = _training_matrix(
        context, embedding, retrieved, human_labels, "validation"
    )
    model = XGBRanker(
        objective="rank:ndcg",
        eval_metric="ndcg@4",
        n_estimators=300,
        max_depth=int(parameters.get("maxDepth", 4)),
        learning_rate=float(parameters.get("learningRate", 0.05)),
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=seed,
        tree_method="hist",
        n_jobs=max(1, min(8, os.cpu_count() or 1)),
        early_stopping_rounds=25,
    )
    model.fit(
        train_x,
        train_y,
        qid=train_qid,
        eval_set=[(validation_x, validation_y)],
        eval_qid=[validation_qid],
        verbose=False,
    )
    return model


def rank_candidates(
    context: FeatureContext,
    embedding: EmbeddingRun,
    retrieved: Sequence[Sequence[int]],
    model: Any,
) -> list[list[tuple[int, float]]]:
    result: list[list[tuple[int, float]]] = []
    for question_index, candidates in enumerate(retrieved):
        features = np.vstack(
            [
                _candidate_features(context, question_index, candidate_index, embedding)
                for candidate_index in candidates
            ]
        )
        if hasattr(model, "decision_function"):
            scores = np.asarray(model.decision_function(features), dtype=np.float64)
        else:
            scores = np.asarray(model.predict(features), dtype=np.float64)
        ranked = list(zip(candidates, scores.tolist(), strict=True))
        ranked.sort(
            key=lambda item: (-item[1], context.elements[item[0]].element_id)
        )
        result.append(ranked)
    return result


def _dcg(relevances: Sequence[int], k: int) -> float:
    return sum(
        (2**relevance - 1) / math.log2(position + 2)
        for position, relevance in enumerate(relevances[:k])
    )


def evaluate_ranking(
    context: FeatureContext,
    retrieved: Sequence[Sequence[int]],
    ranked: Sequence[Sequence[tuple[int, float]]],
    human_labels: Mapping[tuple[str, str], HumanLabel],
    split: str,
) -> dict[str, Any]:
    recall_values: list[float] = []
    ndcg_values: list[float] = []
    precision_values: list[float] = []
    reciprocal_ranks: list[float] = []
    group_count = 0
    for question_index, question in enumerate(context.questions):
        if question.split != split:
            continue
        group_count += 1
        all_relevance = [
            _effective_relevance(context, question_index, candidate_index, human_labels)
            for candidate_index in eligible_candidate_indices(
                context.elements, question.element_index
            )
        ]
        relevant_total = sum(value >= 2 for value in all_relevance)
        retrieved_relevance = [
            _effective_relevance(context, question_index, candidate_index, human_labels)
            for candidate_index in retrieved[question_index]
        ]
        recall_values.append(
            sum(value >= 2 for value in retrieved_relevance) / max(1, relevant_total)
        )
        ranked_relevance = [
            _effective_relevance(context, question_index, candidate_index, human_labels)
            for candidate_index, _ in ranked[question_index]
        ]
        ideal = sorted(all_relevance, reverse=True)
        ideal_dcg = _dcg(ideal, 4)
        ndcg_values.append(_dcg(ranked_relevance, 4) / ideal_dcg if ideal_dcg else 0.0)
        precision_values.append(sum(value >= 2 for value in ranked_relevance[:4]) / 4)
        first_relevant = next(
            (position for position, value in enumerate(ranked_relevance, start=1) if value >= 2),
            None,
        )
        reciprocal_ranks.append(1 / first_relevant if first_relevant else 0.0)
    return {
        "split": split,
        "questionCount": group_count,
        "retrievalRecallAt20": round(float(np.mean(recall_values)), 6),
        "ndcgAt4": round(float(np.mean(ndcg_values)), 6),
        "precisionAt4": round(float(np.mean(precision_values)), 6),
        "mrr": round(float(np.mean(reciprocal_ranks)), 6),
        "labelSource": "human_and_weak_rule" if human_labels else "weak_rule",
    }


def _model_artifact(
    build_dir: Path,
    embedding_id: str,
    retrieval_id: str,
    ranker_id: str,
    model: Any,
) -> tuple[Path, str, int]:
    build_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^0-9A-Za-z._-]+", "-", f"{embedding_id}-{retrieval_id}-{ranker_id}")
    path = build_dir / f"{safe_name}.joblib"
    joblib.dump(model, path, compress=3)
    return path, _sha256_file(path), path.stat().st_size


def _question_bank(
    context: FeatureContext,
    ranked: Sequence[Sequence[tuple[int, float]]],
    model_version: str,
    selected_embedding: str,
    selected_retrieval: str,
    selected_ranker: str,
    fingerprint: str,
    split_hash: str,
    human_labels: Mapping[tuple[str, str], HumanLabel],
) -> tuple[dict[str, Any], dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    answer_leaks = 0
    duplicate_choices = 0
    ambiguous_questions = 0
    ambiguous_question_ids: list[str] = []
    for question_index, question in enumerate(context.questions):
        target = context.elements[question.element_index]
        selected: list[tuple[int, float]] = []
        seen_titles = set(title_alias_keys(target.title))
        # A ranked candidate can still be an obviously weak distractor. Prefer the
        # weak/human relevance >= 2 pool, then fall back only when a question does
        # not have four distinct viable alternatives. This is an output safety
        # constraint; validation/test model selection remains untouched.
        for minimum_relevance in (2, 0):
            for candidate_index, score in ranked[question_index]:
                title_keys = title_alias_keys(context.elements[candidate_index].title)
                if not title_keys or not seen_titles.isdisjoint(title_keys):
                    continue
                if (
                    _effective_relevance(
                        context,
                        question_index,
                        candidate_index,
                        human_labels,
                    )
                    < minimum_relevance
                ):
                    continue
                seen_titles.update(title_keys)
                selected.append((candidate_index, score))
                if len(selected) == 4:
                    break
            if len(selected) == 4:
                break
        if len(selected) != 4:
            raise ConceptModelError(
                f"{question.question_id} does not have four distinct distractors"
            )
        has_weak_distractor = any(
            _effective_relevance(context, question_index, candidate_index, human_labels) < 2
            for candidate_index, _ in selected
        )
        if has_weak_distractor:
            ambiguous_questions += 1
            ambiguous_question_ids.append(question.question_id)

        raw_choices: list[dict[str, Any]] = [
            {
                "elementId": target.element_id,
                "text": target.title,
                "explanation": target.definition,
                "isCorrect": True,
            }
        ]
        for candidate_index, _ in selected:
            candidate = context.elements[candidate_index]
            raw_choices.append(
                {
                    "elementId": candidate.element_id,
                    "text": candidate.title,
                    "explanation": candidate.definition,
                    "isCorrect": False,
                }
            )
        raw_choices.sort(
            key=lambda item: hashlib.sha256(
                f"{question.question_id}:{item['elementId']}".encode("utf-8")
            ).hexdigest()
        )
        choices = [
            {"key": CHOICE_KEYS[index], **choice}
            for index, choice in enumerate(raw_choices)
        ]
        choice_aliases = [title_alias_keys(choice["text"]) for choice in choices]
        if any(
            not left.isdisjoint(right)
            for index, left in enumerate(choice_aliases)
            for right in choice_aliases[index + 1 :]
        ):
            duplicate_choices += 1
        correct_keys = title_alias_keys(target.title)
        if any(
            not title_alias_keys(choice["text"]).isdisjoint(correct_keys)
            and not choice["isCorrect"]
            for choice in choices
        ):
            answer_leaks += 1
        difficulty = 1 if question.question_type == "definition_to_term" else 2
        questions.append(
            {
                "questionId": question.question_id,
                "elementId": question.element_id,
                "questionType": question.question_type,
                "stem": question.stem,
                "explanation": (
                    f"정답은 {target.title}입니다. {target.definition} "
                    f"{target.intuition}"
                ),
                "difficulty": difficulty,
                "modelVersion": model_version,
                "sourceFactIds": [question.fact_id],
                "reviewStatus": (
                    "review_attention"
                    if has_weak_distractor
                    else "reviewed"
                    if human_labels
                    else "bootstrap"
                ),
                "choices": choices,
            }
        )
    bank: dict[str, Any] = {
        "bankVersion": BANK_VERSION,
        "modelVersion": model_version,
        "selectedEmbedding": selected_embedding,
        "selectedRetrievalProfile": selected_retrieval,
        "selectedRanker": selected_ranker,
        "contentFingerprint": fingerprint,
        "splitSha256": split_hash,
        "releaseStatus": "candidate" if human_labels else "bootstrap_not_reviewed",
        "questionCount": len(questions),
        "questions": questions,
    }
    bank["bankSha256"] = _sha256_bytes(_stable_json_bytes(bank))
    safety = {
        "answerLeakCount": answer_leaks,
        "duplicateChoiceCount": duplicate_choices,
        "ambiguousQuestionCount": ambiguous_questions,
        "ambiguousQuestionIds": ambiguous_question_ids,
    }
    return bank, safety


def _element_fingerprints(
    elements: Sequence[ElementRecord],
) -> dict[str, str]:
    return {
        item.element_id: _sha256_bytes(_stable_json_bytes(asdict(item)))
        for item in elements
    }


def _question_review_fingerprint(question: Mapping[str, Any]) -> str:
    choices = question.get("choices")
    payload = {
        "questionId": question.get("questionId"),
        "elementId": question.get("elementId"),
        "questionType": question.get("questionType"),
        "stem": question.get("stem"),
        "explanation": question.get("explanation"),
        "difficulty": question.get("difficulty"),
        "sourceFactIds": question.get("sourceFactIds"),
        "choices": [
            {
                "key": choice.get("key"),
                "elementId": choice.get("elementId"),
                "text": choice.get("text"),
                "explanation": choice.get("explanation"),
                "isCorrect": choice.get("isCorrect"),
            }
            for choice in choices
            if isinstance(choice, Mapping)
        ]
        if isinstance(choices, list)
        else [],
    }
    return _sha256_bytes(_stable_json_bytes(payload))


def _apply_question_edits(
    bank: dict[str, Any],
    question_edits: Mapping[tuple[str, str], Mapping[str, Any]],
) -> int:
    """Apply an exact-fingerprint edit chain to each generated question."""
    edited_count = 0
    for question in bank.get("questions", []):
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("questionId", ""))
        seen_fingerprints: set[str] = set()
        while True:
            fingerprint = _question_review_fingerprint(question)
            if fingerprint in seen_fingerprints:
                raise ConceptModelError(f"Question edit chain cycles for {question_id}")
            seen_fingerprints.add(fingerprint)
            edit = question_edits.get((question_id, fingerprint))
            if edit is None:
                break
            if str(edit.get("elementId")) != str(question.get("elementId")):
                raise ConceptModelError(
                    f"Question edit target mismatch for {question.get('questionId')}"
                )
            question["stem"] = str(edit["stem"])
            question["explanation"] = str(edit["explanation"])
            question["choices"] = [dict(choice) for choice in edit["choices"]]
            edited_count += 1
    return edited_count


def _recompute_question_safety(
    bank: Mapping[str, Any],
    context: FeatureContext,
) -> dict[str, Any]:
    """Recheck safety gates after Admin text/choice edits are applied."""
    elements_by_id = {element.element_id: element for element in context.elements}
    element_indices = {element.element_id: index for index, element in enumerate(context.elements)}
    answer_leaks = 0
    duplicate_choices = 0
    ambiguous_question_ids: list[str] = []
    questions = bank.get("questions", [])
    for question_index, question in enumerate(questions if isinstance(questions, list) else []):
        if not isinstance(question, Mapping):
            continue
        target = elements_by_id.get(str(question.get("elementId")))
        choices = question.get("choices")
        if target is None or not isinstance(choices, list):
            continue
        choice_aliases = [
            title_alias_keys(str(choice.get("text", "")))
            for choice in choices
            if isinstance(choice, Mapping)
        ]
        if any(
            not left.isdisjoint(right)
            for index, left in enumerate(choice_aliases)
            for right in choice_aliases[index + 1 :]
        ):
            duplicate_choices += 1
        correct_aliases = set(title_alias_keys(target.title))
        correct_choice = next(
            (choice for choice in choices if isinstance(choice, Mapping) and choice.get("isCorrect")),
            None,
        )
        if isinstance(correct_choice, Mapping):
            correct_aliases.update(title_alias_keys(str(correct_choice.get("text", ""))))
        if any(
            not title_alias_keys(str(choice.get("text", ""))).isdisjoint(correct_aliases)
            and not bool(choice.get("isCorrect"))
            for choice in choices
            if isinstance(choice, Mapping)
        ):
            answer_leaks += 1
        weak_distractor = False
        for choice in choices:
            if not isinstance(choice, Mapping) or bool(choice.get("isCorrect")):
                continue
            candidate_index = element_indices.get(str(choice.get("elementId")))
            if candidate_index is not None and question_index < len(context.questions):
                if int(context.weak_relevance[question_index, candidate_index]) < 2:
                    weak_distractor = True
        if weak_distractor:
            ambiguous_question_ids.append(str(question.get("questionId")))
    return {
        "answerLeakCount": answer_leaks,
        "duplicateChoiceCount": duplicate_choices,
        "ambiguousQuestionCount": len(ambiguous_question_ids),
        "ambiguousQuestionIds": ambiguous_question_ids,
    }


def _load_previous_question_bank(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _review_reason(
    reason_id: str,
    label: str,
    measured: float | int | bool | str,
    threshold: float | int | bool | str,
) -> dict[str, Any]:
    return {
        "id": reason_id,
        "label": label,
        "measured": measured,
        "threshold": threshold,
    }


def _apply_automated_review_profile(
    *,
    bank: dict[str, Any],
    context: FeatureContext,
    selected_ranked: Sequence[Sequence[tuple[int, float]]],
    ranking_outputs: Mapping[
        tuple[str, str, str], Sequence[Sequence[tuple[int, float]]]
    ],
    previous_bank: Mapping[str, Any] | None,
    review_config: Mapping[str, Any],
    owner_question_decisions: Mapping[
        tuple[str, str], OwnerQuestionDecision
    ],
    owner_batch_decisions: Mapping[str, OwnerBatchDecision],
) -> dict[str, Any]:
    """Classify every generated question and emit only unresolved exceptions."""
    policy_version = str(review_config.get("policyVersion", "concept-auto-review-v1"))
    profile_id = str(review_config.get("id", "reference-balanced"))
    minimum_agreement = float(review_config.get("minimumMeanTop4Agreement", 0.5))
    minimum_support = float(review_config.get("minimumSelectedCandidateSupport", 0.35))
    minimum_margin = float(review_config.get("minimumNormalizedBoundaryMargin", 0.01))
    minimum_relevance = int(review_config.get("minimumDistractorRelevance", 2))
    review_changed_choices = bool(review_config.get("reviewChangedChoiceSet", True))

    previous_element_fingerprints = (
        previous_bank.get("elementFingerprints")
        if isinstance(previous_bank, Mapping)
        and isinstance(previous_bank.get("elementFingerprints"), Mapping)
        else {}
    )
    current_element_fingerprints = _element_fingerprints(context.elements)
    changed_element_ids = sorted(
        element_id
        for element_id, fingerprint in current_element_fingerprints.items()
        if previous_element_fingerprints.get(element_id) != fingerprint
    )
    changed_element_set = set(changed_element_ids)
    previous_questions = {
        str(item.get("questionId")): item
        for item in (
            previous_bank.get("questions", [])
            if isinstance(previous_bank, Mapping)
            and isinstance(previous_bank.get("questions"), list)
            else []
        )
        if isinstance(item, Mapping) and item.get("questionId")
    }
    previous_question_fingerprints = (
        previous_bank.get("questionFingerprints")
        if isinstance(previous_bank, Mapping)
        and isinstance(previous_bank.get("questionFingerprints"), Mapping)
        else {}
    )
    element_indices = {
        element.element_id: index for index, element in enumerate(context.elements)
    }
    all_rankings = list(ranking_outputs.values())
    question_fingerprints: dict[str, str] = {}
    pending_items: list[dict[str, Any]] = []
    resolved_items: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    changed_question_count = 0
    affected_question_count = 0
    stale_decision_count = 0

    for question_index, raw_question in enumerate(bank.get("questions", [])):
        if not isinstance(raw_question, dict):
            continue
        question_id = str(raw_question["questionId"])
        fingerprint = _question_review_fingerprint(raw_question)
        question_fingerprints[question_id] = fingerprint
        question_changed = previous_question_fingerprints.get(question_id) != fingerprint
        if question_changed:
            changed_question_count += 1

        selected_choice_ids = [
            str(choice["elementId"])
            for choice in raw_question.get("choices", [])
            if isinstance(choice, Mapping) and not bool(choice.get("isCorrect"))
        ]
        selected_indices = {
            element_indices[element_id]
            for element_id in selected_choice_ids
            if element_id in element_indices
        }
        target_id = str(raw_question["elementId"])
        affected = question_changed or target_id in changed_element_set or any(
            element_id in changed_element_set for element_id in selected_choice_ids
        )
        affected_question_count += int(affected)
        previous_question = previous_questions.get(question_id)
        previous_choice_ids = [
            str(choice.get("elementId"))
            for choice in (
                previous_question.get("choices", [])
                if isinstance(previous_question, Mapping)
                and isinstance(previous_question.get("choices"), list)
                else []
            )
            if isinstance(choice, Mapping) and not bool(choice.get("isCorrect"))
        ]
        choice_set_changed = bool(previous_question) and set(previous_choice_ids) != set(
            selected_choice_ids
        )

        agreements: list[float] = []
        candidate_support_values: list[float] = []
        if all_rankings:
            top_sets = [
                {candidate_index for candidate_index, _ in run[question_index][:4]}
                for run in all_rankings
            ]
            agreements = [
                len(selected_indices & top_set) / max(1, len(selected_indices | top_set))
                for top_set in top_sets
            ]
            for candidate_index in selected_indices:
                candidate_support_values.append(
                    sum(candidate_index in top_set for top_set in top_sets) / len(top_sets)
                )
        mean_agreement = round(float(np.mean(agreements)), 6) if agreements else 1.0
        minimum_candidate_support = (
            round(float(min(candidate_support_values)), 6)
            if candidate_support_values
            else 1.0
        )

        ranked_row = list(selected_ranked[question_index])
        selected_scores = [
            score for candidate_index, score in ranked_row if candidate_index in selected_indices
        ]
        unselected_scores = [
            score for candidate_index, score in ranked_row if candidate_index not in selected_indices
        ]
        score_span = (
            max(score for _, score in ranked_row) - min(score for _, score in ranked_row)
            if ranked_row
            else 0.0
        )
        boundary_margin = (
            (min(selected_scores) - max(unselected_scores)) / score_span
            if selected_scores and unselected_scores and score_span > 1e-12
            else 0.0
        )
        boundary_margin = round(float(boundary_margin), 6)
        weak_relevances = [
            int(context.weak_relevance[question_index, candidate_index])
            for candidate_index in selected_indices
        ]
        weakest_relevance = min(weak_relevances) if weak_relevances else 0

        hard_reasons: list[dict[str, Any]] = []
        review_reasons: list[dict[str, Any]] = []
        if weakest_relevance < minimum_relevance:
            hard_reasons.append(
                _review_reason(
                    "weak-distractor",
                    "선택 오답의 자동 타당성 등급 미달",
                    weakest_relevance,
                    minimum_relevance,
                )
            )
        if mean_agreement < minimum_agreement:
            review_reasons.append(
                _review_reason(
                    "ranker-disagreement",
                    "랭커 간 Top-4 합의도 낮음",
                    mean_agreement,
                    minimum_agreement,
                )
            )
        if minimum_candidate_support < minimum_support:
            review_reasons.append(
                _review_reason(
                    "candidate-support",
                    "선택 오답의 실험 조합 지지율 낮음",
                    minimum_candidate_support,
                    minimum_support,
                )
            )
        if boundary_margin < minimum_margin:
            review_reasons.append(
                _review_reason(
                    "boundary-margin",
                    "4위 선택 경계가 불안정함",
                    boundary_margin,
                    minimum_margin,
                )
            )
        if review_changed_choices and choice_set_changed:
            review_reasons.append(
                _review_reason(
                    "choice-set-changed",
                    "이전 문항은행 대비 오답 구성이 변경됨",
                    True,
                    False,
                )
            )

        matching_decision = owner_question_decisions.get((question_id, fingerprint))
        if matching_decision is None and any(
            key[0] == question_id for key in owner_question_decisions
        ):
            stale_decision_count += 1
        if matching_decision and matching_decision.decision == "rejected":
            hard_reasons.append(
                _review_reason(
                    "owner-rejected",
                    "Owner가 문항을 차단함",
                    "rejected",
                    "approved",
                )
            )

        if hard_reasons:
            review_status = "blocked"
        elif matching_decision and matching_decision.decision == "approved":
            review_status = "owner_approved"
        elif review_reasons:
            review_status = "needs_owner_review"
        else:
            review_status = "automated_pass"
        raw_question["reviewStatus"] = review_status
        status_counts[review_status] += 1

        item = {
            "questionId": question_id,
            "elementId": target_id,
            "split": context.questions[question_index].split,
            "questionFingerprint": fingerprint,
            "severity": "block" if hard_reasons else "review",
            "stem": raw_question.get("stem"),
            "explanation": raw_question.get("explanation"),
            "choices": raw_question.get("choices"),
            "reasons": [*hard_reasons, *review_reasons],
            "metrics": {
                "meanTop4Agreement": mean_agreement,
                "minimumSelectedCandidateSupport": minimum_candidate_support,
                "normalizedBoundaryMargin": boundary_margin,
                "minimumDistractorRelevance": weakest_relevance,
            },
            "change": {
                "affectedByChangedElement": affected,
                "choiceSetChanged": choice_set_changed,
            },
            "ownerDecision": asdict(matching_decision) if matching_decision else None,
        }
        if review_status in {"needs_owner_review", "blocked"}:
            pending_items.append(item)
        elif matching_decision:
            resolved_items.append(item)

    review_input = {
        "policyVersion": policy_version,
        "profileId": profile_id,
        "policyConfigSha256": _sha256_bytes(_stable_json_bytes(dict(review_config))),
        "contentFingerprint": bank.get("contentFingerprint"),
        "selectedEmbedding": bank.get("selectedEmbedding"),
        "selectedRetrievalProfile": bank.get("selectedRetrievalProfile"),
        "selectedRanker": bank.get("selectedRanker"),
        "questionFingerprints": question_fingerprints,
    }
    review_input_sha = _sha256_bytes(_stable_json_bytes(review_input))
    batch_decision = owner_batch_decisions.get(review_input_sha)
    owner_batch_approved = bool(
        batch_decision and batch_decision.decision == "approved"
    )
    unresolved_count = status_counts["needs_owner_review"]
    blocked_count = status_counts["blocked"]
    owner_review_complete = (
        unresolved_count == 0 and blocked_count == 0 and owner_batch_approved
    )

    bank["elementFingerprints"] = current_element_fingerprints
    bank["questionFingerprints"] = question_fingerprints
    bank["reviewInputSha256"] = review_input_sha
    bank["automatedReviewPolicyVersion"] = policy_version
    bank["automatedReviewProfileId"] = profile_id
    bank["automatedReviewPolicySha256"] = review_input["policyConfigSha256"]
    bank["automatedReview"] = {
        "autoPassedCount": status_counts["automated_pass"],
        "ownerApprovedCount": status_counts["owner_approved"],
        "needsOwnerReviewCount": unresolved_count,
        "blockedCount": blocked_count,
        "ownerBatchApproved": owner_batch_approved,
    }
    return {
        "policyVersion": policy_version,
        "profileId": profile_id,
        "baselineMode": "incremental" if previous_element_fingerprints else "initial",
        "reviewInputSha256": review_input_sha,
        "policyConfigSha256": review_input["policyConfigSha256"],
        "previousBankSha256": previous_bank.get("bankSha256")
        if isinstance(previous_bank, Mapping)
        else None,
        "changedElementCount": len(changed_element_ids),
        "changedElementIds": changed_element_ids,
        "changedQuestionCount": changed_question_count,
        "affectedQuestionCount": affected_question_count,
        "reusedQuestionCount": len(bank.get("questions", [])) - affected_question_count,
        "autoPassedCount": status_counts["automated_pass"],
        "ownerApprovedCount": status_counts["owner_approved"],
        "needsOwnerReviewCount": unresolved_count,
        "blockedCount": blocked_count,
        "staleOwnerDecisionCount": stale_decision_count,
        "ownerBatchApproved": owner_batch_approved,
        "ownerBatchDecision": asdict(batch_decision) if batch_decision else None,
        "ownerReviewComplete": owner_review_complete,
        "queue": pending_items,
        "resolvedItems": resolved_items,
    }


def automated_review_question_bank(
    *,
    bank: dict[str, Any],
    context: FeatureContext,
    selected_ranked: Sequence[Sequence[tuple[int, float]]],
    ranking_outputs: Mapping[
        tuple[str, str, str], Sequence[Sequence[tuple[int, float]]]
    ],
    previous_bank: Mapping[str, Any] | None,
    review_config: Mapping[str, Any],
    owner_question_decisions: Mapping[
        tuple[str, str], OwnerQuestionDecision
    ],
    owner_batch_decisions: Mapping[str, OwnerBatchDecision],
) -> dict[str, Any]:
    """Select an automated-review profile on validation, then evaluate once."""
    raw_profiles = review_config.get("profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ConceptModelError("automatedReview.profiles must contain profiles")
    profiles = [item for item in raw_profiles if isinstance(item, Mapping)]
    if len(profiles) != len(raw_profiles):
        raise ConceptModelError("Every automated review profile must be an object")
    target_rate = float(review_config.get("targetValidationReviewRate", 0.1))
    experiments: list[dict[str, Any]] = []
    for index, profile in enumerate(profiles):
        trial_config = {**dict(review_config), **dict(profile)}
        trial_bank = json.loads(_stable_json_bytes(bank).decode("utf-8"))
        trial = _apply_automated_review_profile(
            bank=trial_bank,
            context=context,
            selected_ranked=selected_ranked,
            ranking_outputs=ranking_outputs,
            previous_bank=None,
            review_config=trial_config,
            owner_question_decisions={},
            owner_batch_decisions={},
        )
        validation_items = [
            item for item in trial["queue"] if item.get("split") == "validation"
        ]
        validation_question_count = sum(
            question.split == "validation" for question in context.questions
        )
        validation_review_rate = (
            len(validation_items) / validation_question_count
            if validation_question_count
            else 0.0
        )
        experiments.append(
            {
                "profileId": str(profile.get("id", f"profile-{index + 1}")),
                "profileIndex": index,
                "thresholds": {
                    "minimumMeanTop4Agreement": float(
                        trial_config.get("minimumMeanTop4Agreement", 0.5)
                    ),
                    "minimumSelectedCandidateSupport": float(
                        trial_config.get("minimumSelectedCandidateSupport", 0.35)
                    ),
                    "minimumNormalizedBoundaryMargin": float(
                        trial_config.get("minimumNormalizedBoundaryMargin", 0.01)
                    ),
                },
                "provenance": str(profile.get("provenance", "")),
                "validationQuestionCount": validation_question_count,
                "validationReviewCount": len(validation_items),
                "validationReviewRate": round(validation_review_rate, 6),
                "validationBlockedCount": sum(
                    item.get("severity") == "block" for item in validation_items
                ),
                "distanceFromTargetReviewRate": round(
                    abs(validation_review_rate - target_rate), 6
                ),
            }
        )
    selected_experiment = min(
        experiments,
        key=lambda item: (
            item["validationBlockedCount"],
            item["distanceFromTargetReviewRate"],
            item["profileIndex"],
        ),
    )
    selected_profile = next(
        profile
        for profile in profiles
        if str(profile.get("id")) == selected_experiment["profileId"]
    )
    selected_config = {**dict(review_config), **dict(selected_profile)}
    result = _apply_automated_review_profile(
        bank=bank,
        context=context,
        selected_ranked=selected_ranked,
        ranking_outputs=ranking_outputs,
        previous_bank=previous_bank,
        review_config=selected_config,
        owner_question_decisions=owner_question_decisions,
        owner_batch_decisions=owner_batch_decisions,
    )
    result["profileExperiments"] = experiments
    result["selectionRule"] = str(review_config.get("selectionRule", ""))
    result["targetValidationReviewRate"] = target_rate
    result["selectedProfileId"] = selected_experiment["profileId"]
    result["selectionReason"] = (
        f"validation 예외율 {selected_experiment['validationReviewRate']:.2%}가 "
        f"목표 {target_rate:.2%}에 가장 가까운 프로필"
    )
    return result


def _human_test_coverage(
    questions: Sequence[QuestionGroup], labels: Mapping[tuple[str, str], HumanLabel]
) -> tuple[float, int, int]:
    test_questions = [item for item in questions if item.split == "test"]
    covered = sum(
        sum(1 for question_id, _ in labels if question_id == question.question_id) >= 8
        for question in test_questions
    )
    return (
        round(covered / len(test_questions), 6) if test_questions else 0.0,
        covered,
        len(test_questions),
    )


def _gate(
    gate_id: str,
    label: str,
    measured: float | int | bool,
    threshold: float | int | bool,
    passed: bool,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "label": label,
        "measured": measured,
        "threshold": threshold,
        "passed": passed,
    }


def _package_version(module_name: str) -> str | None:
    try:
        module = __import__(module_name)
    except ImportError:
        return None
    return str(getattr(module, "__version__", "unknown"))


def _append_admin_history(path: Path, experiment: Mapping[str, Any]) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                existing = value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            existing = {}
    history = existing.get("experiments", [])
    if not isinstance(history, list):
        history = []
    experiment_id = str(experiment["experimentId"])
    history = [item for item in history if isinstance(item, dict) and item.get("experimentId") != experiment_id]
    history.insert(0, dict(experiment))
    result = {
        "reportVersion": REPORT_VERSION,
        "latestExperimentId": experiment_id,
        "experiments": history[:30],
    }
    _atomic_json(path, result)
    return result


def _md_cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def _md_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _md_bytes(value: Any) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KiB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MiB"
    return f"{size / 1024**3:.2f} GiB"


def _render_experiment_markdown(experiment: Mapping[str, Any]) -> str:
    experiment_id = str(experiment.get("experimentId", "unknown-experiment"))
    status = str(experiment.get("status", "unknown"))
    release_ready = bool(experiment.get("releaseReady", False))
    dataset = experiment.get("dataset") if isinstance(experiment.get("dataset"), Mapping) else {}
    labels = experiment.get("labels") if isinstance(experiment.get("labels"), Mapping) else {}
    automated_review = experiment.get("automatedReview") if isinstance(experiment.get("automatedReview"), Mapping) else {}
    selection = experiment.get("selection") if isinstance(experiment.get("selection"), Mapping) else {}
    evaluation = experiment.get("evaluation") if isinstance(experiment.get("evaluation"), Mapping) else {}
    validation = evaluation.get("validation") if isinstance(evaluation.get("validation"), Mapping) else {}
    test = evaluation.get("test") if isinstance(evaluation.get("test"), Mapping) else {}
    weights = experiment.get("weightExperiments") if isinstance(experiment.get("weightExperiments"), Mapping) else {}
    weak = weights.get("weakSupervision") if isinstance(weights.get("weakSupervision"), Mapping) else {}
    fusion = weights.get("fusionBaseline") if isinstance(weights.get("fusionBaseline"), Mapping) else {}
    safety = experiment.get("safety") if isinstance(experiment.get("safety"), Mapping) else {}
    environment = experiment.get("environment") if isinstance(experiment.get("environment"), Mapping) else {}
    artifacts = experiment.get("artifacts") if isinstance(experiment.get("artifacts"), Mapping) else {}
    embeddings = experiment.get("embeddings") if isinstance(experiment.get("embeddings"), list) else []
    ranker_runs = experiment.get("rankerRuns") if isinstance(experiment.get("rankerRuns"), list) else []
    gates = experiment.get("qualityGates") if isinstance(experiment.get("qualityGates"), list) else []
    references = experiment.get("methodReferences") if isinstance(experiment.get("methodReferences"), list) else []
    weak_profiles = weights.get("weakSupervisionProfiles") if isinstance(weights.get("weakSupervisionProfiles"), list) else []
    retrieval_profiles = weights.get("retrievalProfiles") if isinstance(weights.get("retrievalProfiles"), list) else []
    xgboost_grid = weights.get("xgboostGrid") if isinstance(weights.get("xgboostGrid"), list) else []

    lines = [
        f"# 개념형 모델 실험 보고서 — `{experiment_id}`",
        "",
        "> 이 파일은 `tools/train_concept_question_model.py`가 실험 JSON에서 자동 생성한 영구 감사 기록입니다.",
        "> 수동으로 수치를 수정하지 말고 같은 입력과 설정으로 실험을 다시 실행하십시오.",
        "",
        "## 1. 결과 요약",
        "",
    ]
    if not release_ready:
        lines.extend(
            [
                f"> **릴리스 차단:** {_md_cell(experiment.get('releaseBlockReason'))}",
                "> 자동 검수 전의 test 지표는 약지도 규칙 재현도이며 독립적인 교육 품질 성능이 아닙니다.",
                "",
            ]
        )
    lines.extend(
        [
            "| 항목 | 값 |",
            "|---|---|",
            f"| 상태 | `{_md_cell(status)}` |",
            f"| 릴리스 가능 | {_md_cell(release_ready)} |",
            f"| 시작 | {_md_cell(experiment.get('startedAt'))} |",
            f"| 종료 | {_md_cell(experiment.get('finishedAt'))} |",
            f"| 실행 시간 | {_md_cell(experiment.get('durationSeconds'))}초 |",
            f"| 선택 임베딩 | `{_md_cell(selection.get('embeddingId'))}` |",
            f"| 선택 검색 결합 | `{_md_cell(selection.get('retrievalProfileId'))}` |",
            f"| 선택 랭커 | `{_md_cell(selection.get('rankerId'))}` |",
            f"| validation NDCG@4 | {_md_cell(validation.get('ndcgAt4'))} |",
            f"| test NDCG@4 | {_md_cell(test.get('ndcgAt4'))} |",
            f"| test Precision@4 | {_md_cell(test.get('precisionAt4'))} |",
            f"| 사람 test 커버리지 | {_md_percent(labels.get('humanTestCoverage'))} |",
            f"| 자동 검수 프로필 | `{_md_cell(automated_review.get('selectedProfileId'))}` |",
            f"| 자동 통과/Owner 확인/차단 | {_md_cell(automated_review.get('autoPassedCount'))} / {_md_cell(automated_review.get('needsOwnerReviewCount'))} / {_md_cell(automated_review.get('blockedCount'))} |",
            f"| 외부 LLM API 호출 | {_md_cell(environment.get('externalLlmApiCalls'))}회 |",
            "",
            "선택 근거: " + _md_cell(selection.get("reason")),
            "",
            "## 2. 재현성 및 데이터 분할",
            "",
            "| 항목 | 값 |",
            "|---|---|",
            f"| 콘텐츠 fingerprint | `{_md_cell(dataset.get('contentFingerprint'))}` |",
            f"| 설정 SHA-256 | `{_md_cell(dataset.get('configSha256'))}` |",
            f"| split SHA-256 | `{_md_cell(dataset.get('splitSha256'))}` |",
            f"| 요소 | {_md_cell(dataset.get('elementCount'))}개 |",
            f"| 사실 레코드 | {_md_cell(dataset.get('factCount'))}개 |",
            f"| 문항 | {_md_cell(dataset.get('questionCount'))}개 |",
            f"| 오답 후보 | {_md_cell(dataset.get('candidateCount'))}개 |",
            f"| 요소 split | `{_md_cell(dataset.get('elementSplits'))}` |",
            f"| 문항 split | `{_md_cell(dataset.get('questionSplits'))}` |",
            f"| 문항 은행 SHA-256 | `{_md_cell(artifacts.get('questionBankSha256'))}` |",
            f"| 모델 SHA-256 | `{_md_cell(selection.get('modelSha256'))}` |",
            "",
            "## 3. 기준선과 레퍼런스 구분",
            "",
            "| 구분 | 값 | 출처/판정 |",
            "|---|---|---|",
            f"| 검색 결합 기준선 | `{_md_cell(fusion.get('method'))}`, k={_md_cell(fusion.get('rrfK'))} | {_md_cell(fusion.get('reference'))} |",
            "| RRF 기준 가중치 | 사용 신호 동일 가중치 | reference baseline |",
            "| RRF 변형 가중치 | dense/word/char 비중 변화 | 민감도 실험, 논문 기본값 아님 |",
            "| pairwise loss | RankNet-style logistic | Burges et al., ICML 2005 |",
            "| LogisticRegression C=1 | scikit-learn 기본값 | RankNet 논문값 아님 |",
            "| C=0.1/1/10 | 로그 간격 탐색 | validation 실험값 |",
            "| XGBoost depth=6, eta=0.3 | reference implementation 기본값 | FinDone 최적값 아님 |",
            "| 나머지 XGBoost 조합 | 얕은 트리·낮은 학습률 | validation 실험값 |",
            "",
            f"RRF 적용 이유: {_md_cell(fusion.get('rationale'))}",
            "",
            "## 4. 약지도 가중치 민감도",
            "",
            f"기준 프로필: `{_md_cell(weak.get('canonicalProfileId'))}` · RRF k={_md_cell(weak.get('rrfK'))}",
            "",
        ]
    )
    if weak_profiles:
        lines.extend(
            [
                "### 입력 가중치",
                "",
                "| 프로필 | question-word | question-char | answer-word | answer-char | same-domain | same-mode | 성격 |",
                "|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for profile in weak_profiles:
            if not isinstance(profile, Mapping):
                continue
            lines.append(
                "| {id} | {qw} | {qc} | {aw} | {ac} | {domain} | {mode} | {provenance} |".format(
                    id=_md_cell(profile.get("id")),
                    qw=_md_cell(profile.get("questionWord")),
                    qc=_md_cell(profile.get("questionChar")),
                    aw=_md_cell(profile.get("answerWord")),
                    ac=_md_cell(profile.get("answerChar")),
                    domain=_md_cell(profile.get("sameDomain")),
                    mode=_md_cell(profile.get("sameMode")),
                    provenance=_md_cell(profile.get("provenance")),
                )
            )
        lines.append("")
    lines.extend(
        [
            "### 기준 프로필 대비 결과",
            "",
            "| 프로필 | 평균 Top-4 Jaccard | 최소 Jaccard | 변경 문항 |",
            "|---|---:|---:|---:|",
        ]
    )
    comparisons = weak.get("comparisons") if isinstance(weak.get("comparisons"), list) else []
    for item in comparisons:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| {_md_cell(item.get('profileId'))} | {_md_cell(item.get('meanTop4JaccardVsCanonical'))} | {_md_cell(item.get('minimumTop4JaccardVsCanonical'))} | {_md_cell(item.get('changedQuestionCount'))} |"
        )
    lines.extend(
        [
            "",
            f"전체 대안 평균 Jaccard: **{_md_cell(weak.get('meanTop4JaccardAcrossAlternatives'))}**. {_md_cell(weak.get('interpretation'))}",
            "",
            "## 5. 검색 혼합비와 정규화 탐색 범위",
            "",
        ]
    )
    if retrieval_profiles:
        profile_keys = sorted(
            {
                key
                for profile in retrieval_profiles
                if isinstance(profile, Mapping)
                for key in profile
                if key not in {"id", "provenance"}
            }
        )
        lines.append("| 프로필 | " + " | ".join(profile_keys) + " | 성격 |")
        lines.append("|---|" + "---:|" * len(profile_keys) + "---|")
        for profile in retrieval_profiles:
            if not isinstance(profile, Mapping):
                continue
            lines.append(
                "| "
                + _md_cell(profile.get("id"))
                + " | "
                + " | ".join(_md_cell(profile.get(key)) for key in profile_keys)
                + " | "
                + _md_cell(profile.get("provenance"))
                + " |"
            )
        lines.append("")
    lines.extend(
        [
            f"- Pairwise C 탐색: `{_md_cell(weights.get('pairwiseCValues'))}`",
            f"- 검색 프로필 수: {_md_cell(weights.get('retrievalProfileCount'))}",
            f"- 선택 규칙: {_md_cell(weights.get('selectionRule'))}",
            "",
            "### XGBoost 탐색 범위",
            "",
            "| ID | max depth | learning rate | 성격 |",
            "|---|---:|---:|---|",
        ]
    )
    for item in xgboost_grid:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| {_md_cell(item.get('id'))} | {_md_cell(item.get('maxDepth'))} | {_md_cell(item.get('learningRate'))} | {_md_cell(item.get('provenance'))} |"
        )
    lines.extend(
        [
            "",
            "## 6. 임베딩 실행 결과",
            "",
            "| 후보 | 모델 | 상태 | revision | 차원 | 인코딩 시간 | 캐시 | 행렬 SHA-256 | 로컬 크기 | 오류 |",
            "|---|---|---|---|---:|---:|---|---|---:|---|",
        ]
    )
    for item in embeddings:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| {_md_cell(item.get('candidateId'))} | `{_md_cell(item.get('modelId'))}` | {_md_cell(item.get('status'))} | `{_md_cell(item.get('revisionResolved') or item.get('revisionRequested'))}` | {_md_cell(item.get('dimensions'))} | {_md_cell(item.get('encodeSeconds'))}초 | {_md_cell(item.get('cacheHit', False))} | `{_md_cell(item.get('matrixCacheSha256'))}` | {_md_bytes(item.get('artifactBytes'))} | {_md_cell(item.get('error'))} |"
        )
    lines.extend(
        [
            "",
            "## 7. 전체 validation 실험 행렬",
            "",
            f"총 {len(ranker_runs)}개 실행. 선택 전에는 validation만 계산하며, `test=YES`인 한 행만 최종 test를 열었습니다.",
            "",
            "| # | 임베딩 | 검색 프로필 | 랭커 | 하이퍼파라미터 | 상태 | Recall@20 | NDCG@4 | P@4 | MRR | test | 학습초 | 오류 |",
            "|---:|---|---|---|---|---|---:|---:|---:|---:|---|---:|---|",
        ]
    )
    for index, item in enumerate(ranker_runs, start=1):
        if not isinstance(item, Mapping):
            continue
        metrics = item.get("validation") if isinstance(item.get("validation"), Mapping) else {}
        is_selected = (
            item.get("embeddingId") == selection.get("embeddingId")
            and item.get("retrievalProfileId") == selection.get("retrievalProfileId")
            and item.get("rankerId") == selection.get("rankerId")
        )
        ranker_label = f"**{_md_cell(item.get('rankerId'))}**" if is_selected else _md_cell(item.get("rankerId"))
        lines.append(
            f"| {index} | {_md_cell(item.get('embeddingId'))} | {_md_cell(item.get('retrievalProfileId'))} | {ranker_label} | `{_md_cell(item.get('hyperparameters'))}` | {_md_cell(item.get('status'))} | {_md_cell(metrics.get('retrievalRecallAt20'))} | {_md_cell(metrics.get('ndcgAt4'))} | {_md_cell(metrics.get('precisionAt4'))} | {_md_cell(metrics.get('mrr'))} | {_md_cell(item.get('testEvaluated'))} | {_md_cell(item.get('trainingSeconds'))} | {_md_cell(item.get('error'))} |"
        )
    lines.extend(
        [
            "",
            "## 8. 선택된 구성과 최종 test",
            "",
            "| 항목 | validation | test |",
            "|---|---:|---:|",
            f"| Recall@20 | {_md_cell(validation.get('retrievalRecallAt20'))} | {_md_cell(test.get('retrievalRecallAt20'))} |",
            f"| NDCG@4 | {_md_cell(validation.get('ndcgAt4'))} | {_md_cell(test.get('ndcgAt4'))} |",
            f"| Precision@4 | {_md_cell(validation.get('precisionAt4'))} | {_md_cell(test.get('precisionAt4'))} |",
            f"| MRR | {_md_cell(validation.get('mrr'))} | {_md_cell(test.get('mrr'))} |",
            "",
            f"- 라벨 출처: `{_md_cell(evaluation.get('labelSource'))}`",
            f"- 모델 크기: {_md_bytes(selection.get('modelBytes'))}",
            f"- 선택 허용 오차: {_md_cell(selection.get('selectionTolerance'))}",
            f"- 지표 경고: {_md_cell(labels.get('metricWarning'))}",
            "",
            "## 9. 자동 검수 프로필 실험과 증분 영향",
            "",
            f"선택 근거: {_md_cell(automated_review.get('selectionReason'))}",
            "",
            "| 프로필 | validation 예외 | 예외율 | 차단 | 기준선/실험 근거 |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for item in automated_review.get("profileExperiments", []):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| {_md_cell(item.get('profileId'))} | {_md_cell(item.get('validationReviewCount'))}/{_md_cell(item.get('validationQuestionCount'))} | {_md_percent(item.get('validationReviewRate'))} | {_md_cell(item.get('validationBlockedCount'))} | {_md_cell(item.get('provenance'))} |"
        )
    lines.extend(
        [
            "",
            f"- 기준선 모드: `{_md_cell(automated_review.get('baselineMode'))}`",
            f"- 변경 요소: {_md_cell(automated_review.get('changedElementCount'))}개",
            f"- 영향 문항: {_md_cell(automated_review.get('affectedQuestionCount'))}개",
            f"- 재사용 문항: {_md_cell(automated_review.get('reusedQuestionCount'))}개",
            f"- Owner 확인 대기: {_md_cell(automated_review.get('needsOwnerReviewCount'))}개",
            f"- 자동 차단: {_md_cell(automated_review.get('blockedCount'))}개",
            f"- 검수 입력 SHA-256: `{_md_cell(automated_review.get('reviewInputSha256'))}`",
            "",
            "프로필 선택은 validation 예외율만 사용하며 test 문항의 검수 결과는 프로필 선택에 사용하지 않습니다.",
            "",
            "## 10. 안전성 및 릴리스 게이트",
            "",
            "| 안전성 검사 | 값 |",
            "|---|---:|",
            f"| 정답 누출 | {_md_cell(safety.get('answerLeakCount'))} |",
            f"| 중복 선택지 | {_md_cell(safety.get('duplicateChoiceCount'))} |",
            f"| 약한 오답 포함 문항 | {_md_cell(safety.get('ambiguousQuestionCount'))} |",
            "",
            "| 게이트 | 측정 | 기준 | 결과 |",
            "|---|---:|---:|---|",
        ]
    )
    for gate in gates:
        if not isinstance(gate, Mapping):
            continue
        lines.append(
            f"| {_md_cell(gate.get('label'))} | {_md_cell(gate.get('measured'))} | {_md_cell(gate.get('threshold'))} | {'PASS' if gate.get('passed') else 'BLOCK'} |"
        )
    lines.extend(
        [
            "",
            "## 10. 환경과 산출물",
            "",
            "### 환경",
            "",
            "| 항목 | 값 |",
            "|---|---|",
        ]
    )
    for key, value in environment.items():
        lines.append(f"| {_md_cell(key)} | `{_md_cell(value)}` |")
    lines.extend(["", "### 산출물", "", "| 항목 | 값 |", "|---|---|"])
    for key, value in artifacts.items():
        lines.append(f"| {_md_cell(key)} | `{_md_cell(value)}` |")
    lines.extend(["", "## 11. 참고문헌", ""])
    if fusion.get("referenceUrl"):
        lines.append(f"- [{_md_cell(fusion.get('reference'))}]({_md_cell(fusion.get('referenceUrl'))})")
    for reference in references:
        if not isinstance(reference, Mapping):
            continue
        lines.append(
            f"- [{_md_cell(reference.get('title'))}]({_md_cell(reference.get('url'))})"
        )
    if not references and not fusion.get("referenceUrl"):
        lines.append("- 기록된 참고문헌 없음")
    return "\n".join(lines)


def _render_markdown_index(experiments: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# FinDone 개념형 모델 실험 기록",
        "",
        "이 디렉터리는 오프라인 개념형 5지선다 모델링 실험의 사람이 읽을 수 있는 영구 기록이다.",
        "Admin 시각화는 `admin/data/concept-model-experiments.generated.json`을 사용하고, 이 MD들은 감사·비교·의사결정 이력으로 유지한다.",
        "",
        "- 설계 기준: [개념형 5지선다 오프라인 모델링 설계서](CONCEPT_MCQ_MODELING_DESIGN.md)",
        "- 생성 명령: `python tools/train_concept_question_model.py --write-question-bank --write-admin-report --write-markdown-report`",
        "- 원칙: validation으로 조합을 선택하고 선택된 한 조합에만 test를 실행한다.",
        "",
        "| 실험 | 시각 | 상태 | 후보 임베딩 | 실행 조합 | 선택 구성 | val NDCG@4 | test NDCG@4 | 사람 test | 보고서 |",
        "|---|---|---|---:|---:|---|---:|---:|---:|---|",
    ]
    for experiment in experiments:
        selection = experiment.get("selection") if isinstance(experiment.get("selection"), Mapping) else {}
        evaluation = experiment.get("evaluation") if isinstance(experiment.get("evaluation"), Mapping) else {}
        validation = evaluation.get("validation") if isinstance(evaluation.get("validation"), Mapping) else {}
        test = evaluation.get("test") if isinstance(evaluation.get("test"), Mapping) else {}
        labels = experiment.get("labels") if isinstance(experiment.get("labels"), Mapping) else {}
        embeddings = experiment.get("embeddings") if isinstance(experiment.get("embeddings"), list) else []
        runs = experiment.get("rankerRuns") if isinstance(experiment.get("rankerRuns"), list) else []
        experiment_id = str(experiment.get("experimentId", "unknown"))
        selected_label = "/".join(
            str(selection.get(key, "—"))
            for key in ("embeddingId", "retrievalProfileId", "rankerId")
        )
        lines.append(
            f"| `{_md_cell(experiment_id)}` | {_md_cell(experiment.get('startedAt'))} | {_md_cell(experiment.get('status'))} | {len(embeddings)} | {len(runs)} | `{_md_cell(selected_label)}` | {_md_cell(validation.get('ndcgAt4'))} | {_md_cell(test.get('ndcgAt4'))} | {_md_percent(labels.get('humanTestCoverage'))} | [열기](experiments/{experiment_id}.md) |"
        )
    lines.extend(
        [
            "",
            "## 수치 해석 주의",
            "",
            "자동 검수 전 test 수치는 약지도 규칙 재현도이므로 실제 교육 품질이나 일반화 성능으로 해석하면 안 된다. 자동 검수 차단 0건, 예외 확인 완료, Owner 배치 승인과 모든 릴리스 게이트를 통과한 실험만 `release_ready`가 될 수 있다.",
        ]
    )
    return "\n".join(lines)


def write_markdown_history(
    report_dir: Path,
    history: Mapping[str, Any],
) -> list[Path]:
    raw_experiments = history.get("experiments")
    if not isinstance(raw_experiments, list):
        raise ConceptModelError("Experiment history has no experiments list")
    experiments = [item for item in raw_experiments if isinstance(item, Mapping)]
    report_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for experiment in experiments:
        experiment_id = str(experiment.get("experimentId", "")).strip()
        if not re.fullmatch(r"cmq-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}", experiment_id):
            raise ConceptModelError(f"Unsafe experiment id for Markdown report: {experiment_id}")
        path = report_dir / f"{experiment_id}.md"
        _atomic_text(path, _render_experiment_markdown(experiment))
        written.append(path)
    _atomic_text(report_dir.parent / "README.md", _render_markdown_index(experiments))
    return written


def refresh_reference_catalog(
    config_path: Path = DEFAULT_CONFIG,
    admin_report_path: Path = DEFAULT_ADMIN_REPORT,
    markdown_report_dir: Path = DEFAULT_MARKDOWN_REPORT_DIR,
) -> int:
    """Backfill the current primary-source catalog into immutable metric records."""
    config = _load_json_object(config_path)
    references = config.get("methodReferences")
    if not isinstance(references, list) or not all(isinstance(item, Mapping) for item in references):
        raise ConceptModelError("methodReferences is missing from model config")
    history = _load_json_object(admin_report_path)
    experiments = history.get("experiments")
    if not isinstance(experiments, list):
        raise ConceptModelError("Experiment history has no experiments list")
    updated = 0
    for experiment in experiments:
        if not isinstance(experiment, dict):
            continue
        if experiment.get("methodReferences") != references:
            experiment["methodReferences"] = [dict(item) for item in references]
            experiment.pop("reportSha256", None)
            experiment["reportSha256"] = _sha256_bytes(_stable_json_bytes(experiment))
            updated += 1
    _atomic_json(admin_report_path, history)
    write_markdown_history(markdown_report_dir, history)
    return updated


def select_validation_run(
    successful_runs: Sequence[dict[str, Any]],
    candidate_specs: Sequence[Mapping[str, Any]],
    retrieval_profiles: Sequence[Mapping[str, Any]],
    tolerance: float,
) -> dict[str, Any]:
    """Select one run without inspecting test metrics.

    The highest validation NDCG@4 defines the eligible band. Inside that band
    the build-time cost policy prefers the configured embedding priority and a
    linear pairwise ranker. Metrics only break ties inside the same cost group.
    Returning the original run object lets the caller attach the one permitted
    test evaluation after selection.
    """
    if not successful_runs:
        raise ConceptModelError("No successful validation runs are available")
    if tolerance < 0:
        raise ConceptModelError("embeddingSelectionTolerance must be non-negative")

    best_ndcg = max(float(item["validation"]["ndcgAt4"]) for item in successful_runs)
    eligible = [
        item
        for item in successful_runs
        if best_ndcg - float(item["validation"]["ndcgAt4"]) <= tolerance
    ]
    embedding_priority = {
        str(item.get("id")): int(item.get("priority", 999))
        for item in candidate_specs
    }
    retrieval_priority = {
        str(item.get("id")): index for index, item in enumerate(retrieval_profiles)
    }
    simplest_embedding_priority = min(
        embedding_priority.get(str(item["embeddingId"]), 999) for item in eligible
    )
    same_embedding_cost = [
        item
        for item in eligible
        if embedding_priority.get(str(item["embeddingId"]), 999)
        == simplest_embedding_priority
    ]
    simplest_ranker_priority = min(
        0 if item["rankerFamily"] == "pairwise-logistic" else 1
        for item in same_embedding_cost
    )
    same_cost = [
        item
        for item in same_embedding_cost
        if (0 if item["rankerFamily"] == "pairwise-logistic" else 1)
        == simplest_ranker_priority
    ]
    return max(
        same_cost,
        key=lambda item: (
            float(item["validation"]["ndcgAt4"]),
            float(item["validation"]["precisionAt4"]),
            float(item["validation"]["retrievalRecallAt20"]),
            -retrieval_priority.get(str(item["retrievalProfileId"]), 999),
            -int(item["modelBytes"] or 0),
        ),
    )


def run_experiment(
    *,
    config_path: Path = DEFAULT_CONFIG,
    elements_path: Path = DEFAULT_ELEMENTS,
    labels_path: Path = DEFAULT_LABELS,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
    question_edits_path: Path = DEFAULT_QUESTION_EDITS,
    split_path: Path = DEFAULT_SPLIT,
    bank_path: Path = DEFAULT_BANK,
    admin_report_path: Path = DEFAULT_ADMIN_REPORT,
    build_dir: Path = DEFAULT_BUILD_DIR,
    markdown_report_dir: Path = DEFAULT_MARKDOWN_REPORT_DIR,
    embedding_ids: Sequence[str] = (),
    ranker_ids: Sequence[str] = ("pairwise-logistic",),
    device: str = "cpu",
    write_question_bank: bool = False,
    write_admin_report: bool = False,
    write_markdown_report: bool = False,
    progress: ProgressBar | None = None,
) -> dict[str, Any]:
    config_path = _resolve_repo_path(config_path)
    elements_path = _resolve_repo_path(elements_path)
    labels_path = _resolve_repo_path(labels_path)
    owner_decisions_path = _resolve_repo_path(owner_decisions_path)
    question_edits_path = _resolve_repo_path(question_edits_path)
    split_path = _resolve_repo_path(split_path)
    bank_path = _resolve_repo_path(bank_path)
    admin_report_path = _resolve_repo_path(admin_report_path)
    build_dir = _resolve_repo_path(build_dir)
    markdown_report_dir = _resolve_repo_path(markdown_report_dir)
    renderer = progress or ProgressBar(False)
    started_wall = datetime.now(timezone.utc)
    started = time.perf_counter()
    renderer.update(2, "입력 설정과 콘텐츠 스냅샷 확인 중")
    config_hash = _sha256_file(config_path)
    config = _load_json_object(config_path)
    previous_bank = _load_previous_question_bank(bank_path)
    elements = load_elements(elements_path)
    fingerprint = content_fingerprint(elements)
    assignments, split_manifest = build_split(elements, config)
    _atomic_json(split_path, split_manifest)

    renderer.update(10, "검토된 사실 레코드 정규화 중", "135개 요소")
    facts, questions = build_facts_and_questions(elements, assignments)
    build_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(build_dir / "facts.jsonl", (asdict(item) for item in facts))

    renderer.update(23, "질문과 전체 오답 후보 생성 중", "405개 문항")
    weak_profiles = config.get("weakSupervisionProfiles")
    if not isinstance(weak_profiles, list) or not all(
        isinstance(item, Mapping) for item in weak_profiles
    ):
        raise ConceptModelError("weakSupervisionProfiles is missing from model config")
    fusion_baseline = config.get("fusionBaseline")
    if not isinstance(fusion_baseline, Mapping) or fusion_baseline.get("method") != "reciprocal_rank_fusion":
        raise ConceptModelError("fusionBaseline must configure reciprocal_rank_fusion")
    rrf_k = int(fusion_baseline.get("rrfK", 0))
    canonical_weak_profile = str(config.get("canonicalWeakSupervisionProfile", ""))
    context, weak_sensitivity = weak_supervision_sensitivity(
        elements,
        questions,
        weak_profiles,
        canonical_weak_profile,
        rrf_k,
    )
    human_labels = load_human_labels(labels_path)
    owner_question_decisions, owner_batch_decisions = load_owner_decisions(
        owner_decisions_path
    )
    question_edits = load_question_edits(question_edits_path)
    candidate_count = sum(
        len(eligible_candidate_indices(elements, question.element_index))
        for question in questions
    )
    _write_jsonl(
        build_dir / "candidates.jsonl",
        (
            {
                "questionId": question.question_id,
                "candidateElementId": elements[candidate_index].element_id,
                "split": question.split,
                "weakRelevance": int(context.weak_relevance[question_index, candidate_index]),
                "labelSource": "reviewer"
                if (question.question_id, elements[candidate_index].element_id) in human_labels
                else "weak_rule",
            }
            for question_index, question in enumerate(questions)
            for candidate_index in eligible_candidate_indices(
                elements, question.element_index
            )
        ),
    )

    candidate_specs = config.get("embeddingCandidates")
    if not isinstance(candidate_specs, list):
        raise ConceptModelError("embeddingCandidates is missing from model config")
    specs_by_id = {
        str(item.get("id")): item for item in candidate_specs if isinstance(item, Mapping)
    }
    unknown_embeddings = sorted(set(embedding_ids) - set(specs_by_id))
    if unknown_embeddings:
        raise ConceptModelError(f"Unknown embedding candidates: {unknown_embeddings}")
    embeddings = [baseline_embedding_run(context)]
    selected_specs = [specs_by_id[item] for item in embedding_ids if item != "tfidf-word-char"]
    for index, spec in enumerate(selected_specs, start=1):
        percent = 38 + int((index - 1) / max(1, len(selected_specs)) * 20)
        renderer.update(
            percent,
            "로컬 임베딩 후보 실행 중",
            f"{index}/{len(selected_specs)} {spec.get('id')}",
        )
        embeddings.append(
            run_sentence_transformer(
                spec,
                context,
                build_dir / "embeddings",
                device,
            )
        )
    completed_embeddings = [item for item in embeddings if item.status == "completed"]
    if not completed_embeddings:
        raise ConceptModelError("No embedding candidate completed")

    renderer.update(61, "오답 랭커·가중치 그리드 탐색 중", f"{len(completed_embeddings)}개 검색 후보")
    retrieval_limit = int(config.get("retrievalLimit", 20))
    max_pairs = int(config.get("pairwiseMaxPairsPerQuestion", 80))
    seed = int(config.get("splitSeed", 0))
    retrieval_profiles = config.get("retrievalProfiles")
    if not isinstance(retrieval_profiles, list) or not all(
        isinstance(item, Mapping) for item in retrieval_profiles
    ):
        raise ConceptModelError("retrievalProfiles is missing from model config")
    pairwise_c_values = [float(value) for value in config.get("pairwiseLogisticCValues", [1.0])]
    if not pairwise_c_values or any(value <= 0 for value in pairwise_c_values):
        raise ConceptModelError("pairwiseLogisticCValues must contain positive values")
    xgboost_grid = config.get("xgboostGrid", [])
    if not isinstance(xgboost_grid, list) or not all(
        isinstance(item, Mapping) for item in xgboost_grid
    ):
        raise ConceptModelError("xgboostGrid must be a list of objects")
    run_results: list[dict[str, Any]] = []
    ranking_outputs: dict[tuple[str, str, str], list[list[tuple[int, float]]]] = {}
    retrieved_outputs: dict[tuple[str, str], list[list[int]]] = {}
    for embedding in completed_embeddings:
        compatible_profiles = [
            profile
            for profile in retrieval_profiles
            if embedding.query_candidate_similarity is not None
            or (
                float(profile.get("questionSemantic", 0.0)) == 0.0
                and float(profile.get("answerSemantic", 0.0)) == 0.0
            )
        ]
        for retrieval_profile in compatible_profiles:
            retrieval_id = str(retrieval_profile.get("id", ""))
            if not retrieval_id:
                raise ConceptModelError("Every retrieval profile needs an id")
            retrieved = retrieve_candidates(
                context,
                embedding,
                retrieval_limit,
                retrieval_profile,
                rrf_k,
            )
            retrieved_outputs[(embedding.candidate_id, retrieval_id)] = retrieved
            ranker_variants: list[tuple[str, str, dict[str, Any]]] = []
            if "pairwise-logistic" in ranker_ids:
                ranker_variants.extend(
                    (
                        "pairwise-logistic",
                        f"pairwise-logistic-c{str(c_value).replace('.', 'p')}",
                        {"C": c_value},
                    )
                    for c_value in pairwise_c_values
                )
            if "xgboost" in ranker_ids:
                ranker_variants.extend(
                    (
                        "xgboost",
                        f"xgboost-{str(parameters.get('id', 'default'))}",
                        dict(parameters),
                    )
                    for parameters in xgboost_grid
                )
            for ranker_family, ranker_variant, hyperparameters in ranker_variants:
                train_started = time.perf_counter()
                try:
                    if ranker_family == "pairwise-logistic":
                        model = train_pairwise_logistic(
                            context,
                            embedding,
                            retrieved,
                            human_labels,
                            seed,
                            max_pairs,
                            float(hyperparameters["C"]),
                        )
                    elif ranker_family == "xgboost":
                        model = train_xgboost_ranker(
                            context,
                            embedding,
                            retrieved,
                            human_labels,
                            seed,
                            hyperparameters,
                        )
                    else:
                        raise ConceptModelError(f"Unsupported ranker: {ranker_family}")
                    ranked = rank_candidates(context, embedding, retrieved, model)
                    validation = evaluate_ranking(
                        context, retrieved, ranked, human_labels, "validation"
                    )
                    artifact_path, artifact_sha, artifact_size = _model_artifact(
                        build_dir,
                        embedding.candidate_id,
                        retrieval_id,
                        ranker_variant,
                        model,
                    )
                    key = (embedding.candidate_id, retrieval_id, ranker_variant)
                    ranking_outputs[key] = ranked
                    run_results.append(
                        {
                            "embeddingId": embedding.candidate_id,
                            "retrievalProfileId": retrieval_id,
                            "rankerFamily": ranker_family,
                            "rankerId": ranker_variant,
                            "hyperparameters": hyperparameters,
                            "status": "completed",
                            "trainingSeconds": round(time.perf_counter() - train_started, 3),
                            "validation": validation,
                            "test": None,
                            "testEvaluated": False,
                            "modelArtifact": _report_path(artifact_path),
                            "modelSha256": artifact_sha,
                            "modelBytes": artifact_size,
                            "error": None,
                        }
                    )
                except Exception as error:
                    run_results.append(
                        {
                            "embeddingId": embedding.candidate_id,
                            "retrievalProfileId": retrieval_id,
                            "rankerFamily": ranker_family,
                            "rankerId": ranker_variant,
                            "hyperparameters": hyperparameters,
                            "status": "failed",
                            "trainingSeconds": round(time.perf_counter() - train_started, 3),
                            "validation": None,
                            "test": None,
                            "testEvaluated": False,
                            "modelArtifact": None,
                            "modelSha256": None,
                            "modelBytes": None,
                            "error": f"{type(error).__name__}: {str(error)[:500]}",
                        }
                    )
    successful = [item for item in run_results if item["status"] == "completed"]
    if not successful:
        first_failures = "; ".join(
            (
                f"{item['embeddingId']}/{item['retrievalProfileId']}/{item['rankerId']}: "
                f"{item['error']}"
            )
            for item in run_results[:3]
        )
        raise ConceptModelError(
            "Every ranker training run failed"
            + (f". First failures: {first_failures}" if first_failures else "")
        )

    tolerance = float(config.get("embeddingSelectionTolerance", 0.01))
    selected = select_validation_run(
        successful,
        [item for item in candidate_specs if isinstance(item, Mapping)],
        retrieval_profiles,
        tolerance,
    )
    selected_key = (
        str(selected["embeddingId"]),
        str(selected["retrievalProfileId"]),
        str(selected["rankerId"]),
    )
    selected_ranked = ranking_outputs[selected_key]
    selected_retrieved = retrieved_outputs[(selected_key[0], selected_key[1])]
    selected_test = evaluate_ranking(
        context,
        selected_retrieved,
        selected_ranked,
        human_labels,
        "test",
    )
    selected["test"] = selected_test
    selected["testEvaluated"] = True

    renderer.update(84, "독립 분할 평가와 문항 안전성 검사 중")
    bank, safety = _question_bank(
        context,
        selected_ranked,
        str(config.get("modelVersion")),
        selected_key[0],
        selected_key[1],
        selected_key[2],
        fingerprint,
        str(split_manifest["splitSha256"]),
        human_labels,
    )
    edited_question_count = _apply_question_edits(bank, question_edits)
    if edited_question_count:
        safety = _recompute_question_safety(bank, context)
    review_config = config.get("automatedReview")
    if not isinstance(review_config, Mapping):
        raise ConceptModelError("automatedReview is missing from model config")
    automated_review = automated_review_question_bank(
        bank=bank,
        context=context,
        selected_ranked=selected_ranked,
        ranking_outputs=ranking_outputs,
        previous_bank=previous_bank,
        review_config=review_config,
        owner_question_decisions=owner_question_decisions,
        owner_batch_decisions=owner_batch_decisions,
    )
    serialized_once = _stable_json_bytes(bank)
    serialized_twice = _stable_json_bytes(json.loads(serialized_once.decode("utf-8")))
    deterministic_bank = serialized_once == serialized_twice
    human_coverage, covered_test_questions, total_test_questions = _human_test_coverage(
        questions, human_labels
    )
    selected_human_labels = []
    for question_index, question in enumerate(questions):
        if question.split != "test":
            continue
        for candidate_index, _ in selected_ranked[question_index][:4]:
            label = human_labels.get(
                (question.question_id, elements[candidate_index].element_id)
            )
            if label is not None:
                selected_human_labels.append(label.relevance)
    human_approval = (
        round(sum(value >= 2 for value in selected_human_labels) / len(selected_human_labels), 6)
        if selected_human_labels
        else 0.0
    )
    gates_config = config.get("qualityGates")
    if not isinstance(gates_config, Mapping):
        raise ConceptModelError("qualityGates is missing from model config")
    test_metrics = selected["test"]
    question_counts = Counter(item.element_id for item in questions)
    minimum_questions = min(question_counts.values())
    gates = [
        _gate(
            "retrieval-recall-at-20",
            "test Recall@20",
            test_metrics["retrievalRecallAt20"],
            float(gates_config["minimumRetrievalRecallAt20"]),
            test_metrics["retrievalRecallAt20"] >= float(gates_config["minimumRetrievalRecallAt20"]),
        ),
        _gate(
            "test-ndcg-at-4",
            "test NDCG@4",
            test_metrics["ndcgAt4"],
            float(gates_config["minimumTestNdcgAt4"]),
            test_metrics["ndcgAt4"] >= float(gates_config["minimumTestNdcgAt4"]),
        ),
        _gate(
            "test-precision-at-4",
            "test Precision@4",
            test_metrics["precisionAt4"],
            float(gates_config["minimumTestPrecisionAt4"]),
            test_metrics["precisionAt4"] >= float(gates_config["minimumTestPrecisionAt4"]),
        ),
        _gate(
            "automated-review-blocks",
            "자동 검수 차단 문항 수",
            int(automated_review["blockedCount"]),
            0,
            int(automated_review["blockedCount"]) == 0,
        ),
        _gate(
            "owner-exception-review",
            "Owner 미확인 예외 문항 수",
            int(automated_review["needsOwnerReviewCount"]),
            0,
            int(automated_review["needsOwnerReviewCount"]) == 0,
        ),
        _gate(
            "owner-batch-approval",
            "Owner 자동검수 배치 승인",
            bool(automated_review["ownerBatchApproved"]),
            True,
            bool(automated_review["ownerBatchApproved"]),
        ),
        _gate(
            "questions-per-element",
            "요소별 생성 문항 수",
            minimum_questions,
            int(gates_config["minimumQuestionsPerElement"]),
            minimum_questions >= int(gates_config["minimumQuestionsPerElement"]),
        ),
        _gate(
            "answer-leak",
            "정답 누출 건수",
            safety["answerLeakCount"],
            int(gates_config["maximumAnswerLeakCount"]),
            safety["answerLeakCount"] <= int(gates_config["maximumAnswerLeakCount"]),
        ),
        _gate(
            "duplicate-choice",
            "중복 선택지 건수",
            safety["duplicateChoiceCount"],
            int(gates_config["maximumDuplicateChoiceCount"]),
            safety["duplicateChoiceCount"] <= int(gates_config["maximumDuplicateChoiceCount"]),
        ),
        _gate(
            "ambiguous-question",
            "약한 오답 포함 문항 수",
            safety["ambiguousQuestionCount"],
            int(gates_config["maximumAmbiguousQuestionCount"]),
            safety["ambiguousQuestionCount"] <= int(gates_config["maximumAmbiguousQuestionCount"]),
        ),
        _gate(
            "deterministic-bank",
            "문항 은행 직렬화 재현성",
            deterministic_bank,
            bool(gates_config["requireDeterministicBank"]),
            deterministic_bank or not bool(gates_config["requireDeterministicBank"]),
        ),
    ]
    release_ready = bool(automated_review["ownerReviewComplete"]) and all(
        item["passed"] for item in gates
    )
    bank["releaseStatus"] = (
        "release_ready" if release_ready else "candidate"
    )
    bank.pop("bankSha256", None)
    bank["bankSha256"] = _sha256_bytes(_stable_json_bytes(bank))
    if write_question_bank:
        _atomic_json(bank_path, bank)
    finished_wall = datetime.now(timezone.utc)
    experiment_id = (
        f"cmq-{started_wall.strftime('%Y%m%d-%H%M%S')}-{config_hash[:8]}"
    )
    split_counts = Counter(assignments.values())
    question_split_counts = Counter(item.split for item in questions)
    report: dict[str, Any] = {
        "experimentId": experiment_id,
        "reportVersion": REPORT_VERSION,
        "status": "release_ready" if release_ready else "candidate",
        "releaseReady": release_ready,
        "releaseBlockReason": None
        if release_ready
        else "자동 검수 예외 확인 또는 Owner 배치 승인이 필요합니다.",
        "startedAt": started_wall.isoformat(),
        "finishedAt": finished_wall.isoformat(),
        "durationSeconds": round(time.perf_counter() - started, 3),
        "progress": {
            "stage": "completed",
            "percent": 100,
            "processed": len(questions),
            "total": len(questions),
            "message": "자동 검수와 예외 분류 완료",
        },
        "dataset": {
            "contentFingerprint": fingerprint,
            "configSha256": config_hash,
            "splitSha256": split_manifest["splitSha256"],
            "elementCount": len(elements),
            "factCount": len(facts),
            "questionCount": len(questions),
            "candidateCount": candidate_count,
            "elementSplits": {
                name: split_counts[name] for name in ("train", "validation", "test")
            },
            "questionSplits": {
                name: question_split_counts[name] for name in ("train", "validation", "test")
            },
        },
        "labels": {
            "weakLabelCount": candidate_count - len(human_labels),
            "humanLabelCount": len(human_labels),
            "humanLabelCompletion": round(len(human_labels) / candidate_count, 6),
            "humanTestCoverage": human_coverage,
            "coveredTestQuestionCount": covered_test_questions,
            "testQuestionCount": total_test_questions,
            "humanApprovalRate": human_approval,
            "metricWarning": "현재 test 점수는 약지도 규칙 재현도이며 교육 품질의 독립 성능이 아닙니다."
            if not human_labels
            else None,
        },
        "automatedReview": automated_review,
        "weightExperiments": {
            "weakSupervision": weak_sensitivity,
            "weakSupervisionProfiles": [dict(item) for item in weak_profiles],
            "fusionBaseline": dict(fusion_baseline),
            "retrievalProfiles": [dict(item) for item in retrieval_profiles],
            "retrievalProfileCount": len(retrieval_profiles),
            "pairwiseCValues": pairwise_c_values,
            "pairwiseReference": dict(config.get("pairwiseLogisticReference", {})),
            "xgboostGrid": [dict(item) for item in xgboost_grid],
            "selectionRule": "train으로 학습하고 validation NDCG@4로만 선택한 뒤 선택된 1개 구성에만 test를 실행",
        },
        "embeddings": [item.report_dict() for item in embeddings],
        "rankerRuns": run_results,
        "selection": {
            "embeddingId": selected_key[0],
            "retrievalProfileId": selected_key[1],
            "rankerId": selected_key[2],
            "rankerFamily": selected["rankerFamily"],
            "hyperparameters": selected["hyperparameters"],
            "validationNdcgAt4": selected["validation"]["ndcgAt4"],
            "selectionTolerance": tolerance,
            "reason": "최고 validation NDCG@4와 1%p 이내에서 임베딩·랭커 복잡도를 먼저 낮추고, 같은 비용군에서는 validation NDCG@4 최고 조합을 선택",
            "modelSha256": selected["modelSha256"],
            "modelBytes": selected["modelBytes"],
        },
        "evaluation": {
            "validation": selected["validation"],
            "test": selected["test"],
            "labelSource": "human_and_weak_rule" if human_labels else "weak_rule_bootstrap",
        },
        "safety": safety,
        "questionEditCount": edited_question_count,
        "qualityGates": gates,
        "artifacts": {
            "questionBank": _report_path(bank_path),
            "questionBankWritten": write_question_bank,
            "questionBankSha256": bank["bankSha256"],
            "split": _report_path(split_path),
            "facts": _report_path(build_dir / "facts.jsonl"),
            "candidates": _report_path(build_dir / "candidates.jsonl"),
            "ownerDecisions": _report_path(owner_decisions_path),
            "questionEdits": _report_path(question_edits_path),
            "markdownReport": _report_path(markdown_report_dir / f"{experiment_id}.md"),
            "markdownReportWritten": write_markdown_report,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scikitLearn": sklearn.__version__,
            "xgboost": _package_version("xgboost"),
            "sentenceTransformers": _package_version("sentence_transformers"),
            "externalLlmApiCalls": 0,
            "appRuntimeModelCalls": 0,
        },
        "methodReferences": list(config.get("methodReferences", [])),
    }
    report["reportSha256"] = _sha256_bytes(_stable_json_bytes(report))
    _atomic_json(build_dir / "latest-report.json", report)
    history: dict[str, Any] | None = None
    if write_admin_report:
        history = _append_admin_history(admin_report_path, report)
    if write_markdown_report:
        if history is None:
            existing: dict[str, Any] = {}
            if admin_report_path.exists():
                try:
                    loaded = json.loads(admin_report_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        existing = loaded
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    existing = {}
            raw_history = existing.get("experiments")
            previous = raw_history if isinstance(raw_history, list) else []
            merged = [
                item
                for item in previous
                if isinstance(item, dict) and item.get("experimentId") != experiment_id
            ]
            history = {
                "reportVersion": REPORT_VERSION,
                "latestExperimentId": experiment_id,
                "experiments": [report, *merged][:30],
            }
        write_markdown_history(markdown_report_dir, history)
    renderer.update(
        100,
        "개념형 모델링 실험 완료",
        "릴리스 가능" if release_ready else "자동 검수 완료 · Owner 확인 필요",
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--elements", type=Path, default=DEFAULT_ELEMENTS)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument(
        "--owner-decisions", type=Path, default=DEFAULT_OWNER_DECISIONS
    )
    parser.add_argument(
        "--question-edits", type=Path, default=DEFAULT_QUESTION_EDITS
    )
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--question-bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--admin-report", type=Path, default=DEFAULT_ADMIN_REPORT)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument(
        "--markdown-report-dir",
        type=Path,
        default=DEFAULT_MARKDOWN_REPORT_DIR,
    )
    parser.add_argument(
        "--embedding-model",
        action="append",
        default=[],
        help="Configured embedding candidate id; may be repeated",
    )
    parser.add_argument(
        "--all-embeddings",
        action="store_true",
        help="Run every configured Hugging Face embedding candidate",
    )
    parser.add_argument(
        "--ranker",
        choices=("pairwise-logistic", "xgboost", "all"),
        default="all",
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--write-question-bank", action="store_true")
    parser.add_argument("--write-admin-report", action="store_true")
    parser.add_argument("--write-markdown-report", action="store_true")
    parser.add_argument(
        "--refresh-reference-catalog",
        action="store_true",
        help="Update stored experiment reference metadata and Markdown without retraining",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    if args.refresh_reference_catalog:
        updated = refresh_reference_catalog(
            args.config,
            args.admin_report,
            args.markdown_report_dir,
        )
        print(json.dumps({"updatedExperiments": updated}, ensure_ascii=False))
        return 0
    config = _load_json_object(args.config)
    embedding_ids = list(args.embedding_model)
    if args.all_embeddings:
        configured = config.get("embeddingCandidates", [])
        embedding_ids = [
            str(item["id"])
            for item in configured
            if isinstance(item, Mapping) and item.get("provider") == "huggingface"
        ]
    rankers = (
        ("pairwise-logistic", "xgboost")
        if args.ranker == "all"
        else (args.ranker,)
    )
    report = run_experiment(
        config_path=args.config,
        elements_path=args.elements,
        labels_path=args.labels,
        owner_decisions_path=args.owner_decisions,
        question_edits_path=args.question_edits,
        split_path=args.split,
        bank_path=args.question_bank,
        admin_report_path=args.admin_report,
        build_dir=args.build_dir,
        markdown_report_dir=args.markdown_report_dir,
        embedding_ids=embedding_ids,
        ranker_ids=rankers,
        device=args.device,
        write_question_bank=args.write_question_bank,
        write_admin_report=args.write_admin_report,
        write_markdown_report=args.write_markdown_report or args.write_admin_report,
        progress=ProgressBar(not args.quiet),
    )
    print(
        json.dumps(
            {
                "experimentId": report["experimentId"],
                "status": report["status"],
                "releaseReady": report["releaseReady"],
                "selectedEmbedding": report["selection"]["embeddingId"],
                "selectedRetrievalProfile": report["selection"]["retrievalProfileId"],
                "selectedRanker": report["selection"]["rankerId"],
                "testNdcgAt4": report["evaluation"]["test"]["ndcgAt4"],
                "testPrecisionAt4": report["evaluation"]["test"]["precisionAt4"],
                "humanTestCoverage": report["labels"]["humanTestCoverage"],
                "externalLlmApiCalls": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConceptModelError, OSError, ValueError) as error:
        print(f"Concept-question modeling stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
