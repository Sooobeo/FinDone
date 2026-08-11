#!/usr/bin/env python3
"""Compile evidence-grounded FinDone app-content candidates for final review.

The worker consumes immutable source fragments and the current normalized
authoring baseline.  A checked-in, deterministic local ruleset maps explicitly
structured JSON, CSV/TSV, and labelled fields without calling an LLM API.
Every changed field is checked against source-fragment IDs and the same
validator used by Admin.  Ambiguous prose and conflicting values are preserved
as-is for a human or a later checked-in rule update.

Generated candidates remain isolated from authoring tables. Only the owner's
single final-review RPC can apply them and queue a release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import admin_validation_worker as content_validator
from tools import local_content_model
from tools.admin_import_supabase import normalize_supabase_url, resolve_supabase_url


ENQUEUE_RPC = "enqueue_ready_content_generation"
CLAIM_RPC = "claim_content_generation_batch"
FRAGMENTS_RPC = "get_content_generation_fragments"
PROGRESS_RPC = "update_content_generation_progress"
COMPLETE_RPC = "complete_content_generation_batch"
FAIL_RPC = "fail_content_generation_batch"

PROMPT_VERSION = "findone-local-schema-v1"
MAX_HTTP_JSON_BYTES = 32 * 1024 * 1024
MAX_FRAGMENT_CONTEXT_CHARS = 24_000
MAX_FRAGMENT_EXCERPT_CHARS = 4_000
MAX_FRAGMENTS_PER_ELEMENT = 16
MAX_REPAIR_ATTEMPTS = 2
MAX_FAILURE_DETAILS = 20
WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")

ENTITY_FIELDS = local_content_model.ENTITY_FIELDS


class GenerationWorkerError(RuntimeError):
    """Raised when a generation batch cannot be processed safely."""


class CandidateValidationError(GenerationWorkerError):
    def __init__(self, errors: Sequence[str], model_runs: Sequence[dict[str, Any]]) -> None:
        super().__init__("model output remained invalid after automatic repair")
        self.errors = list(errors)
        self.model_runs = list(model_runs)


@dataclass(frozen=True)
class ModelCallResult:
    payload: dict[str, Any]
    response_id: str | None
    input_sha256: str
    output_sha256: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


@dataclass(frozen=True)
class ElementContext:
    element_id: str
    element: dict[str, Any]
    concept: dict[str, Any]
    formula: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CandidateBundle:
    items: tuple[dict[str, Any], ...]
    evidence: tuple[dict[str, Any], ...]
    model_runs: tuple[dict[str, Any], ...]


class ContentModel(Protocol):
    def generate(
        self,
        document: Mapping[str, Any],
        *,
        run_kind: str,
        run_number: int,
        idempotency_key: str,
    ) -> ModelCallResult: ...


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _rpc_object(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1 and isinstance(value[0], dict):
            return value[0]
    if isinstance(value, dict):
        return value
    raise GenerationWorkerError(f"{label} RPC returned an unexpected response")


def _in_filter(values: Sequence[str]) -> str:
    if not values:
        raise GenerationWorkerError("an empty PostgREST in filter is not allowed")
    for value in values:
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
            raise GenerationWorkerError("unsafe identifier in PostgREST filter")
    return "in.(" + ",".join(values) + ")"


def _uuid(value: Any, label: str) -> str:
    try:
        result = str(uuid.UUID(str(value)))
    except (ValueError, AttributeError) as error:
        raise GenerationWorkerError(f"{label} is not a canonical UUID") from error
    if result != str(value).lower():
        raise GenerationWorkerError(f"{label} is not a canonical UUID")
    return result


class SupabaseGenerationClient:
    _ALLOWED_RPCS = {
        ENQUEUE_RPC,
        CLAIM_RPC,
        FRAGMENTS_RPC,
        PROGRESS_RPC,
        COMPLETE_RPC,
        FAIL_RPC,
    }
    _ALLOWED_TABLES = {
        "content_generation_batch_sources",
        "sources",
        "source_element_candidates",
        "element_sources",
        "elements",
        "concepts",
        "formulas",
    }

    def __init__(self, base_url: str, secret_key: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = normalize_supabase_url(base_url)
        self.secret_key = secret_key.strip()
        if not self.secret_key:
            raise GenerationWorkerError("SUPABASE_SECRET_KEY is missing")
        if timeout_seconds < 1 or timeout_seconds > 300:
            raise GenerationWorkerError("Supabase timeout must be between 1 and 300 seconds")
        self.timeout_seconds = timeout_seconds
        self.ssl_context = ssl.create_default_context()

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        max_bytes: int = MAX_HTTP_JSON_BYTES,
    ) -> bytes:
        headers = {"apikey": self.secret_key, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds, context=self.ssl_context
            ) as response:
                result = response.read(max_bytes + 1)
        except urllib.error.HTTPError as error:
            response_body = error.read(4096).decode("utf-8", errors="replace")
            raise GenerationWorkerError(
                f"Supabase {method} {path.split('?', 1)[0]} failed with HTTP "
                f"{error.code}: {response_body[:1000]}"
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise GenerationWorkerError("Could not reach Supabase") from error
        if len(result) > max_bytes:
            raise GenerationWorkerError("Supabase response exceeded its safety limit")
        return result

    def rpc(self, name: str, payload: Mapping[str, Any]) -> Any:
        if name not in self._ALLOWED_RPCS:
            raise GenerationWorkerError("Unsupported content-generation RPC")
        body = canonical_json_bytes(payload)
        if len(body) > 24 * 1024 * 1024:
            raise GenerationWorkerError("Generation RPC payload exceeded its safety limit")
        raw = self._request(
            "POST",
            f"/rest/v1/rpc/{name}",
            body=body,
            max_bytes=MAX_HTTP_JSON_BYTES,
        )
        try:
            return json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GenerationWorkerError(f"{name} returned invalid JSON") from error

    def select(
        self,
        table: str,
        *,
        columns: Sequence[str],
        filters: Mapping[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        max_bytes: int = MAX_HTTP_JSON_BYTES,
    ) -> list[dict[str, Any]]:
        if table not in self._ALLOWED_TABLES:
            raise GenerationWorkerError("Unsupported content-generation table read")
        query: dict[str, str] = {"select": ",".join(columns)}
        query.update(filters or {})
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = str(limit)
        raw = self._request(
            "GET",
            f"/rest/v1/{table}?{urllib.parse.urlencode(query)}",
            max_bytes=max_bytes,
        )
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GenerationWorkerError(f"{table} returned invalid JSON") from error
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise GenerationWorkerError(f"{table} returned an unexpected response")
        return value


class LocalRulesContentModel:
    """Checked-in ruleset adapter implementing the worker's model protocol."""

    def __init__(self, config_path: Path = local_content_model.DEFAULT_MODEL_CONFIG) -> None:
        self.config_path = config_path.resolve()
        self.config = local_content_model.load_model_config(self.config_path)
        self.model_name = str(self.config["modelVersion"])

    def generate(
        self,
        document: Mapping[str, Any],
        *,
        run_kind: str,
        run_number: int,
        idempotency_key: str,
    ) -> ModelCallResult:
        del run_number
        input_bytes = canonical_json_bytes(document)
        started = time.monotonic()
        payload = local_content_model.transform_document(document, self.config)
        repair = document.get("repair")
        if run_kind == "repair" and isinstance(repair, Mapping):
            previous = repair.get("previousCandidate")
            errors = repair.get("validationErrors")
            if isinstance(previous, Mapping) and isinstance(errors, list):
                payload = local_content_model.repair_candidate(
                    document,
                    previous,
                    [str(error) for error in errors],
                )
        output_bytes = canonical_json_bytes(payload)
        return ModelCallResult(
            payload=payload,
            response_id=f"local:{idempotency_key[:18]}",
            input_sha256=sha256_bytes(input_bytes),
            output_sha256=sha256_bytes(output_bytes),
            input_tokens=0,
            output_tokens=0,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        )


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(value)}


