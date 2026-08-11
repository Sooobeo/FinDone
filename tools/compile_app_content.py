#!/usr/bin/env python3
"""Compile, benchmark, and score the offline FinDone app-content database.

The command never calls an external model API.  It runs the canonical MD/JSON
builder repeatedly to prove deterministic output, evaluates the checked-in
local mapping rules against a golden set, applies quality gates, writes the
Admin model report, and only then promotes ``content.sqlite3`` and its manifest.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_content_db
from tools import local_content_model


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "admin" / "data" / "local-content-model-report.generated.json"
DEFAULT_ASSET_DIR = ROOT / "app" / "src" / "main" / "assets"
REPORT_VERSION = 1


class CompilationError(RuntimeError):
    """Raised when a quality gate prevents candidate promotion."""


class ProgressBar:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def update(self, percent: int, label: str) -> None:
        if not self.enabled:
            return
        bounded = max(0, min(100, int(percent)))
        filled = int(bounded / 5)
        bar = "#" * filled + "-" * (20 - filled)
        print(f"[{bar}] {bounded:3d}%  {label}", flush=True)


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def _wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    observed = successes / total
    denominator = 1 + z * z / total
    center = observed + z * z / (2 * total)
    margin = z * math.sqrt((observed * (1 - observed) + z * z / (4 * total)) / total)
    return round(max(0.0, (center - margin) / denominator), 6)


def inspect_database(path: Path) -> dict[str, Any]:
    database = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        build_content_db.validate_database(path)
        row_counts = {
            table: int(database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in (
                "domains",
                "sources",
                "elements",
                "concept_cards",
                "formula_cards",
                "element_sources",
                "knowledge_fts",
            )
        }
        required_queries = (
            ("elements", ("title", "core_relation", "scope_notes", "source_label", "source_locator", "spec_section_locator")),
            ("concept_cards", ("title", "definition", "intuition", "scope_notes", "source_ids_json")),
            ("formula_cards", ("title", "expression", "assumptions", "notes", "source_ids_json")),
        )
        required_total = 0
        required_resolved = 0
        for table, fields in required_queries:
            count = row_counts[table]
            for field in fields:
                required_total += count
                required_resolved += int(
                    database.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE length(trim("{field}")) > 0'
                    ).fetchone()[0]
                )
        traced_elements = int(
            database.execute(
                "SELECT COUNT(*) FROM (SELECT element_id FROM element_sources GROUP BY element_id HAVING COUNT(*) >= 1)"
            ).fetchone()[0]
        )
        multiple_source_elements = int(
            database.execute(
                "SELECT COUNT(*) FROM (SELECT element_id FROM element_sources GROUP BY element_id HAVING COUNT(*) >= 2)"
            ).fetchone()[0]
        )
        source_types = {
            str(source_type): int(count)
            for source_type, count in database.execute(
                "SELECT source_type, COUNT(*) FROM sources GROUP BY source_type ORDER BY source_type"
            )
        }
        return {
            "rowCounts": row_counts,
            "requiredFieldCount": required_total,
            "resolvedRequiredFieldCount": required_resolved,
            "requiredFieldCoverage": _ratio(required_resolved, required_total),
            "tracedElementCount": traced_elements,
            "sourceTraceability": _ratio(traced_elements, row_counts["elements"]),
            "multipleSourceElementCount": multiple_source_elements,
            "multipleSourceCoverage": _ratio(multiple_source_elements, row_counts["elements"]),
            "sourceTypes": source_types,
        }
    finally:
        database.close()


def _gate(
    gate_id: str,
    label: str,
    measured: float | bool,
    threshold: float | bool,
    passed: bool,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "label": label,
        "measured": measured,
        "threshold": threshold,
        "passed": passed,
    }


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
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


def compile_and_measure(
    *,
    spec_path: Path = build_content_db.DEFAULT_SPEC,
    asset_dir: Path = DEFAULT_ASSET_DIR,
    report_path: Path = DEFAULT_REPORT,
    model_config_path: Path = local_content_model.DEFAULT_MODEL_CONFIG,
    golden_set_path: Path = local_content_model.DEFAULT_GOLDEN_SET,
    benchmark_rounds: int = 3,
    promote: bool = True,
    progress: ProgressBar | None = None,
) -> dict[str, Any]:
    if benchmark_rounds < 2 or benchmark_rounds > 10:
        raise CompilationError("benchmark rounds must be between 2 and 10")
    renderer = progress or ProgressBar(False)
    renderer.update(3, "로컬 변환 규칙과 품질 게이트 읽는 중")
    config = local_content_model.load_model_config(model_config_path)
    golden = local_content_model.evaluate_golden_set(config, golden_set_path)

    renderer.update(12, "기존 앱 DB 기준점 확인 중")
    old_manifest = _read_manifest(asset_dir / "content-manifest.json")
    old_sha = str(old_manifest.get("sha256", "")) if old_manifest else ""
    durations_ms: list[float] = []
    manifests: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="findone-local-content-") as directory_name:
        directory = Path(directory_name)
        for index in range(benchmark_rounds):
            renderer.update(
                18 + int(index / benchmark_rounds * 48),
                f"결정론적 앱 DB 빌드 {index + 1}/{benchmark_rounds}",
            )
            round_dir = directory / f"round-{index + 1}"
            started = time.perf_counter()
            manifest = build_content_db.build(spec_path.resolve(), round_dir)
            durations_ms.append((time.perf_counter() - started) * 1000)
            manifests.append(manifest)

        hashes = [str(manifest["sha256"]) for manifest in manifests]
        deterministic = len(set(hashes)) == 1
        candidate_dir = directory / f"round-{benchmark_rounds}"
        candidate_db = candidate_dir / "content.sqlite3"
        candidate_manifest = candidate_dir / "content-manifest.json"
        renderer.update(70, "SQLite 무결성·필드·출처 추적률 측정 중")
        database_metrics = inspect_database(candidate_db)

        element_count = int(database_metrics["rowCounts"]["elements"])
        expected_count = sum(build_content_db.EXPECTED_DOMAIN_COUNTS.values())
        corpus_coverage = _ratio(element_count, expected_count)
        field_coverage = float(database_metrics["requiredFieldCoverage"])
        source_traceability = float(database_metrics["sourceTraceability"])
        golden_accuracy = float(golden.field_accuracy)
        gates_config = config.get("qualityGates")
        weights = config.get("readinessWeights")
        if not isinstance(gates_config, Mapping) or not isinstance(weights, Mapping):
            raise CompilationError("model quality gates or readiness weights are missing")
        gates = [
            _gate(
                "corpus-coverage",
                "검토된 콘텐츠 코퍼스 커버리지",
                corpus_coverage,
                float(gates_config["minimumCorpusCoverage"]),
                corpus_coverage >= float(gates_config["minimumCorpusCoverage"]),
            ),
            _gate(
                "required-fields",
                "앱 필수 필드 완성률",
                field_coverage,
                float(gates_config["minimumRequiredFieldCoverage"]),
                field_coverage >= float(gates_config["minimumRequiredFieldCoverage"]),
            ),
            _gate(
                "source-traceability",
                "요소별 출처 추적률",
                source_traceability,
                float(gates_config["minimumSourceTraceability"]),
                source_traceability >= float(gates_config["minimumSourceTraceability"]),
            ),
            _gate(
                "golden-field-accuracy",
                "골든셋 필드 매핑 정확도",
                golden_accuracy,
                float(gates_config["minimumGoldenFieldAccuracy"]),
                golden_accuracy >= float(gates_config["minimumGoldenFieldAccuracy"]),
            ),
            _gate(
                "deterministic-build",
                "반복 빌드 SHA-256 일치",
                deterministic,
                bool(gates_config["requireDeterministicBuild"]),
                deterministic or not bool(gates_config["requireDeterministicBuild"]),
            ),
        ]
        readiness = round(
            100
            * (
                corpus_coverage * float(weights["corpusCoverage"])
                + field_coverage * float(weights["requiredFieldCoverage"])
                + source_traceability * float(weights["sourceTraceability"])
                + golden_accuracy * float(weights["goldenFieldAccuracy"])
                + (1.0 if deterministic else 0.0) * float(weights["deterministicBuild"])
            ),
            2,
        )
        median_ms = statistics.median(durations_ms)
        report: dict[str, Any] = {
            "reportVersion": REPORT_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "status": "passed" if all(gate["passed"] for gate in gates) else "failed",
            "model": {
                "name": "FinDone Local Content Model",
                "version": config["modelVersion"],
                "schemaVersion": config.get("schemaVersion", 1),
                "type": "deterministic-rule-model",
                "externalLlmApiCalls": 0,
                "supportedAdapters": list(local_content_model.supported_adapter_names()),
            },
            "training": {
                "metricDefinition": "ML 가중치 학습률이 아니라 검토 코퍼스·규칙·평가 통과 비율을 합성한 로컬 모델 준비도",
                "readinessScore": readiness,
                "reviewedContentDatabaseCount": 1,
                "reviewedElementCount": element_count,
                "domainCount": int(database_metrics["rowCounts"]["domains"]),
                "structuredLearningCopyFileCount": len(list(build_content_db.LEARNING_COPY_DIR.glob("*.json"))),
                "cataloguedSourceCount": int(database_metrics["rowCounts"]["sources"]),
                "cataloguedWebSourceCount": int(database_metrics["sourceTypes"].get("web", 0)),
                "sourceReferenceCount": int(database_metrics["rowCounts"]["element_sources"]),
                "corpusCoverage": corpus_coverage,
                "requiredFieldCoverage": field_coverage,
                "sourceTraceability": source_traceability,
                "multipleSourceCoverage": database_metrics["multipleSourceCoverage"],
            },
            "evaluation": {
                **golden.as_dict(),
                "caseAccuracyWilson95LowerBound": _wilson_lower_bound(golden.passed_cases, golden.case_count),
                "fieldAccuracyWilson95LowerBound": _wilson_lower_bound(
                    golden.passed_field_assertions,
                    golden.field_assertion_count,
                ),
                "deterministicBuild": deterministic,
                "buildHashes": hashes,
                "qualityGates": gates,
            },
            "performance": {
                "benchmarkRounds": benchmark_rounds,
                "buildDurationsMs": [round(value, 2) for value in durations_ms],
                "medianBuildMs": round(median_ms, 2),
                "minimumBuildMs": round(min(durations_ms), 2),
                "maximumBuildMs": round(max(durations_ms), 2),
                "elementsPerSecond": round(element_count / (median_ms / 1000), 2),
                "databaseByteSize": candidate_db.stat().st_size,
                "databaseSha256": hashes[-1],
            },
            "content": {
                "contentDbVersion": manifests[-1]["contentDbVersion"],
                "schemaVersion": manifests[-1]["schemaVersion"],
                "changedFromPackagedBaseline": bool(old_sha and old_sha != hashes[-1]),
                "previousDatabaseSha256": old_sha or None,
                "rowCounts": database_metrics["rowCounts"],
                "sourceTypes": database_metrics["sourceTypes"],
                "requiredFieldCount": database_metrics["requiredFieldCount"],
                "resolvedRequiredFieldCount": database_metrics["resolvedRequiredFieldCount"],
                "tracedElementCount": database_metrics["tracedElementCount"],
                "multipleSourceElementCount": database_metrics["multipleSourceElementCount"],
            },
        }
        renderer.update(86, "모델 준비도·성능 리포트 생성 중")
        _atomic_json(report_path, report)
        if report["status"] != "passed":
            renderer.update(100, "품질 게이트 실패 — 앱 DB 승격 중단")
            failed = ", ".join(gate["label"] for gate in gates if not gate["passed"])
            raise CompilationError(f"quality gates failed: {failed}")
        if promote:
            renderer.update(94, "검증된 후보를 앱 내장 DB로 승격 중")
            _atomic_copy(candidate_db, asset_dir / "content.sqlite3")
            _atomic_copy(candidate_manifest, asset_dir / "content-manifest.json")
        renderer.update(100, "로컬 앱 콘텐츠 컴파일 완료")
        return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=build_content_db.DEFAULT_SPEC)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model-config", type=Path, default=local_content_model.DEFAULT_MODEL_CONFIG)
    parser.add_argument("--golden-set", type=Path, default=local_content_model.DEFAULT_GOLDEN_SET)
    parser.add_argument("--benchmark-rounds", type=int, default=3)
    parser.add_argument("--check", action="store_true", help="Measure and report without promoting app assets")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = compile_and_measure(
        spec_path=args.spec,
        asset_dir=args.asset_dir,
        report_path=args.report,
        model_config_path=args.model_config,
        golden_set_path=args.golden_set,
        benchmark_rounds=args.benchmark_rounds,
        promote=not args.check,
        progress=ProgressBar(not args.quiet),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "modelVersion": report["model"]["version"],
                "readinessScore": report["training"]["readinessScore"],
                "goldenFieldAccuracy": report["evaluation"]["fieldAccuracy"],
                "medianBuildMs": report["performance"]["medianBuildMs"],
                "databaseSha256": report["performance"]["databaseSha256"],
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
    except (CompilationError, local_content_model.LocalContentModelError, ValueError, OSError) as error:
        print(f"Local app-content compilation stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
