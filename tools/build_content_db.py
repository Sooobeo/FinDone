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
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "finance_interview_app_final_spec.md"
DEFAULT_ASSET_DIR = ROOT / "app" / "src" / "main" / "assets"
LEARNING_COPY_DIR = ROOT / "content" / "learning-copy"
DEFAULT_QUESTION_BANK = ROOT / "content" / "model" / "concept-question-bank.generated.json"

SCHEMA_VERSION = 2
CONTENT_DB_VERSION = 7
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
    formula_segments: tuple[str, ...]
    scope_notes: str
    source_ids: tuple[str, ...]
    spec_section_locator: str


@dataclass(frozen=True)
class LearningCopy:
    definition: str
    intuition: str
    uses: tuple[str, ...]


def load_learning_copy(
    directory: Path = LEARNING_COPY_DIR,
    expected_element_ids: Iterable[str] | None = None,
) -> dict[str, LearningCopy]:
    """Load the reviewed, learner-facing copy kept separately from generator notes."""
    result: dict[str, LearningCopy] = {}
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ValueError(f"No learning-copy JSON files found in {directory}")

    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read learning copy: {path}") from error
        if not isinstance(payload, dict):
            raise ValueError(f"Learning-copy file must contain an object: {path}")
        for element_id, raw_copy in payload.items():
            if element_id in result:
                raise ValueError(f"Duplicate learning copy for {element_id}")
            if not isinstance(raw_copy, dict):
                raise ValueError(f"Learning copy for {element_id} must be an object")
            definition = raw_copy.get("definition")
            intuition = raw_copy.get("intuition")
            uses = raw_copy.get("uses")
            if not isinstance(definition, str) or len(definition.strip()) < 36:
                raise ValueError(f"{element_id} needs a complete definition of at least 36 characters")
            if not isinstance(intuition, str) or len(intuition.strip()) < 72:
                raise ValueError(f"{element_id} needs a concrete intuition of at least 72 characters")
            if (
                not isinstance(uses, list)
                or len(uses) < 2
                or any(not isinstance(item, str) or len(item.strip()) < 20 for item in uses)
            ):
                raise ValueError(f"{element_id} needs at least two concrete practical uses")
            result[element_id] = LearningCopy(
                definition=definition.strip(),
                intuition=intuition.strip(),
                uses=tuple(item.strip() for item in uses),
            )

    if expected_element_ids is not None:
        expected = set(expected_element_ids)
        actual = set(result)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing or unexpected:
            raise ValueError(
                "Learning-copy coverage differs from the canonical elements: "
                f"missing={missing[:3]}, unexpected={unexpected[:3]}"
            )
    return result


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def load_concept_question_bank(
    path: Path = DEFAULT_QUESTION_BANK,
    expected_element_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Load and strictly validate the build-time five-choice question bank."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read concept question bank: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("Concept question bank must contain an object")

    expected_hash = payload.get("bankSha256")
    unsigned = dict(payload)
    unsigned.pop("bankSha256", None)
    actual_hash = sha256_bytes(stable_json_bytes(unsigned))
    if expected_hash != actual_hash:
        raise ValueError("Concept question bank SHA-256 is invalid")
    if payload.get("bankVersion") != 1:
        raise ValueError("Unsupported concept question bank version")
    if payload.get("releaseStatus") not in {
        "bootstrap_not_reviewed", "candidate", "release_ready"
    }:
        raise ValueError("Concept question bank has an invalid release status")
    if not isinstance(payload.get("modelVersion"), str) or not payload["modelVersion"].strip():
        raise ValueError("Concept question bank model version is missing")

    questions = payload.get("questions")
    if not isinstance(questions, list) or len(questions) != payload.get("questionCount"):
        raise ValueError("Concept question bank count differs from its questions")
    if len(questions) != 405:
        raise ValueError(f"Expected 405 concept questions, found {len(questions)}")
    expected_ids = set(expected_element_ids or ())
    seen_question_ids: set[str] = set()
    questions_per_element: dict[str, int] = {}
    for raw_question in questions:
        if not isinstance(raw_question, dict):
            raise ValueError("Concept question rows must be objects")
        question_id = raw_question.get("questionId")
        element_id = raw_question.get("elementId")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("Concept question id is missing")
        if question_id in seen_question_ids:
            raise ValueError(f"Duplicate concept question id: {question_id}")
        seen_question_ids.add(question_id)
        if not isinstance(element_id, str) or (expected_ids and element_id not in expected_ids):
            raise ValueError(f"Concept question references an unknown element: {element_id}")
        questions_per_element[element_id] = questions_per_element.get(element_id, 0) + 1
        for field in ("questionType", "stem", "explanation", "modelVersion", "reviewStatus"):
            if not isinstance(raw_question.get(field), str) or not raw_question[field].strip():
                raise ValueError(f"{question_id} has an empty {field}")
        difficulty = raw_question.get("difficulty")
        if not isinstance(difficulty, int) or difficulty not in (1, 2, 3):
            raise ValueError(f"{question_id} has an invalid difficulty")
        fact_ids = raw_question.get("sourceFactIds")
        if not isinstance(fact_ids, list) or not fact_ids or any(
            not isinstance(item, str) or not item.strip() for item in fact_ids
        ):
            raise ValueError(f"{question_id} has invalid source fact ids")
        choices = raw_question.get("choices")
        if not isinstance(choices, list) or len(choices) != 5:
            raise ValueError(f"{question_id} must contain five choices")
        if [choice.get("key") for choice in choices if isinstance(choice, dict)] != list("ABCDE"):
            raise ValueError(f"{question_id} choice keys must be A through E")
        choice_texts: set[str] = set()
        correct_choices: list[dict[str, Any]] = []
        for choice in choices:
            if not isinstance(choice, dict):
                raise ValueError(f"{question_id} choices must be objects")
            choice_element_id = choice.get("elementId")
            text = choice.get("text")
            explanation = choice.get("explanation")
            if expected_ids and choice_element_id not in expected_ids:
                raise ValueError(f"{question_id} choice references {choice_element_id}")
            if not isinstance(text, str) or not text.strip() or text in choice_texts:
                raise ValueError(f"{question_id} has an empty or duplicate choice")
            choice_texts.add(text)
            if not isinstance(explanation, str) or not explanation.strip():
                raise ValueError(f"{question_id} choice explanation is empty")
            if not isinstance(choice.get("isCorrect"), bool):
                raise ValueError(f"{question_id} choice correctness is invalid")
            if choice["isCorrect"]:
                correct_choices.append(choice)
        if len(correct_choices) != 1 or correct_choices[0]["elementId"] != element_id:
            raise ValueError(f"{question_id} must have one target-element answer")
    if expected_ids and set(questions_per_element) != expected_ids:
        raise ValueError("Concept question coverage differs from canonical elements")
    if set(questions_per_element.values()) != {3}:
        raise ValueError("Every element must have exactly three concept questions")
    return payload


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
MARKDOWN_CODE_SPAN_RE = re.compile(r"(?P<fence>`+)(?P<body>.*?)(?P=fence)", re.DOTALL)


def markdown_formula_segments(value: str) -> tuple[str, ...]:
    """Keep the spec author's explicit formula boundaries before prose cleanup removes them."""
    return tuple(
        re.sub(r"\s+", " ", match.group("body")).strip()
        for match in MARKDOWN_CODE_SPAN_RE.finditer(value)
        if match.group("body").strip()
    )


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
    top_level_clauses = split_formula_clauses(value)
    if sum(COMPARISON_RE.search(clause) is not None for clause in top_level_clauses) > 1:
        return formula_items_markdown(value)

    output: list[str] = []
    parts = PROSE_CLAUSE_SEPARATOR_RE.split(value)
    for index, part in enumerate(parts):
        if index % 2 == 1 or not part:
            if part and output and "\n" in output[-1] and output[-1].endswith("$$"):
                output.append("\n")
            output.append(part)
            continue
        leading = part[: len(part) - len(part.lstrip())]
        trailing = part[len(part.rstrip()) :]
        clause = part.strip()
        if not clause:
            output.append(part)
            continue
        if COMPARISON_RE.search(clause) is not None:
            formula_clauses = split_formula_clauses(clause)
            rendered = (
                formula_items_markdown(clause)
                if len(formula_clauses) > 1
                else formula_clause_markdown(clause)
            )
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
            rendered_body = render_math_in_prose(body)
            if rendered_body.startswith("$$\n") or rendered_body.startswith("- "):
                nested_body = "\n".join(
                    ("  " + rendered_line) if rendered_line else ""
                    for rendered_line in rendered_body.splitlines()
                )
                spacer = "\n\n" if rendered_body.startswith("$$\n") else "\n"
                line = f"- **{label.strip()}**{separator}{spacer}{nested_body}"
            else:
                line = f"- **{label.strip()}**{separator} {rendered_body}"
        elif line.startswith("- "):
            rendered_body = render_math_in_prose(line[2:])
            line = rendered_body if rendered_body.startswith("- ") else "- " + rendered_body
        else:
            line = render_math_in_prose(line)
        output.append(line)
    return "\n".join(output)


SYMBOLIC_CLAUSE_RE = re.compile(
    r"[A-Za-z0-9_αβγδμρσλΔΣΠ∑∂()\[\]{}+\-−–—×÷*/^%.,=≈≤≥<>²√±& ]+"
)
FORMULA_CLAUSE_SEPARATOR_RE = re.compile(r";\s*|\r?\n+")
COMPARISON_RE = re.compile(r"≤|≥|≈|<=|>=|=|<|>")
PROSE_LHS_TOKEN_GAP_RE = re.compile(
    r"[A-Za-z0-9_αβγδμρσλΔΣ]\s+[A-Za-z0-9_αβγδμρσλΔΣ]"
)
PROSE_HYPHENATED_LABEL_RE = re.compile(r"[A-Za-z]{2,}[-–—][A-Za-z]{2,}")
SINGLE_SYMBOL_RE = re.compile(r"[A-Za-zαβγδμρσλΔΣΠ][A-Za-z0-9_αβγδμρσλΔΣΠ]*")
PARENTHESIZED_SINGLE_SYMBOL_RE = re.compile(
    r"\([A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*\)"
)
MATH_SIGNAL_RE = re.compile(r"[0-9_+\-−–—×÷*/^%=\u2248≤≥<>²√ΣΠ∑∂±&]")
REPEATED_TEX_SCRIPT_RE = re.compile(
    r"(?:_(?:\{[^{}]*\}|[A-Za-z0-9])){2}|(?:\^(?:\{[^{}]*\}|[A-Za-z0-9])){2}"
)
FORBIDDEN_MERGED_PRODUCT_TEX_RE = re.compile(
    r"\\mathrm\{(?:Ke|uS|dS|RS|qV|rT|wR|wD|wE|ke|kd)\}"
)
DIGIT_GROUPING_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")
ROOT_BASE_TOKEN_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9]*|[αβγδμρσλΔΣΠ])"
)
LATEX_FUNCTIONS = {"max", "min", "ln", "log"}
SUPPORTED_GENERATED_LATEX_COMMANDS = {
    "alpha", "approx", "beta", "delta", "div", "gamma", "ge", "lambda",
    "le", "ln", "log", "mathrm", "max", "min", "mu", "rho", "sigma",
    "sqrt", "sum", "prod", "times", "Delta", "partial", "pm",
}
LABEL_PUNCTUATION = {"_", "-", "–", "—", "/", "&", "(", ")", ".", ","}
LABEL_MARKDOWN_ESCAPES = {"\\", "`", "*", "_", "[", "]"}
MAX_INLINE_MATH_WEIGHT = 40
MAX_BLOCK_LINE_WEIGHT = 40

