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
CONTENT_DB_VERSION = 3
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

DOMAIN_INTUITION = {
    "ACC": "재무제표의 숫자가 어떤 인식·측정·분류 과정을 거쳐 만들어지는지 연결하는 개념입니다. 손익 효과와 현금 효과, 일시적 효과와 지속 효과를 구분해 읽는 것이 핵심입니다.",
    "CF": "기업의 현금흐름·위험·자본비용·가치가 어떻게 연결되는지 설명하는 개념입니다. 계산값보다 현금흐름의 시점과 할인율의 기준을 일치시키는 판단이 중요합니다.",
    "INV": "위험을 감수한 대가로 얻는 수익을 측정하고 비교하는 개념입니다. 기대수익과 실현수익, 총위험과 체계적 위험, 절대성과 상대성을 구분해 해석해야 합니다.",
    "FI": "채권의 약정 현금흐름을 금리·신용·유동성 위험과 연결하는 개념입니다. 가격과 수익률의 역관계뿐 아니라 만기·듀레이션·스프레드가 민감도를 어떻게 바꾸는지 보는 것이 핵심입니다.",
    "DER": "기초자산의 미래 가격 위험을 계약 구조와 손익으로 전환하는 개념입니다. 포지션 방향, 만기 손익, 무차익 가정과 헤지 목적을 한 흐름으로 확인해야 합니다.",
    "EQV": "기업의 사업 성과를 재무제표·현금흐름·가치평가로 이어 붙이는 개념입니다. 지표의 분자·분모와 기간을 맞추고, 일회성 요인과 지속 가능한 동인을 분리해야 합니다.",
    "IBT": "거래 구조와 자금 흐름을 기업가치·지분가치·주당가치로 연결하는 개념입니다. 거래 전후 기준, 조달 방식, 희석과 이해관계자별 경제성을 일관되게 추적해야 합니다.",
}

DOMAIN_CHECKLIST = {
    "ACC": ("인식 시점과 측정 기준을 확인한다", "손익·자산/부채·현금흐름 영향을 각각 추적한다", "반대 분개와 롤포워드로 값이 맞는지 검산한다"),
    "CF": ("현금흐름의 시점과 명목/실질 기준을 확인한다", "할인율의 위험·세전/세후·통화 기준을 맞춘다", "가정 변화가 가치에 미치는 방향을 설명한다"),
    "INV": ("수익률의 기간과 벤치마크를 맞춘다", "분산 가능한 위험과 시장 위험을 구분한다", "성과가 위험 조정 후에도 유효한지 확인한다"),
    "FI": ("쿠폰·원금·만기 현금흐름을 먼저 그린다", "금리와 가격의 방향 및 민감도를 확인한다", "국채금리·신용·유동성 스프레드를 분리한다"),
    "DER": ("롱/숏과 권리/의무를 먼저 구분한다", "만기 손익과 현재가치를 분리한다", "무차익 조건과 헤지 후 남는 위험을 확인한다"),
    "EQV": ("지표의 분자·분모·기간을 일치시킨다", "회계 수치에서 반복 가능한 영업 동인을 분리한다", "가정 변화가 실적·현금흐름·가치에 이어지는 경로를 설명한다"),
    "IBT": ("기업가치와 지분가치 브리지를 명시한다", "거래 전후 주식수·순부채·조달조건을 확인한다", "희석·시너지·수수료를 이해관계자별로 검산한다"),
}

KOCW_COURSE_URLS = {
    "finance": "https://www.kocw.net/home/search/kemView.do?kemId=1484248",
    "derivatives": "https://www.kocw.net/home/search/kemView.do?kemId=1367578",
}
KOCW_FINANCE_SOURCE_IDS = {
    "KO-CF-01", "KO-CF-02", "KO-FI-01", "KO-EQV-01", "KO-EQV-02",
    "KO-INV-01", "KO-INV-02",
}
KOCW_DERIVATIVE_SOURCE_IDS = {
    "KO-DER-01", "KO-DER-02", "KO-DER-03", "KO-DER-04", "KO-DER-05", "KO-DER-06",
}
TECHNICAL_AUTHORING_MARKERS = (
    "randInt", "randDec", "randChoice", "파라미터", "정수 보장", "answer-first",
    "생성·검증", "생성 규칙", "reference solver", "MentalMathAudit",
    "rejection sampling", "generation", "generator", "renderer", "seed", "solver",
    "template", "mod ", "중요 생성 원칙", "정수·암산 보장", "암산 보장",
    "tuple", "audit", "fallback", "score ", "Android 계산형",
    "뽑아", "뽑은", "정수화",
)