def _baseline_text(element: Mapping[str, Any], concept: Mapping[str, Any], formula: Mapping[str, Any]) -> str:
    values: list[str] = []
    for row in (element, concept, formula):
        for value in row.values():
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.append(json.dumps(value, ensure_ascii=False))
    return "\n".join(values)


def _select_evidence(
    fragments: Sequence[Mapping[str, Any]],
    baseline_text: str,
    version_scores: Mapping[str, float],
) -> tuple[dict[str, Any], ...]:
    baseline_terms = _tokens(baseline_text)
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for fragment in fragments:
        text_value = str(fragment.get("content_excerpt", ""))[:MAX_FRAGMENT_EXCERPT_CHARS]
        if not text_value.strip():
            continue
        terms = _tokens(text_value)
        overlap = len(baseline_terms & terms) / max(1, min(len(baseline_terms), 80))
        version_id = str(fragment.get("source_version_id", ""))
        kind_bonus = 0.06 if fragment.get("fragment_kind") in {"formula", "table"} else 0.0
        score = float(version_scores.get(version_id, 0.0)) + min(0.5, overlap) + kind_bonus
        fragment_id = str(fragment.get("source_fragment_id", ""))
        ranked.append((score, fragment_id, {**fragment, "content_excerpt": text_value}))
    ranked.sort(key=lambda item: (-item[0], item[1]))

    selected: list[dict[str, Any]] = []
    total_chars = 0
    for _, _, fragment in ranked:
        excerpt = str(fragment["content_excerpt"])
        if selected and total_chars + len(excerpt) > MAX_FRAGMENT_CONTEXT_CHARS:
            continue
        selected.append(fragment)
        total_chars += len(excerpt)
        if len(selected) >= MAX_FRAGMENTS_PER_ELEMENT or total_chars >= MAX_FRAGMENT_CONTEXT_CHARS:
            break
    return tuple(selected)


