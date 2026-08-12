#!/usr/bin/env python3
"""Inspect and record Owner decisions for the concept-question exception queue."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.admin_import_supabase import normalize_supabase_url, resolve_supabase_url


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "admin" / "data" / "concept-model-experiments.generated.json"
DEFAULT_DECISIONS = ROOT / "content" / "model" / "concept-owner-decisions.jsonl"
MAX_SYNC_RESPONSE_BYTES = 1024 * 1024


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


def merge_remote_question_decisions(
    experiment: Mapping[str, Any],
    existing_rows: list[dict[str, Any]],
    remote_rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Merge exact-fingerprint Supabase decisions without duplicating audit rows."""

    current = {
        (str(item.get("questionId")), str(item.get("questionFingerprint")))
        for item in _queue(experiment)
    }
    seen_ids = {
        str(row.get("sourceDecisionId"))
        for row in existing_rows
        if row.get("sourceDecisionId")
    }
    merged = list(existing_rows)
    added = 0
    review = experiment.get("automatedReview")
    review_input_sha = str(review.get("reviewInputSha256", "")) if isinstance(review, Mapping) else ""
    for remote in remote_rows:
        source_id = str(remote.get("concept_question_review_decision_id", ""))
        question_id = str(remote.get("question_id", ""))
        fingerprint = str(remote.get("question_fingerprint", ""))
        decision = str(remote.get("decision", ""))
        if not source_id or source_id in seen_ids:
            continue
        if (question_id, fingerprint) not in current or decision not in {"approved", "rejected"}:
            continue
        merged.append(
            {
                "type": "question",
                "questionId": question_id,
                "questionFingerprint": fingerprint,
                "reviewInputSha256": review_input_sha,
                "decision": decision,
                "reviewerId": str(remote.get("reviewer_id", "owner")),
                "reviewedAt": str(remote.get("decided_at", "")),
                "comment": str(remote.get("comment", "")),
                "source": "supabase-admin",
                "sourceDecisionId": source_id,
            }
        )
        seen_ids.add(source_id)
        added += 1
    return merged, added


def append_auto_batch_if_complete(
    experiment: Mapping[str, Any], rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool]:
    """Bind batch approval once every current exception was explicitly approved."""

    review = experiment.get("automatedReview")
    review_input_sha = str(review.get("reviewInputSha256", "")) if isinstance(review, Mapping) else ""
    queue = _queue(experiment)
    latest_decisions = _latest_question_decisions(rows)
    all_approved = bool(queue) and all(
        latest_decisions.get(
            (str(item.get("questionId")), str(item.get("questionFingerprint")))
        )
        == "approved"
        for item in queue
    )
    already_approved = any(
        row.get("type") == "batch"
        and row.get("reviewInputSha256") == review_input_sha
        and row.get("decision") == "approved"
        for row in rows
    )
    if (
        not all_approved
        or any(item.get("severity") == "block" for item in queue)
        or already_approved
    ):
        return rows, False
    result = list(rows)
    result.append(
        {
            "type": "batch",
            "reviewInputSha256": review_input_sha,
            "decision": "approved",
            "reviewerId": "supabase-owner-review",
            "reviewedAt": datetime.now(timezone.utc).isoformat(),
            "comment": "Admin에서 현재 fingerprint의 모든 예외 승인 완료",
            "source": "supabase-admin-auto-batch",
        }
    )
    return result, True


def sync_from_supabase(
    experiment: Mapping[str, Any],
    decisions_path: Path,
    *,
    base_url: str,
    secret_key: str,
    timeout_seconds: float,
) -> None:
    review = experiment.get("automatedReview")
    review_input_sha = str(review.get("reviewInputSha256", "")) if isinstance(review, Mapping) else ""
    if len(review_input_sha) != 64:
        raise ReviewCommandError("Latest experiment has no valid review input fingerprint")
    secret = secret_key.strip()
    if not secret:
        raise ReviewCommandError(
            "SUPABASE_SECRET_KEY is missing; supply it through the process environment"
        )
    query = urllib.parse.urlencode(
        {
            "select": (
                "concept_question_review_decision_id,question_id,question_fingerprint,"
                "decision,comment,reviewer_id,decided_at"
            ),
            "review_input_sha256": f"eq.{review_input_sha}",
            "order": "decided_at.asc",
        }
    )
    url = (
        normalize_supabase_url(base_url)
        + "/rest/v1/concept_question_review_decisions?"
        + query
    )
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"apikey": secret, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as response:
            body = response.read(MAX_SYNC_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(2048).decode("utf-8", errors="replace")
        raise ReviewCommandError(
            f"Supabase review sync failed with HTTP {error.code}: {detail}"
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ReviewCommandError(f"Could not reach Supabase review decisions: {error}") from error
    if len(body) > MAX_SYNC_RESPONSE_BYTES:
        raise ReviewCommandError("Supabase review decision response exceeded the safety limit")
    try:
        remote_rows = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewCommandError("Supabase review sync returned invalid JSON") from error
    if not isinstance(remote_rows, list) or any(not isinstance(row, dict) for row in remote_rows):
        raise ReviewCommandError("Supabase review sync returned an unexpected payload")
    existing = _read_rows(decisions_path)
    merged, added = merge_remote_question_decisions(experiment, existing, remote_rows)
    merged, auto_batch_approved = append_auto_batch_if_complete(experiment, merged)
    if added or auto_batch_approved:
        _write_rows(decisions_path, merged)
    print(
        json.dumps(
            {
                "reviewInputSha256": review_input_sha,
                "remoteDecisionCount": len(remote_rows),
                "addedDecisionCount": added,
                "autoBatchApproved": auto_batch_approved,
                "decisionsPath": str(decisions_path),
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
    sync = subparsers.add_parser("sync")
    sync.add_argument("--timeout", type=float, default=30.0)
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
    elif args.command == "sync":
        sync_from_supabase(
            experiment,
            args.decisions,
            base_url=resolve_supabase_url(),
            secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
            timeout_seconds=args.timeout,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
