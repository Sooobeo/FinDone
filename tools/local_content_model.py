#!/usr/bin/env python3
"""Deterministic, offline content transformation rules for FinDone.

This module is intentionally network-free.  It turns explicitly structured
JSON, CSV/TSV, or labelled text into the strict content-candidate shape used by
the Admin review pipeline.  Unstructured prose and conflicting values are left
unchanged so the transformer never invents finance content.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_CONFIG = ROOT / "content" / "model" / "local-content-model.json"
DEFAULT_GOLDEN_SET = ROOT / "content" / "model" / "golden-set.json"

ENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "element": ("title", "core_relation", "scope_notes"),
    "concept": (
        "title",
        "definition_markdown",
        "intuition_markdown",
        "learning_notes_markdown",
        "checklist_markdown",
        "glossary_terms",
    ),
    "formula": (
        "title",
        "expression_markdown",
        "assumptions_markdown",
        "notes_markdown",
        "variables",
    ),
}

ELEMENT_ID_RE = re.compile(r"^(ACC|CF|INV|FI|DER|EQV|IBT)-\d{2}$", re.IGNORECASE)
KEY_VALUE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?([^:=]{1,80}?)(?:\*\*)?\s*[:=]\s*(.+?)\s*$"
)
MAX_FRAGMENT_CHARS = 128_000
MAX_FIELD_CHARS = 65_536


class LocalContentModelError(ValueError):
    """Raised when the checked-in model or evaluation corpus is malformed."""


@dataclass(frozen=True)
class ParsedRecord:
    values: dict[str, Any]
    parser: str
    confidence: float


@dataclass(frozen=True)
class GoldenEvaluation:
    case_count: int
    passed_cases: int
    field_assertion_count: int
    passed_field_assertions: int
    case_accuracy: float
    field_accuracy: float
    failures: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "caseCount": self.case_count,
            "passedCases": self.passed_cases,
            "fieldAssertionCount": self.field_assertion_count,
            "passedFieldAssertions": self.passed_field_assertions,
            "caseAccuracy": self.case_accuracy,
            "fieldAccuracy": self.field_accuracy,
            "failures": list(self.failures),
        }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LocalContentModelError(f"Could not read {label}: {path}") from error
    if not isinstance(value, dict):
        raise LocalContentModelError(f"{label} must contain a JSON object: {path}")
    return value


def normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    compact: list[str] = []
    for line in lines:
        if line or (compact and compact[-1]):
            compact.append(line)
    return "\n".join(compact).strip()[:MAX_FIELD_CHARS]


def _flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_key, child in value.items():
        key = str(raw_key).strip()
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, Mapping):
            result.update(_flatten(child, path))
        else:
            result[path] = child
    return result


def _alias_index(config: Mapping[str, Any]) -> tuple[set[str], dict[str, str]]:
    raw_id_aliases = config.get("elementIdAliases")
    raw_field_aliases = config.get("fieldAliases")
    if not isinstance(raw_id_aliases, list) or not all(isinstance(item, str) for item in raw_id_aliases):
        raise LocalContentModelError("elementIdAliases must be an array of strings")
    if not isinstance(raw_field_aliases, dict):
        raise LocalContentModelError("fieldAliases must be an object")

    id_aliases = {normalize_key(value) for value in raw_id_aliases}
    aliases: dict[str, str] = {}
    supported = {f"{entity}.{field}" for entity, fields in ENTITY_FIELDS.items() for field in fields}
    for canonical, raw_aliases in raw_field_aliases.items():
        if canonical not in supported:
            raise LocalContentModelError(f"Unsupported canonical field in model: {canonical}")
        if not isinstance(raw_aliases, list) or not all(isinstance(item, str) for item in raw_aliases):
            raise LocalContentModelError(f"Aliases for {canonical} must be strings")
        for alias in (canonical, *raw_aliases):
            key = normalize_key(alias)
            previous = aliases.get(key)
            if previous is not None and previous != canonical:
                raise LocalContentModelError(f"Ambiguous field alias {alias!r}: {previous} / {canonical}")
            aliases[key] = canonical
    return id_aliases, aliases


def load_model_config(path: Path = DEFAULT_MODEL_CONFIG) -> dict[str, Any]:
    config = load_json_object(path, "local content model")
    version = config.get("modelVersion")
    if not isinstance(version, str) or not version.strip():
        raise LocalContentModelError("modelVersion is required")
    _alias_index(config)
    return config


def _json_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _json_records(item)
        return
    if not isinstance(value, dict):
        return
    flattened = _flatten(value)
    if flattened:
        yield dict(value)
    for key in ("records", "items", "content", "elements", "rows", "data"):
        child = value.get(key)
        if isinstance(child, (dict, list)):
            yield from _json_records(child)


def _parse_json_records(text: str) -> list[ParsedRecord]:
    stripped = text.lstrip("\ufeff \t\r\n")
    if not stripped.startswith(("{", "[")):
        return []
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    return [ParsedRecord(record, "json", 0.99) for record in _json_records(value)]


def _parse_delimited_records(text: str, id_aliases: set[str]) -> list[ParsedRecord]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    header = lines[0]
    delimiters = [delimiter for delimiter in ("\t", ",", ";", "|") if delimiter in header]
    for delimiter in delimiters:
        try:
            reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
            fields = reader.fieldnames or []
            if len(fields) < 2 or not any(normalize_key(field) in id_aliases for field in fields):
                continue
            result = [
                ParsedRecord({str(key): value for key, value in row.items() if key is not None}, "table", 0.97)
                for row in reader
                if any(str(value or "").strip() for value in row.values())
            ]
            if result:
                return result
        except (csv.Error, UnicodeError):
            continue
    return []


def _parse_key_value_record(text: str, id_aliases: set[str]) -> list[ParsedRecord]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = KEY_VALUE_RE.match(line)
        if match:
            values[match.group(1).strip()] = match.group(2).strip()
    if not values or not any(normalize_key(key) in id_aliases for key in values):
        return []
    return [ParsedRecord(values, "labelled_text", 0.92)]


def parse_structured_records(text: str, config: Mapping[str, Any]) -> list[ParsedRecord]:
    bounded = text[:MAX_FRAGMENT_CHARS]
    id_aliases, _ = _alias_index(config)
    parsed = _parse_json_records(bounded)
    if parsed:
        return parsed
    parsed = _parse_delimited_records(bounded, id_aliases)
    if parsed:
        return parsed
    return _parse_key_value_record(bounded, id_aliases)


def _string_list(value: Any) -> list[str] | None:
    if isinstance(value, list):
        items = [normalize_text(str(item)) for item in value if isinstance(item, (str, int, float))]
    elif isinstance(value, str):
        stripped = value.strip()
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            items = [normalize_text(str(item)) for item in decoded if isinstance(item, (str, int, float))]
        else:
            parts = stripped.splitlines()
            if len(parts) < 2:
                for separator in (";", "|"):
                    if separator in stripped:
                        parts = stripped.split(separator)
                        break
            items = [normalize_text(re.sub(r"^\s*[-*•]\s*", "", part)) for part in parts]
    else:
        return None
    result = list(dict.fromkeys(item for item in items if item))
    return result[:100]


def _bullet_markdown(value: Any) -> str | None:
    items = _string_list(value)
    if not items:
        return None
    return "\n".join(f"- {item}" for item in items)


def _variables(value: Any) -> list[dict[str, str]] | None:
    decoded: Any = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            entries = _string_list(value) or []
            parsed: list[dict[str, str]] = []
            for entry in entries:
                symbol, separator, meaning = entry.partition("=")
                if not separator:
                    symbol, separator, meaning = entry.partition(":")
                if separator and symbol.strip() and meaning.strip():
                    parsed.append({"symbol": symbol.strip()[:128], "meaning": meaning.strip()[:2000]})
            decoded = parsed
    if not isinstance(decoded, list):
        return None
    result: list[dict[str, str]] = []
    for item in decoded:
        if not isinstance(item, Mapping):
            return None
        symbol = normalize_text(str(item.get("symbol", "")))[:128]
        meaning = normalize_text(str(item.get("meaning", "")))[:2000]
        if not symbol or not meaning:
            return None
        result.append({"symbol": symbol, "meaning": meaning})
    return result[:100]


def _coerce_field(canonical: str, value: Any) -> Any | None:
    if canonical in {"concept.glossary_terms"}:
        return _string_list(value)
    if canonical == "formula.variables":
        return _variables(value)
    if canonical in {"concept.checklist_markdown", "formula.notes_markdown"}:
        return _bullet_markdown(value)
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        normalized = normalize_text(str(value))
        return normalized or None
    return None


def canonicalize_record(record: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[str, dict[str, Any]] | None:
    id_aliases, aliases = _alias_index(config)
    flattened = _flatten(record)
    element_ids: set[str] = set()
    fields: dict[str, Any] = {}
    conflicting_fields: set[str] = set()
    for raw_key, raw_value in flattened.items():
        key = normalize_key(raw_key)
        if key in id_aliases:
            candidate_id = normalize_text(str(raw_value)).upper()
            if ELEMENT_ID_RE.fullmatch(candidate_id):
                element_ids.add(candidate_id)
            continue
        canonical = aliases.get(key)
        if canonical is None:
            # A nested object can use a known leaf alias without its wrapper.
            canonical = aliases.get(normalize_key(raw_key.rsplit(".", 1)[-1]))
        if canonical is None:
            continue
        coerced = _coerce_field(canonical, raw_value)
        if coerced is None or canonical in conflicting_fields:
            continue
        if canonical in fields and canonical_json_bytes(fields[canonical]) != canonical_json_bytes(coerced):
            fields.pop(canonical, None)
            conflicting_fields.add(canonical)
            continue
        fields[canonical] = coerced
    if len(element_ids) != 1:
        return None
    return next(iter(element_ids)), fields


def _copy_baseline(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = document.get("baseline")
    if not isinstance(raw, Mapping):
        raise LocalContentModelError("transform document baseline is missing")
    baseline: dict[str, dict[str, Any]] = {}
    for entity, fields in ENTITY_FIELDS.items():
        value = raw.get(entity)
        if not isinstance(value, Mapping) or any(field not in value for field in fields):
            raise LocalContentModelError(f"baseline.{entity} is incomplete")
        baseline[entity] = {field: value[field] for field in fields}
    return baseline


def _same_value(left: Any, right: Any) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def transform_document(document: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a strict candidate while preserving every unsupported baseline field."""

    baseline = _copy_baseline(document)
    element_id = normalize_text(str(document.get("elementId", ""))).upper()
    if not ELEMENT_ID_RE.fullmatch(element_id):
        raise LocalContentModelError("transform document elementId is invalid")
    raw_evidence = document.get("sourceEvidence")
    if not isinstance(raw_evidence, list):
        raise LocalContentModelError("transform document sourceEvidence must be an array")

    proposals: dict[str, list[tuple[Any, str, float, str]]] = defaultdict(list)
    parser_kinds: set[str] = set()
    for evidence in raw_evidence:
        if not isinstance(evidence, Mapping):
            continue
        fragment_id = str(evidence.get("sourceFragmentId", ""))
        text = evidence.get("text")
        if not fragment_id or not isinstance(text, str):
            continue
        for parsed in parse_structured_records(text, config):
            canonical = canonicalize_record(parsed.values, config)
            if canonical is None or canonical[0] != element_id:
                continue
            parser_kinds.add(parsed.parser)
            for field, value in canonical[1].items():
                proposals[field].append((value, fragment_id, parsed.confidence, parsed.parser))

    accepted: dict[str, tuple[Any, tuple[str, ...], float, str]] = {}
    conflict_count = 0
    for field, values in proposals.items():
        unique: dict[bytes, list[tuple[Any, str, float, str]]] = defaultdict(list)
        for value in values:
            unique[canonical_json_bytes(value[0])].append(value)
        if len(unique) != 1:
            conflict_count += 1
            continue
        group = next(iter(unique.values()))
        accepted[field] = (
            group[0][0],
            tuple(dict.fromkeys(item[1] for item in group))[:8],
            min(item[2] for item in group),
            group[0][3],
        )

    # Keep the three display titles synchronized unless the input explicitly supplied each one.
    if "element.title" in accepted:
        title = accepted["element.title"]
        accepted.setdefault("concept.title", title)
        accepted.setdefault("formula.title", title)
    # The app intentionally renders one practical-use list in both concept and formula cards.
    if "concept.checklist_markdown" in accepted:
        accepted.setdefault("formula.notes_markdown", accepted["concept.checklist_markdown"])
    elif "formula.notes_markdown" in accepted:
        accepted["concept.checklist_markdown"] = accepted["formula.notes_markdown"]

    generated = {entity: dict(values) for entity, values in baseline.items()}
    evidence_rows: list[dict[str, Any]] = []
    changed_fields: list[str] = []
    confidences: list[float] = []
    for dotted_field, (value, fragment_ids, confidence, parser) in sorted(accepted.items()):
        entity, field = dotted_field.split(".", 1)
        if _same_value(value, baseline[entity][field]):
            continue
        generated[entity][field] = value
        changed_fields.append(dotted_field)
        confidences.append(confidence)
        evidence_rows.append(
            {
                "entity_type": entity,
                "field_path": field,
                "source_fragment_ids": list(fragment_ids),
                "rationale": f"{parser} 입력의 명시적 {dotted_field} 필드를 로컬 규칙으로 매핑했다.",
            }
        )

    high_risk = any(
        field in {
            "element.core_relation",
            "formula.expression_markdown",
            "formula.assumptions_markdown",
            "formula.variables",
        }
        for field in changed_fields
    )
    medium_risk = any(field.startswith("element.") or field.endswith("title") for field in changed_fields)
    risk = "high" if high_risk else "medium" if medium_risk else "low"
    confidence = min(confidences, default=1.0)
    summary = (
        f"구조화 원본의 명시 필드 {len(changed_fields)}개를 로컬 규칙으로 변환했다."
        if changed_fields
        else "이 요소에 안전하게 자동 반영할 구조화 필드가 없어 기존 콘텐츠를 유지했다."
    )
    if conflict_count:
        summary += f" 충돌 필드 {conflict_count}개는 자동 반영하지 않았다."

    return {
        "element": generated["element"],
        "concept": generated["concept"],
        "formula": generated["formula"],
        "evidence": evidence_rows,
        "confidence": round(confidence, 4),
        "risk_level": risk,
        "change_summary": summary,
    }