def load_element_contexts(
    client: SupabaseGenerationClient,
    batch_id: str,
    worker_id: str,
    max_elements: int,
) -> list[ElementContext]:
    batch_sources = client.select(
        "content_generation_batch_sources",
        columns=("source_version_id", "source_id"),
        filters={"batch_id": f"eq.{batch_id}"},
        order="source_id.asc",
        limit=100,
    )
    if not batch_sources:
        raise GenerationWorkerError("generation batch contains no sources")
    version_ids = [str(row["source_version_id"]) for row in batch_sources]
    source_ids = [str(row["source_id"]) for row in batch_sources]
    source_by_version = {str(row["source_version_id"]): str(row["source_id"]) for row in batch_sources}

    candidates = client.select(
        "source_element_candidates",
        columns=("source_version_id", "element_id", "rank", "score", "matched_terms"),
        filters={"source_version_id": _in_filter(version_ids)},
        order="source_version_id.asc,rank.asc",
        limit=2500,
    )
    links = client.select(
        "element_sources",
        columns=("source_id", "element_id"),
        filters={"source_id": _in_filter(source_ids)},
        limit=5000,
    )
    sources = client.select(
        "sources",
        columns=("source_id", "label", "locator", "source_type"),
        filters={"source_id": _in_filter(source_ids)},
        limit=100,
    )
    source_metadata = {str(row["source_id"]): row for row in sources}

    version_scores_by_element: dict[str, dict[str, float]] = defaultdict(dict)
    element_priority: dict[str, float] = defaultdict(float)
    for row in candidates:
        rank = int(row.get("rank", 99))
        score = float(row.get("score", 0.0))
        if rank > 5 and score < 0.20:
            continue
        element_id = str(row.get("element_id", ""))
        version_id = str(row.get("source_version_id", ""))
        if not element_id or not version_id:
            continue
        version_scores_by_element[element_id][version_id] = max(
            score, version_scores_by_element[element_id].get(version_id, 0.0)
        )
        element_priority[element_id] = max(element_priority[element_id], score)

    versions_by_source: dict[str, list[str]] = defaultdict(list)
    for version_id, source_id in source_by_version.items():
        versions_by_source[source_id].append(version_id)
    for row in links:
        element_id = str(row.get("element_id", ""))
        for version_id in versions_by_source.get(str(row.get("source_id", "")), []):
            version_scores_by_element[element_id][version_id] = max(
                1.0, version_scores_by_element[element_id].get(version_id, 0.0)
            )
            element_priority[element_id] = max(element_priority[element_id], 1.0)

    element_ids = sorted(
        version_scores_by_element,
        key=lambda value: (-element_priority[value], value),
    )[:max_elements]
    if not element_ids:
        return []
    element_filter = _in_filter(element_ids)
    elements = client.select(
        "elements",
        columns=(
            "element_id", "domain_id", "element_number", "title", "topic_name",
            "subtopic_name", "mode", "core_relation", "scope_notes", "source_label",
            "source_locator", "spec_section_locator", "display_order", "is_active",
        ),
        filters={"element_id": element_filter},
        limit=max_elements,
    )
    concepts = client.select(
        "concepts",
        columns=(
            "concept_id", "element_id", "title", "definition_markdown",
            "intuition_markdown", "learning_notes_markdown", "checklist_markdown",
            "glossary_terms",
        ),
        filters={"element_id": element_filter},
        limit=max_elements,
    )
    formulas = client.select(
        "formulas",
        columns=(
            "formula_id", "element_id", "formula_key", "title", "expression_markdown",
            "assumptions_markdown", "notes_markdown", "variables", "display_order", "is_primary",
        ),
        filters={"element_id": element_filter, "is_primary": "eq.true"},
        limit=max_elements,
    )
    element_rows = {str(row["element_id"]): row for row in elements}
    concept_rows = {str(row["element_id"]): row for row in concepts}
    formula_rows = {str(row["element_id"]): row for row in formulas}

    raw_fragments = client.rpc(
        FRAGMENTS_RPC,
        {
            "p_batch_id": batch_id,
            "p_worker_id": worker_id,
            "p_limit_per_source": 120,
        },
    )
    if not isinstance(raw_fragments, list) or not all(isinstance(row, dict) for row in raw_fragments):
        raise GenerationWorkerError("generation fragment RPC returned an unexpected response")
    fragments_by_version: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_fragments:
        version_id = str(row.get("source_version_id", ""))
        source_id = source_by_version.get(version_id, str(row.get("source_id", "")))
        metadata = source_metadata.get(source_id, {})
        fragments_by_version[version_id].append(
            {
                **row,
                "source_id": source_id,
                "source_label": metadata.get("label", source_id),
                "source_locator": metadata.get("locator", ""),
            }
        )

    contexts: list[ElementContext] = []
    for element_id in element_ids:
        element = element_rows.get(element_id)
        concept = concept_rows.get(element_id)
        formula = formula_rows.get(element_id)
        if element is None or concept is None or formula is None:
            raise GenerationWorkerError(f"authoring baseline is incomplete for {element_id}")
        associated: list[dict[str, Any]] = []
        for version_id in version_scores_by_element[element_id]:
            associated.extend(fragments_by_version.get(version_id, []))
        evidence = _select_evidence(
            associated,
            _baseline_text(element, concept, formula),
            version_scores_by_element[element_id],
        )
        if evidence:
            contexts.append(
                ElementContext(
                    element_id=element_id,
                    element=dict(element),
                    concept=dict(concept),
                    formula=dict(formula),
                    evidence=evidence,
                )
            )
    return contexts


