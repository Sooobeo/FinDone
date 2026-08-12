#!/usr/bin/env python3
"""Inspect and record Owner decisions for the concept-question exception queue."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "admin" / "data" / "concept-model-experiments.generated.json"
DEFAULT_DECISIONS = ROOT / "content" / "model" / "concept-owner-decisions.jsonl"


class ReviewCommandError(ValueError):
    """Raised when a decision cannot be safely bound to the current review."""


def _load_latest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewCommandError(f"Could not read concept model report: {path}") from error
    experiments = value.get("experiments") if isinstance(value, Mapping) else None
    if not isinstance(experiments, list) or not experiments or not isinstance(experiments[0], dict):
        raise ReviewCommandError("Concept model report has no latest experiment")
    review = experiments[0].get("automatedReview")
    if not isinstance(review, dict):
        raise ReviewCommandError("Latest experiment has no automated review queue")
    return experiments[0]


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReviewCommandError(
                f"Invalid decision JSONL at line {line_number}"
            ) from error
        if not isinstance(value, dict):
            raise ReviewCommandError(f"Decision line {line_number} is not an object")
        rows.append(value)
    return rows


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _queue(experiment: Mapping[str, Any]) -> list[dict[str, Any]]:
    review = experiment.get("automatedReview")
    queue = review.get("queue") if isinstance(review, Mapping) else None
    return [item for item in queue or [] if isinstance(item, dict)]


def _latest_question_decisions(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        if row.get("type", "question") != "question":
            continue
        result[(str(row.get("questionId", "")), str(row.get("questionFingerprint", "")))] = str(
            row.get("decision", "")
        )
    return result


def show(experiment: Mapping[str, Any]) -> None:
    review = experiment["automatedReview"]
    payload = {
        "experimentId": experiment.get("experimentId"),
        "reviewInputSha256": review.get("reviewInputSha256"),
        "selectedProfileId": review.get("selectedProfileId"),
        "autoPassedCount": review.get("autoPassedCount"),
        "needsOwnerReviewCount": review.get("needsOwnerReviewCount"),
        "blockedCount": review.get("blockedCount"),
        "ownerBatchApproved": review.get("ownerBatchApproved"),
        "queue": [
            {
                "questionId": item.get("questionId"),
                "elementId": item.get("elementId"),
                "severity": item.get("severity"),
                "reasons": [reason.get("label") for reason in item.get("reasons", [])],
            }
            for item in _queue(experiment)
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def decide(
    experiment: Mapping[str, Any],
    decisions_path: Path,
    question_id: str,
    decision: str,
    reviewer_id: str,
    comment: str,
) -> None:
    matches = [item for item in _queue(experiment) if item.get("questionId") == question_id]
    if len(matches) != 1:
        raise ReviewCommandError(f"Question is not an unresolved queue item: {question_id}")
    item = matches[0]
    if item.get("severity") == "block" and decision == "approved":
        raise ReviewCommandError("A hard-blocked question cannot be approved; fix and rerun it")
    rows = _read_rows(decisions_path)
    rows.append(
        {
            "type": "question",
            "questionId": question_id,
            "questionFingerprint": item["questionFingerprint"],
            "decision": decision,
            "reviewerId": reviewer_id,
            "reviewedAt": datetime.now(timezone.utc).isoformat(),
            "comment": comment,
        }
    )
    _write_rows(decisions_path, rows)
    print(
        json.dumps(
            {"questionId": question_id, "decision": decision, "rerunRequired": True},
            ensure_ascii=False,
        )
    )


def approve_batch(
    experiment: Mapping[str, Any],
    decisions_path: Path,
    reviewer_id: str,
    comment: str,
) -> None:
    queue = _queue(experiment)
    if any(item.get("severity") == "block" for item in queue):
        raise ReviewCommandError("The current queue contains hard-blocked questions")
    rows = _read_rows(decisions_path)
    decisions = _latest_question_decisions(rows)
    unresolved = [
        str(item.get("questionId"))
        for item in queue
        if decisions.get(
            (str(item.get("questionId")), str(item.get("questionFingerprint")))
        )
        != "approved"
    ]
    if unresolved:
        raise ReviewCommandError(
            "Approve every exception before the batch: " + ", ".join(unresolved[:10])
        )
    review = experiment["automatedReview"]
    rows.append(
        {
            "type": "batch",
            "reviewInputSha256": review["reviewInputSha256"],
            "decision": "approved",
            "reviewerId": reviewer_id,
            "reviewedAt": datetime.now(timezone.utc).isoformat(),
            "comment": comment,
        }
    )
    _write_rows(decisions_path, rows)
    print(
        json.dumps(
            {
                "reviewInputSha256": review["reviewInputSha256"],
                "decision": "approved",
                "rerunRequired": True,
            },
            ensure_ascii=False,
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    decision = subparsers.add_parser("decide")
    decision.add_argument("--question-id", required=True)
    decision.add_argument("--decision", choices=("approved", "rejected"), required=True)
    decision.add_argument("--reviewer", default="owner")
    decision.add_argument("--comment", default="")
    batch = subparsers.add_parser("approve-batch")
    batch.add_argument("--reviewer", default="owner")
    batch.add_argument("--comment", default="자동 검수 예외 확인 완료")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    experiment = _load_latest(args.report)
    if args.command == "show":
        show(experiment)
    elif args.command == "decide":
        decide(
            experiment,
            args.decisions,
            args.question_id,
            args.decision,
            args.reviewer,
            args.comment,
        )
    elif args.command == "approve-batch":
        approve_batch(
            experiment, args.decisions, args.reviewer, args.comment
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