# The source spec writes these relations entirely with Korean term names. JLatexMath has no Hangul
# glyphs, so each entry supplies a faithful symbolic projection plus a native Korean legend instead
# of guessing that the whole sentence is TeX. Keep this list small and review it with the spec.
CANONICAL_FORMULA_OVERRIDES: dict[str, tuple[tuple[str, str], ...]] = {
    "ACC-02": (("발생주의 매출", "Revenue_accrual=CashCollected+AR_end-AR_begin"),),
    "ACC-03": (
        ("기말 대손충당금", "Allowance_end=Allowance_begin+BadDebtExpense-WriteOffs"),
        ("순매출채권", "NetAR=GrossAR-Allowance"),
    ),
    "ACC-04": (
        ("판매가능재고", "GoodsAvailable=BeginningInventory+NetPurchases"),
        ("매출원가", "COGS=GoodsAvailable-EndingInventory"),
    ),
    "ACC-05": (
        ("정액법 감가상각비", "Depreciation=(Cost-SalvageValue)/UsefulLife"),
        ("장부가", "NBV=Cost-AccumulatedDepreciation"),
        ("처분손익", "GainLoss=SaleProceeds-NBV_sale"),
    ),
    "ACC-06": (
        ("현금이자", "CashInterest=FaceValue×CouponRate"),
        ("이자비용", "InterestExpense=CarryingValue_begin×EffectiveRate"),
        (
            "기말 장부금액",
            "CarryingValue_end=CarryingValue_begin+InterestExpense-CashInterest",
        ),
    ),
    "ACC-07": (
        (
            "기본 주당순이익",
            "BasicEPS=(NetIncome-PreferredDividends)/WeightedAverageCommonShares",
        ),
    ),
    "ACC-10": (
        ("영업현금흐름 출발점", "CFO_start=NI"),
        ("감가상각의 CFO 조정", "CFO_adjustment=+Depreciation"),
        ("설비투자의 CFI 조정", "CFI_adjustment=-Capex"),
        ("설비투자의 유형자산 조정", "PPE_adjustment=+Capex"),
    ),
    "ACC-11": (
        ("영업이익률", "OperatingMargin=OperatingIncome/Revenue"),
        ("총자산회전율", "AssetTurnover=Revenue/AverageAssets"),
        ("재고회전율", "InventoryTurnover=COGS/AverageInventory"),
        ("부채비율", "DebtToEquity=Debt/Equity"),
    ),
    "DER-07": (
        ("상승 상태 주가", "S_u=u×S_0"),
        ("하락 상태 주가", "S_d=d×S_0"),
        ("무차익 조건", "d<R<u"),
        ("위험중립확률", "q=(R-d)/(u-d)=(R×S_0-S_d)/(S_u-S_d)"),
        ("옵션 현재가", "V_0=[q×V_u+(1-q)×V_d]/R"),
        ("복제 델타", "Δ=(V_u-V_d)/(S_u-S_d)"),
    ),
    "DER-08": (
        ("무배당 유럽형 콜", "C=S_0×N(d_1)-K×e^(-r×T)×N(d_2)"),
        ("무배당 유럽형 풋", "P=K×e^(-r×T)×N(-d_2)-S_0×N(-d_1)"),
        ("d1", "d_1=[ln(S_0/K)+(r+σ²/2)×T]/(σ×√T)"),
        ("d2", "d_2=d_1-σ×√T"),
    ),
    "EQV-51": (("Reverse DCF 역산 관계", "EV=DCF(g,Margin,ROIC)"),),
}

CANONICAL_EXPRESSION_REWRITES = (
    ("(V_PD_P)/(V_FD_F)", "(V_P×D_P)/(V_F×D_F)"),
    ("uS_0", "u×S_0"),
    ("dS_0", "d×S_0"),
    ("RS_0", "R×S_0"),
    ("qV_u", "q×V_u"),
    ("(1−q)V_d", "(1−q)×V_d"),
    ("wR_A", "w×R_A"),
    ("(1−w)R_B", "(1−w)×R_B"),
    ("(1-w)R_B", "(1-w)×R_B"),
    ("wD_1", "w×D_1"),
    ("(1−w)D_2", "(1−w)×D_2"),
    ("(1-w)D_2", "(1-w)×D_2"),
    ("Ke^(−rT)N(", "K×e^(−r×T)×N("),
    ("Ke^(−rT)", "K×e^(−r×T)"),
    ("Ke^(-rT)", "K×e^(-r×T)"),
    ("S_0N(", "S_0×N("),
    ("(r+σ²/2)T", "(r+σ²/2)×T"),
    ("σ√T", "σ×√T"),
)
CANONICAL_EXPRESSION_REGEX_REWRITES = (
    (re.compile(r"(?<![A-Za-z0-9_])rT(?![A-Za-z0-9_])"), "r×T"),
    (re.compile(r"(?<![A-Za-z0-9_])wE(?![A-Za-z0-9_])"), "w_E"),
    (re.compile(r"(?<![A-Za-z0-9_])wD(?![A-Za-z0-9_])"), "w_D"),
    (re.compile(r"(?<![A-Za-z0-9_])ke(?![A-Za-z0-9_])"), "k_e"),
    (re.compile(r"(?<![A-Za-z0-9_])kd(?![A-Za-z0-9_])"), "k_d"),
)


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


