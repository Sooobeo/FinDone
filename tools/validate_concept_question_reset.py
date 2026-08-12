#!/usr/bin/env python3
"""Validate the intentional empty state between concept-question v1 and v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "admin" / "data" / "concept-model-experiments.generated.json"
DESIGN = ROOT / "docs" / "modeling" / "CONCEPT_MCQ_MODELING_DESIGN.md"
EXPERIMENTS = ROOT / "docs" / "modeling" / "experiments"
QUESTION_BANK = ROOT / "content" / "model" / "concept-question-bank.generated.json"
AUDIT_FILES = (
    ROOT / "content" / "model" / "concept-owner-decisions.jsonl",
    ROOT / "content" / "model" / "concept-question-edits.jsonl",
)


class ConceptQuestionResetError(RuntimeError):
    """Raised when deprecated v1 state leaks into the v2 reset state."""


def _display_path(path: Path, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.resolve().as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConceptQuestionResetError(
            f"Could not read reset JSON: {_display_path(path)}"
        ) from error
    if not isinstance(value, dict):
        raise ConceptQuestionResetError(
            f"Reset JSON must be an object: {_display_path(path)}"
        )
    return value


def validate_reset_state(root: Path = ROOT) -> dict[str, Any]:
    report_path = root / REPORT.relative_to(ROOT)
    design_path = root / DESIGN.relative_to(ROOT)
    experiments_path = root / EXPERIMENTS.relative_to(ROOT)
    question_bank_path = root / QUESTION_BANK.relative_to(ROOT)

    report = _read_json(report_path)
    if report.get("reportVersion") != 2 or report.get("contractVersion") != "2.0":
        raise ConceptQuestionResetError("Admin report is not the v2 reset contract")
    if report.get("latestExperimentId") is not None or report.get("experiments") != []:
        raise ConceptQuestionResetError("Admin report still contains a concept-model experiment")
    if not isinstance(report.get("resetAt"), str) or not report["resetAt"].strip():
        raise ConceptQuestionResetError("Admin report has no reset timestamp")

    stale_reports = sorted(experiments_path.glob("cmq-*.md")) if experiments_path.exists() else []
    if stale_reports:
        names = ", ".join(path.name for path in stale_reports[:3])
        raise ConceptQuestionResetError(f"Deprecated v1 experiment reports remain: {names}")

    for configured_path in AUDIT_FILES:
        path = root / configured_path.relative_to(ROOT)
        if path.exists() and path.read_text(encoding="utf-8").strip():
            raise ConceptQuestionResetError(
                f"Deprecated v1 audit rows remain: {_display_path(path, root)}"
            )

    try:
        design = design_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConceptQuestionResetError("Could not read the v2 modeling design") from error
    required_contract_terms = (
        "term_to_definition",
        "term_to_intuition",
        "term_to_verbal_relation",
        "용어 → 설명",
        "수식 없이 말로 풀어쓴 설명",
    )
    missing_terms = [term for term in required_contract_terms if term not in design]
    if missing_terms:
        raise ConceptQuestionResetError(
            "The v2 modeling design is missing contract terms: " + ", ".join(missing_terms)
        )

    legacy_bank = _read_json(question_bank_path)
    legacy_status = legacy_bank.get("releaseStatus")
    if legacy_status == "release_ready":
        raise ConceptQuestionResetError(
            "The compatibility question bank must remain blocked during the v2 reset"
        )

    return {
        "contractVersion": report["contractVersion"],
        "experimentCount": 0,
        "localAuditRowCount": 0,
        "legacyCompatibilityBankStatus": legacy_status,
        "releaseReady": False,
        "state": "awaiting_v2_implementation",
    }


def main() -> int:
    try:
        result = validate_reset_state()
    except ConceptQuestionResetError as error:
        print(f"Concept-question reset validation failed: {error}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