def contains_authoring_marker(value: str) -> bool:
    normalized = value.casefold()
    return any(marker.casefold() in normalized for marker in TECHNICAL_AUTHORING_MARKERS)


def learning_safe_line(value: str) -> str:
    """Remove an authoring-only line, retaining a factual prefix before its semicolon."""
    stripped = value.strip()
    if not contains_authoring_marker(stripped):
        return stripped
    for separator in (";", "；"):
        if separator not in stripped:
            continue
        factual_prefix = stripped.split(separator, 1)[0].rstrip()
        if factual_prefix and not contains_authoring_marker(factual_prefix):
            return factual_prefix
    return ""

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


PROSE_CLAUSE_SEPARATOR_RE = re.compile(
    r"((?<!\d)[.!?。](?!\d)(?:\s+|$)|;\s*)"
)
BACKTICK_RUN_RE = re.compile(r"`+")


def markdown_code_span(value: str) -> str:
    """Wrap a complete value in a CommonMark code span without losing embedded backticks."""
    longest_run = max((len(match.group(0)) for match in BACKTICK_RUN_RE.finditer(value)), default=0)
    fence = "`" * (longest_run + 1)
    needs_padding = (
        value.startswith("`")
        or value.endswith("`")
        or (value.startswith(" ") and value.endswith(" "))
    )
    return f"{fence} {value} {fence}" if needs_padding else f"{fence}{value}{fence}"


def render_math_in_prose(value: str) -> str:
    """Render complete symbolic sentences while preserving surrounding prose and punctuation."""
    output: list[str] = []
    parts = PROSE_CLAUSE_SEPARATOR_RE.split(value)
    for index, part in enumerate(parts):
        if index % 2 == 1 or not part:
            output.append(part)
            continue
        leading = part[: len(part) - len(part.lstrip())]
        trailing = part[len(part.rstrip()) :]
        clause = part.strip()
        if not clause:
            output.append(part)
            continue
        latex = latex_formula(clause)
        if latex is not None:
            rendered = f"$${latex}$$"
        elif re.search(r"[=≈≤≥<>]", clause):
            rendered = markdown_code_span(clause)
        else:
            rendered = clause
        output.append(leading + rendered + trailing)
    return "".join(output)


def scope_to_markdown(value: str) -> str:
    """Turn the compact spec projection into readable CommonMark without changing facts."""
    output: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[•-]\s*", "- ", line)
        label_match = re.match(r"^- ([^:：]{1,28})([:：])\s*(.*)$", line)
        if label_match is not None:
            label, separator, body = label_match.groups()
            line = f"- **{label.strip()}**{separator} {render_math_in_prose(body)}"
        elif line.startswith("- "):
            line = "- " + render_math_in_prose(line[2:])
        else:
            line = render_math_in_prose(line)
        output.append(line)
    return "\n".join(output)


SYMBOLIC_CLAUSE_RE = re.compile(
    r"[A-Za-z0-9_αβγδμρσλΔΣ∑()\[\]{}+\-−–—×÷*/^%.,=≈≤≥<>²√ ]+"
)
FORMULA_CLAUSE_SEPARATOR_RE = re.compile(r";\s*|\r?\n+|(?<=[.!?。])\s+")


