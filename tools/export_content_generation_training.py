#!/usr/bin/env python3
"""Export only human-approved, released generation examples as JSONL."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.admin_import_supabase import resolve_supabase_url
from tools.admin_release_worker import SupabaseReleaseClient, canonical_json_bytes


class TrainingExportError(RuntimeError):
    """Raised when approved training examples cannot be exported safely."""


def _in_filter(values: Sequence[str]) -> str:
    if not values:
        raise TrainingExportError("training export filter cannot be empty")
    return "in.(" + ",".join(values) + ")"


def build_training_record(
    batch: Mapping[str, Any],
    item: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    fragments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if batch.get("status") != "released" or not item.get("revision_id"):
        raise TrainingExportError("only released, human-approved generation items may be exported")
    evidence_rows: list[dict[str, Any]] = []
    for row in evidence:
        fragment_id = str(row.get("source_fragment_id", ""))
        fragment = fragments.get(fragment_id)
        if fragment is None:
            raise TrainingExportError("approved generation evidence is incomplete")
        evidence_rows.append(
            {
                "fieldPath": row.get("field_path"),
                "sourceFragmentId": fragment_id,
                "locator": fragment.get("locator", {}),
                "text": str(fragment.get("content_text", ""))[:4000],
                "rationale": row.get("rationale", ""),
            }
        )
    if not evidence_rows:
        raise TrainingExportError("approved generation item has no field evidence")
    return {
        "schema": "findone-content-training-v1",
        "input": {
            "entityType": item.get("entity_type"),
            "entityKey": item.get("entity_key"),
            "elementId": item.get("element_id"),
            "baselineSnapshot": item.get("baseline_snapshot"),
            "sourceEvidence": evidence_rows,
        },
        "idealOutput": {
            "generatedSnapshot": item.get("generated_snapshot"),
            "changedFields": item.get("changed_fields"),
            "changeSummary": item.get("change_summary", ""),
        },
        "metadata": {
            "generationBatchId": batch.get("batch_id"),
            "revisionId": item.get("revision_id"),
            "releaseId": batch.get("release_id"),
            "modelName": batch.get("model_name"),
            "promptVersion": batch.get("prompt_version"),
            "riskLevel": item.get("risk_level"),
            "confidence": item.get("confidence"),
        },
    }


def export_records(client: SupabaseReleaseClient, limit: int = 5000) -> list[dict[str, Any]]:
    batches = client.select(
        "content_generation_batches",
        columns=("batch_id", "status", "release_id", "model_name", "prompt_version"),
        filters={"status": "eq.released"},
        order="completed_at.asc",
        limit=1000,
    )
    if not batches:
        return []
    batch_ids = [str(row["batch_id"]) for row in batches]
    items = client.select(
        "content_generation_items",
        columns=(
            "generation_item_id", "batch_id", "element_id", "entity_type", "entity_key",
            "baseline_snapshot", "generated_snapshot", "changed_fields", "change_summary",
            "confidence", "risk_level", "revision_id",
        ),
        filters={"batch_id": _in_filter(batch_ids), "revision_id": "not.is.null"},
        order="created_at.asc",
        limit=limit,
    )
    if not items:
        return []
    item_ids = [str(row["generation_item_id"]) for row in items]
    evidence = client.select(
        "content_generation_evidence",
        columns=(
            "generation_item_id", "field_path", "source_fragment_id", "rationale",
        ),
        filters={"generation_item_id": _in_filter(item_ids)},
        order="created_at.asc",
        limit=min(20_000, limit * 20),
    )
    fragment_ids = sorted({str(row["source_fragment_id"]) for row in evidence})
    fragments = client.select(
        "source_fragments",
        columns=("source_fragment_id", "locator", "content_text"),
        filters={"source_fragment_id": _in_filter(fragment_ids)},
        limit=len(fragment_ids),
        max_bytes=64 * 1024 * 1024,
    ) if fragment_ids else []

    batches_by_id = {str(row["batch_id"]): row for row in batches}
    fragments_by_id = {str(row["source_fragment_id"]): row for row in fragments}
    evidence_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        evidence_by_item[str(row["generation_item_id"])].append(row)
    return [
        build_training_record(
            batches_by_id[str(item["batch_id"])],
            item,
            evidence_by_item[str(item["generation_item_id"])],
            fragments_by_id,
        )
        for item in items
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limit < 1 or args.limit > 5000:
        raise TrainingExportError("--limit must be between 1 and 5000")
    client = SupabaseReleaseClient(
        resolve_supabase_url(),
        os.environ.get("SUPABASE_SECRET_KEY", ""),
        timeout_seconds=args.timeout,
    )
    records = export_records(client, args.limit)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        for record in records:
            stream.write(canonical_json_bytes(record))
    print(json.dumps({"status": "exported", "records": len(records), "output": str(output)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TrainingExportError, ValueError, OSError) as error:
        raise SystemExit(f"Training export stopped: {error}") from error