def repair_candidate(
    document: Mapping[str, Any],
    candidate: Mapping[str, Any],
    validation_errors: Sequence[str],
) -> dict[str, Any]:
    """Drop only locally mapped fields rejected by the shared validator.

    A deterministic transformer cannot rewrite an invalid finance explanation
    creatively.  Its safe repair is to restore the reviewed baseline for the
    rejected field and keep any independently valid changes.
    """

    baseline = _copy_baseline(document)
    repaired: dict[str, Any] = {
        entity: dict(candidate.get(entity, {}))
        for entity in ENTITY_FIELDS
    }
    rejected: set[tuple[str, str]] = set()
    for error in validation_errors:
        match = re.match(r"^(element|concept|formula)\.([a-z_]+)", str(error))
        if match and match.group(2) in ENTITY_FIELDS[match.group(1)]:
            rejected.add((match.group(1), match.group(2)))
        if "checklist_markdown and formula.notes_markdown" in str(error):
            rejected.update(
                {("concept", "checklist_markdown"), ("formula", "notes_markdown")}
            )
    if validation_errors and not rejected:
        for entity, fields in ENTITY_FIELDS.items():
            for field in fields:
                if not _same_value(repaired.get(entity, {}).get(field), baseline[entity][field]):
                    rejected.add((entity, field))

    for entity, field in rejected:
        repaired.setdefault(entity, {})[field] = baseline[entity][field]
    raw_evidence = candidate.get("evidence")
    evidence = [
        dict(item)
        for item in raw_evidence if isinstance(item, Mapping)
        and (str(item.get("entity_type")), str(item.get("field_path"))) not in rejected
    ] if isinstance(raw_evidence, list) else []
    changed = changed_values(repaired, baseline)
    repaired.update(
        {
            "evidence": evidence,
            "confidence": float(candidate.get("confidence", 1.0)),
            "risk_level": candidate.get("risk_level", "low"),
            "change_summary": (
                f"검증에 실패한 로컬 매핑 {len(rejected)}개를 원래 값으로 되돌리고 "
                f"검증 가능한 필드 {len(changed)}개만 유지했다."
            ),
        }
    )
    return repaired