def model_document(context: ElementContext) -> dict[str, Any]:
    return {
        "task": "Map only explicit structured source fields with the checked-in local ruleset and preserve every unsupported baseline field.",
        "elementId": context.element_id,
        "baseline": {
            "element": {field: context.element[field] for field in ENTITY_FIELDS["element"]},
            "concept": {field: context.concept[field] for field in ENTITY_FIELDS["concept"]},
            "formula": {field: context.formula[field] for field in ENTITY_FIELDS["formula"]},
        },
        "sourceEvidence": [
            {
                "sourceFragmentId": fragment["source_fragment_id"],
                "sourceId": fragment.get("source_id", ""),
                "sourceLabel": fragment.get("source_label", ""),
                "sourceLocator": fragment.get("source_locator", ""),
                "fragmentKind": fragment.get("fragment_kind", "text"),
                "fragmentLocator": fragment.get("locator", {}),
                "text": fragment.get("content_excerpt", ""),
            }
            for fragment in context.evidence
        ],
    }


def _candidate_shape_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_top = {
        "element", "concept", "formula", "evidence",
        "confidence", "risk_level", "change_summary",
    }
    if set(payload) != expected_top:
        errors.append("top-level fields do not match the candidate contract")
    for entity_type, fields in ENTITY_FIELDS.items():
        value = payload.get(entity_type)
        if not isinstance(value, dict) or set(value) != set(fields):
            errors.append(f"{entity_type} fields do not match the candidate contract")
            continue
        for field in fields:
            field_value = value.get(field)
            if field in {"glossary_terms", "variables"}:
                if not isinstance(field_value, list):
                    errors.append(f"{entity_type}.{field} must be an array")
            elif not isinstance(field_value, str):
                errors.append(f"{entity_type}.{field} must be text")
    if not isinstance(payload.get("evidence"), list):
        errors.append("evidence must be an array")
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("confidence must be between 0 and 1")
    if payload.get("risk_level") not in {"low", "medium", "high"}:
        errors.append("risk_level is invalid")
    if not isinstance(payload.get("change_summary"), str):
        errors.append("change_summary must be text")
    return errors