def balanced_delimiters(value: str) -> bool:
    """Require correctly nested (), [], and {}; equal counts alone are insufficient."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for character in value:
        if character in "([{":
            stack.append(character)
        elif character in pairs:
            if not stack or stack.pop() != pairs[character]:
                return False
    return not stack


def matching_delimiter_index(value: str, start: int) -> int | None:
    pairs = {"(": ")", "[": "]", "{": "}"}
    opening = value[start]
    closing = pairs[opening]
    depth = 0
    for index in range(start, len(value)):
        if value[index] == opening:
            depth += 1
        elif value[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def brace_multichar_scripts(value: str) -> str:
    """Brace multi-character subscripts/superscripts without changing their contents."""
    output: list[str] = []
    index = 0
    while index < len(value):
        operator = value[index]
        if operator not in "_^" or index + 1 >= len(value):
            output.append(operator)
            index += 1
            continue
        output.append(operator)
        script_start = index + 1
        next_character = value[script_start]
        if next_character == "{":
            script_end = matching_delimiter_index(value, script_start)
            if script_end is None:
                output.append(value[script_start:])
                break
            output.append(value[script_start : script_end + 1])
            index = script_end + 1
            continue
        if next_character == "(":
            script_end = matching_delimiter_index(value, script_start)
            if script_end is None:
                output.append(value[script_start:])
                break
            output.append("{" + value[script_start : script_end + 1] + "}")
            index = script_end + 1
            continue
        token_match = re.match(
            r"(?:[A-Z]+[0-9]*(?![a-z])|[A-Z][a-z0-9]*|[a-z][a-z0-9]*|[0-9]+)",
            value[script_start:],
        )
        if token_match is None:
            output.append(next_character)
            index += 2
            continue
        token = token_match.group(0)
        output.append("{" + token + "}" if len(token) > 1 else token)
        index = script_start + len(token)
    return "".join(output)


def replace_square_roots(value: str) -> str | None:
    """Convert complete square-root atoms; reject the whole clause when an atom is ambiguous."""
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "√":
            output.append(value[index])
            index += 1
            continue
        atom_start = index + 1
        if atom_start >= len(value):
            return None
        if value[atom_start] == "(":
            atom_end = matching_delimiter_index(value, atom_start)
            if atom_end is None:
                return None
            atom = value[atom_start : atom_end + 1]
        else:
            atom_match = re.match(
                r"(?:[A-Za-zαβγδμρσλΔΣ](?:_[A-Za-z0-9]+)?)",
                value[atom_start:],
            )
            if atom_match is None:
                return None
            atom = atom_match.group(0)
            atom_end = atom_start + len(atom) - 1
        output.append(r"\sqrt{" + atom + "}")
        index = atom_end + 1
    return "".join(output)


def split_formula_clauses(value: str) -> list[str]:
    """Split prose/formula clauses without ever treating a decimal point as a delimiter."""
    clauses = []
    for part in FORMULA_CLAUSE_SEPARATOR_RE.split(value):
        cleaned = re.sub(r"^(?:•|[-+])\s+", "", part.strip())
        if cleaned:
            clauses.append(cleaned)
    return clauses or [value.strip()]


def latex_formula(value: str) -> str | None:
    """Convert a whole, balanced symbolic clause or return None without extracting a fragment."""
    candidate = value.strip()
    if (
        not candidate
        or not re.search(r"[=≈≤≥<>]", candidate)
        or re.search(r"[가-힣]", candidate)
        or SYMBOLIC_CLAUSE_RE.fullmatch(candidate) is None
        or not balanced_delimiters(candidate)
    ):
        return None
    rooted = replace_square_roots(candidate)
    if rooted is None:
        return None
    formula = brace_multichar_scripts(rooted)
    formula = (
        formula.replace("×", r" \times ")
        .replace("÷", r" \div ")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("≈", r" \approx ")
        .replace("≤", r" \le ")
        .replace("≥", r" \ge ")
        .replace("²", "^{2}")
        .replace("%", r"\%")
    )
    greek = {
        "α": r"\alpha ", "β": r"\beta ", "γ": r"\gamma ",
        "δ": r"\delta ", "μ": r"\mu ", "ρ": r"\rho ",
        "σ": r"\sigma ", "λ": r"\lambda ", "Δ": r"\Delta ",
        "Σ": r"\sum ", "∑": r"\sum ",
    }
    for symbol, command in greek.items():
        formula = formula.replace(symbol, command)
    return re.sub(r"\s+", " ", formula).strip()


def formula_to_markdown(value: str) -> str:
    """Render every complete clause as LaTeX or preserve that complete clause as code."""
    return "### 핵심 식과 관계\n\n" + formula_items_markdown(value)


def formula_clause_markdown(value: str) -> str:
    """Render one complete formula clause without ever dropping a fallback clause."""
    latex = latex_formula(value)
    if latex is not None:
        return f"$${latex}$$"
    return markdown_code_span(value)


def formula_items_markdown(value: str, indent: str = "") -> str:
    """Render a relation as Markdown list items suitable for nesting in learning cards."""
    return "\n".join(
        f"{indent}- {formula_clause_markdown(clause)}"
        for clause in split_formula_clauses(value)
    )


def assumption_markdown(element: ElementDraft) -> str:
    keywords = ("가정", "조건", "단 ", "기준", "기간", "단위")
    selected = []
    for raw_line in element.scope_notes.splitlines():
        safe_line = learning_safe_line(raw_line)
        if not safe_line:
            continue
        cleaned = re.sub(r"^[•-]\s*", "", safe_line)
        if cleaned and any(keyword in cleaned for keyword in keywords):
            selected.append(cleaned)
        if len(selected) == 6:
            break
    if not selected:
        selected = [
            "식에 넣는 값의 기간·통화·단위가 서로 같은지 확인합니다.",
            "명목/실질, 세전/세후, 기업가치/지분가치 기준을 섞지 않습니다.",
        ]
    return "### 적용 전 가정\n\n" + "\n".join(f"- {item}" for item in selected)


def concept_definition_markdown(element: ElementDraft) -> str:
    return (
        "### 한 문장 정의\n\n"
        f"**{element.title}**의 핵심은 다음 관계를 정확히 이해하고 설명하는 것입니다.\n\n"
        "**핵심 관계**\n\n"
        f"{formula_items_markdown(element.core_relation)}"
    )


def concept_intuition_markdown(element: ElementDraft) -> str:
    safe_scope_lines = [
        safe_line
        for line in element.scope_notes.splitlines()
        if (safe_line := learning_safe_line(line))
    ]
    application = next(
        (
            re.sub(
                r"^(유형\s*[A-Z가-힣0-9]*\s*[—-]\s*|출제 범위:\s*)",
                "",
                re.sub(r"^[•-]\s*", "", line.strip()),
            ).strip()
            for line in safe_scope_lines
            if line.strip()
            and "개념·수식" not in line
        ),
        f"{element.title}의 정의와 핵심 관계를 실제 금융 자료에 적용하는 상황",
    )
    return (
        "### 왜 중요한가\n\n"
        f"{DOMAIN_INTUITION[element.domain_id]}\n\n"
        f"**{element.title}에서 확인할 장면:** {application}\n\n"
        "### 이 개념을 읽는 순서\n\n"
        "1. 무엇을 측정하는지 정의합니다.\n"
        "2. 식의 각 항목과 단위를 확인합니다.\n"
        "3. 입력값이 변할 때 결과의 방향을 설명합니다.\n"
        f"4. **{element.title}**을 실제 재무자료나 거래 상황에 적용할 때 생길 예외를 확인합니다.\n\n"
        "**핵심 관계**\n\n"
        f"{formula_items_markdown(element.core_relation)}"
    )


def learning_notes_markdown(element: ElementDraft) -> str:
    learning_lines = []
    for line in element.scope_notes.splitlines():
        safe_line = learning_safe_line(line)
        if safe_line:
            learning_lines.append(safe_line)
    return (
        "**핵심 관계**\n\n"
        f"{formula_items_markdown(element.core_relation)}\n\n"
        + scope_to_markdown("\n".join(learning_lines))
    )


def checklist_markdown(element: ElementDraft) -> str:
    domain_items = DOMAIN_CHECKLIST[element.domain_id]
    return (
        f"- **{element.title}**을 한 문장으로 정의한다\n"
        + "- **핵심 관계의 각 항목과 방향을 설명한다**\n"
        + formula_items_markdown(element.core_relation, indent="  ")
        + "\n"
        + "\n".join(f"- {item}" for item in domain_items)
        + "\n- 공식의 결과를 숫자뿐 아니라 한 문장으로 해석한다"
        + "\n- 흔한 기준 불일치나 이중계산 가능성을 마지막에 점검한다"
    )


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


def canonical_learning_locator(locator: str, source_id: str = "") -> str:
    if source_id in KOCW_FINANCE_SOURCE_IDS or "/wku/chunghoil0208/" in locator:
        return KOCW_COURSE_URLS["finance"]
    if source_id in KOCW_DERIVATIVE_SOURCE_IDS or "/cau/yooshiyong0724/" in locator:
        return KOCW_COURSE_URLS["derivatives"]
    return locator


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
        ),
        "KOCW-FINANCE-COURSE": SourceDraft(
            source_id="KOCW-FINANCE-COURSE",
            label="원광대 재무관리 공식 강의",
            locator=KOCW_COURSE_URLS["finance"],
            source_type="web",
            notes="화폐의 시간가치·채권·주식가치·포트폴리오·CAPM·자본예산 강의 모음",
        ),
        "KOCW-DERIVATIVES-COURSE": SourceDraft(
            source_id="KOCW-DERIVATIVES-COURSE",
            label="중앙대 파생상품 공식 강의",
            locator=KOCW_COURSE_URLS["derivatives"],
            source_type="web",
            notes="선물가격·헤징·이항모형·옵션 Greeks 강의 모음",
        ),
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
        original_locator = links[0][1] if links else ""
        locator = canonical_learning_locator(original_locator, source_id)
        notes = clean_inline_markdown(" · ".join(cells[2:])) if len(cells) > 2 else ""
        if source_id in KOCW_DERIVATIVE_SOURCE_IDS:
            notes = f"{notes} · 원문 PDF: {original_locator}".strip(" ·")
            label = label.replace(" PDF", " 공식 강의")
        elif source_id in KOCW_FINANCE_SOURCE_IDS:
            notes = f"{notes} · 원문 PDF: {original_locator}".strip(" ·")
            label = label.replace(" PDF", " 공식 강의")
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
    for label, raw_locator in links:
        locator = canonical_learning_locator(raw_locator)
        if locator != raw_locator:
            label = label.replace(" PDF", " 공식 강의")
        source_id = when_kocw_course_source(locator) or locator_to_id.get(locator)
        if source_id is None:
            source_id = "URL-" + hashlib.sha1(locator.encode("utf-8")).hexdigest()[:12].upper()
            sources[source_id] = SourceDraft(
                source_id=source_id,
                label=label,
                locator=locator,
                source_type=infer_source_type(locator),
                notes=(
                    f"명세의 요소별 참고자료 · 원문 PDF: {raw_locator}"
                    if locator != raw_locator
                    else "명세의 요소별 참고자료"
                ),
            )
            locator_to_id[locator] = source_id
        if source_id not in result:
            result.append(source_id)
    return tuple(result)


def when_kocw_course_source(locator: str) -> str | None:
    if locator == KOCW_COURSE_URLS["finance"]:
        return "KOCW-FINANCE-COURSE"
    if locator == KOCW_COURSE_URLS["derivatives"]:
        return "KOCW-DERIVATIVES-COURSE"
    return None


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


KNOWN_FORMULA_MODES = {
    "FI-04": ("latex", "latex", "code"),
    "EQV-50": ("latex", "code"),
    "INV-03": ("latex",),
    "INV-07": ("latex", "code", "code"),
    "DER-08": ("code", "code", "latex"),
}


def validate_formula_rendering(elements: Sequence[ElementDraft]) -> None:
    """Protect whole-clause fidelity, decimal tokens, and script bracing."""
    if formula_clause_markdown("A `quoted` & B") != "``A `quoted` & B``":
        raise ValueError("Embedded-backtick Markdown fallback regressed")
    script_probe = latex_formula("X_AB=Y_Long^Term")
    if script_probe != "X_{AB}=Y_{Long}^{Term}":
        raise ValueError(f"Multi-character script bracing regressed: {script_probe!r}")
    scenario_probe = latex_formula("ExpectedValue=Σp_sV_s")
    if scenario_probe != r"ExpectedValue=\sum p_sV_s":
        raise ValueError(f"Adjacent symbol script parsing regressed: {scenario_probe!r}")
    if split_formula_clauses("• A=B\n• C=D") != ["A=B", "C=D"]:
        raise ValueError("Multiline formula clause splitting regressed")
    unsafe_probes = ("설명: X=Y", "X=(Y]", "X=Y 일부 설명")
    if any(latex_formula(probe) is not None for probe in unsafe_probes):
        raise ValueError("LaTeX conversion accepted a partial or unbalanced clause")

    elements_by_id = {element.element_id: element for element in elements}
    for element in elements:
        rendered = formula_to_markdown(element.core_relation)
        for decimal in re.findall(r"\d+\.\d+", element.core_relation):
            if decimal not in rendered:
                raise ValueError(
                    f"{element.element_id} split or lost decimal token {decimal!r}"
                )
        for clause in split_formula_clauses(element.core_relation):
            latex = latex_formula(clause)
            expected_line = f"- {formula_clause_markdown(clause)}"
            if expected_line not in rendered:
                raise ValueError(
                    f"{element.element_id} did not preserve complete formula clause {clause!r}"
                )

    for element_id, expected_modes in KNOWN_FORMULA_MODES.items():
        element = elements_by_id.get(element_id)
        if element is None:
            raise ValueError(f"Known formula element is missing: {element_id}")
        actual_modes = tuple(
            "latex" if latex_formula(clause) is not None else "code"
            for clause in split_formula_clauses(element.core_relation)
        )
        if actual_modes != expected_modes:
            raise ValueError(
                f"{element_id} formula modes differ: expected {expected_modes}, got {actual_modes}"
            )


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
    validate_formula_rendering(elements)


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
                definition_markdown = concept_definition_markdown(element)
                intuition_markdown = concept_intuition_markdown(element)
                learning_notes = learning_notes_markdown(element)
                formula_markdown = formula_to_markdown(element.core_relation)
                assumptions_markdown = assumption_markdown(element)
                checklist = checklist_markdown(element)
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
                        definition_markdown,
                        intuition_markdown,
                        learning_notes,
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
                        formula_markdown,
                        assumptions_markdown,
                        checklist,
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
                        definition_markdown,
                        intuition_markdown,
                        learning_notes,
                        formula_markdown,
                        assumptions_markdown,
                        checklist,
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
        metadata = dict(database.execute("SELECT key, value FROM metadata").fetchall())
        if metadata.get("schema_version") != str(SCHEMA_VERSION):
            raise ValueError("Metadata schema_version differs from the generator")
        if metadata.get("content_db_version") != str(CONTENT_DB_VERSION):
            raise ValueError("Metadata content_db_version differs from the generator")
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
        thin_cards = database.execute(
            """SELECT e.element_id FROM elements e
               JOIN concept_cards c ON c.element_id = e.element_id
               JOIN formula_cards f ON f.element_id = e.element_id
               WHERE c.definition = e.core_relation
                   OR c.intuition NOT LIKE '%왜 중요한가%'
                   OR c.scope_notes NOT LIKE '%핵심 관계%'
                   OR c.scope_notes LIKE '### 적용·연습 범위%'
                   OR f.expression NOT LIKE '%핵심 식과 관계%'
                   OR f.notes NOT LIKE '%핵심 관계%'
                   OR f.notes LIKE '### 학습 체크리스트%'"""
        ).fetchall()
        if thin_cards:
            raise ValueError(f"Learning cards are not expanded Markdown: {thin_cards[:3]}")
        visible_field_names = (
            "definition", "intuition", "learning_scope",
            "formula", "assumptions", "checklist",
        )
        visible_rows = database.execute(
            """SELECT e.element_id, c.definition, c.intuition, c.scope_notes,
                      f.expression, f.assumptions, f.notes
               FROM elements e
               JOIN concept_cards c ON c.element_id = e.element_id
               JOIN formula_cards f ON f.element_id = e.element_id
               ORDER BY e.display_order"""
        ).fetchall()
        empty_visible_fields: list[tuple[str, str]] = []
        authoring_leaks: list[tuple[str, str, str]] = []
        malformed_math_fields: list[tuple[str, str]] = []
        redundant_outer_headings: list[tuple[str, str]] = []
        distinct_visible_values = {field: set() for field in visible_field_names}
        for row in visible_rows:
            element_id = row[0]
            for field_name, value in zip(visible_field_names, row[1:]):
                if not value.strip():
                    empty_visible_fields.append((element_id, field_name))
                if value.count("$$") % 2 != 0:
                    malformed_math_fields.append((element_id, field_name))
                if (
                    field_name == "learning_scope"
                    and value.lstrip().startswith("### 적용·연습 범위")
                ) or (
                    field_name == "checklist"
                    and value.lstrip().startswith("### 학습 체크리스트")
                ):
                    redundant_outer_headings.append((element_id, field_name))
                distinct_visible_values[field_name].add(value)
                leaked_marker = next(
                    (
                        marker for marker in TECHNICAL_AUTHORING_MARKERS
                        if marker.casefold() in value.casefold()
                    ),
                    None,
                )
                if leaked_marker is not None:
                    authoring_leaks.append((element_id, field_name, leaked_marker))
        if empty_visible_fields:
            raise ValueError(f"Visible learning-card fields are empty: {empty_visible_fields[:3]}")
        if authoring_leaks:
            raise ValueError(f"Authoring internals leaked into visible cards: {authoring_leaks[:3]}")
        if malformed_math_fields:
            raise ValueError(f"Unbalanced Markdown math delimiters: {malformed_math_fields[:3]}")
        if redundant_outer_headings:
            raise ValueError(f"Redundant learning-card headings remain: {redundant_outer_headings[:3]}")

        uniqueness_floors = {
            "definition": 135,
            "intuition": 135,
            "learning_scope": 135,
            "formula": 135,
            "assumptions": 25,
            "checklist": 135,
        }
        uniqueness_counts = {
            field: len(values) for field, values in distinct_visible_values.items()
        }
        uniqueness_failures = {
            field: (uniqueness_counts[field], minimum)
            for field, minimum in uniqueness_floors.items()
            if uniqueness_counts[field] < minimum
        }
        if uniqueness_failures:
            raise ValueError(
                f"Learning-card copy regression detected (actual, minimum): {uniqueness_failures}"
            )

        formula_rows = database.execute(
            """SELECT e.element_id, e.core_relation, f.expression
               FROM elements e JOIN formula_cards f USING(element_id)"""
        ).fetchall()
        formula_mismatches = [
            element_id
            for element_id, core_relation, expression in formula_rows
            if formula_to_markdown(core_relation) != expression
        ]
        if formula_mismatches:
            raise ValueError(f"Stored formula Markdown differs from generator: {formula_mismatches[:3]}")
        relation_card_rows = database.execute(
            """SELECT e.element_id, e.core_relation, c.definition, c.intuition,
                      c.scope_notes, f.notes
               FROM elements e
               JOIN concept_cards c USING(element_id)
               JOIN formula_cards f USING(element_id)"""
        ).fetchall()
        relation_rendering_mismatches = []
        for element_id, core_relation, definition, intuition, learning_scope, checklist in relation_card_rows:
            rendered_relation = formula_items_markdown(core_relation)
            nested_relation = formula_items_markdown(core_relation, indent="  ")
            if (
                rendered_relation not in definition
                or rendered_relation not in intuition
                or rendered_relation not in learning_scope
                or nested_relation not in checklist
            ):
                relation_rendering_mismatches.append(element_id)
        if relation_rendering_mismatches:
            raise ValueError(
                "Core relations are not rendered safely in every learning card: "
                f"{relation_rendering_mismatches[:3]}"
            )
        latex_card_count = sum("$$" in expression for _, _, expression in formula_rows)
        if latex_card_count < 50:
            raise ValueError(f"Whole-clause LaTeX coverage is unexpectedly low: {latex_card_count}")
        linked_raw_kocw = database.execute(
            """SELECT es.element_id FROM element_sources es
               JOIN sources s ON s.source_id = es.source_id
               WHERE s.locator LIKE 'http://kocw-n.%'"""
        ).fetchall()
        if linked_raw_kocw:
            raise ValueError(f"Raw HTTP KOCW links remain in learning sources: {linked_raw_kocw[:3]}")
        elements_without_learning_link = database.execute(
            """SELECT e.element_id FROM elements e
               WHERE NOT EXISTS (
                   SELECT 1 FROM element_sources es
                   JOIN sources s ON s.source_id = es.source_id
                   WHERE es.element_id = e.element_id
                     AND (s.locator LIKE 'https://%' OR s.locator LIKE 'http://%')
               )"""
        ).fetchall()
        if elements_without_learning_link:
            raise ValueError(
                f"Elements without a web learning source: {elements_without_learning_link[:3]}"
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
        fts_projection_rows = database.execute(
            """SELECT k.element_id, k.normalized_text, e.title, e.core_relation,
                      c.definition, c.intuition, c.scope_notes,
                      f.expression, f.assumptions, f.notes
               FROM knowledge_fts k
               JOIN elements e ON e.element_id = k.element_id
               JOIN concept_cards c ON c.element_id = e.element_id
               JOIN formula_cards f ON f.element_id = e.element_id"""
        ).fetchall()
        malformed_fts_rows = []
        for row in fts_projection_rows:
            element_id, normalized_text = row[:2]
            expected_text = "\n".join((element_id, *row[2:]))
            if normalized_text != expected_text:
                malformed_fts_rows.append(element_id)
        if malformed_fts_rows:
            raise ValueError(
                "FTS normalized_text contains raw scope or misses visible content: "
                f"{malformed_fts_rows[:3]}"
            )
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
