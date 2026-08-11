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
DEFAULT_SPLIT = ROOT / "content" / "model" / "concept-split.json"
DEFAULT_BANK = ROOT / "content" / "model" / "concept-question-bank.generated.json"
DEFAULT_ADMIN_REPORT = ROOT / "admin" / "data" / "concept-model-experiments.generated.json"
DEFAULT_BUILD_DIR = ROOT / "build" / "concept-model"
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


def _token_set(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(normalize_text(value))}


def eligible_candidate_indices(
    elements: Sequence[ElementRecord], answer_index: int
) -> list[int]:
    """Exclude the answer element and title aliases that would create two correct labels."""
    answer_key = normalized_key(elements[answer_index].title)
    return [
        index
        for index, element in enumerate(elements)
        if index != answer_index and normalized_key(element.title) != answer_key
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
        model = SentenceTransformer(
            model_id,
            revision=revision,
            trust_remote_code=bool(spec.get("trustRemoteCode", False)),
            cache_folder=str(model_cache),
            device=device,
        )
        query_prefix = str(spec.get("queryPrefix", ""))
        passage_prefix = str(spec.get("passagePrefix", ""))
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
    word_weight = float(retrieval_profile.get("word", -1.0))
    char_weight = float(retrieval_profile.get("char", -1.0))
    semantic_weight = float(retrieval_profile.get("semantic", -1.0))
    if min(word_weight, char_weight, semantic_weight) < 0 or not math.isclose(
        word_weight + char_weight + semantic_weight, 1.0, abs_tol=1e-6
    ):
        raise ConceptModelError(
            f"Retrieval profile {retrieval_profile.get('id')} weights must sum to 1"
        )
    return {"word": word_weight, "char": char_weight, "semantic": semantic_weight}


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
    if embedding.query_candidate_similarity is None and weights["semantic"] > 0:
        raise ConceptModelError("A semantic retrieval profile requires an embedding model")
    if rrf_k <= 0:
        raise ConceptModelError("RRF k must be positive")
    result: list[list[int]] = []
    for question_index, question in enumerate(context.questions):
        candidate_indices = eligible_candidate_indices(
            context.elements, question.element_index
        )
        signal_values: dict[str, dict[int, float]] = {
            "word": {
                index: float(context.question_word_similarity[question_index, index])
                for index in candidate_indices
            },
            "char": {
                index: float(context.question_char_similarity[question_index, index])
                for index in candidate_indices
            },
        }
        if embedding.query_candidate_similarity is not None:
            signal_values["semantic"] = {
                index: float(embedding.query_candidate_similarity[question_index, index])
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
) -> tuple[dict[str, Any], dict[str, int]]:
    questions: list[dict[str, Any]] = []
    answer_leaks = 0
    duplicate_choices = 0
    ambiguous_questions = 0
    for question_index, question in enumerate(context.questions):
        target = context.elements[question.element_index]
        selected: list[tuple[int, float]] = []
        seen_titles = {normalized_key(target.title)}
        for candidate_index, score in ranked[question_index]:
            title_key = normalized_key(context.elements[candidate_index].title)
            if not title_key or title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            selected.append((candidate_index, score))
            if len(selected) == 4:
                break
        if len(selected) != 4:
            raise ConceptModelError(
                f"{question.question_id} does not have four distinct distractors"
            )
        if any(
            _effective_relevance(context, question_index, candidate_index, human_labels) < 2
            for candidate_index, _ in selected
        ):
            ambiguous_questions += 1

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
        choice_keys = [normalized_key(choice["text"]) for choice in choices]
        if len(set(choice_keys)) != 5:
            duplicate_choices += 1
        correct_key = normalized_key(target.title)
        if any(
            normalized_key(choice["text"]) == correct_key and not choice["isCorrect"]
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
                "reviewStatus": "reviewed" if human_labels else "bootstrap",
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
    }
    return bank, safety


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


def run_experiment(
    *,
    config_path: Path = DEFAULT_CONFIG,
    elements_path: Path = DEFAULT_ELEMENTS,
    labels_path: Path = DEFAULT_LABELS,
    split_path: Path = DEFAULT_SPLIT,
    bank_path: Path = DEFAULT_BANK,
    admin_report_path: Path = DEFAULT_ADMIN_REPORT,
    build_dir: Path = DEFAULT_BUILD_DIR,
    embedding_ids: Sequence[str] = (),
    ranker_ids: Sequence[str] = ("pairwise-logistic",),
    device: str = "cpu",
    write_question_bank: bool = False,
    write_admin_report: bool = False,
    progress: ProgressBar | None = None,
) -> dict[str, Any]:
    renderer = progress or ProgressBar(False)
    started_wall = datetime.now(timezone.utc)
    started = time.perf_counter()
    renderer.update(2, "입력 설정과 콘텐츠 스냅샷 확인 중")
    config = _load_json_object(config_path)
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
            or float(profile.get("semantic", 0.0)) == 0.0
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
                            "modelArtifact": str(artifact_path.relative_to(ROOT)).replace("\\", "/"),
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
        raise ConceptModelError("Every ranker training run failed")

    best_ndcg = max(float(item["validation"]["ndcgAt4"]) for item in successful)
    tolerance = float(config.get("embeddingSelectionTolerance", 0.01))
    eligible = [
        item
        for item in successful
        if best_ndcg - float(item["validation"]["ndcgAt4"]) <= tolerance
    ]
    embedding_priority = {
        str(item.get("id")): int(item.get("priority", 999))
        for item in candidate_specs
        if isinstance(item, Mapping)
    }
    retrieval_priority = {
        str(item.get("id")): index for index, item in enumerate(retrieval_profiles)
    }
    selected = min(
        eligible,
        key=lambda item: (
            embedding_priority.get(str(item["embeddingId"]), 999),
            0 if item["rankerFamily"] == "pairwise-logistic" else 1,
            retrieval_priority.get(str(item["retrievalProfileId"]), 999),
            int(item["modelBytes"] or 0),
            str(item["embeddingId"]),
        ),
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
    serialized_once = _stable_json_bytes(bank)
    serialized_twice = _stable_json_bytes(json.loads(serialized_once.decode("utf-8")))
    deterministic_bank = serialized_once == serialized_twice
    if write_question_bank:
        _atomic_json(bank_path, bank)

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
            "independent-human-test",
            "독립 사람 test 라벨 커버리지",
            human_coverage,
            float(gates_config["minimumHumanTestCoverage"]),
            human_coverage >= float(gates_config["minimumHumanTestCoverage"]),
        ),
        _gate(
            "human-approval",
            "사람 최종 승인률",
            human_approval,
            float(gates_config["minimumHumanApprovalRate"]),
            human_approval >= float(gates_config["minimumHumanApprovalRate"]),
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
    release_ready = bool(human_labels) and all(item["passed"] for item in gates)
    finished_wall = datetime.now(timezone.utc)
    config_hash = _sha256_file(config_path)
    experiment_id = (
        f"cmq-{started_wall.strftime('%Y%m%d-%H%M%S')}-{config_hash[:8]}"
    )
    split_counts = Counter(assignments.values())
    question_split_counts = Counter(item.split for item in questions)
    report: dict[str, Any] = {
        "experimentId": experiment_id,
        "reportVersion": REPORT_VERSION,
        "status": "release_ready" if release_ready else "bootstrap" if not human_labels else "candidate",
        "releaseReady": release_ready,
        "releaseBlockReason": None
        if release_ready
        else "독립 사람 test 라벨과 최종 검토가 필요합니다."
        if not human_labels
        else "하나 이상의 릴리스 품질 게이트가 미통과입니다.",
        "startedAt": started_wall.isoformat(),
        "finishedAt": finished_wall.isoformat(),
        "durationSeconds": round(time.perf_counter() - started, 3),
        "progress": {
            "stage": "completed",
            "percent": 100,
            "processed": len(questions),
            "total": len(questions),
            "message": "bootstrap 평가 완료" if not human_labels else "사람 라벨 평가 완료",
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
        "weightExperiments": {
            "weakSupervision": weak_sensitivity,
            "fusionBaseline": dict(fusion_baseline),
            "retrievalProfileCount": len(retrieval_profiles),
            "pairwiseCValues": pairwise_c_values,
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
            "reason": "최고 validation NDCG@4와 1%p 이내인 후보 중 더 단순하고 작은 구성을 선택",
            "modelSha256": selected["modelSha256"],
            "modelBytes": selected["modelBytes"],
        },
        "evaluation": {
            "validation": selected["validation"],
            "test": selected["test"],
            "labelSource": "human_and_weak_rule" if human_labels else "weak_rule_bootstrap",
        },
        "safety": safety,
        "qualityGates": gates,
        "artifacts": {
            "questionBank": str(bank_path.relative_to(ROOT)).replace("\\", "/"),
            "questionBankWritten": write_question_bank,
            "questionBankSha256": bank["bankSha256"],
            "split": str(split_path.relative_to(ROOT)).replace("\\", "/"),
            "facts": str((build_dir / "facts.jsonl").relative_to(ROOT)).replace("\\", "/"),
            "candidates": str((build_dir / "candidates.jsonl").relative_to(ROOT)).replace("\\", "/"),
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
    _atomic_json(build_dir / "latest-report.json", report)
    if write_admin_report:
        _append_admin_history(admin_report_path, report)
    renderer.update(
        100,
        "개념형 모델링 실험 완료",
        "릴리스 가능" if release_ready else "bootstrap · 사람 test 필요",
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--elements", type=Path, default=DEFAULT_ELEMENTS)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--question-bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--admin-report", type=Path, default=DEFAULT_ADMIN_REPORT)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
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
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
        split_path=args.split,
        bank_path=args.question_bank,
        admin_report_path=args.admin_report,
        build_dir=args.build_dir,
        embedding_ids=embedding_ids,
        ranker_ids=rankers,
        device=args.device,
        write_question_bank=args.write_question_bank,
        write_admin_report=args.write_admin_report,
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
