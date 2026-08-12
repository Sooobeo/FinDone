#!/usr/bin/env python3
"""Generate the authored glossary catalog with isolated, resumable Codex batches.

The generator is a PC/Admin authoring tool. Its output is reviewed and compiled into a
static SQLite pack; no model code, credentials, prompts, or remote calls enter Android.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.glossary_content import (
    CONCEPT_TYPES,
    DEFAULT_CATALOG,
    DEFAULT_INVENTORY,
    GlossaryContentError,
    JURISDICTIONS,
    canonical_json_bytes,
    catalog_from_batches,
    chunks,
    inventory_term_payload,
    load_catalog,
    parse_inventory,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH_DIR = ROOT / "content" / "glossary" / "agent-batches"
DEFAULT_REVIEW_OVERRIDES = ROOT / "content" / "glossary" / "agent-review-overrides.json"
DEFAULT_BATCH_SIZE = 25
JURISDICTION_ALIASES = {
    "글로벌": "GLOBAL",
    "전세계": "GLOBAL",
    "대한민국": "KR",
    "한국": "KR",
    "미국": "US",
    "United States": "US",
    "US GAAP": "US",
    "유럽연합": "EU",
    "유럽": "EU",
    "영국": "UK",
    "United Kingdom": "UK",
    "일본": "JP",
    "중국": "CN",
    "다국가": "MULTI",
    "국제": "MULTI",
    "International": "MULTI",
    "South Korea": "KR",
    "관할 의존": "MULTI",
    "국제 실무": "MULTI",
    "캐나다": "MULTI",
    "아일랜드": "EU",
    "IFRS": "GLOBAL",
    "IFRS/K-IFRS": "MULTI",
    "MULTI_JURISDICTION": "MULTI",
    "국가별 규제체계": "MULTI",
    "글로벌(IFRS 중심)": "GLOBAL",
    "대한민국(K-IFRS)": "KR",
    "발행·판매 관할": "MULTI",
    "배출권거래제 관할": "MULTI",
}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "termId",
                    "categoryId",
                    "conceptType",
                    "oneLineDefinitionKo",
                    "coreDefinitionKo",
                    "practicalContextKo",
                    "whyItMattersKo",
                    "exampleKo",
                    "limitationsKo",
                    "sourceCodes",
                    "jurisdictions",
                    "asOfDate",
                    "reviewStatus",
                    "reviewFlags",
                    "relatedTermIds",
                    "formulaLatex",
                    "formulaNotesKo",
                ],
                "properties": {
                    "termId": {"type": "string"},
                    "categoryId": {"type": "string"},
                    "conceptType": {"type": "string"},
                    "oneLineDefinitionKo": {"type": "string"},
                    "coreDefinitionKo": {"type": "string"},
                    "practicalContextKo": {"type": "string"},
                    "whyItMattersKo": {"type": "string"},
                    "exampleKo": {"type": "string"},
                    "limitationsKo": {"type": "array", "items": {"type": "string"}},
                    "sourceCodes": {"type": "array", "items": {"type": "string"}},
                    "jurisdictions": {"type": "array", "items": {"type": "string"}},
                    "asOfDate": {"type": "string"},
                    "reviewStatus": {"type": "string"},
                    "reviewFlags": {"type": "array", "items": {"type": "string"}},
                    "relatedTermIds": {"type": "array", "items": {"type": "string"}},
                    "formulaLatex": {"type": "string"},
                    "formulaNotesKo": {"type": "string"},
                },
            },
        }
    },
}
REVIEW_OVERRIDE_FIELDS = {
    "conceptType",
    "oneLineDefinitionKo",
    "coreDefinitionKo",
    "practicalContextKo",
    "whyItMattersKo",
    "exampleKo",
    "limitationsKo",
    "sourceCodes",
    "jurisdictions",
    "asOfDate",
    "reviewStatus",
    "reviewFlags",
    "relatedTermIds",
    "formulaLatex",
    "formulaNotesKo",
}


def source_catalog_text(inventory: Any) -> str:
    return "\n".join(
        f"- {source.source_code}: {source.title} — {source.url}"
        for source in inventory.sources
    )


def prompt_for_batch(inventory: Any, terms: list[Any]) -> str:
    return f"""
