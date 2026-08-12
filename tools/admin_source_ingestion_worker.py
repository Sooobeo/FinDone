#!/usr/bin/env python3
"""Extract queued FinDone source files/URLs and persist reproducible evidence.

The worker claims only ``file_extract`` and ``url_fetch`` jobs through dedicated
service-role RPCs. It streams private Storage objects or safely pinned public
HTTP(S) responses into a temporary sandbox, verifies or calculates SHA-256,
preserves URL snapshots, parses supported documents, runs local OCR when
available, builds deterministic element-match candidates, and atomically seals
the source version. It never approves content or modifies Android data.
"""

from __future__ import annotations

import argparse
import csv
import http.client
import hashlib
import html
import io
import ipaddress
import json
import math
import mimetypes
import os
import re
import socket
import sqlite3
import ssl
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.admin_import_supabase import normalize_supabase_url, resolve_supabase_url


SOURCE_BUCKET = "source-private"
QUEUE_CATALOG_RPC = "queue_catalog_url_sources"
CLAIM_RPC = "claim_source_ingestion_job"
PROGRESS_RPC = "update_source_ingestion_progress"
COMPLETE_RPC = "complete_source_ingestion_job"
FAIL_RPC = "fail_source_ingestion_job"
STATE_RPC = "get_source_ingestion_job_state"
PARSER_NAME = "findone-source-ingestion"
PARSER_VERSION = "admin-v1"

WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
MAX_HTTP_JSON_BYTES = 16 * 1024 * 1024
MAX_EXTRACTED_CHARS = 3_000_000
MAX_EXTRACTED_UTF8_BYTES = 3 * 1024 * 1024
MAX_FRAGMENT_CHARS = 96_000
MAX_FRAGMENT_UTF8_BYTES = 100 * 1024
MAX_FRAGMENTS = 3_500
MAX_TEXT_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SQLITE_TABLES = 200
MAX_SQLITE_COLUMNS = 500
MAX_SQLITE_ROWS = 1_000_000
MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_RATIO = 250
MAX_PDF_PAGES = 2_000
MAX_OCR_PAGES = 120
MAX_IMAGE_PIXELS = 80_000_000
MAX_URL_REDIRECTS = 5
OCR_REVIEW_THRESHOLD = 0.90
MATCH_REVIEW_THRESHOLD = 0.92
MATCH_MINIMUM_SCORE = 0.08

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".pptx": "pptx",
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".db": "sqlite",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".html": "html",
    ".htm": "html",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}

URL_MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/x-ndjson": ".jsonl",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
UNSAFE_HOST_SUFFIXES = (
    ".localhost", ".local", ".internal", ".home.arpa", ".nip.io", ".sslip.io", ".xip.io",
)

FORMULA_LINE_RE = re.compile(
    r"(?:=|≤|≥|≠|≈|∑|√|\^|\b(?:NPV|IRR|WACC|CAPM|DCF|ROE|ROA|EBITDA)\b)",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


class SourceWorkerError(RuntimeError):
    """Raised when a source cannot be processed or persisted safely."""


@dataclass(frozen=True)
class SourceFragment:
    kind: str
    text: str
    locator: dict[str, Any]
    ocr_confidence: float | None = None

    def as_rpc(self) -> dict[str, Any]:
        normalized = normalize_text(self.text)
        result: dict[str, Any] = {
            "kind": self.kind,
            "text": self.text,
            "normalizedText": normalized,
            "locator": self.locator,
        }
        if self.ocr_confidence is not None:
            result["ocrConfidence"] = round(self.ocr_confidence, 4)
        return result


@dataclass(frozen=True)
class ElementCandidate:
    element_id: str
    rank: int
    score: float
    reason: str
    matched_terms: tuple[str, ...]

    def as_rpc(self) -> dict[str, Any]:
        return {
            "elementId": self.element_id,
            "rank": self.rank,
            "score": round(self.score, 5),
            "reason": self.reason,
            "matchedTerms": list(self.matched_terms),
        }


@dataclass
class ExtractionResult:
    fragments: list[SourceFragment]
    metadata: dict[str, Any]
    requires_review: bool = False
    review_reasons: list[str] = field(default_factory=list)

    @property
    def extracted_text(self) -> str:
        return join_extracted_text(self.fragments)

    def require_review(self, reason: str) -> None:
        self.requires_review = True
        if reason not in self.review_reasons:
            self.review_reasons.append(reason)


@dataclass(frozen=True)
class WorkerOutcome:
    job_id: str
    source_version_id: str
    parse_status: str
    fragment_count: int
    candidate_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "sourceVersionId": self.source_version_id,
            "parseStatus": self.parse_status,
            "fragmentCount": self.fragment_count,
            "candidateCount": self.candidate_count,
        }


@dataclass(frozen=True)
class URLFetchResult:
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    content_type: str
    original_filename: str
    byte_size: int
    sha256: str
    response_headers: dict[str, str]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\x00", " ")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in normalized.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if line:
            compact.append(line)
            blank = False
        elif compact and not blank:
            compact.append("")
            blank = True
    return "\n".join(compact).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_uuid(value: Any, label: str) -> str:
    try:
        result = str(uuid.UUID(str(value)))
    except (ValueError, AttributeError) as error:
        raise SourceWorkerError(f"{label} is not a canonical UUID") from error
    if result != str(value).lower():
        raise SourceWorkerError(f"{label} is not a canonical UUID")
    return result


