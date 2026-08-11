#!/usr/bin/env python3
"""Claim and validate one immutable FinDone content revision.

The worker is intentionally narrow: it claims only ``content_validation`` jobs.
It does not fetch URLs, extract files, build releases, or touch either packaged
or user SQLite databases. Supabase credentials are read only from environment
variables and are never included in logs or validation output.
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
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.admin_import_supabase import SupabaseImportError, normalize_supabase_url

VALIDATOR_NAME = "findone-content-validator"
# This is the validator contract queued by the current Admin workflow route.
# A mismatched run is failed instead of being stamped with misleading metadata.
VALIDATOR_VERSION = "admin-v2"
CLAIM_RPC = "claim_ingestion_job"
COMPLETE_RPC = "complete_content_validation_job"
FAIL_RPC = "fail_ingestion_job"

MAX_HTTP_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_HTTP_REQUEST_BYTES = 512 * 1024
MAX_SNAPSHOT_BYTES = 1024 * 1024
MAX_MARKDOWN_BYTES = 256 * 1024
MAX_JSON_DEPTH = 20
MAX_ISSUES = 100

DOMAIN_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,15}$")
ELEMENT_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,15}-[0-9]{2,3}$")
CONCEPT_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,15}-[0-9]{2,3}-C[0-9]{2,3}$")
FORMULA_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,15}-[0-9]{2,3}-F[0-9]{2,3}$")
FORMULA_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ValidationWorkerError(RuntimeError):
    """Raised when a job cannot be processed or persisted safely."""


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    field_path: str | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_rpc(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "fieldPath": self.field_path,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class ValidationResult:
    status: str
    checks_total: int
    checks_passed: int
    checks_failed: int
    issues: tuple[ValidationIssue, ...]
    summary: dict[str, Any]


@dataclass(frozen=True)
class WorkerOutcome:
    job_id: str
    revision_id: str
    validation_run_id: str
    validation_status: str
    checks_total: int
    checks_failed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "revisionId": self.revision_id,
            "validationRunId": self.validation_run_id,
            "validationStatus": self.validation_status,
            "checksTotal": self.checks_total,
            "checksFailed": self.checks_failed,
        }


class _Collector:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.issues: list[ValidationIssue] = []

    def check(
        self,
        condition: bool,
        *,
        code: str,
        field_path: str | None,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> bool:
        self.total += 1
        if condition:
            self.passed += 1
            return True
        self.failed += 1
        self.add_issue(
            ValidationIssue(
                severity="error",
                code=code,
                field_path=field_path,
                message=message,
                details=dict(details or {}),
            )
        )
        return False

    def add_issue(self, issue: ValidationIssue) -> None:
        if len(self.issues) < MAX_ISSUES:
            self.issues.append(issue)


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValidationWorkerError(
            "revision snapshot is not canonical JSON"
        ) from error
    return encoded


def _json_depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        return depth
    if isinstance(value, dict):
        return max(
            (_json_depth(item, depth + 1) for item in value.values()), default=depth
        )
    if isinstance(value, list):
        return max((_json_depth(item, depth + 1) for item in value), default=depth)
    return depth


def _first_control_character(
    value: Any, path: str = "snapshot"
) -> tuple[str, int] | None:
    if isinstance(value, str):
        for index, character in enumerate(value):
            if ord(character) < 32 and character not in "\t\r\n":
                return path, index
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            result = _first_control_character(item, f"{path}.{key}")
            if result is not None:
                return result
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result = _first_control_character(item, f"{path}[{index}]")
            if result is not None:
                return result
    return None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_string(
    collector: _Collector,
    snapshot: Mapping[str, Any],
    name: str,
    *,
    non_blank: bool = False,
    max_length: int = 65536,
) -> str | None:
    value = snapshot.get(name)
    valid = isinstance(value, str) and len(value) <= max_length
    if non_blank:
        valid = valid and bool(value.strip())
    collector.check(
        valid,
        code="required_string_invalid",
        field_path=f"snapshot.{name}",
        message=f"{name} must be a valid{' non-blank' if non_blank else ''} string",
        details={"maxLength": max_length},
    )
    return value if isinstance(value, str) else None


def _require_int(
    collector: _Collector,
    snapshot: Mapping[str, Any],
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    value = snapshot.get(name)
    valid = _is_int(value)
    if valid and minimum is not None:
        valid = value >= minimum
    if valid and maximum is not None:
        valid = value <= maximum
    collector.check(
        valid,
        code="required_integer_invalid",
        field_path=f"snapshot.{name}",
        message=f"{name} must be an integer in the allowed range",
        details={"minimum": minimum, "maximum": maximum},
    )
    return value if _is_int(value) else None


def _require_bool(
    collector: _Collector,
    snapshot: Mapping[str, Any],
    name: str,
) -> bool | None:
    value = snapshot.get(name)
    collector.check(
        isinstance(value, bool),
        code="required_boolean_invalid",
        field_path=f"snapshot.{name}",
        message=f"{name} must be a boolean",
    )
    return value if isinstance(value, bool) else None


def _require_list(
    collector: _Collector,
    snapshot: Mapping[str, Any],
    name: str,
    *,
    maximum_items: int = 500,
) -> list[Any] | None:
    value = snapshot.get(name)
    collector.check(
        isinstance(value, list) and len(value) <= maximum_items,
        code="required_array_invalid",
        field_path=f"snapshot.{name}",
        message=f"{name} must be an array within its item limit",
        details={"maximumItems": maximum_items},
    )
    return value if isinstance(value, list) else None


def _validate_glossary_terms(collector: _Collector, value: list[Any] | None) -> None:
    if value is None:
        return
    normalized: list[str] = []
    for index, item in enumerate(value):
        valid = isinstance(item, str) and bool(item.strip()) and len(item) <= 300
        collector.check(
            valid,
            code="glossary_term_invalid",
            field_path=f"snapshot.glossary_terms[{index}]",
            message="each glossary term must be a non-blank string",
            details={"maxLength": 300},
        )
        if valid:
            normalized.append(item.strip())
    collector.check(
        len(normalized) == len(set(normalized)),
        code="glossary_term_duplicate",
        field_path="snapshot.glossary_terms",
        message="glossary terms must be unique after trimming",
    )


def _validate_formula_variables(collector: _Collector, value: list[Any] | None) -> None:
    if value is None:
        return
    symbols: list[str] = []
    for index, item in enumerate(value):
        item_is_object = collector.check(
            isinstance(item, dict),
            code="formula_variable_invalid",
            field_path=f"snapshot.variables[{index}]",
            message="each formula variable must be an object",
        )
        if not item_is_object:
            continue
        symbol = item.get("symbol")
        meaning = item.get("meaning")
        symbol_valid = (
            isinstance(symbol, str) and bool(symbol.strip()) and len(symbol) <= 128
        )
        collector.check(
            symbol_valid,
            code="formula_variable_symbol_invalid",
            field_path=f"snapshot.variables[{index}].symbol",
            message="formula variable symbol must be a non-blank string",
            details={"maxLength": 128},
        )
        collector.check(
            isinstance(meaning, str) and bool(meaning.strip()) and len(meaning) <= 2000,
            code="formula_variable_meaning_invalid",
            field_path=f"snapshot.variables[{index}].meaning",
            message="formula variable meaning must be a non-blank string",
            details={"maxLength": 2000},
        )
        if symbol_valid:
            symbols.append(symbol.strip())
    collector.check(
        len(symbols) == len(set(symbols)),
        code="formula_variable_symbol_duplicate",
        field_path="snapshot.variables",
        message="formula variable symbols must be unique after trimming",
    )


def _add_markdown_issue(
    issues: list[ValidationIssue],
    code: str,
    field_path: str,
    message: str,
    details: Mapping[str, Any],
) -> None:
    if len(issues) < MAX_ISSUES:
        issues.append(
            ValidationIssue("error", code, field_path, message, dict(details))
        )


def _markdown_fence_run(line: str) -> tuple[str, int, bool] | None:
    marker_index = 0
    while marker_index < len(line) and marker_index < 4 and line[marker_index] == " ":
        marker_index += 1
    if marker_index > 3 or marker_index >= len(line):
        return None
    marker = line[marker_index]
    if marker not in "`~":
        return None
    end = marker_index
    while end < len(line) and line[end] == marker:
        end += 1
    length = end - marker_index
    if length < 3:
        return None
    return marker, length, not line[end:].strip()


def _is_indented_code_line(line: str) -> bool:
    columns = 0
    for character in line:
        if character == " ":
            columns += 1
        elif character == "\t":
            columns += 4 - (columns % 4)
        else:
            return False
        if columns >= 4:
            return True
    return False


def _find_closing_dollars(line: str, start: int, width: int) -> int:
    index = start
    while index < len(line):
        if line[index] == "\\":
            index += 2
            continue
        if width == 1 and line.startswith("$$", index):
            return -1
        if line.startswith("$" * width, index):
            return index
        index += 1
    return -1


def _validate_latex_structure(
    latex: str,
    field_path: str,
    base_offset: int,
    issues: list[ValidationIssue],
) -> None:
    brace_depth = 0
    index = 0
    while index < len(latex) and len(issues) < MAX_ISSUES:
        if latex[index] == "\\":
            index += 2
            continue
        if latex[index] == "{":
            brace_depth += 1
        elif latex[index] == "}":
            if brace_depth == 0:
                _add_markdown_issue(
                    issues,
                    "latex_closing_brace_unmatched",
                    field_path,
                    "LaTeX contains a closing brace without an opening brace",
                    {"offset": base_offset + index},
                )
            else:
                brace_depth -= 1
        index += 1
    if brace_depth and len(issues) < MAX_ISSUES:
        _add_markdown_issue(
            issues,
            "latex_braces_unbalanced",
            field_path,
            "LaTeX braces are not balanced inside the math span",
            {"openingOffset": base_offset, "unclosedBraceCount": brace_depth},
        )

    left_right_depth = 0
    for match in re.finditer(r"(?<!\\)\\(left|right)\b", latex):
        if match.group(1) == "left":
            left_right_depth += 1
        elif left_right_depth:
            left_right_depth -= 1
        else:
            _add_markdown_issue(
                issues,
                "latex_right_without_left",
                field_path,
                "LaTeX \\right does not have a matching \\left",
                {"offset": base_offset + match.start()},
            )
        if len(issues) >= MAX_ISSUES:
            return
    if left_right_depth:
        _add_markdown_issue(
            issues,
            "latex_left_without_right",
            field_path,
            "LaTeX \\left does not have a matching \\right",
            {"openingOffset": base_offset, "unclosedCount": left_right_depth},
        )

    environments: list[tuple[str, int]] = []
    for match in re.finditer(r"(?<!\\)\\(begin|end)\s*\{([^{}]+)\}", latex):
        action, name = match.group(1), match.group(2).strip()
        if action == "begin":
            environments.append((name, match.start()))
        elif not environments or environments[-1][0] != name:
            _add_markdown_issue(
                issues,
                "latex_environment_mismatch",
                field_path,
                "LaTeX environment begin/end markers do not match",
                {"offset": base_offset + match.start(), "environment": name[:128]},
            )
        else:
            environments.pop()
        if len(issues) >= MAX_ISSUES:
            return
    if environments:
        name, opening = environments[-1]
        _add_markdown_issue(
            issues,
            "latex_environment_unclosed",
            field_path,
            "LaTeX environment is not closed",
            {"openingOffset": base_offset + opening, "environment": name[:128]},
        )


def markdown_latex_issues(markdown: str, field_path: str) -> list[ValidationIssue]:
    """Validate the same Markdown/LaTeX boundaries recognized by the Android app."""

    issues: list[ValidationIssue] = []
    fenced_code: tuple[str, int, int] | None = None
    block_latex_start: int | None = None
    block_latex_lines: list[str] = []
    inline_ticks = 0
    inline_start = -1
    line_start = 0

    while line_start < len(markdown) and len(issues) < MAX_ISSUES:
        newline_index = markdown.find("\n", line_start)
        line_end = newline_index if newline_index >= 0 else len(markdown)
        content_end = (
            line_end - 1
            if line_end > line_start and markdown[line_end - 1] == "\r"
            else line_end
        )
        line = markdown[line_start:content_end]
        fence_run = _markdown_fence_run(line)

        if fenced_code is not None:
            marker, minimum_length, _ = fenced_code
            if (
                fence_run is not None
                and fence_run[0] == marker
                and fence_run[1] >= minimum_length
                and fence_run[2]
            ):
                fenced_code = None
        elif block_latex_start is not None:
            if line.strip() == "$$":
                _validate_latex_structure(
                    "\n".join(block_latex_lines),
                    field_path,
                    block_latex_start + 2,
                    issues,
                )
                block_latex_start = None
                block_latex_lines = []
            else:
                block_latex_lines.append(line)
        elif inline_ticks == 0 and fence_run is not None:
            fenced_code = (fence_run[0], fence_run[1], line_start)
        elif inline_ticks == 0 and line.strip() == "$$":
            block_latex_start = line_start + line.index("$$")
            block_latex_lines = []
        elif inline_ticks == 0 and _is_indented_code_line(line):
            pass
        else:
            index = 0
            while index < len(line) and len(issues) < MAX_ISSUES:
                if line[index] == "`":
                    run_end = index
                    while run_end < len(line) and line[run_end] == "`":
                        run_end += 1
                    run_length = run_end - index
                    if inline_ticks == 0:
                        inline_ticks = run_length
                        inline_start = line_start + index
                    elif inline_ticks == run_length:
                        inline_ticks = 0
                    index = run_end
                    continue
                if inline_ticks:
                    index += 1
                    continue
                if line[index] == "\\":
                    if index + 1 < len(line) and line[index + 1] in "()[]":
                        _add_markdown_issue(
                            issues,
                            "latex_delimiter_unsupported",
                            field_path,
                            "Use $ or $$ delimiters; Android does not recognize \\( \\) \\[ \\] math delimiters",
                            {"offset": line_start + index},
                        )
                    index += 2
                    continue
                if line[index] != "$":
                    index += 1
                    continue

                run_end = index
                while run_end < len(line) and line[run_end] == "$":
                    run_end += 1
                run_length = run_end - index
                if run_length > 2:
                    _add_markdown_issue(
                        issues,
                        "latex_delimiter_run_invalid",
                        field_path,
                        "LaTeX math delimiters must use one or two dollar signs",
                        {"offset": line_start + index, "runLength": run_length},
                    )
                    index = run_end
                    continue

                closing = _find_closing_dollars(line, run_end, run_length)
                if closing < 0:
                    next_character = line[run_end] if run_end < len(line) else ""
                    if run_length == 2 or (
                        next_character
                        and not next_character.isspace()
                        and not next_character.isdigit()
                    ):
                        _add_markdown_issue(
                            issues,
                            "latex_delimiter_unclosed",
                            field_path,
                            "LaTeX math delimiter is not closed on the same line",
                            {
                                "openingOffset": line_start + index,
                                "delimiterLength": run_length,
                            },
                        )
                    index = run_end
                    continue

                latex = line[run_end:closing]
                if run_length == 1 and (
                    not latex or latex[0].isspace() or latex[-1].isspace()
                ):
                    opening_currency = bool(latex) and latex[0].isdigit()
                    closing_currency = (
                        closing + 1 < len(line) and line[closing + 1].isdigit()
                    )
                    if not (opening_currency and closing_currency):
                        _add_markdown_issue(
                            issues,
                            "latex_inline_spacing_invalid",
                            field_path,
                            "Inline LaTeX must not have whitespace next to $ delimiters",
                            {"openingOffset": line_start + index},
                        )
                    else:
                        index += 1
                        continue
                else:
                    _validate_latex_structure(
                        latex, field_path, line_start + run_end, issues
                    )
                index = closing + run_length

        line_start = newline_index + 1 if newline_index >= 0 else len(markdown)

    if len(issues) < MAX_ISSUES and block_latex_start is not None:
        _add_markdown_issue(
            issues,
            "latex_delimiter_unclosed",
            field_path,
            "LaTeX display block delimiter is not closed",
            {"openingOffset": block_latex_start, "delimiterLength": 2},
        )
    if len(issues) < MAX_ISSUES and inline_ticks:
        _add_markdown_issue(
            issues,
            "markdown_inline_code_unclosed",
            field_path,
            "Markdown inline-code delimiter is not closed",
            {"openingOffset": inline_start, "delimiterLength": inline_ticks},
        )
    if len(issues) < MAX_ISSUES and fenced_code is not None:
        _add_markdown_issue(
            issues,
            "markdown_fence_unclosed",
            field_path,
            "Markdown fenced-code block is not closed",
            {"openingOffset": fenced_code[2], "delimiterLength": fenced_code[1]},
        )
    return issues


def _validate_markdown(
    collector: _Collector,
    field_path: str,
    markdown: str | None,
) -> None:
    if markdown is None:
        return
    byte_size = len(markdown.encode("utf-8"))
    if not collector.check(
        byte_size <= MAX_MARKDOWN_BYTES,
        code="markdown_too_large",
        field_path=field_path,
        message="Markdown field exceeds the validation size limit",
        details={"byteSize": byte_size, "maximumBytes": MAX_MARKDOWN_BYTES},
    ):
        return
    issues = markdown_latex_issues(markdown, field_path)
    collector.total += 1
    if issues:
        collector.failed += 1
        for issue in issues:
            collector.add_issue(issue)
    else:
        collector.passed += 1


def _validate_domain(collector: _Collector, snapshot: Mapping[str, Any]) -> str | None:
    entity_id = _require_string(
        collector, snapshot, "domain_id", non_blank=True, max_length=16
    )
    collector.check(
        entity_id is not None and DOMAIN_ID.fullmatch(entity_id) is not None,
        code="stable_id_invalid",
        field_path="snapshot.domain_id",
        message="domain_id does not use the stable domain ID format",
    )
    _require_string(collector, snapshot, "name", non_blank=True, max_length=200)
    _require_string(collector, snapshot, "description", max_length=10000)
    _require_int(collector, snapshot, "display_order", minimum=0)
    _require_string(collector, snapshot, "color_token", non_blank=True, max_length=128)
    _require_bool(collector, snapshot, "is_active")
    expected = snapshot.get("expected_element_count")
    collector.check(
        expected is None or (_is_int(expected) and expected >= 0),
        code="expected_element_count_invalid",
        field_path="snapshot.expected_element_count",
        message="expected_element_count must be null or a non-negative integer",
    )
    return entity_id


def _validate_element(collector: _Collector, snapshot: Mapping[str, Any]) -> str | None:
    entity_id = _require_string(
        collector, snapshot, "element_id", non_blank=True, max_length=24
    )
    domain_id = _require_string(
        collector, snapshot, "domain_id", non_blank=True, max_length=16
    )
    collector.check(
        entity_id is not None and ELEMENT_ID.fullmatch(entity_id) is not None,
        code="stable_id_invalid",
        field_path="snapshot.element_id",
        message="element_id does not use the stable element ID format",
    )
    collector.check(
        domain_id is not None and DOMAIN_ID.fullmatch(domain_id) is not None,
        code="domain_id_invalid",
        field_path="snapshot.domain_id",
        message="domain_id does not use the stable domain ID format",
    )
    if entity_id and domain_id:
        collector.check(
            entity_id.startswith(f"{domain_id}-"),
            code="element_domain_mismatch",
            field_path="snapshot.element_id",
            message="element_id prefix must match domain_id",
        )
    _require_int(collector, snapshot, "element_number", minimum=1)
    _require_string(collector, snapshot, "title", non_blank=True, max_length=300)
    for name in (
        "topic_name",
        "subtopic_name",
        "core_relation",
        "scope_notes",
        "source_label",
        "source_locator",
        "spec_section_locator",
    ):
        _require_string(collector, snapshot, name, max_length=10000)
    _require_string(collector, snapshot, "mode", non_blank=True, max_length=64)
    _require_int(collector, snapshot, "display_order", minimum=0)
    _require_bool(collector, snapshot, "is_active")
    return entity_id


def _validate_concept(collector: _Collector, snapshot: Mapping[str, Any]) -> str | None:
    entity_id = _require_string(
        collector, snapshot, "concept_id", non_blank=True, max_length=32
    )
    element_id = _require_string(
        collector, snapshot, "element_id", non_blank=True, max_length=24
    )
    collector.check(
        entity_id is not None and CONCEPT_ID.fullmatch(entity_id) is not None,
        code="stable_id_invalid",
        field_path="snapshot.concept_id",
        message="concept_id does not use the stable concept ID format",
    )
    collector.check(
        element_id is not None and ELEMENT_ID.fullmatch(element_id) is not None,
        code="element_id_invalid",
        field_path="snapshot.element_id",
        message="element_id does not use the stable element ID format",
    )
    if entity_id and element_id:
        collector.check(
            entity_id.startswith(f"{element_id}-C"),
            code="concept_element_mismatch",
            field_path="snapshot.concept_id",
            message="concept_id must be stable under its element_id",
        )
    _require_string(collector, snapshot, "title", non_blank=True, max_length=300)
    markdown_values = {
        name: _require_string(
            collector,
            snapshot,
            name,
            non_blank=True,
            max_length=MAX_MARKDOWN_BYTES,
        )
        for name in (
            "definition_markdown",
            "intuition_markdown",
            "learning_notes_markdown",
            "checklist_markdown",
        )
    }
    glossary_terms = _require_list(collector, snapshot, "glossary_terms")
    _validate_glossary_terms(collector, glossary_terms)
    for name, value in markdown_values.items():
        _validate_markdown(collector, f"snapshot.{name}", value)
    definition = markdown_values["definition_markdown"]
    intuition = markdown_values["intuition_markdown"]
    learning_notes = markdown_values["learning_notes_markdown"]
    practical_uses = markdown_values["checklist_markdown"]
    collector.check(
        isinstance(definition, str) and len(definition.strip()) >= 36 and "$$" not in definition,
        code="learning_definition_quality",
        field_path="snapshot.definition_markdown",
        message="definition must be a complete formula-free sentence of at least 36 characters",
    )
    collector.check(
        isinstance(intuition, str)
        and len(intuition.strip()) >= 72
        and "$$" not in intuition
        and "이 개념을 읽는 순서" not in intuition,
        code="learning_intuition_quality",
        field_path="snapshot.intuition_markdown",
        message="intuition must explain this element concretely without generic reading-order copy or formulas",
    )
    collector.check(
        isinstance(learning_notes, str)
        and re.search(r"(?m)^###\s+\S", learning_notes) is not None
        and "$$" not in learning_notes,
        code="learning_application_sections",
        field_path="snapshot.learning_notes_markdown",
        message="application notes must use ### toggle headings and must not repeat the formula",
    )
    collector.check(
        isinstance(practical_uses, str)
        and len(re.findall(r"(?m)^\s*-\s+\S", practical_uses)) >= 2
        and "$$" not in practical_uses,
        code="learning_practical_uses",
        field_path="snapshot.checklist_markdown",
        message="practical uses must contain at least two concrete formula-free list items",
    )
    return entity_id


def _validate_formula(collector: _Collector, snapshot: Mapping[str, Any]) -> str | None:
    entity_id = _require_string(
        collector, snapshot, "formula_id", non_blank=True, max_length=32
    )
    element_id = _require_string(
        collector, snapshot, "element_id", non_blank=True, max_length=24
    )
    formula_key = _require_string(
        collector, snapshot, "formula_key", non_blank=True, max_length=64
    )
    collector.check(
        entity_id is not None and FORMULA_ID.fullmatch(entity_id) is not None,
        code="stable_id_invalid",
        field_path="snapshot.formula_id",
        message="formula_id does not use the stable formula ID format",
    )
    collector.check(
        element_id is not None and ELEMENT_ID.fullmatch(element_id) is not None,
        code="element_id_invalid",
        field_path="snapshot.element_id",
        message="element_id does not use the stable element ID format",
    )
    if entity_id and element_id:
        collector.check(
            entity_id.startswith(f"{element_id}-F"),
            code="formula_element_mismatch",
            field_path="snapshot.formula_id",
            message="formula_id must be stable under its element_id",
        )
    collector.check(
        formula_key is not None and FORMULA_KEY.fullmatch(formula_key) is not None,
        code="formula_key_invalid",
        field_path="snapshot.formula_key",
        message="formula_key does not use the stable key format",
    )
    _require_string(collector, snapshot, "title", non_blank=True, max_length=300)
    markdown_values = {
        "expression_markdown": _require_string(
            collector,
            snapshot,
            "expression_markdown",
            non_blank=True,
            max_length=MAX_MARKDOWN_BYTES,
        ),
        "assumptions_markdown": _require_string(
            collector,
            snapshot,
            "assumptions_markdown",
            max_length=MAX_MARKDOWN_BYTES,
        ),
        "notes_markdown": _require_string(
            collector,
            snapshot,
            "notes_markdown",
            max_length=MAX_MARKDOWN_BYTES,
        ),
    }
    variables = _require_list(collector, snapshot, "variables")
    _validate_formula_variables(collector, variables)
    _require_int(collector, snapshot, "display_order", minimum=0)
    _require_bool(collector, snapshot, "is_primary")
    for name, value in markdown_values.items():
        _validate_markdown(collector, f"snapshot.{name}", value)
    expression = markdown_values["expression_markdown"]
    notes = markdown_values["notes_markdown"]
    collector.check(
        isinstance(expression, str) and "$$" in expression and not expression.lstrip().startswith("### "),
        code="formula_dedicated_card",
        field_path="snapshot.expression_markdown",
        message="the dedicated formula field must contain rendered LaTeX without a redundant outer heading",
    )
    collector.check(
        isinstance(notes, str)
        and len(re.findall(r"(?m)^\s*-\s+\S", notes)) >= 2
        and "$$" not in notes,
        code="formula_practical_uses_projection",
        field_path="snapshot.notes_markdown",
        message="formula notes must mirror the app's practical-use list without repeating the formula",
    )
    return entity_id


def _validate_distractor(
    collector: _Collector, snapshot: Mapping[str, Any]
) -> str | None:
    entity_id = _require_string(
        collector, snapshot, "distractor_id", non_blank=True, max_length=36
    )
    element_id = _require_string(
        collector, snapshot, "element_id", non_blank=True, max_length=24
    )
    try:
        valid_uuid = (
            entity_id is not None and str(uuid.UUID(entity_id)) == entity_id.lower()
        )
    except (ValueError, AttributeError):
        valid_uuid = False
    collector.check(
        valid_uuid,
        code="stable_id_invalid",
        field_path="snapshot.distractor_id",
        message="distractor_id must be a canonical UUID",
    )
    collector.check(
        element_id is not None and ELEMENT_ID.fullmatch(element_id) is not None,
        code="element_id_invalid",
        field_path="snapshot.element_id",
        message="element_id does not use the stable element ID format",
    )
    _require_string(
        collector, snapshot, "distractor_key", non_blank=True, max_length=128
    )
    _require_string(collector, snapshot, "text", non_blank=True, max_length=10000)
    _require_string(collector, snapshot, "explanation", max_length=10000)
    _require_string(collector, snapshot, "misconception_type", max_length=128)
    _require_int(collector, snapshot, "difficulty", minimum=1, maximum=5)
    _require_int(collector, snapshot, "display_order", minimum=0)
    _require_bool(collector, snapshot, "is_enabled")
    return entity_id


ENTITY_VALIDATORS = {
    "domain": _validate_domain,
    "element": _validate_element,
    "concept": _validate_concept,
    "formula": _validate_formula,
    "distractor": _validate_distractor,
}


def validate_revision(revision: Mapping[str, Any]) -> ValidationResult:
    collector = _Collector()
    revision_id = revision.get("revision_id")
    try:
        revision_uuid_valid = (
            str(uuid.UUID(str(revision_id))) == str(revision_id).lower()
        )
    except (ValueError, AttributeError):
        revision_uuid_valid = False
    collector.check(
        revision_uuid_valid,
        code="revision_id_invalid",
        field_path="revision_id",
        message="revision_id must be a canonical UUID",
    )
    entity_type = revision.get("entity_type")
    collector.check(
        entity_type in ENTITY_VALIDATORS,
        code="entity_type_unsupported",
        field_path="entity_type",
        message="revision entity_type is not supported by this validator",
    )
    entity_key = revision.get("entity_key")
    collector.check(
        isinstance(entity_key, str)
        and bool(entity_key.strip())
        and len(entity_key) <= 128,
        code="entity_key_invalid",
        field_path="entity_key",
        message="revision entity_key must be a non-blank stable identifier",
    )
    collector.check(
        _is_int(revision.get("revision_number")) and revision["revision_number"] > 0,
        code="revision_number_invalid",
        field_path="revision_number",
        message="revision_number must be a positive integer",
    )
    collector.check(
        revision.get("operation") in {"insert", "update", "delete"},
        code="revision_operation_invalid",
        field_path="operation",
        message="revision operation is invalid",
    )
    content_hash = revision.get("content_hash")
    collector.check(
        isinstance(content_hash, str) and SHA256.fullmatch(content_hash) is not None,
        code="content_hash_invalid",
        field_path="content_hash",
        message="revision content_hash must be a lowercase SHA-256",
    )

    snapshot = revision.get("snapshot")
    snapshot_is_object = collector.check(
        isinstance(snapshot, dict),
        code="snapshot_invalid",
        field_path="snapshot",
        message="revision snapshot must be a JSON object",
    )
    snapshot_digest = ""
    snapshot_size = 0
    if snapshot_is_object:
        encoded = canonical_json_bytes(snapshot)
        snapshot_size = len(encoded)
        snapshot_digest = hashlib.sha256(encoded).hexdigest()
        collector.check(
            snapshot_size <= MAX_SNAPSHOT_BYTES,
            code="snapshot_too_large",
            field_path="snapshot",
            message="revision snapshot exceeds the validation size limit",
            details={"byteSize": snapshot_size, "maximumBytes": MAX_SNAPSHOT_BYTES},
        )
        depth = _json_depth(snapshot)
        collector.check(
            depth <= MAX_JSON_DEPTH,
            code="snapshot_too_deep",
            field_path="snapshot",
            message="revision snapshot exceeds the JSON nesting limit",
            details={"depth": depth, "maximumDepth": MAX_JSON_DEPTH},
        )
        control = _first_control_character(snapshot)
        collector.check(
            control is None,
            code="control_character_invalid",
            field_path=control[0] if control else "snapshot",
            message="revision snapshot contains a forbidden control character",
            details={"offset": control[1]} if control else None,
        )

        validator = ENTITY_VALIDATORS.get(str(entity_type))
        entity_id = validator(collector, snapshot) if validator else None
        collector.check(
            entity_id is not None and entity_id == entity_key,
            code="revision_entity_key_mismatch",
            field_path="entity_key",
            message="revision entity_key must match the immutable ID in its snapshot",
        )

    status = "failed" if collector.failed else "passed"
    summary = {
        "validatorName": VALIDATOR_NAME,
        "validatorVersion": VALIDATOR_VERSION,
        "entityType": entity_type if isinstance(entity_type, str) else None,
        "entityKey": entity_key if isinstance(entity_key, str) else None,
        "snapshotByteSize": snapshot_size,
        "snapshotCanonicalSha256": snapshot_digest,
        "issueCount": len(collector.issues),
        "errorCount": sum(issue.severity == "error" for issue in collector.issues),
    }
    return ValidationResult(
        status=status,
        checks_total=collector.total,
        checks_passed=collector.passed,
        checks_failed=collector.failed,
        issues=tuple(collector.issues),
        summary=summary,
    )


class SupabaseRestClient:
    def __init__(
        self,
        *,
        base_url: str,
        secret_key: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        try:
            self.base_url = normalize_supabase_url(base_url)
        except SupabaseImportError as error:
            raise ValidationWorkerError(str(error)) from error
        self.secret_key = secret_key.strip()
        if not self.secret_key:
            raise ValidationWorkerError("SUPABASE_SECRET_KEY is missing")
        if not 1.0 <= timeout_seconds <= 60.0:
            raise ValidationWorkerError("timeout must be between 1 and 60 seconds")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        body: bytes | None = None
        headers = {
            "apikey": self.secret_key,
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if len(body) > MAX_HTTP_REQUEST_BYTES:
                raise ValidationWorkerError("Supabase request exceeds the safety limit")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=ssl.create_default_context(),
            ) as response:
                response_body = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            error.read(4096)
            raise ValidationWorkerError(
                f"Supabase {method} {path.split('?', 1)[0]} failed with HTTP {error.code}"
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ValidationWorkerError(
                "Supabase request failed or timed out"
            ) from error
        if len(response_body) > MAX_HTTP_RESPONSE_BYTES:
            raise ValidationWorkerError("Supabase response exceeds the safety limit")
        if not response_body:
            return None
        try:
            return json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationWorkerError("Supabase returned invalid JSON") from error

    def rpc(self, name: str, payload: Mapping[str, Any]) -> Any:
        if name not in {CLAIM_RPC, COMPLETE_RPC, FAIL_RPC}:
            raise ValidationWorkerError("Unsupported worker RPC")
        return self._request("POST", f"/rest/v1/rpc/{name}", dict(payload))

    def select_one(
        self,
        table: str,
        *,
        key: str,
        value: str,
        columns: tuple[str, ...],
    ) -> dict[str, Any]:
        if table not in {"content_revisions", "validation_runs"}:
            raise ValidationWorkerError("Unsupported worker table read")
        try:
            canonical_uuid = str(uuid.UUID(value))
        except ValueError as error:
            raise ValidationWorkerError("Supabase row key must be a UUID") from error
        query = urllib.parse.urlencode(
            {
                "select": ",".join(columns),
                key: f"eq.{canonical_uuid}",
                "limit": "2",
            }
        )
        result = self._request("GET", f"/rest/v1/{table}?{query}")
        if (
            not isinstance(result, list)
            or len(result) != 1
            or not isinstance(result[0], dict)
        ):
            raise ValidationWorkerError(f"Expected exactly one {table} row")
        return result[0]


class ContentValidationWorker:
    def __init__(self, client: SupabaseRestClient, worker_id: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", worker_id) is None:
            raise ValidationWorkerError("worker id is invalid")
        self.client = client
        self.worker_id = worker_id

    @staticmethod
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
        raise ValidationWorkerError(f"{label} RPC returned an unexpected response")

    def process_one(self) -> WorkerOutcome | None:
        claimed = self._rpc_object(
            self.client.rpc(
                CLAIM_RPC,
                {
                    "p_worker_id": self.worker_id,
                    "p_allowed_job_kinds": ["content_validation"],
                },
            ),
            "claim",
        )
        if claimed is None:
            return None

        job_id = str(claimed.get("job_id", ""))
        try:
            uuid.UUID(job_id)
        except ValueError as error:
            raise ValidationWorkerError(
                "claim RPC returned an invalid job id"
            ) from error

        result: ValidationResult | None = None
        try:
            revision_id = str(claimed.get("revision_id", ""))
            job_input = claimed.get("input")
            validation_run_id = (
                str(job_input.get("validationRunId", ""))
                if isinstance(job_input, dict)
                else ""
            )
            uuid.UUID(revision_id)
            uuid.UUID(validation_run_id)
            if (
                claimed.get("job_kind") != "content_validation"
                or claimed.get("status") != "running"
            ):
                raise ValidationWorkerError(
                    "claim RPC returned a non-validation or non-running job"
                )
            run = self.client.select_one(
                "validation_runs",
                key="validation_run_id",
                value=validation_run_id,
                columns=(
                    "validation_run_id",
                    "target_type",
                    "revision_id",
                    "status",
                    "validator_name",
                    "validator_version",
                ),
            )
            if (
                run.get("status") != "running"
                or run.get("target_type") != "revision"
                or str(run.get("revision_id")) != revision_id
                or run.get("validator_name") != VALIDATOR_NAME
                or run.get("validator_version") != VALIDATOR_VERSION
            ):
                raise ValidationWorkerError(
                    "claimed validation run target or validator contract is inconsistent"
                )
            revision = self.client.select_one(
                "content_revisions",
                key="revision_id",
                value=revision_id,
                columns=(
                    "revision_id",
                    "entity_type",
                    "entity_key",
                    "revision_number",
                    "operation",
                    "snapshot",
                    "content_hash",
                ),
            )
            result = validate_revision(revision)
            self.client.rpc(
                COMPLETE_RPC,
                {
                    "p_job_id": job_id,
                    "p_worker_id": self.worker_id,
                    "p_validation_run_id": validation_run_id,
                    "p_validation_status": result.status,
                    "p_checks_total": result.checks_total,
                    "p_checks_passed": result.checks_passed,
                    "p_checks_failed": result.checks_failed,
                    "p_summary": result.summary,
                    "p_issues": [issue.as_rpc() for issue in result.issues],
                    "p_output": {
                        "validatorName": VALIDATOR_NAME,
                        "validatorVersion": VALIDATOR_VERSION,
                        "snapshotCanonicalSha256": result.summary[
                            "snapshotCanonicalSha256"
                        ],
                    },
                },
            )
        except Exception as error:
            safe_message = str(error).replace(self.client.secret_key, "[redacted]")[
                :1000
            ]
            if not safe_message:
                safe_message = error.__class__.__name__
            try:
                terminal = self._rpc_object(
                    self.client.rpc(
                        FAIL_RPC,
                        {
                            "p_job_id": job_id,
                            "p_worker_id": self.worker_id,
                            "p_error_message": safe_message,
                            "p_output": {
                                "validatorName": VALIDATOR_NAME,
                                "validatorVersion": VALIDATOR_VERSION,
                                "failureType": error.__class__.__name__,
                            },
                        },
                    ),
                    "failure reconciliation",
                )
            except Exception as failure_error:
                raise ValidationWorkerError(
                    "validation failed and its claimed job could not be marked failed"
                ) from failure_error
            if terminal is not None and terminal.get("jobStatus") == "succeeded":
                if result is None:
                    raise ValidationWorkerError(
                        "validation completion was committed but its local result is unavailable"
                    ) from error
                return WorkerOutcome(
                    job_id=job_id,
                    revision_id=revision_id,
                    validation_run_id=validation_run_id,
                    validation_status=result.status,
                    checks_total=result.checks_total,
                    checks_failed=result.checks_failed,
                )
            raise ValidationWorkerError(
                "claimed validation job failed safely"
            ) from error

        return WorkerOutcome(
            job_id=job_id,
            revision_id=revision_id,
            validation_run_id=validation_run_id,
            validation_status=result.status,
            checks_total=result.checks_total,
            checks_failed=result.checks_failed,
        )


def default_worker_id() -> str:
    hostname = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:48] or "host"
    return f"findone-validator:{hostname}:{os.getpid()}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", default=default_worker_id())
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    client = SupabaseRestClient(
        base_url=os.environ.get("SUPABASE_URL", ""),
        secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
        timeout_seconds=args.timeout,
    )
    outcome = ContentValidationWorker(client, args.worker_id).process_one()
    if outcome is None:
        print(json.dumps({"status": "idle"}, sort_keys=True))
    else:
        print(json.dumps(outcome.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationWorkerError, ValueError) as error:
        print(f"Validation worker stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