당신은 FinDone 금융 실무 용어집의 저작 Agent다. 아래 inventory identity는 절대 변경하지 말고,
각 용어의 한국어 의미·실무 문맥·짧은 예시를 독립적으로 작성하라. Android 앱은 결과를 정적
SQLite로만 사용하며 런타임 LLM은 없다.

작성 규칙:
- conceptType은 허용 ontology type 중 정확히 하나를 선택한다.
- oneLineDefinitionKo는 초심자가 이해할 수 있는 완결된 한 문장이다.
- coreDefinitionKo는 경계와 작동 방식을 2~4문장으로 설명한다.
- practicalContextKo는 실제 직무·딜·운용·리스크 업무에서의 사용을 1~3문장으로 설명한다.
- whyItMattersKo와 exampleKo는 구체적이고 짧게 쓴다. 예시는 투자 권유가 아닌 업무/계산 상황이다.
- limitationsKo는 오해, 적용 한계 또는 문맥 차이 한 가지 이상을 쓴다.
- 공식이 명확한 지표만 formulaLatex/formulaNotesKo를 채우고 아니면 빈 문자열로 둔다.
- sourceCodes는 아래 허용 출처 중 핵심 의미를 실제로 뒷받침하는 코드 1~3개만 고른다.
- 최신 규정·공시·관할 의존 항목은 reviewFlags에 human_jurisdiction_review를 넣는다.
- 근거가 불충분하거나 다의어면 추측하지 말고 reviewFlags에 ambiguity_review를 넣는다.
- 입력 batch 안에서 직접 관련된 용어 ID만 relatedTermIds에 넣고, 없으면 빈 배열로 둔다.
- reviewStatus는 agent_reviewed, asOfDate는 2026-08-12로 고정한다.
- 원문 정의를 복제하지 말고 자체 한국어 문장으로 요약한다.
- Markdown 설명이나 코드블록 없이 지정 JSON만 반환한다.

허용 conceptType:
INSTITUTION, BUSINESS_FUNCTION, ORG_UNIT, ROLE, ASSET_CLASS, INSTRUMENT, STRATEGY,
DEAL, PROCESS, ACTIVITY, METHODOLOGY, MODEL, METRIC, ACCOUNTING_CONCEPT, RISK,
EVENT, ARTIFACT, DISCLOSURE, REGULATION, MARKET_INFRA, DATA_SOURCE, IDENTIFIER,
TOOL_SKILL, SECTOR.

허용 출처:
{source_catalog_text(inventory)}