def script_end(value: str, start: int) -> int | None:
    """Return a complete script atom end, rejecting missing/operator script bodies."""
    if start >= len(value):
        return None
    if value[start] in "{(":
        end = matching_delimiter_index(value, start)
        return None if end is None or end <= start + 1 else end + 1
    if value[start] in "+-−–—":
        match = re.match(r"[+-−–—]\d+", value[start:])
        return None if match is None else start + len(match.group(0))
    match = re.match(
        r"(?:[A-Z]+[0-9]*(?![a-z])|[A-Z][a-z0-9]*|[a-z][a-z0-9]*|[0-9]+)",
        value[start:],
    )
    return None if match is None else start + len(match.group(0))


def brace_multichar_scripts(value: str) -> str | None:
    """Brace complete scripts and reject malformed script syntax without partial output."""
    output: list[str] = []
    index = 0
    while index < len(value):
        operator = value[index]
        if operator not in "_^":
            output.append(operator)
            index += 1
            continue
        if index + 1 >= len(value):
            return None
        output.append(operator)
        script_start = index + 1
        script_end_index = script_end(value, script_start)
        if script_end_index is None:
            return None
        next_character = value[script_start]
        if next_character == "{":
            inner = brace_multichar_scripts(value[script_start + 1 : script_end_index - 1])
            if inner is None:
                return None
            output.append("{" + inner + "}")
            index = script_end_index
            continue
        if next_character == "(":
            inner = brace_multichar_scripts(value[script_start + 1 : script_end_index - 1])
            if inner is None:
                return None
            output.append("{(" + inner + ")}")
            index = script_end_index
            continue
        token = value[script_start:script_end_index]
        output.append("{" + token + "}" if len(token) > 1 else token)
        index = script_end_index
    return "".join(output)


def root_atom_end(value: str, start: int) -> int | None:
    match = ROOT_BASE_TOKEN_RE.match(value, start)
    if match is None:
        return None
    cursor = match.end()
    while cursor < len(value):
        if value[cursor] == "²":
            cursor += 1
        elif value[cursor] in "_^":
            next_cursor = script_end(value, cursor + 1)
            if next_cursor is None:
                return None
            cursor = next_cursor
        else:
            break
    return cursor


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
            atom_end_exclusive = root_atom_end(value, atom_start)
            if atom_end_exclusive is None:
                return None
            atom = value[atom_start:atom_end_exclusive]
            atom_end = atom_end_exclusive - 1
        output.append(r"\sqrt{" + atom + "}")
        index = atom_end + 1
    return "".join(output)


def is_digit_grouping_comma(value: str, index: int) -> bool:
    return (
        index > 0
        and value[index - 1].isdigit()
        and index + 3 < len(value)
        and value[index + 1 : index + 4].isdigit()
        and (index + 4 == len(value) or not value[index + 4].isdigit())
    )


def is_decimal_point(value: str, index: int) -> bool:
    return (
        value[index] == "."
        and index > 0
        and index + 1 < len(value)
        and value[index - 1].isdigit()
        and value[index + 1].isdigit()
    )


def has_unsafe_top_level_punctuation(value: str) -> bool:
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for index, character in enumerate(value):
        if character in "([{":
            stack.append(character)
        elif character in pairs:
            if stack:
                stack.pop()
        elif character == "," and not stack and not is_digit_grouping_comma(value, index):
            return True
        elif (
            character in ".!?。"
            and not stack
            and not is_decimal_point(value, index)
            and value[index + 1 :].strip()
        ):
            return True
    return False


def split_formula_clauses(value: str) -> list[str]:
    """Split top-level formula clauses without splitting function or numeric commas."""
    clauses: list[str] = []
    for part in FORMULA_CLAUSE_SEPARATOR_RE.split(value):
        cleaned = re.sub(r"^(?:•|[-+])\s+", "", part.strip())
        if not cleaned:
            continue
        if not balanced_delimiters(cleaned):
            clauses.append(cleaned)
            continue
        stack: list[str] = []
        segment_start = 0
        pairs = {")": "(", "]": "[", "}": "{"}
        for index, character in enumerate(cleaned):
            if character in "([{":
                stack.append(character)
            elif character in pairs:
                if stack and stack[-1] == pairs[character]:
                    stack.pop()
            elif character == "," and not stack:
                if is_digit_grouping_comma(cleaned, index):
                    continue
                before = cleaned[segment_start:index]
                after = cleaned[index + 1 :]
                if COMPARISON_RE.search(before) is not None and COMPARISON_RE.search(after) is not None:
                    clause = before.strip()
                    if clause:
                        clauses.append(clause)
                    segment_start = index + 1
            elif (
                character in ".!?。"
                and not stack
                and not is_decimal_point(cleaned, index)
                and cleaned[index + 1 :].strip()
            ):
                before = cleaned[segment_start:index]
                if COMPARISON_RE.search(before) is not None:
                    clause = cleaned[segment_start : index + 1].strip()
                    if clause:
                        clauses.append(clause)
                    segment_start = index + 1
        final_clause = cleaned[segment_start:].strip()
        if final_clause:
            clauses.append(final_clause)
    return clauses or [value.strip()]


def split_terminal_punctuation(value: str) -> tuple[str, str]:
    """Keep sentence punctuation visible but outside a generated math span."""
    candidate = value.rstrip()
    match = re.search(r"([.!?。]+)$", candidate)
    if match is None:
        return candidate, ""
    formula = candidate[: match.start()].rstrip()
    return (formula, match.group(1)) if formula else (candidate, "")


def has_prose_like_comparison_label(value: str) -> bool:
    """Reject labels whose spaces/hyphens would be corrupted by TeX math semantics."""
    comparison = COMPARISON_RE.search(value)
    if comparison is None:
        return False
    label = value[: comparison.start()]
    return (
        PROSE_LHS_TOKEN_GAP_RE.search(label) is not None
        or PROSE_HYPHENATED_LABEL_RE.search(label) is not None
    )


def upright_ascii_identifiers(value: str) -> str:
    """Make multi-letter identifiers upright while preserving generated TeX commands."""
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\":
            command_end = index + 1
            while command_end < len(value) and value[command_end].isascii() and value[command_end].isalpha():
                command_end += 1
            output.append(value[index:command_end])
            index = command_end
            continue
        if not (value[index].isascii() and value[index].isalpha()):
            output.append(value[index])
            index += 1
            continue

        if index > 0 and value[index - 1] in "_^":
            # Multi-character scripts were braced above; an unbraced script is one atom.
            token_end = index + 1
        else:
            token_end = index
            while token_end < len(value) and (
                (value[token_end].isascii() and value[token_end].isalpha())
                or value[token_end].isdigit()
            ):
                token_end += 1
        token = value[index:token_end]
        letter_count = sum(character.isalpha() for character in token)
        next_non_space = token_end
        while next_non_space < len(value) and value[next_non_space].isspace():
            next_non_space += 1
        if (
            token in LATEX_FUNCTIONS
            and next_non_space < len(value)
            and value[next_non_space] == "("
        ):
            output.append("\\" + token)
        elif letter_count > 1:
            output.append(r"\mathrm{" + token + "}")
        else:
            output.append(token)
        index = token_end
    return "".join(output)