def _safe_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise SourceWorkerError(f"{label} is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise SourceWorkerError(f"{label} is invalid") from error
    if result < minimum:
        raise SourceWorkerError(f"{label} is invalid")
    return result


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _numeric_suffix(value: str) -> tuple[float, str]:
    match = re.search(r"(\d+)(?=\.[^.]+$)", value)
    return (int(match.group(1)) if match else math.inf, value)


def decode_document_text(body: bytes) -> tuple[str, str]:
    if body.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates = ("utf-16",)
    else:
        candidates = ("utf-8-sig", "cp949", "utf-16")
    for encoding in candidates:
        try:
            text = body.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if "\x00" not in text[:4096]:
            return text, encoding
    raise SourceWorkerError("텍스트 인코딩을 안전하게 판별할 수 없습니다")


def _read_bounded_text_source(path: Path) -> bytes:
    if path.stat().st_size > MAX_TEXT_SOURCE_BYTES:
        raise SourceWorkerError("텍스트 원본 크기가 parser 안전 제한(64 MiB)을 초과했습니다")
    return path.read_bytes()


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _normalize_table_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\x00", " ")
    lines: list[str] = []
    for line in normalized.splitlines():
        cells = [re.sub(r"[ \f\v]+", " ", cell).strip() for cell in line.split("\t")]
        if any(cells):
            lines.append("\t".join(cells))
    return "\n".join(lines).strip()


def _split_fragment_text(value: str, *, preserve_tabs: bool = False) -> list[str]:
    remaining = _normalize_table_text(value) if preserve_tabs else normalize_text(value)
    chunks: list[str] = []
    while remaining:
        chunk = _truncate_utf8(remaining[:MAX_FRAGMENT_CHARS], MAX_FRAGMENT_UTF8_BYTES)
        if not chunk:
            break
        chunks.append(chunk)
        remaining = remaining[len(chunk) :].lstrip()
    return chunks


def _chunk_text(
    text: str,
    *,
    kind: str,
    locator: Mapping[str, Any],
    chunk_chars: int = 8_000,
    ocr_confidence: float | None = None,
) -> list[SourceFragment]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for paragraph in re.split(r"\n{2,}", normalized):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) > chunk_chars:
            if current:
                chunks.append("\n\n".join(current))
                current, current_size = [], 0
            chunks.extend(paragraph[index : index + chunk_chars] for index in range(0, len(paragraph), chunk_chars))
            continue
        projected = current_size + len(paragraph) + (2 if current else 0)
        if current and projected > chunk_chars:
            chunks.append("\n\n".join(current))
            current, current_size = [], 0
        current.append(paragraph)
        current_size += len(paragraph) + (2 if current_size else 0)
    if current:
        chunks.append("\n\n".join(current))
    return [
        SourceFragment(
            kind=kind,
            text=chunk[:MAX_FRAGMENT_CHARS],
            locator={**locator, "chunk": index},
            ocr_confidence=ocr_confidence,
        )
        for index, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def _formula_fragments(
    text: str,
    locator: Mapping[str, Any],
    *,
    limit: int = 100,
) -> list[SourceFragment]:
    result: list[SourceFragment] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = normalize_text(raw_line)
        if len(line) < 3 or len(line) > 1_000 or not FORMULA_LINE_RE.search(line):
            continue
        fingerprint = line.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(
            SourceFragment(
                kind="formula",
                text=line,
                locator={**locator, "line": line_number, "candidate": True},
            )
        )
        if len(result) >= limit:
            break
    return result


def _bounded_result(result: ExtractionResult) -> ExtractionResult:
    bounded: list[SourceFragment] = []
    total_chars = 0
    total_bytes = 0
    truncated = False
    for fragment in result.fragments:
        for part_index, text in enumerate(
            _split_fragment_text(fragment.text, preserve_tabs=fragment.kind == "table")
        ):
            if len(bounded) >= MAX_FRAGMENTS or total_chars >= MAX_EXTRACTED_CHARS or total_bytes >= MAX_EXTRACTED_UTF8_BYTES:
                truncated = True
                break
            remaining_chars = MAX_EXTRACTED_CHARS - total_chars
            remaining_bytes = MAX_EXTRACTED_UTF8_BYTES - total_bytes
            if len(text) > remaining_chars or len(text.encode("utf-8")) > remaining_bytes:
                text = _truncate_utf8(text[:remaining_chars], remaining_bytes)
                truncated = True
            if not text:
                break
            locator = dict(fragment.locator)
            if part_index:
                locator["part"] = part_index
            bounded.append(
                SourceFragment(
                    kind=fragment.kind,
                    text=text,
                    locator=locator,
                    ocr_confidence=fragment.ocr_confidence,
                )
            )
            total_chars += len(text) + 2
            total_bytes += len(text.encode("utf-8")) + 2
        if truncated:
            break
    result.fragments = bounded
    if truncated:
        result.metadata["outputTruncated"] = True
        result.require_review("extraction_limit_reached")
    if not result.fragments:
        result.require_review("no_extractable_text")
    return result


def join_extracted_text(fragments: Sequence[SourceFragment]) -> str:
    primary = [fragment.text for fragment in fragments if fragment.kind != "formula"]
    if not primary:
        primary = [fragment.text for fragment in fragments]
    return _truncate_utf8(
        normalize_text("\n\n".join(primary))[:MAX_EXTRACTED_CHARS],
        MAX_EXTRACTED_UTF8_BYTES,
    )


def validate_zip_archive(archive: zipfile.ZipFile) -> dict[str, int]:
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise SourceWorkerError("압축 문서의 항목 수가 안전 제한을 초과했습니다")
    total = 0
    for entry in entries:
        if entry.flag_bits & 0x1:
            raise SourceWorkerError("암호화된 압축 문서는 처리할 수 없습니다")
        if entry.file_size > MAX_ARCHIVE_MEMBER_BYTES:
            raise SourceWorkerError("압축 문서 내부 항목이 안전 제한을 초과했습니다")
        total += entry.file_size
        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise SourceWorkerError("압축 해제 크기가 안전 제한을 초과했습니다")
        if entry.compress_size > 0 and entry.file_size / entry.compress_size > MAX_ARCHIVE_RATIO:
            raise SourceWorkerError("비정상적으로 높은 압축률의 문서를 거부했습니다")
    return {"archiveEntryCount": len(entries), "archiveUncompressedBytes": total}


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        entry = archive.getinfo(name)
    except KeyError as error:
        raise SourceWorkerError(f"문서 필수 항목이 없습니다: {name}") from error
    if entry.file_size > MAX_ARCHIVE_MEMBER_BYTES:
        raise SourceWorkerError("문서 내부 XML이 안전 제한을 초과했습니다")
    body = archive.read(entry)
    if len(body) != entry.file_size:
        raise SourceWorkerError("문서 내부 XML 크기가 일치하지 않습니다")
    if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
        raise SourceWorkerError("외부·사용자 정의 XML entity가 포함된 문서를 거부했습니다")
    return body


class _VisibleHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "caption", "dd", "div", "dl",
        "dt", "figcaption", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header",
        "hr", "li", "main", "nav", "p", "pre", "section", "table", "td", "th", "tr",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title = ""
        self.canonical_url = ""
        self.author = ""
        self.published_at = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        attributes = {name.casefold(): value or "" for name, value in attrs}
        if lowered == "link" and "canonical" in attributes.get("rel", "").casefold().split():
            self.canonical_url = attributes.get("href", "")[:2048]
        if lowered == "meta":
            key = (attributes.get("name") or attributes.get("property")).casefold()
            content = normalize_text(attributes.get("content", ""))
            if key in {"author", "article:author"} and content:
                self.author = content[:500]
            if key in {"article:published_time", "date", "datepublished", "publishdate"} and content:
                self.published_at = content[:200]
        if lowered in self.SKIP_TAGS:
            self.skip_depth += 1
        if lowered == "title":
            self._in_title = True
        if not self.skip_depth and lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "title":
            self._in_title = False
        if lowered in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if not self.skip_depth and lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        value = html.unescape(data)
        self.parts.append(value)
        if self._in_title:
            self.title += value

    @property
    def text(self) -> str:
        return normalize_text(" ".join(self.parts))


def extract_plain_text(path: Path, source_format: str) -> ExtractionResult:
    body = _read_bounded_text_source(path)
    text, encoding = decode_document_text(body)
    metadata: dict[str, Any] = {"parser": source_format, "encoding": encoding}
    if source_format == "html":
        parser = _VisibleHTMLParser()
        parser.feed(text)
        parser.close()
        text = parser.text
        metadata["title"] = normalize_text(parser.title)[:500]
        if parser.canonical_url:
            metadata["canonicalUrl"] = parser.canonical_url
        if parser.author:
            metadata["author"] = parser.author
        if parser.published_at:
            metadata["publishedAt"] = parser.published_at
    fragments = _chunk_text(text, kind="text", locator={"type": source_format})
    fragments.extend(_formula_fragments(text, {"type": source_format}))
    return _bounded_result(ExtractionResult(fragments=fragments, metadata=metadata))


def extract_csv(path: Path) -> ExtractionResult:
    body = _read_bounded_text_source(path)
    text, encoding = decode_document_text(body)
    sample = text[:64_000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    csv.field_size_limit(1024 * 1024)
    reader = csv.reader(io.StringIO(text), dialect)
    fragments: list[SourceFragment] = []
    rows: list[str] = []
    start_row = 1
    row_count = 0
    max_columns = 0
    for row_count, row in enumerate(reader, start=1):
        if len(row) > 2_000:
            raise SourceWorkerError("CSV 열 개수가 안전 제한을 초과했습니다")
        max_columns = max(max_columns, len(row))
        rows.append("\t".join(normalize_text(cell) for cell in row))
        if len(rows) >= 100 or sum(map(len, rows)) >= 32_000:
            fragments.append(
                SourceFragment(
                    kind="table",
                    text="\n".join(rows),
                    locator={"type": "csv", "rowStart": start_row, "rowEnd": row_count},
                )
            )
            rows = []
            start_row = row_count + 1
        if row_count >= 1_000_000:
            raise SourceWorkerError("CSV 행 개수가 안전 제한을 초과했습니다")
    if rows:
        fragments.append(
            SourceFragment(
                kind="table",
                text="\n".join(rows),
                locator={"type": "csv", "rowStart": start_row, "rowEnd": row_count},
            )
        )
    all_text = "\n".join(fragment.text for fragment in fragments)
    fragments.extend(_formula_fragments(all_text, {"type": "csv"}))
    return _bounded_result(
        ExtractionResult(
            fragments=fragments,
            metadata={
                "parser": "csv",
                "encoding": encoding,
                "rowCount": row_count,
                "maxColumnCount": max_columns,
                "delimiter": getattr(dialect, "delimiter", ","),
            },
        )
    )


def _json_input_records(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("records", "items", "content", "elements", "rows", "data"):
            child = value.get(key)
            if isinstance(child, list):
                return child
        return [value]
    raise SourceWorkerError("JSON 원본은 객체 또는 배열이어야 합니다")


def extract_json(path: Path, *, json_lines: bool = False) -> ExtractionResult:
    body = _read_bounded_text_source(path)
    text, encoding = decode_document_text(body)
    records: list[Any] = []
    try:
        if json_lines:
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                records.append(json.loads(line))
                if len(records) > MAX_SQLITE_ROWS:
                    raise SourceWorkerError("JSONL 레코드 수가 안전 제한을 초과했습니다")
        else:
            records = _json_input_records(json.loads(text))
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise SourceWorkerError("JSON 구조를 안전하게 해석할 수 없습니다") from error

    fragments: list[SourceFragment] = []
    batch: list[Any] = []
    batch_chars = 0
    batch_start = 1
    for index, record in enumerate(records, start=1):
        serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if batch and (len(batch) >= 50 or batch_chars + len(serialized) > 32_000):
            fragments.append(
                SourceFragment(
                    "table",
                    json.dumps(batch, ensure_ascii=False, separators=(",", ":")),
                    {"type": "jsonl" if json_lines else "json", "recordStart": batch_start, "recordEnd": index - 1},
                )
            )
            batch = []
            batch_chars = 0
            batch_start = index
        batch.append(record)
        batch_chars += len(serialized)
    if batch:
        payload: Any = batch[0] if len(batch) == 1 else batch
        fragments.append(
            SourceFragment(
                "table",
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                {"type": "jsonl" if json_lines else "json", "recordStart": batch_start, "recordEnd": len(records)},
            )
        )
    return _bounded_result(
        ExtractionResult(
            fragments=fragments,
            metadata={
                "parser": "jsonl" if json_lines else "json",
                "encoding": encoding,
                "recordCount": len(records),
            },
        )
    )


def _sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sqlite_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return f"[BLOB {len(value)} bytes sha256={hashlib.sha256(value).hexdigest()}]"
    return normalize_text(str(value))[:32_000]


def extract_sqlite(path: Path) -> ExtractionResult:
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            raise SourceWorkerError("SQLite 확장자와 실제 파일 서명이 일치하지 않습니다")
    uri = f"file:{urllib.parse.quote(path.resolve().as_posix(), safe='/:')}?mode=ro&immutable=1"
    try:
        database = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise SourceWorkerError("SQLite DB를 읽기 전용으로 열 수 없습니다") from error
    fragments: list[SourceFragment] = []
    total_rows = 0
    table_count = 0
    try:
        database.enable_load_extension(False)
        database.execute("PRAGMA query_only = ON")
        database.execute("PRAGMA trusted_schema = OFF")
        integrity = database.execute("PRAGMA quick_check(1)").fetchone()
        if not integrity or integrity[0] != "ok":
            raise SourceWorkerError("SQLite quick_check를 통과하지 못했습니다")
        tables = database.execute(
            "SELECT name, coalesce(sql, '') FROM sqlite_schema "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if len(tables) > MAX_SQLITE_TABLES:
            raise SourceWorkerError("SQLite 테이블 수가 안전 제한을 초과했습니다")
        for raw_table_name, create_sql in tables:
            table_name = str(raw_table_name)
            if str(create_sql).lstrip().upper().startswith("CREATE VIRTUAL TABLE"):
                continue
            table_count += 1
            identifier = _sqlite_identifier(table_name)
            try:
                cursor = database.execute(f"SELECT * FROM {identifier}")
            except sqlite3.Error as error:
                raise SourceWorkerError(f"SQLite 테이블을 읽을 수 없습니다: {table_name[:120]}") from error
            columns = [str(item[0]) for item in (cursor.description or [])]
            if not columns or len(columns) > MAX_SQLITE_COLUMNS:
                raise SourceWorkerError("SQLite 열 개수가 안전 제한을 초과했습니다")
            batch_rows: list[str] = []
            batch_start = 1
            table_row = 0
            for row in cursor:
                table_row += 1
                total_rows += 1
                if total_rows > MAX_SQLITE_ROWS:
                    raise SourceWorkerError("SQLite 전체 행 수가 안전 제한을 초과했습니다")
                batch_rows.append("\t".join(_sqlite_cell(value) for value in row))
                if len(batch_rows) >= 100 or sum(map(len, batch_rows)) >= 32_000:
                    fragments.append(
                        SourceFragment(
                            "table",
                            "\t".join(columns) + "\n" + "\n".join(batch_rows),
                            {"type": "sqlite", "table": table_name[:300], "rowStart": batch_start, "rowEnd": table_row},
                        )
                    )
                    batch_rows = []
                    batch_start = table_row + 1
            if batch_rows:
                fragments.append(
                    SourceFragment(
                        "table",
                        "\t".join(columns) + "\n" + "\n".join(batch_rows),
                        {"type": "sqlite", "table": table_name[:300], "rowStart": batch_start, "rowEnd": table_row},
                    )
                )
    except sqlite3.Error as error:
        raise SourceWorkerError("SQLite DB 구조를 안전하게 해석할 수 없습니다") from error
    finally:
        database.close()
    if not fragments:
        raise SourceWorkerError("SQLite DB에 읽을 수 있는 사용자 테이블 행이 없습니다")
    return _bounded_result(
        ExtractionResult(
            fragments=fragments,
            metadata={"parser": "sqlite3-readonly", "tableCount": table_count, "rowCount": total_rows},
        )
    )


def extract_docx(path: Path) -> ExtractionResult:
    with zipfile.ZipFile(path) as archive:
        archive_stats = validate_zip_archive(archive)
        root = ElementTree.fromstring(_read_zip_member(archive, "word/document.xml"))
    body = next((node for node in root.iter() if _local_name(node.tag) == "body"), root)
    fragments: list[SourceFragment] = []
    paragraph_count = 0
    table_count = 0
    for block_index, block in enumerate(list(body)):
        kind = _local_name(block.tag)
        if kind == "p":
            value = normalize_text("".join(node.text or "" for node in block.iter() if _local_name(node.tag) == "t"))
            if value:
                fragments.append(SourceFragment("text", value, {"type": "docx", "block": block_index, "paragraph": paragraph_count}))
                paragraph_count += 1
        elif kind == "tbl":
            rows: list[str] = []
            for row in (node for node in block.iter() if _local_name(node.tag) == "tr"):
                cells: list[str] = []
                for cell in (node for node in list(row) if _local_name(node.tag) == "tc"):
                    cells.append(normalize_text("".join(node.text or "" for node in cell.iter() if _local_name(node.tag) == "t")))
                if cells:
                    rows.append("\t".join(cells))
            if rows:
                fragments.append(SourceFragment("table", "\n".join(rows), {"type": "docx", "block": block_index, "table": table_count}))
                table_count += 1
    combined = "\n".join(fragment.text for fragment in fragments)
    fragments.extend(_formula_fragments(combined, {"type": "docx"}))
    return _bounded_result(
        ExtractionResult(
            fragments=fragments,
            metadata={**archive_stats, "parser": "docx", "paragraphCount": paragraph_count, "tableCount": table_count},
        )
    )


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(_read_zip_member(archive, "xl/sharedStrings.xml"))
    result: list[str] = []
    for item in (node for node in root.iter() if _local_name(node.tag) == "si"):
        result.append(normalize_text("".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t")))
    return result


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: Sequence[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    formula = next((node.text or "" for node in cell if _local_name(node.tag) == "f"), "")
    raw = next((node.text or "" for node in cell if _local_name(node.tag) == "v"), "")
    inline = "".join(node.text or "" for node in cell.iter() if _local_name(node.tag) == "t")
    if cell_type == "s" and raw.isdigit() and int(raw) < len(shared_strings):
        value = shared_strings[int(raw)]
    elif cell_type == "inlineStr":
        value = inline
    elif cell_type == "b":
        value = "TRUE" if raw == "1" else "FALSE"
    else:
        value = raw or inline
    if formula:
        return f"={formula}" + (f" → {value}" if value else "")
    return normalize_text(value)


def extract_xlsx(path: Path) -> ExtractionResult:
    with zipfile.ZipFile(path) as archive:
        archive_stats = validate_zip_archive(archive)
        names = archive.namelist()
        if "xl/workbook.xml" not in names:
            raise SourceWorkerError("XLSX workbook.xml이 없습니다")
        shared_strings = _xlsx_shared_strings(archive)
        worksheets = sorted(
            (name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)),
            key=_numeric_suffix,
        )
        fragments: list[SourceFragment] = []
        total_rows = 0
        for sheet_number, worksheet_name in enumerate(worksheets, start=1):
            root = ElementTree.fromstring(_read_zip_member(archive, worksheet_name))
            batch: list[str] = []
            batch_start = 1
            last_row = 0
            for row in (node for node in root.iter() if _local_name(node.tag) == "row"):
                row_number = int(row.attrib.get("r", last_row + 1))
                values = [
                    _xlsx_cell_value(cell, shared_strings)
                    for cell in row
                    if _local_name(cell.tag) == "c"
                ]
                batch.append("\t".join(values))
                last_row = row_number
                total_rows += 1
                if len(batch) >= 100 or sum(map(len, batch)) >= 32_000:
                    fragments.append(
                        SourceFragment(
                            "table",
                            "\n".join(batch),
                            {"type": "xlsx", "sheet": sheet_number, "rowStart": batch_start, "rowEnd": row_number},
                        )
                    )
                    batch, batch_start = [], row_number + 1
                if total_rows > 1_000_000:
                    raise SourceWorkerError("XLSX 전체 행 개수가 안전 제한을 초과했습니다")
            if batch:
                fragments.append(
                    SourceFragment(
                        "table",
                        "\n".join(batch),
                        {"type": "xlsx", "sheet": sheet_number, "rowStart": batch_start, "rowEnd": last_row},
                    )
                )
    combined = "\n".join(fragment.text for fragment in fragments)
    fragments.extend(_formula_fragments(combined, {"type": "xlsx"}))
    return _bounded_result(
        ExtractionResult(
            fragments=fragments,
            metadata={**archive_stats, "parser": "xlsx", "sheetCount": len(worksheets), "rowCount": total_rows},
        )
    )


def extract_pptx(path: Path) -> ExtractionResult:
    with zipfile.ZipFile(path) as archive:
        archive_stats = validate_zip_archive(archive)
        slides = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=_numeric_suffix,
        )
        fragments: list[SourceFragment] = []
        for slide_number, slide_name in enumerate(slides, start=1):
            root = ElementTree.fromstring(_read_zip_member(archive, slide_name))
            values = [normalize_text(node.text or "") for node in root.iter() if _local_name(node.tag) == "t"]
            text = "\n".join(value for value in values if value)
            fragments.extend(_chunk_text(text, kind="text", locator={"type": "pptx", "slide": slide_number}))
            fragments.extend(_formula_fragments(text, {"type": "pptx", "slide": slide_number}, limit=20))
    return _bounded_result(
        ExtractionResult(
            fragments=fragments,
            metadata={**archive_stats, "parser": "pptx", "slideCount": len(slides)},
        )
    )


def _ocr_image(image: Any) -> tuple[str, float | None, str]:
    try:
        import pytesseract  # type: ignore[import-not-found]
        from pytesseract import Output  # type: ignore[import-not-found]
    except ImportError as error:
        raise SourceWorkerError("로컬 OCR 구성요소(pytesseract)가 설치되지 않았습니다") from error

    try:
        languages = set(pytesseract.get_languages(config=""))
    except Exception as error:
        raise SourceWorkerError("Tesseract OCR 실행 파일을 사용할 수 없습니다") from error
    language = "kor+eng" if {"kor", "eng"}.issubset(languages) else "eng" if "eng" in languages else ""
    if not language:
        raise SourceWorkerError("Tesseract OCR 언어 데이터가 설치되지 않았습니다")
    try:
        data = pytesseract.image_to_data(image, lang=language, output_type=Output.DICT, config="--psm 6")
    except Exception as error:
        raise SourceWorkerError("Tesseract OCR 실행에 실패했습니다") from error
    words: list[str] = []
    confidences: list[float] = []
    for word, raw_confidence in zip(data.get("text", []), data.get("conf", []), strict=False):
        value = normalize_text(str(word))
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = -1
        if value:
            words.append(value)
            if confidence >= 0:
                confidences.append(confidence / 100)
    average = sum(confidences) / len(confidences) if confidences else None
    return " ".join(words), average, language


def extract_image(path: Path) -> ExtractionResult:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as error:
        raise SourceWorkerError("이미지 처리 구성요소(Pillow)가 설치되지 않았습니다") from error
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with Image.open(path) as image:
        width, height = image.size
        if width * height > MAX_IMAGE_PIXELS:
            raise SourceWorkerError("이미지 픽셀 수가 OCR 안전 제한을 초과했습니다")
        image.load()
        text, confidence, language = _ocr_image(image.convert("RGB"))
    fragments = _chunk_text(
        text,
        kind="ocr",
        locator={"type": "image", "width": width, "height": height},
        ocr_confidence=confidence,
    )
    result = ExtractionResult(
        fragments=fragments,
        metadata={
            "parser": "image-ocr",
            "width": width,
            "height": height,
            "ocrLanguage": language,
            "ocrConfidence": confidence,
        },
    )
    if confidence is None or confidence < OCR_REVIEW_THRESHOLD:
        result.require_review("low_ocr_confidence")
    return _bounded_result(result)


def extract_pdf(
    path: Path,
    progress: Callable[[int, str, Mapping[str, Any]], None] | None = None,
) -> ExtractionResult:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as error:
        raise SourceWorkerError("PDF 처리 구성요소(PyMuPDF)가 설치되지 않았습니다") from error

    try:
        document = fitz.open(path)
    except Exception as error:
        raise SourceWorkerError("PDF를 열 수 없습니다") from error
    page_count = document.page_count
    fragments: list[SourceFragment] = []
    review_reasons: list[str] = []
    ocr_confidences: list[float] = []
    ocr_pages = 0
    missing_ocr_pages = 0
    try:
        if document.needs_pass:
            raise SourceWorkerError("암호화된 PDF는 처리할 수 없습니다")
        if page_count > MAX_PDF_PAGES:
            raise SourceWorkerError("PDF 페이지 수가 안전 제한을 초과했습니다")
        for page_index in range(page_count):
            page = document.load_page(page_index)
            page_texts: list[str] = []
            try:
                blocks = page.get_text("blocks", sort=True)
            except Exception as error:
                raise SourceWorkerError(f"PDF {page_index + 1}페이지 텍스트 추출에 실패했습니다") from error
            for block_index, block in enumerate(blocks):
                if len(block) < 5:
                    continue
                text = normalize_text(str(block[4]))
                if not text:
                    continue
                locator = {
                    "type": "pdf",
                    "page": page_index + 1,
                    "block": block_index,
                    "bbox": [round(float(value), 2) for value in block[:4]],
                }
                fragments.append(SourceFragment("text", text, locator))
                page_texts.append(text)
            native_text = "\n".join(page_texts)
            if len(re.sub(r"\s+", "", native_text)) < 40:
                if ocr_pages >= MAX_OCR_PAGES:
                    missing_ocr_pages += 1
                else:
                    try:
                        from PIL import Image  # type: ignore[import-not-found]

                        ocr_scale = 300 / 72
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(ocr_scale, ocr_scale), alpha=False)
                        if pixmap.width * pixmap.height > MAX_IMAGE_PIXELS:
                            raise SourceWorkerError("PDF OCR 이미지 픽셀 수가 안전 제한을 초과했습니다")
                        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                        ocr_text, confidence, language = _ocr_image(image)
                        ocr_pages += 1
                        if ocr_text:
                            fragments.extend(
                                _chunk_text(
                                    ocr_text,
                                    kind="ocr",
                                    locator={"type": "pdf", "page": page_index + 1, "ocr": True},
                                    ocr_confidence=confidence,
                                )
                            )
                        if confidence is not None:
                            ocr_confidences.append(confidence)
                        if confidence is None or confidence < OCR_REVIEW_THRESHOLD:
                            review_reasons.append("low_ocr_confidence")
                    except SourceWorkerError:
                        missing_ocr_pages += 1
            page_formula_text = native_text
            fragments.extend(
                _formula_fragments(page_formula_text, {"type": "pdf", "page": page_index + 1}, limit=30)
            )
            if progress and page_count:
                progress(
                    48 + int(24 * (page_index + 1) / page_count),
                    "ocr" if ocr_pages else "extracting",
                    {"page": page_index + 1, "pageCount": page_count},
                )
    finally:
        document.close()

    metadata: dict[str, Any] = {
        "parser": "pymupdf",
        "parserLibraryVersion": getattr(fitz, "VersionBind", "unknown"),
        "pageCount": page_count,
        "ocrPageCount": ocr_pages,
        "ocrUnavailablePageCount": missing_ocr_pages,
        "ocrDpi": 300,
        "ocrConfidence": sum(ocr_confidences) / len(ocr_confidences) if ocr_confidences else None,
    }
    result = ExtractionResult(fragments=fragments, metadata=metadata)
    for reason in review_reasons:
        result.require_review(reason)
    if missing_ocr_pages:
        result.require_review("ocr_required_or_unavailable")
    return _bounded_result(result)


def detect_source_format(path: Path, original_filename: str, mime_type: str) -> str:
    extension = Path(original_filename).suffix.casefold()
    source_format = SUPPORTED_EXTENSIONS.get(extension)
    if source_format is None:
        raise SourceWorkerError(f"지원하지 않는 파일 형식입니다: {extension or '(확장자 없음)'}")
    with path.open("rb") as stream:
        prefix = stream.read(16)
    if source_format == "pdf" and not prefix.startswith(b"%PDF-"):
        raise SourceWorkerError("PDF 확장자와 실제 파일 서명이 일치하지 않습니다")
    if source_format in {"docx", "xlsx", "pptx"} and not prefix.startswith(b"PK"):
        raise SourceWorkerError("Office 문서 확장자와 실제 ZIP 서명이 일치하지 않습니다")
    if source_format == "image":
        valid = (
            prefix.startswith(b"\x89PNG\r\n\x1a\n")
            or prefix.startswith(b"\xff\xd8\xff")
            or (prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP")
        )
        if not valid:
            raise SourceWorkerError("이미지 확장자와 실제 파일 서명이 일치하지 않습니다")
    if source_format == "sqlite" and prefix != b"SQLite format 3\x00":
        raise SourceWorkerError("SQLite 확장자와 실제 파일 서명이 일치하지 않습니다")
    if source_format in {"text", "markdown", "csv", "json", "jsonl", "html"} and b"\x00" in prefix:
        raise SourceWorkerError("텍스트 파일에서 바이너리 서명이 감지되었습니다")
    if not mime_type.strip():
        raise SourceWorkerError("등록된 MIME 형식이 없습니다")
    return source_format


def extract_source(
    path: Path,
    original_filename: str,
    mime_type: str,
    progress: Callable[[int, str, Mapping[str, Any]], None] | None = None,
) -> ExtractionResult:
    source_format = detect_source_format(path, original_filename, mime_type)
    if source_format == "pdf":
        return extract_pdf(path, progress)
    if source_format == "docx":
        return extract_docx(path)
    if source_format == "xlsx":
        return extract_xlsx(path)
    if source_format == "pptx":
        return extract_pptx(path)
    if source_format == "csv":
        return extract_csv(path)
    if source_format == "json":
        return extract_json(path)
    if source_format == "jsonl":
        return extract_json(path, json_lines=True)
    if source_format == "sqlite":
        return extract_sqlite(path)
    if source_format == "image":
        return extract_image(path)
    return extract_plain_text(path, source_format)


def _terms(value: str) -> Counter[str]:
    tokens = [token.casefold() for token in TOKEN_RE.findall(normalize_text(value))]
    return Counter(tokens)


def _character_ngrams(value: str, size: int = 3) -> set[str]:
    compact = re.sub(r"[^0-9a-z가-힣]+", "", normalize_text(value).casefold())
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def match_elements(source_text: str, catalog: Sequence[Mapping[str, Any]]) -> list[ElementCandidate]:
    source_sample = source_text[:750_000]
    normalized_source = normalize_text(source_sample).casefold()
    source_terms = _terms(source_sample)
    source_ngrams = _character_ngrams(source_sample)
    scored: list[tuple[float, str, tuple[str, ...]]] = []
    for row in catalog:
        element_id = str(row.get("element_id", ""))
        segments = [
            str(row.get(field, "") or "")
            for field in (
                "title", "topic_name", "subtopic_name", "core_relation", "scope_notes",
                "concept_title", "definition_markdown", "intuition_markdown",
                "formula_titles", "formula_expressions",
            )
            if str(row.get(field, "") or "").strip()
        ]
        corpus = "\n".join(segments)
        candidate_terms = _terms(corpus)
        if not element_id or not candidate_terms:
            continue
        matched = sorted(
            (term for term in candidate_terms if term in source_terms),
            key=lambda term: (-len(term), term),
        )
        weighted_total = sum(min(count, 3) * max(1, len(term) - 1) for term, count in candidate_terms.items())
        weighted_match = sum(
            min(candidate_terms[term], source_terms[term], 3) * max(1, len(term) - 1)
            for term in matched
        )
        token_score = weighted_match / weighted_total if weighted_total else 0.0
        segment_scores: list[float] = []
        for segment in segments:
            segment_normalized = normalize_text(segment).casefold()
            segment_ngrams = _character_ngrams(segment)
            if len(segment_normalized) >= 4 and segment_normalized in normalized_source:
                segment_scores.append(1.0)
            elif segment_ngrams:
                segment_scores.append(len(segment_ngrams & source_ngrams) / len(segment_ngrams))
        ngram_score = max(segment_scores, default=0.0)
        title = normalize_text(str(row.get("title", ""))).casefold()
        title_exact = bool(len(title) >= 4 and title in normalized_source)
        element_id_exact = bool(
            re.search(
                rf"(?<![0-9a-z]){re.escape(element_id.casefold())}(?![0-9a-z])",
                normalized_source,
            )
        )
        score = min(1.0, 0.25 * token_score + 0.75 * ngram_score)
        if element_id_exact:
            score = 1.0
        elif title_exact:
            score = max(score, 0.96)
        scored.append((score, element_id, tuple(matched[:12])))
    scored.sort(key=lambda item: (-item[0], item[1]))
    result: list[ElementCandidate] = []
    for rank, (score, element_id, matched) in enumerate(scored[:5], start=1):
        if score < MATCH_MINIMUM_SCORE and result:
            continue
        reason = (
            "원본의 명시적 요소 ID와 카탈로그 ID가 정확히 일치합니다"
            if re.search(rf"(?<![0-9a-z]){re.escape(element_id.casefold())}(?![0-9a-z])", normalized_source)
            else f"정규화 용어 {len(matched)}개와 문자 패턴을 결정론적으로 대조했습니다"
            if matched
            else "직접 일치 용어가 적어 낮은 점수의 후보입니다"
        )
        result.append(ElementCandidate(element_id, rank, score, reason, matched))
    return result


def route_after_matching(result: ExtractionResult, candidates: Sequence[ElementCandidate]) -> str:
    if result.metadata.get("duplicateOfSourceVersionId"):
        return "R0_DUPLICATE"
    if not candidates:
        result.require_review("no_element_match")
        return "REVIEW_NO_MATCH"
    top_score = candidates[0].score
    gap = top_score - (candidates[1].score if len(candidates) > 1 else 0.0)
    result.metadata["elementTop1Score"] = round(top_score, 5)
    result.metadata["top1Top2Gap"] = round(gap, 5)
    if top_score >= MATCH_REVIEW_THRESHOLD and gap >= 0.12:
        return "R0_DETERMINISTIC_MATCH"
    result.require_review("ambiguous_element_match")
    return "REVIEW_SEMANTIC_MATCH"


def resolve_public_source_url(
    value: str,
    resolver: Callable[..., Sequence[tuple[Any, ...]]] = socket.getaddrinfo,
) -> tuple[urllib.parse.SplitResult, tuple[str, ...]]:
    if not value or len(value) > 2048 or re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise SourceWorkerError("URL 형식이 안전하지 않습니다")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise SourceWorkerError("URL 포트 형식이 올바르지 않습니다") from error
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceWorkerError("URL은 공개 HTTP 또는 HTTPS 주소여야 합니다")
    if parsed.username is not None or parsed.password is not None:
        raise SourceWorkerError("인증정보가 포함된 URL은 수집하지 않습니다")

    raw_hostname = parsed.hostname.rstrip(".")
    try:
        hostname = raw_hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as error:
        raise SourceWorkerError("URL 호스트 이름을 해석할 수 없습니다") from error
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise SourceWorkerError("IP 주소를 직접 지정한 URL은 수집하지 않습니다")
    if (
        "." not in hostname
        or hostname == "localhost"
        or ".." in hostname
        or hostname.startswith("-")
        or hostname.endswith("-")
        or any(hostname.endswith(suffix) for suffix in UNSAFE_HOST_SUFFIXES)
        or re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", hostname) is None
    ):
        raise SourceWorkerError("공개 DNS 호스트가 아닌 URL은 수집하지 않습니다")

    default_port = 443 if scheme == "https" else 80
    if port is not None and port != default_port:
        raise SourceWorkerError("URL 수집은 HTTP/HTTPS 기본 포트만 허용합니다")
    try:
        address_rows = resolver(hostname, default_port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise SourceWorkerError("URL 호스트의 DNS를 해석할 수 없습니다") from error
    addresses = sorted({str(row[4][0]).split("%", 1)[0] for row in address_rows if len(row) >= 5 and row[4]})
    if not addresses:
        raise SourceWorkerError("URL 호스트에 연결 가능한 DNS 주소가 없습니다")
    for address in addresses:
        try:
            resolved_ip = ipaddress.ip_address(address)
        except ValueError as error:
            raise SourceWorkerError("DNS가 올바르지 않은 IP 주소를 반환했습니다") from error
        if not resolved_ip.is_global:
            raise SourceWorkerError("DNS가 사설망·로컬·예약 주소를 반환해 수집을 차단했습니다")

    normalized = urllib.parse.SplitResult(
        scheme,
        hostname,
        parsed.path or "/",
        parsed.query,
        "",
    )
    return normalized, tuple(addresses)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, port: int, pinned_ip: str, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = self._create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        port: int,
        pinned_ip: str,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=context)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        raw_socket = self._create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def _open_pinned_public_response(
    parsed: urllib.parse.SplitResult,
    addresses: Sequence[str],
    timeout_seconds: float,
    ssl_context: ssl.SSLContext,
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    request_target = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    default_port = 443 if parsed.scheme == "https" else 80
    last_error: Exception | None = None
    for address in addresses:
        connection: http.client.HTTPConnection
        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(parsed.hostname or "", default_port, address, timeout_seconds, ssl_context)
        else:
            connection = _PinnedHTTPConnection(parsed.hostname or "", default_port, address, timeout_seconds)
        try:
            connection.request(
                "GET",
                request_target,
                headers={
                    "Accept": "text/html,application/pdf,text/plain,text/csv,text/markdown,application/vnd.openxmlformats-officedocument.*;q=0.8,image/*;q=0.6",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "User-Agent": "FinDoneSourceWorker/1.0",
                },
            )
            return connection, connection.getresponse()
        except (OSError, ssl.SSLError, http.client.HTTPException) as error:
            last_error = error
            connection.close()
    raise SourceWorkerError("검증된 공개 IP로 URL 원본에 연결하지 못했습니다") from last_error


def _safe_url_filename(final_url: str, content_type: str, content_disposition: str) -> str:
    filename = ""
    encoded_match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
    plain_match = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;]+))', content_disposition, re.IGNORECASE)
    if encoded_match:
        filename = urllib.parse.unquote(encoded_match.group(1))
    elif plain_match:
        filename = (plain_match.group(1) or plain_match.group(2) or "").strip()
    if not filename:
        filename = urllib.parse.unquote(Path(urllib.parse.urlsplit(final_url).path).name)
    filename = Path(filename.replace("\\", "/")).name
    filename = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", filename)[:300].strip("._")
    expected_extension = URL_MIME_EXTENSIONS[content_type]
    if not filename:
        filename = "url-snapshot" + expected_extension
    elif Path(filename).suffix.casefold() != expected_extension:
        filename = (Path(filename).stem[:260] or "url-snapshot") + expected_extension
    return filename


def _url_content_type(raw_content_type: str, final_url: str) -> str:
    content_type = raw_content_type.split(";", 1)[0].strip().casefold()
    if content_type == "application/xhtml+xml":
        return "text/html"
    if content_type in URL_MIME_EXTENSIONS:
        return content_type
    if content_type in {"", "application/octet-stream", "binary/octet-stream"}:
        guessed, _ = mimetypes.guess_type(urllib.parse.urlsplit(final_url).path)
        guessed = (guessed or "").casefold()
        if guessed in URL_MIME_EXTENSIONS:
            return guessed
    raise SourceWorkerError("URL 응답의 문서 형식을 지원하지 않습니다")


def fetch_public_url_to_path(
    requested_url: str,
    destination: Path,
    *,
    max_bytes: int,
    timeout_seconds: float,
    on_progress: Callable[[int, int], None] | None = None,
    resolver: Callable[..., Sequence[tuple[Any, ...]]] = socket.getaddrinfo,
    opener: Callable[
        [urllib.parse.SplitResult, Sequence[str], float, ssl.SSLContext],
        tuple[http.client.HTTPConnection, http.client.HTTPResponse],
    ] = _open_pinned_public_response,
) -> URLFetchResult:
    if max_bytes < 1:
        raise SourceWorkerError("URL 다운로드 안전 제한이 올바르지 않습니다")
    ssl_context = ssl.create_default_context()
    current_url = requested_url
    redirect_chain: list[str] = []

    for redirect_index in range(MAX_URL_REDIRECTS + 1):
        parsed, addresses = resolve_public_source_url(current_url, resolver)
        normalized_url = urllib.parse.urlunsplit(parsed)
        if not redirect_chain or redirect_chain[-1] != normalized_url:
            redirect_chain.append(normalized_url)
        connection, response = opener(parsed, addresses, timeout_seconds, ssl_context)
        try:
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                response.read(64 * 1024)
                if redirect_index >= MAX_URL_REDIRECTS or not location:
                    raise SourceWorkerError("URL redirect 횟수 또는 Location header가 안전 기준을 벗어났습니다")
                next_url = urllib.parse.urljoin(normalized_url, location)
                if parsed.scheme == "https" and urllib.parse.urlsplit(next_url).scheme.casefold() == "http":
                    raise SourceWorkerError("HTTPS에서 HTTP로 내려가는 redirect는 차단했습니다")
                current_url = next_url
                continue
            if response.status != 200:
                response.read(64 * 1024)
                raise SourceWorkerError(f"URL 원본 응답이 HTTP {response.status}입니다")
            content_encoding = (response.getheader("Content-Encoding") or "identity").strip().casefold()
            if content_encoding not in {"", "identity"}:
                raise SourceWorkerError("압축된 HTTP 응답은 안전한 크기 검증을 위해 거부했습니다")
            content_length_header = response.getheader("Content-Length")
            try:
                content_length = int(content_length_header) if content_length_header else 0
            except ValueError as error:
                raise SourceWorkerError("URL 응답 Content-Length가 올바르지 않습니다") from error
            if content_length < 0 or content_length > max_bytes:
                raise SourceWorkerError("URL 원본이 Worker 다운로드 안전 제한을 초과했습니다")
            content_type = _url_content_type(response.getheader("Content-Type") or "", normalized_url)
            filename = _safe_url_filename(
                normalized_url,
                content_type,
                response.getheader("Content-Disposition") or "",
            )
            selected_headers = {
                name: value[:2000]
                for name in ("Content-Type", "Content-Length", "ETag", "Last-Modified", "Cache-Control")
                if (value := response.getheader(name))
            }
            digest = hashlib.sha256()
            downloaded = 0
            with destination.open("xb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > max_bytes or (content_length and downloaded > content_length):
                        raise SourceWorkerError("URL 원본이 선언 크기 또는 안전 제한을 초과했습니다")
                    output.write(block)
                    digest.update(block)
                    if on_progress:
                        on_progress(downloaded, content_length or max_bytes)
            if content_length and downloaded != content_length:
                raise SourceWorkerError("URL 원본 다운로드 크기가 Content-Length와 다릅니다")
            if downloaded < 1:
                raise SourceWorkerError("URL 원본 응답이 비어 있습니다")
            return URLFetchResult(
                requested_url=redirect_chain[0],
                final_url=normalized_url,
                redirect_chain=tuple(redirect_chain),
                content_type=content_type,
                original_filename=filename,
                byte_size=downloaded,
                sha256=digest.hexdigest(),
                response_headers=selected_headers,
            )
        except (OSError, ssl.SSLError, http.client.HTTPException) as error:
            raise SourceWorkerError("URL 원본을 읽는 중 연결이 끊겼습니다") from error
        finally:
            connection.close()
    raise SourceWorkerError("URL redirect 안전 제한을 초과했습니다")


class SupabaseSourceClient:
    def __init__(self, base_url: str, secret_key: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = normalize_supabase_url(base_url)
        self.secret_key = secret_key.strip()
        if not self.secret_key:
            raise SourceWorkerError("SUPABASE_SECRET_KEY is missing")
        if timeout_seconds < 1 or timeout_seconds > 300:
            raise SourceWorkerError("timeout must be between 1 and 300 seconds")
        self.timeout_seconds = timeout_seconds
        self.ssl_context = ssl.create_default_context()

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        max_bytes: int = MAX_HTTP_JSON_BYTES,
        accept: str = "application/json",
    ) -> bytes:
        headers = {"apikey": self.secret_key, "Accept": accept}
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(self.base_url + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                result = response.read(max_bytes + 1)
        except urllib.error.HTTPError as error:
            response_body = error.read(4096).decode("utf-8", errors="replace")
            raise SourceWorkerError(
                f"Supabase {method} {path.split('?', 1)[0]} failed with HTTP {error.code}: {response_body[:1000]}"
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise SourceWorkerError("Could not reach Supabase") from error
        if len(result) > max_bytes:
            raise SourceWorkerError("Supabase response exceeded its safety limit")
        return result

    def rpc(self, name: str, payload: Mapping[str, Any]) -> Any:
        if name not in {QUEUE_CATALOG_RPC, CLAIM_RPC, PROGRESS_RPC, COMPLETE_RPC, FAIL_RPC}:
            raise SourceWorkerError("Unsupported source worker RPC")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(body) > 20 * 1024 * 1024:
            raise SourceWorkerError("Source worker RPC payload exceeded its safety limit")
        raw = self._request("POST", f"/rest/v1/rpc/{name}", body=body, max_bytes=2 * 1024 * 1024)
        try:
            return json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceWorkerError(f"{name} returned invalid JSON") from error

    def select(
        self,
        table: str,
        *,
        columns: Sequence[str],
        filters: Mapping[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        max_bytes: int = MAX_HTTP_JSON_BYTES,
    ) -> list[dict[str, Any]]:
        allowed = {
            "source_versions", "source_files", "source_fragments", "source_element_candidates",
            "elements", "concepts", "formulas",
        }
        if table not in allowed:
            raise SourceWorkerError("Unsupported source worker table read")
        query: dict[str, str] = {"select": ",".join(columns)}
        query.update(filters or {})
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = str(limit)
        raw = self._request("GET", f"/rest/v1/{table}?{urllib.parse.urlencode(query)}", max_bytes=max_bytes)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceWorkerError(f"{table} returned invalid JSON") from error
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise SourceWorkerError(f"{table} returned an unexpected response")
        return value

    def select_one(self, table: str, **kwargs: Any) -> dict[str, Any]:
        rows = self.select(table, limit=2, **kwargs)
        if len(rows) != 1:
            raise SourceWorkerError(f"Expected exactly one {table} row")
        return rows[0]

    @staticmethod
    def _storage_path(bucket: str, object_path: str) -> str:
        parts = [urllib.parse.quote(part, safe="") for part in object_path.split("/")]
        return "/storage/v1/object/" + urllib.parse.quote(bucket, safe="") + "/" + "/".join(parts)

    def download_to_path(
        self,
        bucket: str,
        object_path: str,
        destination: Path,
        *,
        expected_bytes: int,
        max_bytes: int,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> str:
        if expected_bytes < 1 or expected_bytes > max_bytes:
            raise SourceWorkerError(
                f"원본 파일 크기가 Worker 안전 제한({max_bytes // (1024 * 1024)} MiB)을 초과했습니다"
            )
        headers = {"apikey": self.secret_key, "Accept": "application/octet-stream"}
        request = urllib.request.Request(
            self.base_url + self._storage_path(bucket, object_path),
            method="GET",
            headers=headers,
        )
        digest = hashlib.sha256()
        downloaded = 0
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) != expected_bytes:
                    raise SourceWorkerError("Storage 원본 크기가 등록 metadata와 다릅니다")
                with destination.open("xb") as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        downloaded += len(block)
                        if downloaded > max_bytes or downloaded > expected_bytes:
                            raise SourceWorkerError("Storage 원본이 등록 크기 또는 안전 제한을 초과했습니다")
                        output.write(block)
                        digest.update(block)
                        if on_progress:
                            on_progress(downloaded, expected_bytes)
        except urllib.error.HTTPError as error:
            error.read(4096)
            raise SourceWorkerError(f"Storage 원본 다운로드가 HTTP {error.code}로 실패했습니다") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise SourceWorkerError("Storage 원본 다운로드 연결이 실패했습니다") from error
        if downloaded != expected_bytes:
            raise SourceWorkerError("Storage 원본 다운로드 크기가 등록 metadata와 다릅니다")
        return digest.hexdigest()

    def upload_from_path(
        self,
        bucket: str,
        object_path: str,
        source: Path,
        *,
        content_type: str,
        max_bytes: int,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        byte_size = source.stat().st_size
        if byte_size < 1 or byte_size > max_bytes:
            raise SourceWorkerError("URL snapshot 크기가 Storage 업로드 안전 제한을 벗어났습니다")
        base = urllib.parse.urlsplit(self.base_url)
        connection_class = http.client.HTTPSConnection if base.scheme == "https" else http.client.HTTPConnection
        connection = connection_class(base.hostname or "", port=base.port, timeout=self.timeout_seconds)
        request_path = self._storage_path(bucket, object_path)
        if base.path and base.path != "/":
            request_path = base.path.rstrip("/") + request_path
        try:
            connection.putrequest("POST", request_path)
            connection.putheader("apikey", self.secret_key)
            connection.putheader("Accept", "application/json")
            connection.putheader("Content-Type", content_type)
            connection.putheader("Content-Length", str(byte_size))
            connection.putheader("Cache-Control", "3600")
            connection.putheader("x-upsert", "true")
            connection.endheaders()
            uploaded = 0
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    connection.send(block)
                    uploaded += len(block)
                    if on_progress:
                        on_progress(uploaded, byte_size)
            response = connection.getresponse()
            response_body = response.read(8193)
            if len(response_body) > 8192:
                raise SourceWorkerError("Storage snapshot 응답이 안전 제한을 초과했습니다")
            if response.status not in {200, 201}:
                detail = response_body.decode("utf-8", errors="replace")[:1000]
                raise SourceWorkerError(f"URL snapshot 저장이 HTTP {response.status}로 실패했습니다: {detail}")
        except (OSError, ssl.SSLError, http.client.HTTPException) as error:
            raise SourceWorkerError("URL snapshot을 Storage에 저장하지 못했습니다") from error
        finally:
            connection.close()


def _rpc_object(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1 and isinstance(value[0], dict):
            return value[0]
    if isinstance(value, dict):
        return value
    raise SourceWorkerError(f"{label} RPC returned an unexpected response")


class SourceIngestionWorker:
    def __init__(
        self,
        client: SupabaseSourceClient,
        worker_id: str,
        *,
        max_source_bytes: int = MAX_SOURCE_BYTES,
        auto_queue_catalog: int = 0,
    ) -> None:
        if WORKER_ID_RE.fullmatch(worker_id) is None:
            raise SourceWorkerError("worker id is invalid")
        if max_source_bytes < 1024 or max_source_bytes > 10 * 1024 * 1024 * 1024:
            raise SourceWorkerError("max source bytes is outside the safe supported range")
        if auto_queue_catalog < 0 or auto_queue_catalog > 100:
            raise SourceWorkerError("auto queue catalog count must be between 0 and 100")
        self.client = client
        self.worker_id = worker_id
        self.max_source_bytes = max_source_bytes
        self.auto_queue_catalog = auto_queue_catalog
        self._catalog_queue_attempted = False
        self._last_progress = 0
        self._last_stage = ""
        self._last_progress_at = 0.0

    def _progress(self, job_id: str, percent: int, stage: str, details: Mapping[str, Any] | None = None) -> None:
        percent = max(1, min(99, percent))
        now = time.monotonic()
        if stage == self._last_stage and percent <= self._last_progress and now - self._last_progress_at < 20:
            return
        if stage == self._last_stage and percent - self._last_progress < 3 and now - self._last_progress_at < 10:
            return
        self.client.rpc(
            PROGRESS_RPC,
            {
                "p_job_id": job_id,
                "p_worker_id": self.worker_id,
                "p_progress_percent": percent,
                "p_stage": stage,
                "p_details": dict(details or {}),
            },
        )
        self._last_progress = max(self._last_progress, percent)
        self._last_stage = stage
        self._last_progress_at = now

    def _is_paused(self, job_id: str) -> bool:
        state = _rpc_object(self.client.rpc(STATE_RPC, {"p_job_id": job_id}), "source job state")
        return bool(state and state.get("jobStatus") == "paused")

    def _catalog(self) -> list[dict[str, Any]]:
        elements = self.client.select(
            "elements",
            columns=("element_id", "title", "topic_name", "subtopic_name", "core_relation", "scope_notes"),
            filters={"is_active": "eq.true"},
            order="display_order.asc",
            limit=500,
        )
        by_element = {str(row["element_id"]): dict(row) for row in elements if row.get("element_id")}
        concepts = self.client.select(
            "concepts",
            columns=("element_id", "title", "definition_markdown", "intuition_markdown"),
            limit=500,
        )
        for row in concepts:
            target = by_element.get(str(row.get("element_id", "")))
            if target is not None:
                target["concept_title"] = row.get("title", "")
                target["definition_markdown"] = row.get("definition_markdown", "")
                target["intuition_markdown"] = row.get("intuition_markdown", "")
        formulas = self.client.select(
            "formulas",
            columns=("element_id", "title", "expression_markdown"),
            order="element_id.asc,display_order.asc",
            limit=2_000,
        )
        formula_values: dict[str, dict[str, list[str]]] = {}
        for row in formulas:
            bucket = formula_values.setdefault(str(row.get("element_id", "")), {"titles": [], "expressions": []})
            bucket["titles"].append(str(row.get("title", "")))
            bucket["expressions"].append(str(row.get("expression_markdown", "")))
        for element_id, values in formula_values.items():
            target = by_element.get(element_id)
            if target is not None:
                target["formula_titles"] = "\n".join(values["titles"])
                target["formula_expressions"] = "\n".join(values["expressions"])
        return list(by_element.values())

    def _duplicate_result(self, source_version_id: str, sha256: str) -> ExtractionResult | None:
        duplicates = self.client.select(
            "source_versions",
            columns=("source_version_id", "parse_status", "extracted_text", "extraction_metadata"),
            filters={
                "sha256": f"eq.{sha256}",
                "source_version_id": f"neq.{source_version_id}",
                "parse_status": "in.(ready,needs_review)",
            },
            order="created_at.asc",
            limit=1,
            max_bytes=10 * 1024 * 1024,
        )
        if not duplicates:
            return None
        duplicate = duplicates[0]
        duplicate_id = _canonical_uuid(duplicate.get("source_version_id"), "duplicate source version id")
        fragments_rows = self.client.select(
            "source_fragments",
            columns=("fragment_kind", "content_text", "locator", "ocr_confidence"),
            filters={"source_version_id": f"eq.{duplicate_id}"},
            order="ordinal.asc",
            limit=MAX_FRAGMENTS,
            max_bytes=12 * 1024 * 1024,
        )
        if not fragments_rows:
            return None
        fragments = [
            SourceFragment(
                kind=str(row.get("fragment_kind", "text")),
                text=str(row.get("content_text", "")),
                locator=dict(row.get("locator") or {}),
                ocr_confidence=float(row["ocr_confidence"]) if row.get("ocr_confidence") is not None else None,
            )
            for row in fragments_rows
            if str(row.get("content_text", "")).strip()
        ]
        metadata = dict(duplicate.get("extraction_metadata") or {})
        metadata.update({"duplicateOfSourceVersionId": duplicate_id, "parser": "duplicate-reuse"})
        result = ExtractionResult(fragments=fragments, metadata=metadata)
        if duplicate.get("parse_status") == "needs_review":
            result.require_review("duplicate_requires_review")
        return _bounded_result(result)

    def process_one(self) -> WorkerOutcome | None:
        if self.auto_queue_catalog and not self._catalog_queue_attempted:
            self._catalog_queue_attempted = True
            queued = _rpc_object(
                self.client.rpc(
                    QUEUE_CATALOG_RPC,
                    {
                        "p_source_ids": None,
                        "p_limit": self.auto_queue_catalog,
                        "p_refresh": False,
                    },
                ),
                "queue catalog sources",
            )
            if queued is not None:
                queued_count = queued.get("queuedCount", 0)
                if type(queued_count) is not int or not 0 <= queued_count <= self.auto_queue_catalog:
                    raise SourceWorkerError("catalog queue RPC returned an invalid count")
        claimed = _rpc_object(
            self.client.rpc(CLAIM_RPC, {"p_worker_id": self.worker_id}),
            "claim source ingestion",
        )
        if claimed is None:
            return None
        self._last_progress = 0
        self._last_stage = ""
        self._last_progress_at = 0.0
        job_id = _canonical_uuid(claimed.get("job_id"), "job id")
        source_version_id = _canonical_uuid(claimed.get("source_version_id"), "source version id")
        job_kind = str(claimed.get("job_kind", ""))
        snapshot_details: dict[str, Any] = {}

        try:
            if job_kind not in {"file_extract", "url_fetch"} or claimed.get("status") != "running":
                raise SourceWorkerError("claim RPC returned an unsupported or non-running source job")
            version = self.client.select_one(
                "source_versions",
                columns=(
                    "source_version_id", "source_id", "original_filename", "mime_type", "byte_size",
                    "sha256", "parse_status", "fetch_url", "created_by",
                ),
                filters={"source_version_id": f"eq.{source_version_id}"},
            )
            job_input = claimed.get("input")
            if not isinstance(job_input, dict):
                raise SourceWorkerError("source job input is invalid")

            with tempfile.TemporaryDirectory(prefix="findone-source-") as directory_name:
                last_download_percent = -1

                def download_progress(downloaded: int, total: int) -> None:
                    nonlocal last_download_percent
                    percent = 4 + int(28 * downloaded / total)
                    if percent != last_download_percent:
                        self._progress(
                            job_id,
                            percent,
                            "downloading",
                            {"bytesDownloaded": downloaded, "bytesTotal": total},
                        )
                        last_download_percent = percent

                if job_kind == "file_extract":
                    files = self.client.select(
                        "source_files",
                        columns=(
                            "bucket_id", "object_path", "original_filename", "mime_type",
                            "byte_size", "sha256", "file_role",
                        ),
                        filters={"source_version_id": f"eq.{source_version_id}", "file_role": "eq.original"},
                        limit=2,
                    )
                    if len(files) != 1:
                        raise SourceWorkerError("source version must have exactly one original file")
                    source_file = files[0]
                    byte_size = _safe_int(version.get("byte_size"), "source byte size", minimum=1)
                    source_sha256 = str(version.get("sha256", ""))
                    if not SHA256_RE.fullmatch(source_sha256):
                        raise SourceWorkerError("registered source SHA-256 is invalid")
                    if (
                        source_file.get("bucket_id") != SOURCE_BUCKET
                        or source_file.get("byte_size") != version.get("byte_size")
                        or source_file.get("sha256") != source_sha256
                    ):
                        raise SourceWorkerError("source file metadata is inconsistent")
                    object_path = str(source_file.get("object_path", ""))
                    if job_input.get("objectPath") != object_path:
                        raise SourceWorkerError("source job object path is inconsistent")
                    original_filename = str(version.get("original_filename") or source_file.get("original_filename") or "")
                    mime_type = str(version.get("mime_type") or source_file.get("mime_type") or "")
                    source_path = Path(directory_name) / ("source" + Path(original_filename).suffix.casefold())
                    self._progress(job_id, 4, "downloading", {"bytesTotal": byte_size})
                    downloaded_sha256 = self.client.download_to_path(
                        SOURCE_BUCKET,
                        object_path,
                        source_path,
                        expected_bytes=byte_size,
                        max_bytes=self.max_source_bytes,
                        on_progress=download_progress,
                    )
                    self._progress(job_id, 34, "validating", {"bytesVerified": byte_size})
                    if downloaded_sha256 != source_sha256 or sha256_file(source_path) != source_sha256:
                        raise SourceWorkerError("다운로드한 원본의 SHA-256이 등록값과 다릅니다")
                    detect_source_format(source_path, original_filename, mime_type)
                    capture_metadata: dict[str, Any] = {"captureKind": "storage-file"}
                    dedupe_progress = 39
                    extract_progress = 44
                else:
                    requested_url = str(job_input.get("url") or "")
                    if not requested_url or requested_url != str(version.get("fetch_url") or ""):
                        raise SourceWorkerError("source URL job and version metadata are inconsistent")
                    source_path = Path(directory_name) / "url-snapshot"
                    self._progress(job_id, 4, "downloading", {"urlHost": urllib.parse.urlsplit(requested_url).hostname})
                    fetched = fetch_public_url_to_path(
                        requested_url,
                        source_path,
                        max_bytes=self.max_source_bytes,
                        timeout_seconds=self.client.timeout_seconds,
                        on_progress=download_progress,
                    )
                    byte_size = fetched.byte_size
                    source_sha256 = fetched.sha256
                    original_filename = fetched.original_filename
                    mime_type = fetched.content_type
                    self._progress(job_id, 34, "validating", {"bytesVerified": byte_size})
                    if sha256_file(source_path) != source_sha256:
                        raise SourceWorkerError("URL snapshot의 SHA-256 재검증이 실패했습니다")
                    detect_source_format(source_path, original_filename, mime_type)
                    creator_id = _canonical_uuid(version.get("created_by"), "source creator id")
                    safe_source_id = re.sub(r"[^0-9A-Za-z._-]", "-", str(version.get("source_id", "")))[:120] or "url"
                    snapshot_object_path = (
                        f"{creator_id}/sources/{safe_source_id}/{source_version_id}/url-snapshot/"
                        f"{original_filename}"
                    )
                    snapshot_details = {
                        "snapshotObjectPath": snapshot_object_path,
                        "sourceSha256": source_sha256,
                        "sourceByteSize": byte_size,
                        "originalFilename": original_filename,
                        "mimeType": mime_type,
                        "requestedUrl": fetched.requested_url,
                        "finalUrl": fetched.final_url,
                    }
                    self._progress(job_id, 38, "archiving", {"bytesTotal": byte_size})
                    last_archive_percent = -1

                    def archive_progress(uploaded: int, total: int) -> None:
                        nonlocal last_archive_percent
                        percent = 38 + int(4 * uploaded / total)
                        if percent != last_archive_percent:
                            self._progress(
                                job_id,
                                percent,
                                "archiving",
                                {"bytesArchived": uploaded, "bytesTotal": total},
                            )
                            last_archive_percent = percent

                    self.client.upload_from_path(
                        SOURCE_BUCKET,
                        snapshot_object_path,
                        source_path,
                        content_type=mime_type,
                        max_bytes=self.max_source_bytes,
                        on_progress=archive_progress,
                    )
                    capture_metadata = {
                        "captureKind": "url-snapshot",
                        "requestedUrl": fetched.requested_url,
                        "finalUrl": fetched.final_url,
                        "redirectChain": list(fetched.redirect_chain),
                        "responseHeaders": fetched.response_headers,
                        "fetchedAt": datetime.now(timezone.utc).isoformat(),
                        **snapshot_details,
                    }
                    dedupe_progress = 43
                    extract_progress = 48

                self._progress(job_id, dedupe_progress, "deduplicating", {"sourceSha256": source_sha256})
                result = self._duplicate_result(source_version_id, source_sha256)
                reused_duplicate = result is not None
                if result is None:
                    self._progress(job_id, extract_progress, "extracting", {"filename": original_filename[:300]})
                    result = extract_source(
                        source_path,
                        original_filename,
                        mime_type,
                        lambda percent, stage, details: self._progress(job_id, percent, stage, details),
                    )

            self._progress(job_id, 75, "normalizing", {"fragmentCount": len(result.fragments)})
            result.metadata.update(
                {
                    "parserName": PARSER_NAME,
                    "parserVersion": PARSER_VERSION,
                    "sourceSha256": source_sha256,
                    "sourceByteSize": byte_size,
                    "originalFilename": original_filename,
                    "mimeType": mime_type,
                    "reviewReasons": result.review_reasons,
                    **capture_metadata,
                }
            )
            extracted_text = result.extracted_text
            if not extracted_text and not result.requires_review:
                raise SourceWorkerError("추출된 텍스트가 없습니다")

            self._progress(job_id, 82, "matching", {"extractedCharacters": len(extracted_text)})
            candidates = match_elements(extracted_text, self._catalog()) if extracted_text else []
            route = route_after_matching(result, candidates)
            result.metadata["route"] = route
            result.metadata["reviewReasons"] = result.review_reasons

            self._progress(
                job_id,
                94,
                "saving",
                {"fragmentCount": len(result.fragments), "candidateCount": len(candidates)},
            )
            completed = _rpc_object(
                self.client.rpc(
                    COMPLETE_RPC,
                    {
                        "p_job_id": job_id,
                        "p_worker_id": self.worker_id,
                        "p_extracted_text": extracted_text,
                        "p_extraction_metadata": result.metadata,
                        "p_fragments": [fragment.as_rpc() for fragment in result.fragments],
                        "p_candidates": [candidate.as_rpc() for candidate in candidates],
                        "p_requires_review": result.requires_review,
                        "p_output": {
                            "parserName": PARSER_NAME,
                            "parserVersion": PARSER_VERSION,
                            "jobKind": job_kind,
                            "route": route,
                            "duplicateReused": reused_duplicate,
                            "extractedCharacters": len(extracted_text),
                        },
                    },
                ),
                "complete source ingestion",
            )
            parse_status = str((completed or {}).get("parseStatus") or ("needs_review" if result.requires_review else "ready"))
            return WorkerOutcome(job_id, source_version_id, parse_status, len(result.fragments), len(candidates))
        except Exception as error:
            # Owner pause is a normal cooperative stop, not a failed job. The
            # pause may arrive during parsing, so check state before reporting
            # the exception as terminal failure.
            try:
                if self._is_paused(job_id):
                    return WorkerOutcome(job_id, source_version_id, "paused", 0, 0)
            except Exception:
                pass
            safe_message = str(error).replace(self.client.secret_key, "[redacted]")[:1800]
            terminal = _rpc_object(
                self.client.rpc(
                    FAIL_RPC,
                    {
                        "p_job_id": job_id,
                        "p_worker_id": self.worker_id,
                        "p_error_message": safe_message or error.__class__.__name__,
                        "p_output": {
                            "parserName": PARSER_NAME,
                            "parserVersion": PARSER_VERSION,
                            "jobKind": job_kind,
                            "failureType": error.__class__.__name__,
                            **snapshot_details,
                        },
                    },
                ),
                "fail source ingestion",
            )
            if terminal is not None and terminal.get("jobStatus") == "succeeded":
                return WorkerOutcome(job_id, source_version_id, "ready", 0, 0)
            raise SourceWorkerError("claimed source job failed safely") from error


def default_worker_id() -> str:
    hostname = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:48] or "host"
    return f"findone-source:{hostname}:{os.getpid()}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", default=default_worker_id())
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--max-jobs", type=int, default=4)
    parser.add_argument(
        "--auto-queue-catalog",
        type=int,
        default=int(os.environ.get("ADMIN_SOURCE_WORKER_AUTO_QUEUE_CATALOG", "4")),
    )
    parser.add_argument(
        "--max-source-mib",
        type=int,
        default=int(os.environ.get("ADMIN_SOURCE_WORKER_MAX_MIB", str(MAX_SOURCE_BYTES // (1024 * 1024)))),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_jobs < 1 or args.max_jobs > 20:
        raise SourceWorkerError("--max-jobs must be between 1 and 20")
    if args.max_source_mib < 1 or args.max_source_mib > 10 * 1024:
        raise SourceWorkerError("--max-source-mib must be between 1 and 10240")
    if args.auto_queue_catalog < 0 or args.auto_queue_catalog > 100:
        raise SourceWorkerError("--auto-queue-catalog must be between 0 and 100")
    client = SupabaseSourceClient(
        base_url=resolve_supabase_url(),
        secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
        timeout_seconds=args.timeout,
    )
    worker = SourceIngestionWorker(
        client,
        args.worker_id,
        max_source_bytes=args.max_source_mib * 1024 * 1024,
        auto_queue_catalog=args.auto_queue_catalog,
    )
    outcomes: list[dict[str, Any]] = []
    for _ in range(args.max_jobs):
        outcome = worker.process_one()
        if outcome is None:
            break
        outcomes.append(outcome.as_dict())
    print(json.dumps({"status": "processed" if outcomes else "idle", "jobs": outcomes}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SourceWorkerError, ValueError) as error:
        print(f"Source ingestion worker stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