def _golden_baseline() -> dict[str, dict[str, Any]]:
    checklist = "- 기존 사용 사례 한 가지를 구체적으로 확인한다.\n- 기존 사용 사례 두 가지를 비교하여 검토한다."
    return {
        "element": {
            "title": "기존 제목",
            "core_relation": "기존 핵심 관계를 설명하는 문장이다.",
            "scope_notes": "기존 적용 범위를 설명하는 문장이다.",
        },
        "concept": {
            "title": "기존 제목",
            "definition_markdown": "기존 정의를 충분한 길이의 문장으로 설명하여 기준값으로 사용한다.",
            "intuition_markdown": "기존 직관 설명은 개념이 현실에서 어떻게 연결되는지를 충분한 문장으로 설명한다.",
            "learning_notes_markdown": "### 기존 설명\n\n기존 상세 학습 설명을 유지한다.",
            "checklist_markdown": checklist,
            "glossary_terms": ["기존 용어"],
        },
        "formula": {
            "title": "기존 제목",
            "expression_markdown": "$$X=Y$$",
            "assumptions_markdown": "기존 수식 가정을 설명한다.",
            "notes_markdown": checklist,
            "variables": [{"symbol": "X", "meaning": "기존 변수"}],
        },
    }


def changed_values(payload: Mapping[str, Any], baseline: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for entity, fields in ENTITY_FIELDS.items():
        generated = payload.get(entity)
        if not isinstance(generated, Mapping):
            continue
        for field in fields:
            if field in generated and not _same_value(generated[field], baseline[entity][field]):
                result[f"{entity}.{field}"] = generated[field]
    return result


def evaluate_golden_set(
    config: Mapping[str, Any] | None = None,
    path: Path = DEFAULT_GOLDEN_SET,
) -> GoldenEvaluation:
    model = dict(config) if config is not None else load_model_config()
    golden = load_json_object(path, "golden evaluation set")
    cases = golden.get("cases")
    if not isinstance(cases, list) or not cases:
        raise LocalContentModelError("golden evaluation set requires cases")

    passed_cases = 0
    field_total = 0
    field_passed = 0
    failures: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise LocalContentModelError(f"golden case {index} must be an object")
        case_id = str(case.get("id", f"case-{index}"))
        element_id = str(case.get("elementId", "")).upper()
        fragments = case.get("fragments")
        expected = case.get("expectedChanges")
        if not ELEMENT_ID_RE.fullmatch(element_id) or not isinstance(fragments, list) or not isinstance(expected, dict):
            raise LocalContentModelError(f"golden case {case_id} is malformed")
        baseline = _golden_baseline()
        evidence: list[dict[str, Any]] = []
        for fragment_index, fragment in enumerate(fragments):
            if not isinstance(fragment, Mapping) or not isinstance(fragment.get("text"), str):
                raise LocalContentModelError(f"golden case {case_id} has an invalid fragment")
            evidence.append(
                {
                    "sourceFragmentId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"golden:{case_id}:{fragment_index}")),
                    "fragmentKind": str(fragment.get("kind", "text")),
                    "text": fragment["text"],
                }
            )
        payload = transform_document(
            {"elementId": element_id, "baseline": baseline, "sourceEvidence": evidence},
            model,
        )
        actual = changed_values(payload, baseline)
        assertion_fields = sorted(set(expected) | set(actual))
        if not assertion_fields:
            assertion_fields = ["__no_changes__"]
        failed_fields: list[str] = []
        for field in assertion_fields:
            field_total += 1
            if field == "__no_changes__" or (
                field in expected and field in actual and _same_value(expected[field], actual[field])
            ):
                field_passed += 1
            else:
                failed_fields.append(field)
        if not failed_fields and set(actual) == set(expected):
            passed_cases += 1
        else:
            failures.append(
                {
                    "caseId": case_id,
                    "failedFields": failed_fields,
                    "expected": expected,
                    "actual": actual,
                }
            )

    return GoldenEvaluation(
        case_count=len(cases),
        passed_cases=passed_cases,
        field_assertion_count=field_total,
        passed_field_assertions=field_passed,
        case_accuracy=round(passed_cases / len(cases), 6),
        field_accuracy=round(field_passed / field_total, 6),
        failures=tuple(failures),
    )


def supported_adapter_names() -> tuple[str, ...]:
    return ("sqlite-table", "json", "json-list", "jsonl", "csv", "tsv", "labelled-text")