def canonical_expression_source(value: str) -> str:
    candidate = value
    for original, canonical in CANONICAL_EXPRESSION_REWRITES:
        candidate = candidate.replace(original, canonical)
    for pattern, canonical in CANONICAL_EXPRESSION_REGEX_REWRITES:
        candidate = pattern.sub(canonical, candidate)
    return candidate


def latex_expression(value: str, *, require_comparison: bool = False) -> str | None:
    """Convert a complete safe symbolic expression without extracting a fragment."""
    candidate = canonical_expression_source(value.strip())
    if (
        not candidate
        or (require_comparison and COMPARISON_RE.search(candidate) is None)
        or re.search(r"[가-힣]", candidate)
        or SYMBOLIC_CLAUSE_RE.fullmatch(candidate) is None
        or not balanced_delimiters(candidate)
        or has_prose_like_comparison_label(candidate)
        or has_unsafe_top_level_punctuation(candidate)
        or (
            not require_comparison
            and MATH_SIGNAL_RE.search(candidate) is None
            and SINGLE_SYMBOL_RE.fullmatch(candidate) is None
            and PARENTHESIZED_SINGLE_SYMBOL_RE.fullmatch(candidate) is None
        )
    ):
        return None
    rooted = replace_square_roots(candidate)
    if rooted is None:
        return None
    formula = brace_multichar_scripts(rooted)
    if formula is None:
        return None
    if REPEATED_TEX_SCRIPT_RE.search(formula) is not None:
        return None
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
        .replace("∂", r"\partial ")
        .replace("±", r"\pm ")
        .replace("&", r"\&")
    )
    greek = {
        "α": r"\alpha ", "β": r"\beta ", "γ": r"\gamma ",
        "δ": r"\delta ", "μ": r"\mu ", "ρ": r"\rho ",
        "σ": r"\sigma ", "λ": r"\lambda ", "Δ": r"\Delta ",
        "Σ": r"\sum ", "∑": r"\sum ", "Π": r"\prod ",
    }
    for symbol, command in greek.items():
        formula = formula.replace(symbol, command)
    formula = DIGIT_GROUPING_COMMA_RE.sub("{,}", formula)
    formula = upright_ascii_identifiers(formula)
    formula = re.sub(r"\s+", " ", formula).strip()
    return formula


def latex_formula(value: str) -> str | None:
    """Convert a whole comparison clause or return None without extracting a fragment."""
    formula, _ = split_terminal_punctuation(value)
    return latex_expression(formula, require_comparison=True)


def latex_render_weight(latex: str) -> int:
    """Estimate visible width from transformed TeX rather than the unrelated source length."""
    visible = re.sub(r"\\mathrm\{([^{}]*)}", r"\1", latex)
    visible = re.sub(r"\\(?:alpha|beta|gamma|delta|mu|rho|sigma|lambda|Delta)", "x", visible)
    visible = re.sub(r"\\(?:times|div|approx|le|ge|pm|partial|sum|prod)", "x", visible)
    visible = visible.replace("\\%", "%").replace("\\&", "&")
    return len(re.sub(r"[{}\s]", "", visible))


def semantic_formula_lines(source: str) -> list[str]:
    """Keep one semantic equation intact; the Android renderer fits block math to its canvas."""
    return [source]


def math_markdown(source: str, latex: str) -> str:
    """Choose inline/block layout without breaking an equation at arbitrary operators."""
    if latex_render_weight(latex) <= MAX_INLINE_MATH_WEIGHT:
        return f"$${latex}$$"
    return f"$$\n{latex}\n$$"


def is_readable_label(value: str) -> bool:
    return any(character.isalpha() for character in value) and all(
        character.isalnum() or character.isspace() or character in LABEL_PUNCTUATION
        for character in value
    )


def escape_markdown_label(value: str) -> str:
    return "".join(
        ("\\" if character in LABEL_MARKDOWN_ESCAPES else "") + character
        for character in value
    )


def labeled_formula_markdown(value: str) -> str | None:
    """Keep a prose label outside math and safely render or preserve the complete RHS."""
    candidate = value.strip()
    for separator in (":", "："):
        separator_index = candidate.find(separator)
        if separator_index <= 0:
            continue
        label = candidate[:separator_index].strip()
        expression = candidate[separator_index + 1 :].strip()
        expression_latex = latex_expression(expression)
        if (
            is_readable_label(label)
            and expression
            and (expression_latex is not None or COMPARISON_RE.search(expression) is not None)
        ):
            rendered = (
                math_markdown(expression, expression_latex)
                if expression_latex is not None
                else native_mixed_math_markdown(expression) or markdown_code_span(expression)
            )
            prefix = f"**{escape_markdown_label(label)}**{separator}"
            return f"{prefix}\n\n{rendered}" if rendered.startswith("$$\n") else f"{prefix} {rendered}"

    comparison = COMPARISON_RE.search(candidate)
    if comparison is None or not has_prose_like_comparison_label(candidate):
        return None
    label = candidate[: comparison.start()].strip()
    expression = candidate[comparison.end() :].strip()
    if not expression or not is_readable_label(label):
        return None
    expression_latex = latex_expression(expression)
    rendered = (
        math_markdown(expression, expression_latex)
        if expression_latex is not None
        else native_mixed_math_markdown(expression) or markdown_code_span(expression)
    )
    prefix = f"**{escape_markdown_label(label)}** {comparison.group(0)}"
    return f"{prefix}\n\n{rendered}" if rendered.startswith("$$\n") else f"{prefix} {rendered}"


HANGUL_RE = re.compile(r"[가-힣]")
MIXED_SYMBOL_ATOM_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\([A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*\)|"
    r"[A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*|"
    r"[0-9]+(?:\.[0-9]+)?%?)(?![A-Za-z0-9_])"
)


def native_mixed_math_markdown(value: str) -> str | None:
    """Render Hangul as native Markdown and only safe symbolic atoms as JLatex spans."""
    if HANGUL_RE.search(value) is None:
        return None
    candidate = canonical_expression_source(value)
    if not balanced_delimiters(candidate) or "$" in candidate or "`" in candidate:
        return None
    if MATH_SIGNAL_RE.search(candidate) is None:
        return candidate

    output: list[str] = []
    cursor = 0
    for match in MIXED_SYMBOL_ATOM_RE.finditer(candidate):
        output.append(candidate[cursor : match.start()])
        atom = match.group(0)
        atom_latex = latex_expression(atom)
        output.append(math_markdown(atom, atom_latex) if atom_latex is not None else atom)
        cursor = match.end()
    output.append(candidate[cursor:])
    return "".join(output)


def segmented_formula_markdown(value: str, explicit_segments: Sequence[str]) -> str | None:
    """Rebuild a clause from the spec's code-span boundaries without putting prose in TeX."""
    if not explicit_segments:
        return None
    output: list[str] = []
    cursor = 0
    matched = False
    for raw_segment in explicit_segments:
        segment = clean_inline_markdown(raw_segment)
        if not segment:
            continue
        start = value.find(segment, cursor)
        if start < 0:
            continue
        output.append(value[cursor:start])
        segment_latex = latex_expression(segment)
        rendered = (
            math_markdown(segment, segment_latex)
            if segment_latex is not None
            else formula_clause_markdown(segment)
        )
        if rendered == markdown_code_span(segment):
            # An explicit source formula is still safer and more readable as native text than as
            # a fake monospaced 'formula'. Coverage validation below makes this case visible.
            rendered = segment
        if rendered.startswith("$$\n"):
            rendered = "\n\n" + rendered + "\n\n"
        output.append(rendered)
        cursor = start + len(segment)
        matched = True
    if not matched:
        return None
    output.append(value[cursor:])
    return "".join(output).strip()


def formula_to_markdown(value: str, formula_segments: Sequence[str] = ()) -> str:
    """Render every complete clause as LaTeX or preserve that complete clause as code."""
    return formula_items_markdown(value, formula_segments=formula_segments)


