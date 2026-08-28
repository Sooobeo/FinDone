#!/usr/bin/env python3
"""Convert the standalone FinDone workbook HTML into unit-sized Admin data.

The importer intentionally uses only the Python standard library so the same
command can run in local development and CI without another parser dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "output" / "html" / "findone_theory_workbook_ross_integrated_30q.html"
DEFAULT_OUTPUT = ROOT / "admin" / "content" / "workbook"
EXPECTED_SOURCE_SHA256 = "edf526c295d299916bf873cb74900ff31765990280f362f42994c8ded873be52"
CIRCLED_ANSWERS = ("①", "②", "③", "④", "⑤")
UNIT_ID_PATTERN = re.compile(r"^[A-Z0-9-]+$")


class WorkbookImportError(RuntimeError):
    """Raised when the source no longer matches the validated workbook shape."""


@dataclass(frozen=True)
class TocUnit:
    id: str
    anchor: str
    title: str
    question_count: int


@dataclass(frozen=True)
class TocSubject:
    id: str
    title: str
    units: tuple[TocUnit, ...]


def _repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _require_match(pattern: str, source: str, label: str, *, flags: int = re.DOTALL) -> re.Match[str]:
    match = re.search(pattern, source, flags)
    if match is None:
        raise WorkbookImportError(f"Missing {label}")
    return match


def _plain_text(fragment: str, *, preserve_breaks: bool = False) -> str:
    if preserve_breaks:
        fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    else:
        fragment = re.sub(r"<br\s*/?>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = html.unescape(fragment).replace("\xa0", " ")
    if preserve_breaks:
        return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in fragment.splitlines()).strip()
    return re.sub(r"\s+", " ", fragment).strip()


def _class_tokens(attributes: str) -> set[str]:
    match = re.search(r'\bclass="([^"]*)"', attributes)
    return set(match.group(1).split()) if match else set()


def _theory_kind(tag: str, classes: set[str]) -> str:
    if "theory-section-title" in classes or tag == "h3":
        return "section"
    if "element-title" in classes:
        return "element"
    if "concept-title" in classes or tag == "h4":
        return "concept"
    if "theory-label" in classes:
        return "label"
    if "theory-bullet" in classes:
        return "bullet"
    return "body"


def _parse_theory(fragment: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    pattern = re.compile(r"<(h3|h4|p)([^>]*)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
    for match in pattern.finditer(fragment):
        tag = match.group(1).lower()
        classes = _class_tokens(match.group(2))
        text = _plain_text(match.group(3), preserve_breaks=True)
        if not text:
            continue
        blocks.append({"kind": _theory_kind(tag, classes), "text": text})
    if not blocks:
        raise WorkbookImportError("Theory section contains no readable blocks")
    return blocks


def _parse_questions(fragment: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    article_pattern = re.compile(
        r'<article class="question-card searchable" id="([^"]+)">(.*?)</article>',
        re.DOTALL,
    )
    for article_match in article_pattern.finditer(fragment):
        question_id, article = article_match.groups()
        header = _require_match(
            r"<header><strong>([^<]+)</strong><span>(.*?)</span></header>",
            article,
            f"{question_id} header",
        )
        displayed_id = _plain_text(header.group(1))
        if displayed_id != question_id:
            raise WorkbookImportError(f"Question ID mismatch: article={question_id}, header={displayed_id}")
        meta = _plain_text(header.group(2))
        meta_match = re.fullmatch(r"난이도\s+(\d+)\s*·\s*(.+)", meta)
        if meta_match is None:
            raise WorkbookImportError(f"Invalid metadata for {question_id}: {meta}")
        difficulty = int(meta_match.group(1))
        kind = meta_match.group(2).strip()
        if difficulty not in range(1, 6) or not kind:
            raise WorkbookImportError(f"Invalid difficulty/type for {question_id}: {meta}")
        stem = _plain_text(_require_match(r'<p class="stem">(.*?)</p>', article, f"{question_id} stem").group(1), preserve_breaks=True)
        if not stem:
            raise WorkbookImportError(f"Question {question_id} has an empty stem")
        choices_html = _require_match(r'<ol class="choices">(.*?)</ol>', article, f"{question_id} choices").group(1)
        choices = []
        for choice_match in re.finditer(r"<li>(.*?)</li>", choices_html, re.DOTALL):
            choice = _plain_text(choice_match.group(1), preserve_breaks=True)
            choice = re.sub(r"^[①②③④⑤]\s*", "", choice)
            choices.append(choice)
        if len(choices) != 5:
            raise WorkbookImportError(f"Expected 5 choices for {question_id}, found {len(choices)}")
        if any(not choice for choice in choices):
            raise WorkbookImportError(f"Question {question_id} has an empty choice")
        evidence = _plain_text(_require_match(r'<p class="evidence">(.*?)</p>', article, f"{question_id} evidence").group(1))
        evidence = re.sub(r"^근거:\s*", "", evidence)
        if not evidence:
            raise WorkbookImportError(f"Question {question_id} has empty evidence")
        questions.append(
            {
                "id": question_id,
                "difficulty": difficulty,
                "kind": kind,
                "stem": stem,
                "choices": choices,
                "evidence": evidence,
            }
        )
    return questions


def _parse_solutions(fragment: str) -> dict[str, dict[str, Any]]:
    solutions: dict[str, dict[str, Any]] = {}
    detail_pattern = re.compile(
        r'<details class="solution-card searchable" data-answer="([①②③④⑤])">'
        r"<summary><strong>([^<]+)</strong><span>정답 ([①②③④⑤]) · .*?</span></summary>"
        r'<div class="solution-body">(.*?)</div></details>',
        re.DOTALL,
    )
    for detail_match in detail_pattern.finditer(fragment):
        answer, question_id, displayed_answer, body = detail_match.groups()
        if question_id in solutions:
            raise WorkbookImportError(f"Duplicate solution for {question_id}")
        if displayed_answer != answer:
            raise WorkbookImportError(
                f"Solution answer mismatch for {question_id}: data={answer}, summary={displayed_answer}"
            )
        segments: list[dict[str, Any]] = []
        for line_match in re.finditer(r'<p class="solution-line([^"]*)">(.*?)</p>', body, re.DOTALL):
            text = _plain_text(line_match.group(2), preserve_breaks=True)
            if text:
                segments.append({"labelled": "labelled" in line_match.group(1).split(), "text": text})
        if not segments:
            raise WorkbookImportError(f"Solution for {question_id} has no explanation")
        solutions[question_id] = {"answerIndex": CIRCLED_ANSWERS.index(answer), "solution": segments}
    return solutions


def _parse_toc(source: str) -> tuple[TocSubject, ...]:
    toc = _require_match(
        r'<section class="front-section" id="toc">(.*?)</section>', source, "table of contents"
    ).group(1)
    subjects: list[TocSubject] = []
    group_pattern = re.compile(r'<div class="toc-group"><h3>(.*?)</h3>(.*?)</div>', re.DOTALL)
    link_pattern = re.compile(
        r'<a href="#([^"]+)"><span>(.*?)</span><b>(\d+)문항</b></a>', re.DOTALL
    )
    for subject_index, group_match in enumerate(group_pattern.finditer(toc), start=1):
        title = _plain_text(group_match.group(1))
        units: list[TocUnit] = []
        for link_match in link_pattern.finditer(group_match.group(2)):
            anchor, unit_title, question_count = link_match.groups()
            unit_id = anchor.removeprefix("unit-")
            if anchor != f"unit-{unit_id}" or UNIT_ID_PATTERN.fullmatch(unit_id) is None:
                raise WorkbookImportError(f"Unsafe or invalid unit ID in TOC: {anchor}")
            units.append(TocUnit(unit_id, anchor, _plain_text(unit_title), int(question_count)))
        if not units:
            raise WorkbookImportError(f"TOC subject has no units: {title}")
        subjects.append(TocSubject(f"subject-{subject_index:02d}", title, tuple(units)))
    return tuple(subjects)


def _unit_slices(source: str) -> dict[str, str]:
    starts = list(
        re.finditer(
            r'<section class="unit" id="unit-([^"]+)" data-unit="([^"]+)"(?: data-qa="true")?>',
            source,
        )
    )
    slices: dict[str, str] = {}
    for index, start in enumerate(starts):
        anchor_id, unit_id = start.groups()
        if anchor_id != unit_id:
            raise WorkbookImportError(f"Unit anchor/data mismatch: {anchor_id} != {unit_id}")
        if UNIT_ID_PATTERN.fullmatch(unit_id) is None:
            raise WorkbookImportError(f"Unsafe or invalid unit section ID: {unit_id}")
        end = starts[index + 1].start() if index + 1 < len(starts) else source.find('<section class="appendix"', start.end())
        if end < 0:
            raise WorkbookImportError(f"Could not find end of unit {unit_id}")
        if unit_id in slices:
            raise WorkbookImportError(f"Duplicate unit {unit_id}")
        slices[unit_id] = source[start.start() : end]
    return slices


def _parse_unit(unit_id: str, fragment: str, subject: TocSubject, toc_unit: TocUnit, source_sha256: str) -> dict[str, Any]:
    opener_end = fragment.find('<section class="theory-section">')
    problem_start = fragment.find('<section class="problem-section">')
    solution_start = fragment.find('<section class="solution-section">')
    if min(opener_end, problem_start, solution_start) < 0 or not (opener_end < problem_start < solution_start):
        raise WorkbookImportError(f"Invalid section order for unit {unit_id}")

    opener = fragment[:opener_end]
    theory_html = fragment[opener_end:problem_start]
    problem_html = fragment[problem_start:solution_start]
    solution_html = fragment[solution_start:]

    title = _plain_text(_require_match(r'<div class="unit-opener">.*?<h2>(.*?)</h2>', opener, f"{unit_id} title").group(1))
    subtitle_match = re.search(r'<p class="unit-subtitle">(.*?)</p>', opener, re.DOTALL)
    subtitle = _plain_text(subtitle_match.group(1)) if subtitle_match else ""
    meta_match = re.search(r'<div class="unit-meta">(.*?)</div>', opener, re.DOTALL)
    meta = [_plain_text(item) for item in re.findall(r"<span>(.*?)</span>", meta_match.group(1), re.DOTALL)] if meta_match else []
    source_match = re.search(r'<p class="source-note">(.*?)</p>', opener, re.DOTALL)
    source_note = _plain_text(source_match.group(1)) if source_match else ""

    questions = _parse_questions(problem_html)
    solutions = _parse_solutions(solution_html)
    question_ids = [question["id"] for question in questions]
    if len(question_ids) != toc_unit.question_count:
        raise WorkbookImportError(
            f"Unit {unit_id} expected {toc_unit.question_count} questions, found {len(question_ids)}"
        )
    if set(question_ids) != set(solutions):
        missing = sorted(set(question_ids) - set(solutions))
        extra = sorted(set(solutions) - set(question_ids))
        raise WorkbookImportError(f"Question/solution mismatch for {unit_id}: missing={missing}, extra={extra}")
    for question in questions:
        question.update(solutions[question["id"]])

    toc_heading = toc_unit.title.split("·", maxsplit=1)[-1].strip()
    if title != toc_heading:
        raise WorkbookImportError(f"TOC/unit title mismatch for {unit_id}: {toc_unit.title!r} != {title!r}")

    return {
        "schemaVersion": 1,
        "sourceSha256": source_sha256,
        "id": unit_id,
        "anchor": toc_unit.anchor,
        "subjectId": subject.id,
        "subjectTitle": subject.title,
        "title": toc_unit.title,
        "subtitle": subtitle,
        "meta": meta,
        "sourceNote": source_note,
        "theory": _parse_theory(theory_html),
        "questions": questions,
    }


def build_workbook(
    source_bytes: bytes,
    *,
    require_known_source: bool = True,
    source_file_name: str = DEFAULT_SOURCE.name,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if require_known_source and source_sha256 != EXPECTED_SOURCE_SHA256:
        raise WorkbookImportError(
            f"Source hash changed: expected {EXPECTED_SOURCE_SHA256}, found {source_sha256}. "
            "Review the new workbook and pass --accept-source-change to regenerate deliberately."
        )
    try:
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise WorkbookImportError("Workbook must be UTF-8") from error

    title = _plain_text(_require_match(r"<title>(.*?)</title>", source, "document title").group(1))
    subjects = _parse_toc(source)
    slices = _unit_slices(source)
    toc_units = [(subject, unit) for subject in subjects for unit in subject.units]
    if set(slices) != {unit.id for _, unit in toc_units}:
        raise WorkbookImportError("TOC and unit section IDs do not match")

    units: dict[str, dict[str, Any]] = {}
    all_question_ids: set[str] = set()
    for subject, toc_unit in toc_units:
        parsed = _parse_unit(toc_unit.id, slices[toc_unit.id], subject, toc_unit, source_sha256)
        current_ids = {question["id"] for question in parsed["questions"]}
        duplicates = current_ids & all_question_ids
        if duplicates:
            raise WorkbookImportError(f"Duplicate question IDs: {sorted(duplicates)}")
        all_question_ids.update(current_ids)
        units[toc_unit.id] = parsed

    question_count = sum(len(unit["questions"]) for unit in units.values())
    if len(subjects) != 12 or len(units) != 45 or question_count != 1350:
        raise WorkbookImportError(
            f"Unexpected workbook totals: subjects={len(subjects)}, units={len(units)}, questions={question_count}"
        )

    concept_element_count = len(re.findall(r'class="element-card searchable"', source))
    glossary_term_count = len(re.findall(r'class="glossary-card searchable"', source))
    if concept_element_count != 135 or glossary_term_count != 1649:
        raise WorkbookImportError(
            "Unexpected appendix totals: "
            f"conceptElements={concept_element_count}, glossaryTerms={glossary_term_count}"
        )

    index = {
        "schemaVersion": 1,
        "source": {
            "fileName": source_file_name,
            "sha256": source_sha256,
            "title": title,
        },
        "stats": {
            "subjectCount": len(subjects),
            "unitCount": len(units),
            "questionCount": question_count,
            "conceptElementCount": concept_element_count,
            "glossaryTermCount": glossary_term_count,
        },
        "subjects": [
            {
                "id": subject.id,
                "title": subject.title,
                "units": [
                    {
                        "id": unit.id,
                        "anchor": unit.anchor,
                        "title": unit.title,
                        "questionCount": unit.question_count,
                    }
                    for unit in subject.units
                ],
            }
            for subject in subjects
        ],
    }
    return index, units


def write_workbook(index: dict[str, Any], units: dict[str, dict[str, Any]], output: Path) -> None:
    output = output.resolve()
    units_dir = output / "units"
    units_dir.mkdir(parents=True, exist_ok=True)

    expected_files = {f"{unit_id}.json" for unit_id in units}
    stale_files = sorted(path.name for path in units_dir.glob("*.json") if path.name not in expected_files)
    if stale_files:
        raise WorkbookImportError(
            f"Refusing to leave stale generated unit files in {_repo_path(units_dir)}: {', '.join(stale_files)}"
        )

    json_options = {"ensure_ascii": False, "indent": 2}

    def atomic_write(path: Path, value: dict[str, Any]) -> None:
        resolved = path.resolve()
        if resolved.parent not in {output, units_dir}:
            raise WorkbookImportError(f"Refusing to write outside workbook output: {_repo_path(resolved)}")
        temporary = resolved.with_name(f".{resolved.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(value, **json_options) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(resolved)

    atomic_write(output / "index.json", index)
    for unit_id, unit in units.items():
        if UNIT_ID_PATTERN.fullmatch(unit_id) is None:
            raise WorkbookImportError(f"Refusing to write unsafe unit ID: {unit_id}")
        atomic_write(units_dir / f"{unit_id}.json", unit)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Standalone workbook HTML")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Admin workbook data directory")
    parser.add_argument(
        "--accept-source-change",
        action="store_true",
        help="Allow a reviewed source whose SHA-256 differs from the pinned workbook",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise WorkbookImportError(f"Workbook source not found: {_repo_path(source)}")
    index, units = build_workbook(
        source.read_bytes(),
        require_known_source=not args.accept_source_change,
        source_file_name=source.name,
    )
    write_workbook(index, units, args.output)
    print(
        "Workbook import complete\n"
        f"  source: {_repo_path(source)}\n"
        f"  output: {_repo_path(args.output)}\n"
        f"  subjects: {index['stats']['subjectCount']}\n"
        f"  units: {index['stats']['unitCount']}\n"
        f"  questions: {index['stats']['questionCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