입력 용어:
{json.dumps([inventory_term_payload(term) for term in terms], ensure_ascii=False, indent=2)}
""".strip()


def run_batch(
    inventory: Any,
    terms: list[Any],
    output_path: Path,
    *,
    model: str | None,
    timeout_seconds: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="findone-glossary-agent-") as directory_name:
        directory = Path(directory_name)
        schema_path = directory / "schema.json"
        result_path = directory / "result.json"
        schema_path.write_bytes(canonical_json_bytes(OUTPUT_SCHEMA))
        command = [
            "codex",
            "exec",
            "-",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(result_path),
            "--cd",
            str(directory),
            "--color",
            "never",
        ]
        if model:
            command.extend(("--model", model))
        environment = os.environ.copy()
        completed = subprocess.run(
            command,
            input=prompt_for_batch(inventory, terms),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            env=environment,
            check=False,
        )
        if completed.returncode != 0 or not result_path.is_file():
            detail = (completed.stderr or completed.stdout).strip()[-2000:]
            raise GlossaryContentError(f"Codex glossary batch failed: {detail}")
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GlossaryContentError("Codex glossary batch returned invalid JSON") from error
        validate_batch_result(inventory, terms, result)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_bytes(canonical_json_bytes(result))
        os.replace(temporary, output_path)


def validate_batch_result(inventory: Any, terms: list[Any], result: Any) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        raise GlossaryContentError("Glossary batch must contain an items array")
    items = result["items"]
    if not all(isinstance(item, dict) for item in items):
        raise GlossaryContentError("Glossary batch items must be objects")
    expected_ids = [term.term_id for term in terms]
    actual_ids = [item.get("termId") for item in items]
    if actual_ids != expected_ids:
        raise GlossaryContentError(
            f"Codex glossary batch identity/order mismatch: expected {expected_ids[:2]}..., "
            f"found {actual_ids[:2]}..."
        )
    source_codes = {source.source_code for source in inventory.sources}
    known_term_ids = {term.term_id for term in inventory.terms}
    identity_by_id = {term.term_id: term for term in terms}
    text_minimums = {
        "oneLineDefinitionKo": 18,
        "coreDefinitionKo": 35,
        "practicalContextKo": 18,
        "whyItMattersKo": 12,
        "exampleKo": 15,
    }
    for item in items:
        term_id = str(item["termId"])
        identity = identity_by_id[term_id]
        if isinstance(item.get("conceptType"), str):
            item["conceptType"] = item["conceptType"].strip().upper()
        if isinstance(item.get("reviewStatus"), str):
            item["reviewStatus"] = item["reviewStatus"].strip().lower()
        for normalized_key in ("sourceCodes", "jurisdictions"):
            normalized_values = item.get(normalized_key)
            if isinstance(normalized_values, list):
                item[normalized_key] = [
                    (
                        JURISDICTION_ALIASES.get(value.strip(), value.strip().upper())
                        if normalized_key == "jurisdictions" and isinstance(value, str)
                        else value.strip().upper() if isinstance(value, str) else value
                    )
                    for value in normalized_values
                ]
        if item.get("jurisdictions") == []:
            item["jurisdictions"] = ["GLOBAL"]
            flags = item.get("reviewFlags")
            if isinstance(flags, list) and "jurisdiction_default_review" not in flags:
                flags.append("jurisdiction_default_review")
        related_values = item.get("relatedTermIds")
        if isinstance(related_values, list):
            normalized_related = list(
                dict.fromkeys(
                    value.strip().upper()
                    for value in related_values
                    if isinstance(value, str)
                    and value.strip().upper() != term_id
                    and value.strip().upper() in known_term_ids
                )
            )
            if len(normalized_related) != len(related_values):
                flags = item.get("reviewFlags")
                if isinstance(flags, list) and "related_id_cleanup_review" not in flags:
                    flags.append("related_id_cleanup_review")
            item["relatedTermIds"] = normalized_related
        if item.get("categoryId") != identity.category_id:
            raise GlossaryContentError(f"{term_id}.categoryId differs from inventory")
        if item.get("conceptType") not in CONCEPT_TYPES:
            raise GlossaryContentError(f"{term_id}.conceptType is unsupported")
        if item.get("reviewStatus") != "agent_reviewed" or item.get("asOfDate") != "2026-08-12":
            raise GlossaryContentError(f"{term_id} has invalid review metadata")
        for key, minimum in text_minimums.items():
            value = item.get(key)
            if not isinstance(value, str) or len(value.strip()) < minimum:
                raise GlossaryContentError(f"{term_id}.{key} is incomplete")
            if value.strip() in {"TBD", "TODO", "미작성"} or "..." in value:
                raise GlossaryContentError(f"{term_id}.{key} contains placeholder text")
        list_rules = {
            "limitationsKo": (1, None),
            "sourceCodes": (1, source_codes),
            "jurisdictions": (1, JURISDICTIONS),
            "reviewFlags": (0, None),
            "relatedTermIds": (0, known_term_ids),
        }
        for key, (minimum, allowed) in list_rules.items():
            values = item.get(key)
            if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
                raise GlossaryContentError(f"{term_id}.{key} is not a valid text array")
            if len(values) < minimum or (allowed is not None and any(value not in allowed for value in values)):
                raise GlossaryContentError(f"{term_id}.{key} contains unsupported values")
        if not isinstance(item.get("formulaLatex"), str) or not isinstance(item.get("formulaNotesKo"), str):
            raise GlossaryContentError(f"{term_id} formula fields must be strings")


def apply_review_overrides(catalog: dict[str, Any], path: Path) -> None:
    if not path.is_file():
        return
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlossaryContentError(f"Glossary review overrides are invalid: {path}") from error
    overrides = root.get("overrides") if isinstance(root, dict) and root.get("formatVersion") == 1 else None
    if not isinstance(overrides, dict) or not all(
        isinstance(term_id, str) and isinstance(fields, dict)
        for term_id, fields in overrides.items()
    ):
        raise GlossaryContentError("Glossary review overrides must map term IDs to field objects")
    by_id = {str(term.get("termId")): term for term in catalog["terms"]}
    for term_id, fields in overrides.items():
        if term_id not in by_id:
            raise GlossaryContentError(f"Glossary review override references unknown term: {term_id}")
        unsupported = set(fields) - REVIEW_OVERRIDE_FIELDS
        if unsupported:
            raise GlossaryContentError(
                f"{term_id} review override contains immutable/unsupported fields: "
                f"{', '.join(sorted(unsupported))}"
            )
        by_id[term_id].update(fields)


def merge_batches(
    inventory: Any,
    batch_dir: Path,
    output: Path,
    generation_model: str,
    review_overrides: Path = DEFAULT_REVIEW_OVERRIDES,
) -> None:
    paths = sorted(batch_dir.glob("batch-*.json"))
    if not paths:
        raise GlossaryContentError("No glossary agent batches exist")
    batches = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    catalog = catalog_from_batches(inventory, batches, generation_model=generation_model)
    apply_review_overrides(catalog, review_overrides)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(canonical_json_bytes(catalog))
    os.replace(temporary, output)
    load_catalog(output, inventory=inventory)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "merge", "validate"))
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--review-overrides", type=Path, default=DEFAULT_REVIEW_OVERRIDES)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--model")
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    inventory = parse_inventory(args.inventory)

    if args.command == "validate":
        catalog = load_catalog(args.output, inventory=inventory)
        print(json.dumps({"status": "valid", "terms": len(catalog["terms"])}, ensure_ascii=False))
        return 0
    if args.command == "merge":
        merge_batches(
            inventory,
            args.batch_dir,
            args.output,
            args.model or "codex-authoring-agent",
            args.review_overrides,
        )
        print(json.dumps({"status": "merged", "output": str(args.output)}, ensure_ascii=False))
        return 0

    if args.batch_size < 1 or args.batch_size > 50:
        raise GlossaryContentError("--batch-size must be between 1 and 50")
    if args.workers < 1 or args.workers > 12:
        raise GlossaryContentError("--workers must be between 1 and 12")
    planned = list(chunks(inventory.terms, args.batch_size))
    pending: list[tuple[int, tuple[Any, ...], Path]] = []
    skipped = 0
    for index, term_batch in enumerate(planned, start=1):
        output_path = args.batch_dir / f"batch-{index:04d}.json"
        if output_path.is_file():
            try:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise GlossaryContentError(f"Existing glossary batch is invalid: {output_path}") from error
            original_bytes = canonical_json_bytes(existing)
            validate_batch_result(inventory, list(term_batch), existing)
            normalized_bytes = canonical_json_bytes(existing)
            if normalized_bytes != original_bytes:
                temporary = output_path.with_suffix(output_path.suffix + ".tmp")
                temporary.write_bytes(normalized_bytes)
                os.replace(temporary, output_path)
            skipped += 1
            continue
        pending.append((index, term_batch, output_path))
    if args.max_batches is not None:
        pending = pending[: args.max_batches]

    def generate(item: tuple[int, tuple[Any, ...], Path]) -> tuple[int, int]:
        index, term_batch, output_path = item
        run_batch(
            inventory,
            list(term_batch),
            output_path,
            model=args.model,
            timeout_seconds=args.timeout,
        )
        return index, len(term_batch)

    generated = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(generate, item): item[0] for item in pending}
        for future in concurrent.futures.as_completed(futures):
            index, term_count = future.result()
            generated += 1
            print(
                json.dumps(
                    {"batch": index, "totalBatches": len(planned), "terms": term_count},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    print(json.dumps({"status": "generated", "generated": generated, "skipped": skipped}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GlossaryContentError, OSError, subprocess.SubprocessError) as error:
        print(f"Glossary generation stopped: {error}", file=__import__("sys").stderr)
        raise SystemExit(1) from error
