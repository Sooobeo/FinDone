#!/usr/bin/env python3
"""Build the compact, offline FinDone knowledge database from the app spec.

The script deliberately uses only the Python standard library.  It parses the
canonical element sections and tables in ``finance_interview_app_final_spec.md``,
writes a deterministic SQLite release asset, validates its invariants, and then
emits the SHA-256 manifest consumed by ``ContentRepository`` on Android.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "finance_interview_app_final_spec.md"
DEFAULT_ASSET_DIR = ROOT / "app" / "src" / "main" / "assets"

SCHEMA_VERSION = 1
CONTENT_DB_VERSION = 1
DOMAIN_ORDER = ("ACC", "CF", "INV", "FI", "DER", "EQV", "IBT")
EXPECTED_DOMAIN_COUNTS = {
    "ACC": 12,
    "CF": 12,
    "INV": 9,
    "FI": 10,
    "DER": 10,
    "EQV": 64,
    "IBT": 18,
}
DOMAIN_COLOR_TOKENS = {
    "ACC": "research.default",
    "CF": "analysis.default",
    "INV": "insight.default",
    "FI": "research.dark",
    "DER": "analysis.dark",
    "EQV": "insight.dark",
    "IBT": "outlineStrong",
}

# EQV-20~64 are intentionally specified as formula/scope rows rather than as
# element headings.  These labels are the concise UI names of those canonical
# rows; every formula, scope, source, and locator is still parsed from the spec.
TABLE_TITLE_OVERRIDES = {
    "EQV-20": "매출 브리지",
    "EQV-21": "가격·물량 매출 브리지",
    "EQV-22": "사업부 믹스·연결 EBIT",
    "EQV-23": "ARR·NRR·GRR",
    "EQV-24": "CAC·LTV·회수기간",
    "EQV-25": "점포 매출·단위경제성",
    "EQV-26": "GMV·Take Rate·공헌이익",
    "EQV-27": "가동률·손익분기점",
    "EQV-28": "Backlog·Book-to-Bill",
    "EQV-29": "발생액비율·현금전환",
    "EQV-30": "운전자본 일수·현금전환주기",
    "EQV-31": "Billings·계약자산·계약부채",
    "EQV-32": "재고회전율·충당률",
    "EQV-33": "R&D 자산화·순설비투자",
    "EQV-34": "정상화 영업이익·일회성 조정",
    "EQV-35": "주식보상·희석주식수",
    "EQV-36": "리스 조정 순부채",
    "EQV-37": "연금 적립상태",
    "EQV-38": "실효세율·NOL",
    "EQV-39": "영업권",
    "EQV-40": "보통주 지분가치 브리지",
    "EQV-41": "ROIC·투하자본",
    "EQV-42": "ROIC 마진·회전율 분해",
    "EQV-43": "증분 ROIC",
    "EQV-44": "5단계 DuPont",
    "EQV-45": "성장·재투자",
    "EQV-46": "EVA·가치 스프레드",
    "EQV-47": "FCFF·FCFE·잔여이익",
    "EQV-48": "재무제표 롤포워드",
    "EQV-49": "계속가치·안정기 재투자",
    "EQV-50": "Mid-year·Stub 할인",
    "EQV-51": "Reverse DCF",
    "EQV-52": "가치평가 배수 일치",
    "EQV-53": "SOTP",
    "EQV-54": "시나리오·민감도",
    "EQV-55": "은행 수익성·NIM",
    "EQV-56": "은행 충당금·CET1·ROTCE",
    "EQV-57": "손해보험 손해율·합산비율",
    "EQV-58": "생명보험 CSM·지급여력",
    "EQV-59": "경기민감·원자재 정상화",
    "EQV-60": "자원기업 NAV·매장량수명",
    "EQV-61": "추정치 괴리·실적 서프라이즈",
    "EQV-62": "기대 TSR·촉매",
    "EQV-63": "기대손실·유동성 런웨이",
    "EQV-64": "주주환원수익률·자본배분",
}

HEADING_ELEMENT_RE = re.compile(
    r"^###\s+(ACC|CF|INV|FI|DER)-(\d{2})\.\s+(.+?)\s*$"
)
TABLE_ELEMENT_RE = re.compile(
    r"^\|\s+\*\*((EQV|IBT)-(\d{2}))(?:\s+([^*]+?))?\*\*\s+\|"
)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)]\(([^)]+)\)")
SOURCE_CODE_RE = re.compile(r"\b(?:R|ER|BOOK|RIGHT|AI|SCOPE|KOCW)-[A-Z0-9-]+\b")


@dataclass(frozen=True)
class DomainDraft:
    domain_id: str
    name: str
    description: str
    count: int


@dataclass(frozen=True)
class SourceDraft:
    source_id: str
    label: str
    locator: str
    source_type: str
    notes: str


@dataclass(frozen=True)
class ElementDraft:
    element_id: str
    domain_id: str
    number: int
    title: str
    mode: str
    core_relation: str
    scope_notes: str
    source_ids: tuple[str, ...]
    spec_section_locator: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_markdown_row(line: str) -> list[str]:
    """Split a simple Markdown table row, ignoring pipes inside code spans."""
    row = line.strip()
    if not row.startswith("|") or not row.endswith("|"):
        raise ValueError(f"Not a Markdown table row: {line[:80]!r}")
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    escaped = False
    for character in row[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == "`":
            current.append(character)
            in_code = not in_code
        elif character == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip())
    return cells


def clean_inline_markdown(value: str) -> str:
    value = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), value)
    value = re.sub(r"<([^>]+)>", r"\1", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t-:")


def clean_markdown_block(lines: Iterable[str]) -> str:
    output: list[str] = []
    for original in lines:
        line = original.strip()
        if not line or line.startswith("###"):
            continue
        line = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        line = re.sub(r"^\s*-\s*", "• ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            output.append(line)
    return "\n".join(output)


def markdown_links(value: str) -> list[tuple[str, str]]:
    return [(label.strip(), locator.strip()) for label, locator in MARKDOWN_LINK_RE.findall(value)]


def infer_source_type(locator: str, source_id: str = "") -> str:
    lower = locator.lower()
    if source_id.startswith("RIGHT-"):
        return "license"
    if lower.endswith(".pdf") or ".pdf?" in lower:
        return "pdf"
    if "api" in lower or source_id.endswith("-API"):
        return "api"
    if source_id.startswith("BOOK-"):
        return "book"
    if locator.startswith("finance_interview_app_final_spec.md"):
        return "local_spec"
    return "web"


def heading_paths(lines: Sequence[str]) -> list[str]:
    paths: list[str] = []
    stack: dict[int, str] = {}
    for line in lines:
        match = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            stack[level] = clean_inline_markdown(match.group(2))
            for old_level in tuple(stack):
                if old_level > level:
                    del stack[old_level]
        paths.append(" > ".join(stack[level] for level in sorted(stack)))
    return paths


def parse_domains(lines: Sequence[str]) -> list[DomainDraft]:
    start = next(i for i, line in enumerate(lines) if line.startswith("### 5.1 "))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## A. "))
    domains: dict[str, DomainDraft] = {}
    for line in lines[start:end]:
        if not line.startswith("|"):
            continue
        cells = split_markdown_row(line)
        if len(cells) != 3:
            continue
        id_match = re.search(r"`(ACC|CF|INV|FI|DER|EQV|IBT)-", cells[1])
        count_text = clean_inline_markdown(cells[2])
        if not id_match or not count_text.isdigit():
            continue
        domain_id = id_match.group(1)
        domains[domain_id] = DomainDraft(
            domain_id=domain_id,
            name=clean_inline_markdown(cells[0]),
            description=clean_inline_markdown(cells[1]),
            count=int(count_text),
        )
    if tuple(domain for domain in DOMAIN_ORDER if domain in domains) != DOMAIN_ORDER:
        raise ValueError(f"Expected domains {DOMAIN_ORDER}, parsed {tuple(domains)}")
    result = [domains[domain] for domain in DOMAIN_ORDER]
    for domain in result:
        expected = EXPECTED_DOMAIN_COUNTS[domain.domain_id]
        if domain.count != expected:
            raise ValueError(
                f"{domain.domain_id} summary says {domain.count}; expected {expected}"
            )
    return result


def parse_source_registry(lines: Sequence[str]) -> dict[str, SourceDraft]:
    sources: dict[str, SourceDraft] = {
        "SPEC-FINAL": SourceDraft(
            source_id="SPEC-FINAL",
            label="Finance Interview 앱 최종 명세",
            locator="finance_interview_app_final_spec.md",
            source_type="local_spec",
            notes="요소 정의, 핵심 관계, 범위 및 원문 절 위치의 기준 문서",
        )
    }
    in_source_section = False
    for line in lines:
        if line.startswith("## 8. "):
            in_source_section = True
            continue
        if line.startswith("## 9. "):
            break
        if not in_source_section or not line.startswith("|"):
            continue
        cells = split_markdown_row(line)
        if len(cells) < 2:
            continue
        id_match = re.fullmatch(r"`([A-Z][A-Z0-9-]+)`", cells[0].strip())
        if not id_match:
            continue
        source_id = id_match.group(1)
        links = markdown_links(cells[1])
        label = clean_inline_markdown(cells[1]) or source_id
        locator = links[0][1] if links else ""
        notes = clean_inline_markdown(" · ".join(cells[2:])) if len(cells) > 2 else ""
        sources[source_id] = SourceDraft(
            source_id=source_id,
            label=label,
            locator=locator,
            source_type=infer_source_type(locator, source_id),
            notes=notes,
        )
    return sources


def register_url_sources(
    links: Sequence[tuple[str, str]], sources: dict[str, SourceDraft]
) -> tuple[str, ...]:
    locator_to_id = {
        source.locator: source_id for source_id, source in sources.items() if source.locator
    }
    result: list[str] = []
    for label, locator in links:
        source_id = locator_to_id.get(locator)
        if source_id is None:
            source_id = "URL-" + hashlib.sha1(locator.encode("utf-8")).hexdigest()[:12].upper()
            sources[source_id] = SourceDraft(
                source_id=source_id,
                label=label,
                locator=locator,
                source_type=infer_source_type(locator),
                notes="명세의 요소별 참고자료",
            )
            locator_to_id[locator] = source_id
        if source_id not in result:
            result.append(source_id)
    return tuple(result)


def extract_core_relation(block: Sequence[str], element_id: str) -> str:
    for index, line in enumerate(block):
        match = re.match(
            r"^-\s+\*\*개념·수식(?::)?\*\*:?\s*(.*)$",
            line.strip(),
        )
        if not match:
            continue
        parts = [match.group(1).strip()] if match.group(1).strip() else []
        for continuation in block[index + 1 :]:
            stripped = continuation.strip()
            if stripped.startswith("- **유형") or stripped.startswith("- **참고"):
                break
            if stripped.startswith("- **"):
                break
            if stripped:
                parts.append(stripped)
        relation = clean_markdown_block(parts)
        if relation:
            return relation
    raise ValueError(f"{element_id} has no concept/formula block")


def parse_heading_elements(
    lines: Sequence[str], paths: Sequence[str], sources: dict[str, SourceDraft]
) -> list[ElementDraft]:
    heading_indices = [i for i, line in enumerate(lines) if HEADING_ELEMENT_RE.match(line)]
    elements: list[ElementDraft] = []
    for heading_index in heading_indices:
        match = HEADING_ELEMENT_RE.match(lines[heading_index])
        assert match is not None
        domain_id, number_text, raw_title = match.groups()
        end = heading_index + 1
        while end < len(lines) and not lines[end].startswith("### ") and not lines[end].startswith("## "):
            end += 1
        block = lines[heading_index + 1 : end]
        element_id = f"{domain_id}-{number_text}"
        reference_lines = [
            line for line in block if line.strip().startswith("- **참고")
        ]
        source_ids = register_url_sources(
            [link for line in reference_lines for link in markdown_links(line)], sources
        )
        if not source_ids:
            source_ids = ("SPEC-FINAL",)
        scope_lines = [line for line in block if line not in reference_lines]
        elements.append(
            ElementDraft(
                element_id=element_id,
                domain_id=domain_id,
                number=int(number_text),
                title=clean_inline_markdown(raw_title),
                mode="calculation",
                core_relation=extract_core_relation(block, element_id),
                scope_notes=clean_markdown_block(scope_lines),
                source_ids=source_ids,
                spec_section_locator=(
                    f"finance_interview_app_final_spec.md:L{heading_index + 1} · "
                    f"{paths[heading_index]}"
                ),
            )
        )
    return elements


def infer_table_title(element_id: str, raw_core: str) -> str:
    if element_id in TABLE_TITLE_OVERRIDES:
        return TABLE_TITLE_OVERRIDES[element_id]
    clean = clean_inline_markdown(raw_core)
    for separator in (":", "："):
        if separator in clean:
            return clean.split(separator, 1)[0].strip()
    return clean


def parse_table_elements(
    lines: Sequence[str], paths: Sequence[str], sources: dict[str, SourceDraft]
) -> list[ElementDraft]:
    elements: list[ElementDraft] = []
    for line_index, line in enumerate(lines):
        match = TABLE_ELEMENT_RE.match(line)
        if not match:
            continue
        element_id, domain_id, number_text, raw_mode = match.groups()
        cells = split_markdown_row(line)
        if len(cells) != 5:
            raise ValueError(f"{element_id} row has {len(cells)} cells, expected 5")
        raw_core, raw_problem, raw_params, raw_sources = cells[1:]
        source_ids = tuple(dict.fromkeys(SOURCE_CODE_RE.findall(raw_sources)))
        missing_sources = [source_id for source_id in source_ids if source_id not in sources]
        if missing_sources:
            raise ValueError(f"{element_id} uses unknown sources: {missing_sources}")
        if not source_ids:
            source_ids = register_url_sources(markdown_links(raw_sources), sources)
        if not source_ids:
            source_ids = ("SPEC-FINAL",)
        mode = clean_inline_markdown(raw_mode or "calculation")
        scope_notes = "\n".join(
            (
                f"출제 범위: {clean_inline_markdown(raw_problem)}",
                f"생성·검증 메모: {clean_inline_markdown(raw_params)}",
            )
        )
        elements.append(
            ElementDraft(
                element_id=element_id,
                domain_id=domain_id,
                number=int(number_text),
                title=infer_table_title(element_id, raw_core),
                mode=mode,
                core_relation=clean_inline_markdown(raw_core),
                scope_notes=scope_notes,
                source_ids=source_ids,
                spec_section_locator=(
                    f"finance_interview_app_final_spec.md:L{line_index + 1} · "
                    f"{paths[line_index]} > {element_id}"
                ),
            )
        )
    return elements


def validate_parsed_content(domains: Sequence[DomainDraft], elements: Sequence[ElementDraft]) -> None:
    if len(domains) != len(DOMAIN_ORDER):
        raise ValueError(f"Expected 7 domains, found {len(domains)}")
    if len(elements) != sum(EXPECTED_DOMAIN_COUNTS.values()):
        raise ValueError(f"Expected 135 elements, found {len(elements)}")
    ids = [element.element_id for element in elements]
    if len(ids) != len(set(ids)):
        duplicates = sorted({element_id for element_id in ids if ids.count(element_id) > 1})
        raise ValueError(f"Duplicate element IDs: {duplicates}")
    for domain_id, expected_count in EXPECTED_DOMAIN_COUNTS.items():
        domain_elements = sorted(
            (element for element in elements if element.domain_id == domain_id),
            key=lambda element: element.number,
        )
        expected_ids = [f"{domain_id}-{number:02d}" for number in range(1, expected_count + 1)]
        actual_ids = [element.element_id for element in domain_elements]
        if actual_ids != expected_ids:
            raise ValueError(
                f"{domain_id} ID sequence differs: expected {expected_ids}, got {actual_ids}"
            )
        for element in domain_elements:
            if not all(
                (
                    element.title,
                    element.core_relation,
                    element.scope_notes,
                    element.spec_section_locator,
                )
            ):
                raise ValueError(f"{element.element_id} has an empty required content field")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA page_size = 4096;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE domains (
    domain_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    element_count INTEGER NOT NULL CHECK (element_count > 0),
    display_order INTEGER NOT NULL UNIQUE,
    color_token TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY NOT NULL,
    label TEXT NOT NULL,
    locator TEXT NOT NULL,
    source_type TEXT NOT NULL,
    notes TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE elements (
    element_id TEXT PRIMARY KEY NOT NULL,
    domain_id TEXT NOT NULL REFERENCES domains(domain_id),
    element_number INTEGER NOT NULL CHECK (element_number > 0),
    title TEXT NOT NULL,
    mode TEXT NOT NULL,
    core_relation TEXT NOT NULL,
    scope_notes TEXT NOT NULL,
    source_label TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    spec_section_locator TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    UNIQUE (domain_id, element_number)
);

CREATE TABLE concept_cards (
    concept_id TEXT PRIMARY KEY NOT NULL,
    element_id TEXT NOT NULL UNIQUE REFERENCES elements(element_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    definition TEXT NOT NULL,
    intuition TEXT NOT NULL,
    scope_notes TEXT NOT NULL,
    source_ids_json TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE formula_cards (
    formula_id TEXT PRIMARY KEY NOT NULL,
    element_id TEXT NOT NULL UNIQUE REFERENCES elements(element_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    expression TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    notes TEXT NOT NULL,
    source_ids_json TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE element_sources (
    element_id TEXT NOT NULL REFERENCES elements(element_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (element_id, source_id)
) WITHOUT ROWID;

CREATE INDEX elements_domain_order_idx
    ON elements(domain_id, display_order);
CREATE INDEX element_sources_source_idx
    ON element_sources(source_id, element_id);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    element_id UNINDEXED,
    domain_id UNINDEXED,
    title,
    normalized_text,
    source_label,
    locator_text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def build_database(
    output_path: Path,
    spec_path: Path,
    spec_sha256: str,
    domains: Sequence[DomainDraft],
    elements: Sequence[ElementDraft],
    sources: dict[str, SourceDraft],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=output_path.name + ".", suffix=".tmp", dir=output_path.parent
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()
    try:
        database = sqlite3.connect(temporary_path)
        try:
            database.executescript(SCHEMA_SQL)
            database.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            database.execute("PRAGMA application_id = 1179534414")  # ASCII-ish FNDN
            database.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                (
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("content_db_version", str(CONTENT_DB_VERSION)),
                    ("source_spec", spec_path.name),
                    ("source_spec_sha256", spec_sha256),
                    ("generator", "tools/build_content_db.py"),
                    ("domain_count", str(len(domains))),
                    ("element_count", str(len(elements))),
                ),
            )
            database.executemany(
                """
                INSERT INTO domains(
                    domain_id, name, description, element_count, display_order, color_token
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        domain.domain_id,
                        domain.name,
                        domain.description,
                        domain.count,
                        order,
                        DOMAIN_COLOR_TOKENS[domain.domain_id],
                    )
                    for order, domain in enumerate(domains)
                ),
            )
            database.executemany(
                """
                INSERT INTO sources(source_id, label, locator, source_type, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        source.source_id,
                        source.label,
                        source.locator,
                        source.source_type,
                        source.notes,
                    )
                    for source in sorted(sources.values(), key=lambda source: source.source_id)
                ),
            )

            domain_display_order = {domain_id: index for index, domain_id in enumerate(DOMAIN_ORDER)}
            ordered_elements = sorted(
                elements,
                key=lambda element: (domain_display_order[element.domain_id], element.number),
            )
            for display_order, element in enumerate(ordered_elements):
                primary_source = sources[element.source_ids[0]]
                source_ids_json = json.dumps(
                    element.source_ids, ensure_ascii=False, separators=(",", ":")
                )
                database.execute(
                    """
                    INSERT INTO elements(
                        element_id, domain_id, element_number, title, mode,
                        core_relation, scope_notes, source_label, source_locator,
                        spec_section_locator, display_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        element.element_id,
                        element.domain_id,
                        element.number,
                        element.title,
                        element.mode,
                        element.core_relation,
                        element.scope_notes,
                        primary_source.label,
                        primary_source.locator,
                        element.spec_section_locator,
                        display_order,
                    ),
                )
                database.execute(
                    """
                    INSERT INTO concept_cards(
                        concept_id, element_id, title, definition, intuition,
                        scope_notes, source_ids_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{element.element_id}-C01",
                        element.element_id,
                        element.title,
                        element.core_relation,
                        element.scope_notes.splitlines()[0],
                        element.scope_notes,
                        source_ids_json,
                    ),
                )
                database.execute(
                    """
                    INSERT INTO formula_cards(
                        formula_id, element_id, title, expression, assumptions,
                        notes, source_ids_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{element.element_id}-F01",
                        element.element_id,
                        element.title,
                        element.core_relation,
                        "명세에 적힌 단위·기간·모형 가정을 적용한다.",
                        element.scope_notes,
                        source_ids_json,
                    ),
                )
                database.executemany(
                    """
                    INSERT INTO element_sources(element_id, source_id, ordinal)
                    VALUES (?, ?, ?)
                    """,
                    (
                        (element.element_id, source_id, ordinal)
                        for ordinal, source_id in enumerate(element.source_ids)
                    ),
                )
                search_text = "\n".join(
                    (
                        element.element_id,
                        element.title,
                        element.core_relation,
                        element.scope_notes,
                    )
                )
                database.execute(
                    """
                    INSERT INTO knowledge_fts(
                        element_id, domain_id, title, normalized_text,
                        source_label, locator_text
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        element.element_id,
                        element.domain_id,
                        element.title,
                        search_text,
                        primary_source.label,
                        f"{primary_source.locator} {element.spec_section_locator}",
                    ),
                )
            database.commit()
            database.execute("PRAGMA optimize")
            database.execute("VACUUM")
        finally:
            database.close()
        validate_database(temporary_path)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def query_count(database: sqlite3.Connection, table: str) -> int:
    return int(database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def validate_database(path: Path) -> dict[str, int]:
    database = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite integrity_check failed: {integrity}")
        foreign_key_errors = database.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise ValueError(f"SQLite foreign_key_check failed: {foreign_key_errors[:3]}")
        if database.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise ValueError("Unexpected SQLite user_version")
        row_counts = {
            table: query_count(database, table)
            for table in (
                "metadata",
                "domains",
                "elements",
                "concept_cards",
                "formula_cards",
                "sources",
                "element_sources",
                "knowledge_fts",
            )
        }
        expected_fixed = {
            "domains": 7,
            "elements": 135,
            "concept_cards": 135,
            "formula_cards": 135,
            "knowledge_fts": 135,
        }
        for table, expected in expected_fixed.items():
            if row_counts[table] != expected:
                raise ValueError(f"{table}: expected {expected}, found {row_counts[table]}")
        actual_domain_counts = dict(
            database.execute(
                "SELECT domain_id, COUNT(*) FROM elements GROUP BY domain_id"
            ).fetchall()
        )
        if actual_domain_counts != EXPECTED_DOMAIN_COUNTS:
            raise ValueError(
                f"Domain element counts differ: {actual_domain_counts}"
            )
        duplicate_fts = database.execute(
            """
            SELECT element_id, COUNT(*) AS n
            FROM knowledge_fts
            GROUP BY element_id
            HAVING n != 1
            """
        ).fetchall()
        if duplicate_fts:
            raise ValueError(f"FTS projection is not one row per element: {duplicate_fts[:3]}")
        return row_counts
    finally:
        database.close()


def write_manifest(
    manifest_path: Path,
    database_path: Path,
    spec_path: Path,
    spec_sha256: str,
    row_counts: dict[str, int],
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "manifestVersion": 1,
        "schemaVersion": SCHEMA_VERSION,
        "contentDbVersion": CONTENT_DB_VERSION,
        "databaseAsset": database_path.name,
        "sha256": sha256_file(database_path),
        "byteSize": database_path.stat().st_size,
        "sourceSpec": spec_path.name,
        "sourceSha256": spec_sha256,
        "rowCounts": row_counts,
        "domainElementCounts": EXPECTED_DOMAIN_COUNTS,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=manifest_path.name + ".", suffix=".tmp", dir=manifest_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, manifest_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return manifest


def parse_spec(spec_path: Path) -> tuple[
    list[DomainDraft], list[ElementDraft], dict[str, SourceDraft], str
]:
    spec_bytes = spec_path.read_bytes()
    text = spec_bytes.decode("utf-8")
    lines = text.splitlines()
    paths = heading_paths(lines)
    domains = parse_domains(lines)
    sources = parse_source_registry(lines)
    elements = parse_heading_elements(lines, paths, sources)
    elements.extend(parse_table_elements(lines, paths, sources))
    validate_parsed_content(domains, elements)
    return domains, elements, sources, sha256_bytes(spec_bytes)


def build(spec_path: Path, asset_dir: Path) -> dict[str, object]:
    domains, elements, sources, spec_sha256 = parse_spec(spec_path)
    database_path = asset_dir / "content.sqlite3"
    manifest_path = asset_dir / "content-manifest.json"
    build_database(
        database_path,
        spec_path,
        spec_sha256,
        domains,
        elements,
        sources,
    )
    row_counts = validate_database(database_path)
    return write_manifest(
        manifest_path,
        database_path,
        spec_path,
        spec_sha256,
        row_counts,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    args = parser.parse_args()
    manifest = build(args.spec.resolve(), args.asset_dir.resolve())
    counts = manifest["domainElementCounts"]
    print(
        "Built content.sqlite3: "
        f"{manifest['rowCounts']['domains']} domains, "
        f"{manifest['rowCounts']['elements']} elements "
        f"({', '.join(f'{key}={value}' for key, value in counts.items())}), "
        f"sha256={manifest['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