def validate_candidate(
    context: ElementContext,
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    errors = _candidate_shape_errors(payload)
    if errors:
        return [], [], errors[:MAX_FAILURE_DETAILS]

    baselines = {
        "element": context.element,
        "concept": context.concept,
        "formula": context.formula,
    }
    generated: dict[str, dict[str, Any]] = {}
    changed_by_entity: dict[str, list[str]] = {}
    for entity_type, fields in ENTITY_FIELDS.items():
        generated[entity_type] = deepcopy(baselines[entity_type])
        generated[entity_type].update(payload[entity_type])
        changed_by_entity[entity_type] = [
            field for field in fields
            if baselines[entity_type].get(field) != generated[entity_type].get(field)
        ]

    if generated["concept"]["checklist_markdown"] != generated["formula"]["notes_markdown"]:
        errors.append("concept.checklist_markdown and formula.notes_markdown must remain identical")

    allowed_fragment_ids = {
        _uuid(fragment.get("source_fragment_id"), "source fragment id")
        for fragment in context.evidence
    }
    evidence_map: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for index, evidence in enumerate(payload.get("evidence", [])):
        if not isinstance(evidence, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        entity_type = evidence.get("entity_type")
        field = evidence.get("field_path")
        fragment_ids = evidence.get("source_fragment_ids")
        rationale = evidence.get("rationale")
        if entity_type not in ENTITY_FIELDS or field not in ENTITY_FIELDS.get(str(entity_type), ()):
            errors.append(f"evidence[{index}] targets an unsupported field")
            continue
        if field not in changed_by_entity[str(entity_type)]:
            errors.append(f"evidence[{index}] targets unchanged field {entity_type}.{field}")
            continue
        if not isinstance(fragment_ids, list) or not fragment_ids:
            errors.append(f"evidence[{index}] requires at least one source fragment")
            continue
        if not isinstance(rationale, str):
            errors.append(f"evidence[{index}].rationale must be text")
            continue
        for raw_id in fragment_ids:
            try:
                fragment_id = _uuid(raw_id, "model evidence fragment id")
            except GenerationWorkerError:
                errors.append(f"evidence[{index}] contains an invalid fragment id")
                continue
            if fragment_id not in allowed_fragment_ids:
                errors.append(f"evidence[{index}] cites a fragment outside the model context")
                continue
            if (fragment_id, rationale) not in evidence_map[(str(entity_type), str(field))]:
                evidence_map[(str(entity_type), str(field))].append((fragment_id, rationale))

    for entity_type, fields in changed_by_entity.items():
        for field in fields:
            if not evidence_map[(entity_type, field)]:
                errors.append(f"changed field {entity_type}.{field} has no source evidence")

    items: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    entity_keys = {
        "element": str(context.element["element_id"]),
        "concept": str(context.concept["concept_id"]),
        "formula": str(context.formula["formula_id"]),
    }
    for entity_type, fields in changed_by_entity.items():
        if not fields:
            continue
        revision = {
            "revision_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"candidate:{context.element_id}:{entity_type}")),
            "entity_type": entity_type,
            "entity_key": entity_keys[entity_type],
            "revision_number": 1,
            "operation": "update",
            "snapshot": generated[entity_type],
            "content_hash": sha256_bytes(canonical_json_bytes(generated[entity_type])),
        }
        validation = content_validator.validate_revision(revision)
        if validation.status != "passed":
            errors.extend(
                f"{entity_type}.{issue.field_path}: {issue.code} - {issue.message}"
                for issue in validation.issues
            )
            continue
        items.append(
            {
                "elementId": context.element_id,
                "entityType": entity_type,
                "entityKey": entity_keys[entity_type],
                "baselineSnapshot": baselines[entity_type],
                "generatedSnapshot": generated[entity_type],
                "changedFields": fields,
                "changeSummary": str(payload["change_summary"])[:2000],
                "confidence": float(payload["confidence"]),
                "riskLevel": payload["risk_level"],
                "validationSummary": {
                    "validatorName": content_validator.VALIDATOR_NAME,
                    "validatorVersion": content_validator.VALIDATOR_VERSION,
                    "checksTotal": validation.checks_total,
                    "checksPassed": validation.checks_passed,
                    "checksFailed": validation.checks_failed,
                },
            }
        )
        for field in fields:
            for position, (fragment_id, rationale) in enumerate(evidence_map[(entity_type, field)]):
                evidence_rows.append(
                    {
                        "entityType": entity_type,
                        "entityKey": entity_keys[entity_type],
                        "fieldPath": field,
                        "sourceFragmentId": fragment_id,
                        "supportRole": "primary" if position == 0 else "corroborating",
                        "rationale": rationale[:1000],
                    }
                )
    return items, evidence_rows, errors[:MAX_FAILURE_DETAILS]


def _model_run_record(
    result: ModelCallResult,
    context: ElementContext,
    run_kind: str,
    run_number: int,
) -> dict[str, Any]:
    return {
        "elementId": context.element_id,
        "runKind": run_kind,
        "runNumber": run_number,
        "responseId": result.response_id,
        "inputSha256": result.input_sha256,
        "outputSha256": result.output_sha256,
        "inputTokens": result.input_tokens,
        "outputTokens": result.output_tokens,
        "durationMs": result.duration_ms,
        "status": "succeeded",
    }


def generate_element_candidate(
    model: ContentModel,
    batch_id: str,
    context: ElementContext,
    on_repair: Callable[[int, Sequence[str]], None] | None = None,
) -> CandidateBundle:
    document = model_document(context)
    model_runs: list[dict[str, Any]] = []
    errors: list[str] = []
    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        run_kind = "generate" if attempt == 0 else "repair"
        run_number = 1 if attempt == 0 else attempt
        if attempt:
            if on_repair:
                on_repair(attempt, errors)
            document = {
                **model_document(context),
                "repair": {
                    "previousCandidate": result.payload,
                    "validationErrors": errors,
                    "instruction": "Restore rejected fields to baseline and retain only independently valid local mappings.",
                },
            }
        idempotency_key = str(
            uuid.uuid5(
                uuid.UUID(batch_id),
                f"{context.element_id}:{PROMPT_VERSION}:{run_kind}:{run_number}",
            )
        )
        result = model.generate(
            document,
            run_kind=run_kind,
            run_number=run_number,
            idempotency_key=idempotency_key,
        )
        model_runs.append(_model_run_record(result, context, run_kind, run_number))
        items, evidence, errors = validate_candidate(context, result.payload)
        if not errors:
            return CandidateBundle(tuple(items), tuple(evidence), tuple(model_runs))
    raise CandidateValidationError(errors, model_runs)


class ContentGenerationWorker:
    def __init__(
        self,
        client: SupabaseGenerationClient,
        model: ContentModel,
        worker_id: str,
        model_name: str,
        *,
        max_elements: int = 135,
        auto_enqueue_sources: int = 50,
    ) -> None:
        if WORKER_ID_RE.fullmatch(worker_id) is None:
            raise GenerationWorkerError("worker id is invalid")
        if max_elements < 1 or max_elements > 135:
            raise GenerationWorkerError("max elements must be between 1 and 135")
        if auto_enqueue_sources < 1 or auto_enqueue_sources > 100:
            raise GenerationWorkerError("auto enqueue source count must be between 1 and 100")
        self.client = client
        self.model = model
        self.worker_id = worker_id
        self.model_name = model_name
        self.max_elements = max_elements
        self.auto_enqueue_sources = auto_enqueue_sources

    def _enqueue(self) -> dict[str, Any] | None:
        return _rpc_object(
            self.client.rpc(
                ENQUEUE_RPC,
                {
                    "p_model_name": self.model_name,
                    "p_prompt_version": PROMPT_VERSION,
                    "p_max_sources": self.auto_enqueue_sources,
                },
            ),
            "auto enqueue generation",
        )

    def _claim(self) -> dict[str, Any] | None:
        return _rpc_object(
            self.client.rpc(
                CLAIM_RPC,
                {
                    "p_worker_id": self.worker_id,
                    "p_model_name": self.model_name,
                    "p_prompt_version": PROMPT_VERSION,
                },
            ),
            "claim generation",
        )

    def _progress(
        self,
        batch_id: str,
        progress: int,
        stage: str,
        statistics: Mapping[str, Any] | None = None,
    ) -> None:
        self.client.rpc(
            PROGRESS_RPC,
            {
                "p_batch_id": batch_id,
                "p_worker_id": self.worker_id,
                "p_progress_percent": progress,
                "p_processing_stage": stage,
                "p_statistics": dict(statistics or {}),
            },
        )

    def process_one(self) -> dict[str, Any] | None:
        self._enqueue()
        batch = self._claim()
        if batch is None:
            return None
        batch_id = _uuid(batch.get("batch_id"), "batch id")
        if batch.get("status") != "running" or batch.get("claimed_by") != self.worker_id:
            raise GenerationWorkerError("claim did not return an owned running generation batch")

        try:
            contexts = load_element_contexts(
                self.client,
                batch_id,
                self.worker_id,
                self.max_elements,
            )
            self._progress(
                batch_id,
                6,
                "evidence_matching",
                {"targetElementCount": len(contexts)},
            )
            all_items: list[dict[str, Any]] = []
            all_evidence: list[dict[str, Any]] = []
            all_runs: list[dict[str, Any]] = []
            failed_elements: list[dict[str, Any]] = []
            total = max(1, len(contexts))

            for index, context in enumerate(contexts):
                base_progress = min(90, 8 + int(index / total * 80))
                self._progress(
                    batch_id,
                    base_progress,
                    "local_schema_mapping",
                    {
                        "currentElementId": context.element_id,
                        "processedElementCount": index,
                        "targetElementCount": len(contexts),
                    },
                )

                def on_repair(attempt: int, issues: Sequence[str]) -> None:
                    self._progress(
                        batch_id,
                        min(92, base_progress + attempt),
                        "deterministic_repair",
                        {
                            "currentElementId": context.element_id,
                            "repairAttempt": attempt,
                            "repairIssueCount": len(issues),
                        },
                    )

                try:
                    bundle = generate_element_candidate(
                        self.model,
                        batch_id,
                        context,
                        on_repair=on_repair,
                    )
                    all_items.extend(bundle.items)
                    all_evidence.extend(bundle.evidence)
                    all_runs.extend(bundle.model_runs)
                except CandidateValidationError as error:
                    all_runs.extend(error.model_runs)
                    failed_elements.append(
                        {"elementId": context.element_id, "errors": error.errors[:5]}
                    )

            if contexts and failed_elements and not all_items:
                raise GenerationWorkerError(
                    "all candidate elements failed validation after automatic repair"
                )
            self._progress(
                batch_id,
                94,
                "final_validation",
                {
                    "generatedItemCount": len(all_items),
                    "evidenceCount": len(all_evidence),
                    "failedElementCount": len(failed_elements),
                },
            )
            result = _rpc_object(
                self.client.rpc(
                    COMPLETE_RPC,
                    {
                        "p_batch_id": batch_id,
                        "p_worker_id": self.worker_id,
                        "p_items": all_items,
                        "p_evidence": all_evidence,
                        "p_model_runs": all_runs,
                        "p_statistics": {
                            "transformerType": "deterministic-local-rules",
                            "rulesetVersion": PROMPT_VERSION,
                            "targetElementCount": len(contexts),
                            "processedElementCount": len(contexts),
                            "failedElements": failed_elements[:MAX_FAILURE_DETAILS],
                        },
                    },
                ),
                "complete generation",
            )
            return result or {"batchId": batch_id, "status": "completed"}
        except Exception as error:
            secret_values = [self.client.secret_key]
            safe_message = str(error)
            for secret in secret_values:
                if secret:
                    safe_message = safe_message.replace(secret, "[redacted]")
            safe_message = safe_message[:2000] or error.__class__.__name__
            terminal = _rpc_object(
                self.client.rpc(
                    FAIL_RPC,
                    {
                        "p_batch_id": batch_id,
                        "p_worker_id": self.worker_id,
                        "p_error_message": safe_message,
                        "p_statistics": {"failureType": error.__class__.__name__},
                    },
                ),
                "fail generation",
            )
            if terminal is not None and terminal.get("alreadyTerminal"):
                return terminal
            raise GenerationWorkerError("claimed generation batch failed safely") from error


def default_worker_id() -> str:
    hostname = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:48] or "host"
    return f"findone-local-compiler:{hostname}:{os.getpid()}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", default=default_worker_id())
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--model-config",
        type=Path,
        default=local_content_model.DEFAULT_MODEL_CONFIG,
        help="Checked-in local ruleset JSON",
    )
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--max-elements", type=int, default=135)
    parser.add_argument("--auto-enqueue-sources", type=int, default=50)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_batches < 1 or args.max_batches > 5:
        raise GenerationWorkerError("--max-batches must be between 1 and 5")
    model = LocalRulesContentModel(args.model_config)
    model_name = model.model_name
    client = SupabaseGenerationClient(
        resolve_supabase_url(),
        os.environ.get("SUPABASE_SECRET_KEY", ""),
        timeout_seconds=args.timeout,
    )
    worker = ContentGenerationWorker(
        client,
        model,
        args.worker_id,
        model_name,
        max_elements=args.max_elements,
        auto_enqueue_sources=args.auto_enqueue_sources,
    )
    outcomes: list[dict[str, Any]] = []
    for _ in range(args.max_batches):
        result = worker.process_one()
        if result is None:
            break
        outcomes.append(result)
    print(
        json.dumps(
            {"status": "processed" if outcomes else "idle", "batches": outcomes},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GenerationWorkerError, ValueError, OSError) as error:
        print(f"Local content compiler worker stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