def formula_clause_markdown(value: str, explicit_segments: Sequence[str] = ()) -> str:
    """Render one complete formula clause without ever dropping a fallback clause."""
    formula, punctuation = split_terminal_punctuation(value)
    segmented = segmented_formula_markdown(formula, explicit_segments)
    if segmented is not None:
        rendered = segmented
        if not punctuation:
            return rendered
        if "\n" in rendered and rendered.endswith("$$"):
            if set(punctuation) <= {".", "。"}:
                return rendered
            return f"{rendered}\n{punctuation}"
        return rendered + punctuation
    latex = latex_formula(formula)
    if latex is not None:
        rendered = math_markdown(formula, latex)
    else:
        labeled = labeled_formula_markdown(formula)
        if labeled is None:
            native = native_mixed_math_markdown(formula)
            if native is None:
                return markdown_code_span(value.strip())
            rendered = native
        else:
            rendered = labeled
    if not punctuation:
        return rendered
    if "\n" in rendered and rendered.endswith("$$"):
        if set(punctuation) <= {".", "。"}:
            return rendered
        return f"{rendered}\n{punctuation}"
    return rendered + punctuation


def formula_items_markdown(
    value: str,
    indent: str = "",
    formula_segments: Sequence[str] = (),
) -> str:
    """Render a relation as Markdown list items suitable for nesting in learning cards."""
    items: list[str] = []
    remaining_segments = list(formula_segments)
    for clause in split_formula_clauses(value):
        clause_segments: list[str] = []
        for segment in tuple(remaining_segments):
            cleaned = clean_inline_markdown(segment)
            if cleaned and cleaned in clause:
                clause_segments.append(segment)
                remaining_segments.remove(segment)
        rendered = formula_clause_markdown(clause, clause_segments)
        if rendered.startswith("$$\n"):
            # A block delimiter must occupy its own line; `- $$` is parsed as inline math.
            items.append("\n".join(indent + line for line in rendered.splitlines()))
        else:
            lines = [line.rstrip() for line in rendered.splitlines()]
            item_lines = [f"{indent}- {lines[0]}"]
            continuation_indent = indent + "  "
            item_lines.extend(
                (continuation_indent + line) if line else ""
                for line in lines[1:]
            )
            items.append("\n".join(item_lines))
    if remaining_segments:
        raise ValueError(
            "Explicit formula segment was not preserved in its canonical relation: "
            f"{remaining_segments[0]!r}"
        )
    return "\n".join(items)


def element_formula_items_markdown(element: ElementDraft, indent: str = "") -> str:
    override = CANONICAL_FORMULA_OVERRIDES.get(element.element_id)
    if override is None:
        return formula_items_markdown(
            element.core_relation,
            indent=indent,
            formula_segments=element.formula_segments,
        )

    items: list[str] = []
    for label, source in override:
        latex = latex_expression(source, require_comparison=True)
        if latex is None:
            raise ValueError(
                f"{element.element_id} canonical formula is not supported: {source!r}"
            )
        rendered = math_markdown(source, latex)
        native_label = f"{indent}- **{escape_markdown_label(label)}**"
        if rendered.startswith("$$\n"):
            continuation_indent = indent + "  "
            rendered = "\n".join(
                (continuation_indent + line) if line else ""
                for line in rendered.splitlines()
            )
            items.append(f"{native_label}\n{rendered}")
        else:
            items.append(f"{native_label}: {rendered}")
    return "\n".join(items)


def element_formula_to_markdown(element: ElementDraft) -> str:
    return element_formula_items_markdown(element)


def assumption_markdown(element: ElementDraft) -> str:
    keywords = ("가정", "조건", "기준", "제외", "포함", "동일")
    selected: list[str] = []
    for raw_line in element.scope_notes.splitlines():
        safe_line = learning_safe_line(raw_line)
        if not safe_line:
            continue
        cleaned = re.sub(r"^[•-]\s*", "", safe_line)
        if cleaned.startswith(("개념·수식", "파라미터", "정답", "해설식", "출제 범위")):
            continue
        if cleaned.startswith("유형 "):
            quote_end = max(cleaned.rfind("”"), cleaned.rfind("\""))
            cleaned = cleaned[quote_end + 1 :].strip() if quote_end >= 0 else ""
        condition_match = re.search(r"(?:^|[.。]\s*)(단[, ]\s*.+)$", cleaned)
        explicit_condition = condition_match is not None
        if condition_match is not None:
            cleaned = condition_match.group(1).strip()
        if (
            cleaned
            and COMPARISON_RE.search(cleaned) is None
            and (explicit_condition or any(keyword in cleaned for keyword in keywords))
        ):
            selected.append(cleaned.rstrip(".。") + ".")
        if len(selected) == 4:
            break
    for fallback in DOMAIN_CHECKLIST[element.domain_id]:
        sentence = fallback.rstrip(".。") + "."
        if sentence not in selected:
            selected.append(sentence)
        if len(selected) >= 2:
            break
    return "\n".join(f"- {item}" for item in selected)


def concept_definition_markdown(copy: LearningCopy) -> str:
    return copy.definition


def concept_intuition_markdown(copy: LearningCopy) -> str:
    return copy.intuition


def _application_section_body(element: ElementDraft, label: str, value: str) -> str:
    body = value.strip()
    if not body or contains_authoring_marker(body) or "같은 생성 데이터" in body:
        return (
            f"{label}에서는 {element.title}의 입력값과 기준을 먼저 확인한 뒤, "
            "계산 또는 판단 결과가 무엇을 뜻하는지 한 문장으로 설명합니다."
        )
    return body


def _type_sections(element: ElementDraft, line: str) -> list[tuple[str, str]]:
    """Extract learner-facing type labels while dropping generator parameters and answers."""
    candidate = re.sub(r"^[•-]\s*", "", line.strip())
    if not candidate.startswith("유형 "):
        return []
    heading_part, separator, body = candidate.partition(":")
    if not separator:
        body = ""
    parts = re.split(r"\s*/\s*(?=유형\s+)", heading_part)
    sections: list[tuple[str, str]] = []
    for part in parts:
        match = re.match(r"유형\s+([^—–-]+?)\s*[—–-]\s*(.+)$", part.strip())
        if match is None:
            continue
        type_name, label = (item.strip() for item in match.groups())
        title = f"유형 {type_name} · {label}"
        sections.append((title, _application_section_body(element, label, body)))
    return sections


def learning_notes_markdown(element: ElementDraft) -> str:
    sections: list[tuple[str, str]] = []
    for raw_line in element.scope_notes.splitlines():
        safe_line = learning_safe_line(raw_line)
        if not safe_line:
            continue
        sections.extend(_type_sections(element, safe_line))
        candidate = re.sub(r"^[•-]\s*", "", safe_line.strip())
        if candidate.startswith("출제 범위:"):
            body = candidate.split(":", 1)[1].strip()
            sections.append(
                ("기본 적용", _application_section_body(element, "기본 적용", body))
            )

    if not sections:
        sections.append(
            (
                "기본 적용",
                f"{element.title}의 입력값과 기준을 확인하고, 계산 또는 판단 결과를 실제 상황의 언어로 해석합니다.",
            )
        )
    return "\n\n".join(f"### {title}\n\n{body}" for title, body in sections)


def practical_uses_markdown(copy: LearningCopy) -> str:
    return "\n".join(f"- {item}" for item in copy.uses)


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


