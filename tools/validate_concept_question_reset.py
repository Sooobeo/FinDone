#!/usr/bin/env python3
"""Validate the active concept-question v2 modeling contract and artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import train_concept_question_model as model


REPORT = ROOT / "admin" / "data" / "concept-model-experiments.generated.json"
DESIGN = ROOT / "docs" / "modeling" / "CONCEPT_MCQ_MODELING_DESIGN.md"
EXPERIMENTS = ROOT / "docs" / "modeling" / "experiments"
QUESTION_BANK = ROOT / "content" / "model" / "concept-question-bank.generated.json"


class ConceptQuestionResetError(RuntimeError):
    """Backward-compatible error name for a v2 contract validation failure."""


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
            f"Could not read v2 JSON: {_display_path(path)}"
        ) from error
    if not isinstance(value, dict):
        raise ConceptQuestionResetError(
            f"v2 JSON must be an object: {_display_path(path)}"
        )
    return value


def _stable_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def validate_reset_state(root: Path = ROOT) -> dict[str, Any]:
    """Validate v2 and retain the historical callable used by repository tests."""
    report_path = root / REPORT.relative_to(ROOT)
    design_path = root / DESIGN.relative_to(ROOT)
    experiments_path = root / EXPERIMENTS.relative_to(ROOT)
    question_bank_path = root / QUESTION_BANK.relative_to(ROOT)

    report = _read_json(report_path)
    if report.get("reportVersion") != 2 or report.get("contractVersion") != "2.0":
        raise ConceptQuestionResetError("Admin report is not the v2 contract")
    experiments = report.get("experiments")
    latest_id = report.get("latestExperimentId")
    if not isinstance(experiments, list) or not experiments or not isinstance(latest_id, str):
        raise ConceptQuestionResetError("Admin report has no active v2 experiment")
    latest = next(
        (
            item
            for item in experiments
            if isinstance(item, dict) and item.get("experimentId") == latest_id
        ),
        None,
    )
    if latest is None or latest.get("contractVersion") != "2.0":
        raise ConceptQuestionResetError("Latest Admin experiment is not contract v2")
    markdown_report = experiments_path / f"{latest_id}.md"
    if not markdown_report.is_file():
        raise ConceptQuestionResetError(
            f"Latest experiment Markdown is missing: {_display_path(markdown_report, root)}"
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

    bank = _read_json(question_bank_path)
    expected_sha = bank.get("bankSha256")
    unsigned = dict(bank)
    unsigned.pop("bankSha256", None)
    actual_sha = hashlib.sha256(_stable_json_bytes(unsigned)).hexdigest()
    if expected_sha != actual_sha:
        raise ConceptQuestionResetError("v2 question-bank SHA-256 is invalid")
    if bank.get("bankVersion") != 2 or bank.get("contractVersion") != "2.0":
        raise ConceptQuestionResetError("Question bank is not v2")
    if bank.get("releaseStatus") not in {"candidate", "release_ready"}:
        raise ConceptQuestionResetError("v2 question bank has an invalid release status")
    questions = bank.get("questions")
    if not isinstance(questions, list) or len(questions) != 405:
        raise ConceptQuestionResetError("v2 question bank must contain 405 questions")

    elements = {item.element_id: item for item in model.load_elements(root / model.DEFAULT_ELEMENTS.relative_to(ROOT))}
    type_counts: Counter[str] = Counter()
    term_leaks = 0
    formula_choices = 0
    malformed = 0
    for question in questions:
        if not isinstance(question, dict):
            malformed += 1
            continue
        question_type = str(question.get("questionType", ""))
        type_counts[question_type] += 1
        target = elements.get(str(question.get("elementId")))
        choices = question.get("choices")
        if (
            question_type not in model.V2_QUESTION_TYPES
            or target is None
            or not str(question.get("stem", "")).startswith(f"용어: {target.title}\n")
            or not isinstance(choices, list)
            or len(choices) != 5
            or sum(bool(item.get("isCorrect")) for item in choices if isinstance(item, dict)) != 1
        ):
            malformed += 1
            continue
        fact_type = model.fact_type_for_question(question_type)
        for choice in choices:
            if not isinstance(choice, dict):
                malformed += 1
                continue
            source = elements.get(str(choice.get("elementId")))
            text = str(choice.get("text", ""))
            expected_fact_id = f"{choice.get('elementId')}:{fact_type}:01"
            if source is None or choice.get("factId") != expected_fact_id or not text.strip():
                malformed += 1
                continue
            term_leaks += int(model.text_mentions_title(text, source.title))
            if question_type == "term_to_verbal_relation":
                formula_choices += int(bool(model.FORMULA_CHOICE_RE.search(text)))
    if malformed:
        raise ConceptQuestionResetError(f"v2 question bank has {malformed} malformed rows")
    if type_counts != Counter({question_type: 135 for question_type in model.V2_QUESTION_TYPES}):
        raise ConceptQuestionResetError(f"v2 question type coverage differs: {dict(type_counts)}")
    if term_leaks or formula_choices:
        raise ConceptQuestionResetError(
            f"v2 visible-choice safety failed: termLeaks={term_leaks}, formulaChoices={formula_choices}"
        )
    if any(question_type in model.LEGACY_QUESTION_TYPES for question_type in type_counts):
        raise ConceptQuestionResetError("Legacy explanation-to-term questions remain")

    latest_release_ready = bool(latest.get("releaseReady"))
    bank_release_ready = bank.get("releaseStatus") == "release_ready"
    if latest_release_ready != bank_release_ready:
        raise ConceptQuestionResetError("Admin report and question-bank release states differ")

    return {
        "contractVersion": "2.0",
        "experimentCount": len(experiments),
        "latestExperimentId": latest_id,
        "questionCount": len(questions),
        "questionTypes": dict(sorted(type_counts.items())),
        "termLeakCount": term_leaks,
        "formulaChoiceCount": formula_choices,
        "releaseReady": bank_release_ready,
        "state": "release_ready" if bank_release_ready else "candidate_review",
    }


def main() -> int:
    try:
        result = validate_reset_state()
    except ConceptQuestionResetError as error:
        print(f"Concept-question v2 validation failed: {error}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