def extract_core_relation(block: Sequence[str], element_id: str) -> tuple[str, tuple[str, ...]]:
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
            return relation, markdown_formula_segments("\n".join(parts))
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
        core_relation, formula_segments = extract_core_relation(block, element_id)
        elements.append(
            ElementDraft(
                element_id=element_id,
                domain_id=domain_id,
                number=int(number_text),
                title=clean_inline_markdown(raw_title),
                mode="calculation",
                core_relation=core_relation,
                formula_segments=formula_segments,
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
                formula_segments=markdown_formula_segments(raw_core),
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
    "CF-09": ("code", "code", "code"),
    "FI-04": ("latex", "latex", "code"),
    "INV-08": ("latex", "latex", "code"),
    "INV-03": ("latex", "latex", "latex"),
    "INV-07": ("latex", "code"),
    "DER-08": ("code", "code", "latex", "latex"),
    "EQV-35": ("code", "code"),
    "EQV-37": ("latex", "code"),
    "EQV-50": ("code", "code"),
}


def validate_formula_rendering(elements: Sequence[ElementDraft]) -> None:
    """Protect whole-clause fidelity, decimal tokens, and script bracing."""
    if formula_clause_markdown("A `quoted` & B") != "``A `quoted` & B``":
        raise ValueError("Embedded-backtick Markdown fallback regressed")
    script_probe = latex_formula("X_AB=Y_Long^Term")
    if script_probe != r"X_{\mathrm{AB}}=Y_{\mathrm{Long}}^{\mathrm{Term}}":
        raise ValueError(f"Multi-character script bracing regressed: {script_probe!r}")
    scenario_probe = latex_formula("ExpectedValue=Σp_sV_s")
    if scenario_probe != r"\mathrm{ExpectedValue}=\sum p_sV_s":
        raise ValueError(f"Adjacent symbol script parsing regressed: {scenario_probe!r}")
    if split_formula_clauses("• A=B\n• C=D") != ["A=B", "C=D"]:
        raise ValueError("Multiline formula clause splitting regressed")
    compound_probe = "Cov(A,B)=X, rho_AB=Cov(A,B)/(s_A s_B), -1≤rho_AB≤1."
    if split_formula_clauses(compound_probe) != [
        "Cov(A,B)=X",
        "rho_AB=Cov(A,B)/(s_A s_B)",
        "-1≤rho_AB≤1.",
    ]:
        raise ValueError("Top-level equation comma splitting regressed")
    if split_formula_clauses("X=max(A,B)+1,000") != ["X=max(A,B)+1,000"]:
        raise ValueError("Function or digit-grouping comma splitting regressed")
    if formula_clause_markdown("X=Y.") != "$$X=Y$$.":
        raise ValueError("Terminal punctuation moved inside the math span")
    if split_formula_clauses("X=Y. A=B.") != ["X=Y.", "A=B."]:
        raise ValueError("Top-level sentence comparison splitting regressed")
    if latex_formula("X=Y. explanation") is not None:
        raise ValueError("Ambiguous sentence punctuation was promoted to LaTeX")
    if split_formula_clauses("X=Y. explanation") != ["X=Y.", "explanation"]:
        raise ValueError("Formula-to-prose sentence boundary was not preserved safely")

    root_probe = latex_formula("SD=√Variance")
    if root_probe != r"\mathrm{SD}=\sqrt{\mathrm{Variance}}":
        raise ValueError(f"Complete square-root atom parsing regressed: {root_probe!r}")
    squared_root_probe = latex_formula("σ=√σ²")
    if squared_root_probe != r"\sigma =\sqrt{\sigma ^{2}}":
        raise ValueError(f"Square-root script parsing regressed: {squared_root_probe!r}")
    if latex_expression("x^-2") != "x^{-2}":
        raise ValueError("Signed exponent bracing regressed")
    if latex_formula("x_=1") is not None or latex_expression("x_^2") is not None:
        raise ValueError("Malformed script syntax was accepted")

    if latex_formula("X=1,234") != "X=1{,}234":
        raise ValueError("Three-digit grouping comma conversion regressed")
    if latex_formula("X=1,2") is not None:
        raise ValueError("Non-grouping top-level comma was promoted to LaTeX")
    if split_formula_clauses("X=1,Y=2") != ["X=1", "Y=2"]:
        raise ValueError("Comma-connected equations were not split")
    if latex_formula("X=max(1,2)") != r"X=\max(1,2)":
        raise ValueError("Function argument comma handling regressed")

    exact_markdown_probes = {
        "Project FCF=OCF-Capex-ΔNWC": (
            r"**Project FCF** = $$\mathrm{OCF}-\mathrm{Capex}-\Delta \mathrm{NWC}$$"
        ),
        "Mid-year PV=FCF_t/(1+r)^(t-0.5)": (
            r"**Mid-year PV** = $$\mathrm{FCF}_t/(1+r)^{(t-0.5)}$$"
        ),
        "민감도: ΔEV=EBITDA×ΔMultiple": (
            r"**민감도**: $$\Delta \mathrm{EV}=\mathrm{EBITDA} \times "
            r"\Delta \mathrm{Multiple}$$"
        ),
        "설명: X=Y 일부 설명": "**설명**: $$X$$=$$Y$$ 일부 설명",
    }
    for source, expected in exact_markdown_probes.items():
        actual = formula_clause_markdown(source)
        if actual != expected:
            raise ValueError(f"Labeled formula rendering regressed: {source!r} -> {actual!r}")

    upright_probe = latex_formula("ΔPrice=max(FCF,ln(WACC))+D_Mod")
    upright_expected = (
        r"\Delta \mathrm{Price}=\max(\mathrm{FCF},\ln(\mathrm{WACC}))"
        r"+D_{\mathrm{Mod}}"
    )
    if upright_probe != upright_expected:
        raise ValueError(f"Upright identifier rendering regressed: {upright_probe!r}")
    factor_boundary_probes = {
        "F_0=(S_0-I)(1+rT)": r"F_0=(S_0-I)(1+r \times T)",
        "E(R_p)=wR_A+(1−w)R_B": r"E(R_p)=w \times R_A+(1-w) \times R_B",
        "wD_1+(1−w)D_2=D_L": r"w \times D_1+(1-w) \times D_2=D_L",
        "WACC=wE×ke+wD×kd×(1-T)": (
            r"\mathrm{WACC}=w_E \times k_e+w_D \times k_d \times (1-T)"
        ),
        "S_u=u×S_0": r"S_u=u \times S_0",
        "V_0=[q×V_u+(1-q)×V_d]/R": (
            r"V_0=[q \times V_u+(1-q) \times V_d]/R"
        ),
        "C=S_0×N(d_1)-K×e^(-r×T)×N(d_2)": (
            r"C=S_0 \times N(d_1)-K \times e^{(-r \times T)} \times N(d_2)"
        ),
    }
    for source, expected in factor_boundary_probes.items():
        actual = latex_expression(source, require_comparison=True)
        if actual != expected:
            raise ValueError(
                f"Implicit-product boundary regressed: {source!r} -> {actual!r}"
            )
    comma_probe = latex_expression("(1,000 - 800 + 20) × 100 / 1,000")
    if comma_probe != r"(1{,}000 - 800 + 20) \times 100 / 1{,}000":
        raise ValueError(f"Digit grouping comma rendering regressed: {comma_probe!r}")

    long_formula = "X=1+2+3+4+5+6+7+8+9+10+11+12+13+14+15+16+17+18+19"
    rendered_long_formula = formula_clause_markdown(long_formula)
    if (
        rendered_long_formula.count("$$\n") != 1
        or not rendered_long_formula.startswith("$$\n")
        or not rendered_long_formula.endswith("\n$$")
    ):
        raise ValueError("Long formula was not kept in one delimiter-only block")
    if formula_items_markdown(long_formula) != rendered_long_formula:
        raise ValueError("Long formula block delimiter was prefixed as a list item")
    if formula_items_markdown("X=1") != "- $$X=1$$":
        raise ValueError("Short formula no longer uses inline math")

    unsafe_probes = (
        "설명: X=Y",
        "X=(Y]",
        "X=Y 일부 설명",
        "Project FCF=OCF-Capex-ΔNWC",
        "Jensen α=R_p-[R_f+β_p(R_m-R_f)]",
        "Treasury-stock method IncrementalShares=Options×max(P-K,0)/P",
        "FD Shares=Basic+Incremental+RSU+Convertibles",
        "debt-like deficit=max(DBO-PlanAssets,0)",
        "Mid-year PV=FCF_t/(1+r)^(t-0.5)",
    )
    if any(latex_formula(probe) is not None for probe in unsafe_probes):
        raise ValueError("LaTeX conversion accepted a partial or unbalanced clause")

    elements_by_id = {element.element_id: element for element in elements}
    for element in elements:
        rendered = element_formula_to_markdown(element)
        override = CANONICAL_FORMULA_OVERRIDES.get(element.element_id)
        if override is not None:
            for label, source in override:
                latex = latex_expression(source, require_comparison=True)
                if label not in rendered or latex is None or "$$" not in rendered:
                    raise ValueError(
                        f"{element.element_id} canonical relation was not preserved: {source!r}"
                    )
            continue
        for decimal in re.findall(r"\d+\.\d+", element.core_relation):
            if decimal not in rendered:
                raise ValueError(
                    f"{element.element_id} split or lost decimal token {decimal!r}"
                )
        remaining_segments = list(element.formula_segments)
        for clause in split_formula_clauses(element.core_relation):
            clause_segments: list[str] = []
            for segment in tuple(remaining_segments):
                cleaned = clean_inline_markdown(segment)
                if cleaned and cleaned in clause:
                    clause_segments.append(segment)
                    remaining_segments.remove(segment)
            rendered_clause = formula_clause_markdown(clause, clause_segments)
            for math_body in re.findall(r"\$\$\n?(.*?)\n?\$\$", rendered_clause, re.DOTALL):
                commands = set(re.findall(r"\\([A-Za-z]+)", math_body))
                unsupported = commands - SUPPORTED_GENERATED_LATEX_COMMANDS
                if unsupported:
                    raise ValueError(
                        f"{element.element_id} generated unsupported LaTeX commands: "
                        f"{sorted(unsupported)}"
                    )

            comparison = COMPARISON_RE.search(clause)
            expression_source = clause.strip()
            colon_split = next(
                (
                    (clause[:index].strip(), clause[index + 1 :].strip())
                    for separator in (":", "：")
                    if (index := clause.find(separator)) > 0
                ),
                None,
            )
            if colon_split is not None and is_readable_label(colon_split[0]):
                expression_source = colon_split[1]
            elif comparison is not None and has_prose_like_comparison_label(clause):
                label = clause[: comparison.start()].strip()
                candidate_rhs = clause[comparison.end() :].strip()
                if is_readable_label(label) and candidate_rhs:
                    expression_source = candidate_rhs
                    if rendered_clause == markdown_code_span(clause):
                        raise ValueError(
                            f"{element.element_id} collapsed a readable formula label into code"
                        )
            oversized_inline = [
                body
                for body in re.findall(r"\$\$([^$\n]+)\$\$", rendered_clause)
                if latex_render_weight(body) > MAX_INLINE_MATH_WEIGHT
            ]
            if oversized_inline:
                raise ValueError(
                    f"{element.element_id} kept transformed long formula inline: "
                    f"{oversized_inline[0]!r}"
                )

            expected_line = (
                rendered_clause
                if rendered_clause.startswith("$$\n")
                else f"- {rendered_clause}"
            )
            normalized_expected_line = "\n".join(
                line.strip() for line in expected_line.splitlines()
            )
            normalized_rendered = "\n".join(
                line.strip() for line in rendered.splitlines()
            )
            if normalized_expected_line not in normalized_rendered:
                raise ValueError(
                    f"{element.element_id} did not preserve complete formula clause {clause!r}"
                )

    for fixture_id in ("DER-09", "EQV-44"):
        fixture = elements_by_id[fixture_id]
        nested = element_formula_items_markdown(fixture, indent="  ")
        if any(line == "$$" for line in nested.splitlines()):
            raise ValueError(f"{fixture_id} embedded block math escaped checklist indentation")
        if any(line.strip() in {".", "。"} for line in nested.splitlines()):
            raise ValueError(f"{fixture_id} left terminal punctuation on an orphan line")

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

CREATE TABLE concept_questions (
    question_id TEXT PRIMARY KEY NOT NULL,
    element_id TEXT NOT NULL REFERENCES elements(element_id) ON DELETE CASCADE,
    question_type TEXT NOT NULL,
    stem TEXT NOT NULL,
    explanation TEXT NOT NULL,
    difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 3),
    model_version TEXT NOT NULL,
    review_status TEXT NOT NULL,
    source_fact_ids_json TEXT NOT NULL,
    display_order INTEGER NOT NULL UNIQUE
) WITHOUT ROWID;

CREATE TABLE concept_question_choices (
    question_id TEXT NOT NULL REFERENCES concept_questions(question_id) ON DELETE CASCADE,
    choice_key TEXT NOT NULL CHECK (choice_key IN ('A', 'B', 'C', 'D', 'E')),
    choice_order INTEGER NOT NULL CHECK (choice_order BETWEEN 0 AND 4),
    element_id TEXT NOT NULL REFERENCES elements(element_id),
    text TEXT NOT NULL,
    explanation TEXT NOT NULL,
    is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
    PRIMARY KEY (question_id, choice_key),
    UNIQUE (question_id, choice_order)
) WITHOUT ROWID;

CREATE TABLE element_sources (
    element_id TEXT NOT NULL REFERENCES elements(element_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (element_id, source_id)
) WITHOUT ROWID;

CREATE INDEX elements_domain_order_idx
    ON elements(domain_id, display_order);
CREATE INDEX concept_questions_element_idx
    ON concept_questions(element_id, difficulty, display_order);
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
    learning_copy: dict[str, LearningCopy],
    question_bank: dict[str, Any],
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
                    ("concept_question_bank_version", str(question_bank["bankVersion"])),
                    ("concept_question_bank_sha256", str(question_bank["bankSha256"])),
                    ("concept_question_model_version", str(question_bank["modelVersion"])),
                    ("concept_question_release_status", str(question_bank["releaseStatus"])),
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
                copy = learning_copy[element.element_id]
                primary_source = sources[element.source_ids[0]]
                source_ids_json = json.dumps(
                    element.source_ids, ensure_ascii=False, separators=(",", ":")
                )
                definition_markdown = concept_definition_markdown(copy)
                intuition_markdown = concept_intuition_markdown(copy)
                learning_notes = learning_notes_markdown(element)
                formula_markdown = element_formula_to_markdown(element)
                assumptions_markdown = assumption_markdown(element)
                practical_uses = practical_uses_markdown(copy)
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
                        practical_uses,
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
                        practical_uses,
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
            for question_order, question in enumerate(question_bank["questions"]):
                database.execute(
                    """
                    INSERT INTO concept_questions(
                        question_id, element_id, question_type, stem, explanation,
                        difficulty, model_version, review_status,
                        source_fact_ids_json, display_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        question["questionId"],
                        question["elementId"],
                        question["questionType"],
                        question["stem"],
                        question["explanation"],
                        question["difficulty"],
                        question["modelVersion"],
                        question["reviewStatus"],
                        json.dumps(
                            question["sourceFactIds"],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        question_order,
                    ),
                )
                database.executemany(
                    """
                    INSERT INTO concept_question_choices(
                        question_id, choice_key, choice_order, element_id,
                        text, explanation, is_correct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            question["questionId"],
                            choice["key"],
                            choice_order,
                            choice["elementId"],
                            choice["text"],
                            choice["explanation"],
                            int(choice["isCorrect"]),
                        )
                        for choice_order, choice in enumerate(question["choices"])
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
                "concept_questions",
                "concept_question_choices",
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
            "concept_questions": 405,
            "concept_question_choices": 2025,
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
        bank_hash = metadata.get("concept_question_bank_sha256", "")
        if re.fullmatch(r"[0-9a-f]{64}", bank_hash) is None:
            raise ValueError("Concept question bank metadata hash is invalid")
        if metadata.get("concept_question_release_status") not in {
            "bootstrap_not_reviewed", "candidate", "release_ready"
        }:
            raise ValueError("Concept question bank release metadata is invalid")
        malformed_question_groups = database.execute(
            """
            SELECT q.question_id
            FROM concept_questions q
            LEFT JOIN concept_question_choices c ON c.question_id = q.question_id
            GROUP BY q.question_id, q.element_id
            HAVING COUNT(c.choice_key) != 5
                OR SUM(c.is_correct) != 1
                OR SUM(CASE WHEN c.is_correct = 1 AND c.element_id = q.element_id THEN 1 ELSE 0 END) != 1
                OR COUNT(DISTINCT c.text) != 5
            """
        ).fetchall()
        if malformed_question_groups:
            raise ValueError(
                "Concept questions must have five distinct choices and one target answer: "
                f"{malformed_question_groups[:3]}"
            )
        malformed_question_coverage = database.execute(
            """
            SELECT e.element_id, COUNT(q.question_id)
            FROM elements e LEFT JOIN concept_questions q USING(element_id)
            GROUP BY e.element_id
            HAVING COUNT(q.question_id) != 3
            """
        ).fetchall()
        if malformed_question_coverage:
            raise ValueError(
                "Every element must have exactly three concept questions: "
                f"{malformed_question_coverage[:3]}"
            )
        malformed_learning_structure = database.execute(
            """SELECT e.element_id FROM elements e
               JOIN concept_cards c ON c.element_id = e.element_id
               JOIN formula_cards f ON f.element_id = e.element_id
               WHERE length(trim(c.definition)) < 36
                   OR length(trim(c.intuition)) < 72
                   OR c.intuition LIKE '%이 개념을 읽는 순서%'
                   OR c.scope_notes NOT LIKE '### %'
                   OR f.expression LIKE '### %'
                   OR f.assumptions LIKE '### %'
                   OR f.notes NOT LIKE '- %'"""
        ).fetchall()
        if malformed_learning_structure:
            raise ValueError(
                "Learning cards do not follow the six-part learner structure: "
                f"{malformed_learning_structure[:3]}"
            )
        visible_field_names = (
            "definition", "intuition", "learning_scope",
            "formula", "assumptions", "practical_uses",
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
        malformed_math_contexts: list[tuple[str, str, int]] = []
        compound_math_spans: list[tuple[str, str]] = []
        hangul_math_spans: list[tuple[str, str]] = []
        oversized_inline_math: list[tuple[str, str, int]] = []
        visible_code_spans: list[tuple[str, str, str]] = []
        merged_product_math: list[tuple[str, str, str]] = []
        misplaced_headings: list[tuple[str, str]] = []
        formula_duplications: list[tuple[str, str]] = []
        weak_application_sections: list[str] = []
        weak_practical_uses: list[str] = []
        distinct_visible_values = {field: set() for field in visible_field_names}
        for row in visible_rows:
            element_id = row[0]
            for field_name, value in zip(visible_field_names, row[1:]):
                if not value.strip():
                    empty_visible_fields.append((element_id, field_name))
                if value.count("$$") % 2 != 0:
                    malformed_math_fields.append((element_id, field_name))
                for line_number, line in enumerate(value.splitlines(), start=1):
                    if line.count("$$") % 2 != 0 and line.strip() != "$$":
                        malformed_math_contexts.append(
                            (element_id, field_name, line_number)
                        )
                for math_body in re.findall(r"\$\$\n?(.*?)\n?\$\$", value, re.DOTALL):
                    if len(split_formula_clauses(math_body.strip())) > 1:
                        compound_math_spans.append((element_id, field_name))
                    if HANGUL_RE.search(math_body) is not None:
                        hangul_math_spans.append((element_id, field_name))
                    merged = FORBIDDEN_MERGED_PRODUCT_TEX_RE.search(math_body)
                    if merged is not None:
                        merged_product_math.append(
                            (element_id, field_name, merged.group(0))
                        )
                for inline_body in re.findall(r"\$\$([^$\n]+)\$\$", value):
                    weight = latex_render_weight(inline_body)
                    if weight > MAX_INLINE_MATH_WEIGHT:
                        oversized_inline_math.append((element_id, field_name, weight))
                for code_match in MARKDOWN_CODE_SPAN_RE.finditer(value):
                    code_body = code_match.group("body")
                    visible_code_spans.append((element_id, field_name, code_body[:80]))
                if field_name == "learning_scope":
                    if not value.lstrip().startswith("### "):
                        misplaced_headings.append((element_id, field_name))
                    if len(re.findall(r"(?m)^###\s+\S", value)) < 1:
                        weak_application_sections.append(element_id)
                elif value.lstrip().startswith("### "):
                    misplaced_headings.append((element_id, field_name))
                if field_name in {
                    "definition", "intuition", "learning_scope", "practical_uses"
                } and "$$" in value:
                    formula_duplications.append((element_id, field_name))
                if field_name == "practical_uses" and len(
                    re.findall(r"(?m)^-\s+\S", value)
                ) < 2:
                    weak_practical_uses.append(element_id)
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
        if malformed_math_contexts:
            raise ValueError(
                "Block math delimiters share a line with Markdown content: "
                f"{malformed_math_contexts[:3]}"
            )
        if compound_math_spans:
            raise ValueError(
                "Top-level comma-connected equations remain in one math span: "
                f"{compound_math_spans[:3]}"
            )
        if hangul_math_spans:
            raise ValueError(
                "Hangul leaked into JLatex-only spans: "
                f"{hangul_math_spans[:3]}"
            )
        if oversized_inline_math:
            raise ValueError(
                "Transformed long formulas remain inline: "
                f"{oversized_inline_math[:3]}"
            )
        if visible_code_spans:
            raise ValueError(
                "Learning-card fields contain unapproved code spans: "
                f"{visible_code_spans[:3]}"
            )
        if merged_product_math:
            raise ValueError(
                "Implicit products were merged into upright identifiers: "
                f"{merged_product_math[:3]}"
            )
        if misplaced_headings:
            raise ValueError(f"Learning-card headings are misplaced: {misplaced_headings[:3]}")
        if formula_duplications:
            raise ValueError(
                "A formula is repeated outside the dedicated formula card: "
                f"{formula_duplications[:3]}"
            )
        if weak_application_sections:
            raise ValueError(
                "Application content is not segmented into toggle sections: "
                f"{weak_application_sections[:3]}"
            )
        if weak_practical_uses:
            raise ValueError(
                "Practical-use content needs at least two list items: "
                f"{weak_practical_uses[:3]}"
            )

        uniqueness_floors = {
            "definition": 135,
            "intuition": 135,
            "learning_scope": 135,
            "formula": 135,
            "assumptions": 7,
            "practical_uses": 135,
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
            """SELECT e.element_id, f.expression
               FROM elements e JOIN formula_cards f USING(element_id)"""
        ).fetchall()
        formula_code_fallbacks = [
            element_id
            for element_id, expression in formula_rows
            if MARKDOWN_CODE_SPAN_RE.search(expression) is not None
        ]
        if formula_code_fallbacks:
            raise ValueError(
                "Formula cards contain code-span formula fallbacks: "
                f"{formula_code_fallbacks[:3]}"
            )
        latex_card_count = sum("$$" in expression for _, expression in formula_rows)
        if latex_card_count != 135:
            raise ValueError(
                f"Every formula card must contain explicit LaTeX: {latex_card_count}/135"
            )
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
    question_bank: dict[str, Any],
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
        "conceptQuestionBankVersion": question_bank["bankVersion"],
        "conceptQuestionBankSha256": question_bank["bankSha256"],
        "conceptQuestionModelVersion": question_bank["modelVersion"],
        "conceptQuestionReleaseStatus": question_bank["releaseStatus"],
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


def build(
    spec_path: Path,
    asset_dir: Path,
    question_bank_path: Path = DEFAULT_QUESTION_BANK,
) -> dict[str, object]:
    domains, elements, sources, spec_sha256 = parse_spec(spec_path)
    learning_copy = load_learning_copy(
        expected_element_ids=(element.element_id for element in elements)
    )
    question_bank = load_concept_question_bank(
        question_bank_path,
        expected_element_ids=(element.element_id for element in elements),
    )
    database_path = asset_dir / "content.sqlite3"
    manifest_path = asset_dir / "content-manifest.json"
    build_database(
        database_path,
        spec_path,
        spec_sha256,
        domains,
        elements,
        sources,
        learning_copy,
        question_bank,
    )
    row_counts = validate_database(database_path)
    return write_manifest(
        manifest_path,
        database_path,
        spec_path,
        spec_sha256,
        row_counts,
        question_bank,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--question-bank", type=Path, default=DEFAULT_QUESTION_BANK)
    args = parser.parse_args()
    manifest = build(
        args.spec.resolve(),
        args.asset_dir.resolve(),
        args.question_bank.resolve(),
    )
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
