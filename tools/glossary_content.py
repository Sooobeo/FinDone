#!/usr/bin/env python3
"""Shared parser and validation helpers for the standalone FinDone glossary pack."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "용어집" / "2_finance_term_master_inventory.md"
DEFAULT_CATALOG = ROOT / "content" / "glossary" / "glossary-catalog.json"
DEFAULT_AS_OF_DATE = date(2026, 8, 12)
CATALOG_FORMAT_VERSION = 1

TERM_ID_RE = re.compile(r"^FIN-(\d{2})-(\d{3})$")
CATEGORY_RE = re.compile(r"^##\s+((?:0[1-9]|1\d|2[01]))\.\s+(.+?)\s*$")
TERM_ROW_RE = re.compile(
    r"^\|\s*(FIN-\d{2}-\d{3})\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$"
)
SOURCE_RE = re.compile(r"^-\s+\*\*\[(S\d{2})\]\*\*\s+(.+?):\s+(https?://\S+)\s*$")

CONCEPT_TYPES = {
    "INSTITUTION",
    "BUSINESS_FUNCTION",
    "ORG_UNIT",
    "ROLE",
    "ASSET_CLASS",
    "INSTRUMENT",
    "STRATEGY",
    "DEAL",
    "PROCESS",
    "ACTIVITY",
    "METHODOLOGY",
    "MODEL",
    "METRIC",
    "ACCOUNTING_CONCEPT",
    "RISK",
    "EVENT",
    "ARTIFACT",
    "DISCLOSURE",
    "REGULATION",
    "MARKET_INFRA",
    "DATA_SOURCE",
    "IDENTIFIER",
    "TOOL_SKILL",
    "SECTOR",
}
REVIEW_STATUSES = {"agent_reviewed", "approved"}
JURISDICTIONS = {"GLOBAL", "KR", "US", "EU", "UK", "JP", "CN", "MULTI"}


class GlossaryContentError(ValueError):
    """Raised when glossary authoring data is incomplete or inconsistent."""


@dataclass(frozen=True)
class InventoryCategory:
    category_id: str
    name: str
    display_order: int


@dataclass(frozen=True)
class InventoryTerm:
    term_id: str
    category_id: str
    category_name: str
    canonical_name_en: str
    canonical_name_ko: str
    aliases: tuple[str, ...]
    display_order: int


@dataclass(frozen=True)
class InventorySource:
    source_code: str
    title: str
    url: str


@dataclass(frozen=True)
class Inventory:
    categories: tuple[InventoryCategory, ...]
    terms: tuple[InventoryTerm, ...]
    sources: tuple[InventorySource, ...]
    sha256: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def split_aliases(value: str) -> tuple[str, ...]:
    aliases: list[str] = []
    for part in re.split(r"\s*/\s*|\s*;\s*", value.strip()):
        cleaned = part.strip()
        if cleaned and cleaned not in {"—", "-"} and cleaned not in aliases:
            aliases.append(cleaned)
    return tuple(aliases)


def parse_inventory(
    path: Path = DEFAULT_INVENTORY,
    *,
    expected_term_count: int | None = 1_649,
) -> Inventory:
    try:
        body = path.read_bytes()
        text = body.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise GlossaryContentError(f"Could not read glossary inventory: {path}") from error

    categories: list[InventoryCategory] = []
    terms: list[InventoryTerm] = []
    sources: dict[str, InventorySource] = {}
    current_category: InventoryCategory | None = None
    category_term_order: dict[str, int] = {}

    for line in text.splitlines():
        category_match = CATEGORY_RE.match(line)
        if category_match:
            category_id, name = category_match.groups()
            current_category = InventoryCategory(category_id, name.strip(), len(categories))
            categories.append(current_category)
            category_term_order[category_id] = 0
            continue

        source_match = SOURCE_RE.match(line)
        if source_match:
            source_code, title, url = source_match.groups()
            sources.setdefault(source_code, InventorySource(source_code, title.strip(), url.strip()))
            continue

        term_match = TERM_ROW_RE.match(line)
        if not term_match:
            continue
        term_id, canonical_en, canonical_ko, aliases = term_match.groups()
        id_match = TERM_ID_RE.fullmatch(term_id)
        if id_match is None:
            raise GlossaryContentError(f"Malformed inventory term id: {term_id}")
        category_id = id_match.group(1)
        if current_category is None or current_category.category_id != category_id:
            raise GlossaryContentError(f"{term_id} is outside its numbered category")
        order = category_term_order[category_id]
        category_term_order[category_id] = order + 1
        terms.append(
            InventoryTerm(
                term_id=term_id,
                category_id=category_id,
                category_name=current_category.name,
                canonical_name_en=canonical_en.strip(),
                canonical_name_ko=canonical_ko.strip(),
                aliases=split_aliases(aliases),
                display_order=order,
            )
        )

    ids = [term.term_id for term in terms]
    if len(ids) != len(set(ids)):
        raise GlossaryContentError("Glossary inventory contains duplicate term IDs")
    if expected_term_count is not None and len(terms) != expected_term_count:
        raise GlossaryContentError(
            f"Expected {expected_term_count:,} glossary terms, found {len(terms):,}"
        )
    if not terms:
        raise GlossaryContentError("Glossary inventory has no active terms")
    if [category.category_id for category in categories] != [f"{value:02d}" for value in range(1, 22)]:
        raise GlossaryContentError("Glossary inventory must contain categories 01 through 21 in order")
    if not sources:
        raise GlossaryContentError("Glossary inventory has no source catalog")
    return Inventory(tuple(categories), tuple(terms), tuple(sources.values()), sha256_bytes(body))


def _required_text(row: Mapping[str, Any], key: str, term_id: str, *, minimum: int = 1) -> str:
    value = row.get(key)
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise GlossaryContentError(f"{term_id}.{key} must contain at least {minimum} characters")
    cleaned = value.strip()
    if "..." in cleaned or cleaned in {"TBD", "TODO", "미작성"}:
        raise GlossaryContentError(f"{term_id}.{key} contains placeholder text")
    return cleaned


def _text_list(
    row: Mapping[str, Any],
    key: str,
    term_id: str,
    *,
    minimum_items: int = 0,
    allowed: set[str] | None = None,
) -> list[str]:
    value = row.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise GlossaryContentError(f"{term_id}.{key} must be an array of non-blank strings")
    cleaned = list(dict.fromkeys(item.strip() for item in value))
    if len(cleaned) < minimum_items:
        raise GlossaryContentError(f"{term_id}.{key} needs at least {minimum_items} item(s)")
    if allowed is not None and any(item not in allowed for item in cleaned):
        raise GlossaryContentError(f"{term_id}.{key} contains an unsupported value")
    return cleaned


def load_catalog(
    path: Path = DEFAULT_CATALOG,
    *,
    inventory: Inventory | None = None,
) -> dict[str, Any]:
    inventory = inventory or parse_inventory()
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlossaryContentError(f"Could not read glossary catalog: {path}") from error
    if not isinstance(catalog, dict):
        raise GlossaryContentError("Glossary catalog root must be an object")
    if catalog.get("formatVersion") != CATALOG_FORMAT_VERSION:
        raise GlossaryContentError("Unsupported glossary catalog format")
    if catalog.get("inventorySha256") != inventory.sha256:
        raise GlossaryContentError("Glossary catalog was generated from a different inventory")
    terms = catalog.get("terms")
    if not isinstance(terms, list) or not all(isinstance(item, dict) for item in terms):
        raise GlossaryContentError("Glossary catalog terms must be an object array")

    inventory_by_id = {term.term_id: term for term in inventory.terms}
    catalog_ids = [str(row.get("termId", "")) for row in terms]
    if len(catalog_ids) != len(set(catalog_ids)):
        raise GlossaryContentError("Glossary catalog contains duplicate term IDs")
    missing = set(inventory_by_id) - set(catalog_ids)
    extra = set(catalog_ids) - set(inventory_by_id)
    if missing or extra:
        raise GlossaryContentError(
            f"Glossary catalog coverage mismatch: {len(missing)} missing, {len(extra)} extra"
        )

    source_codes = {source.source_code for source in inventory.sources}
    normalized: list[dict[str, Any]] = []
    for row in terms:
        term_id = _required_text(row, "termId", "catalog")
        identity = inventory_by_id[term_id]
        if row.get("categoryId") != identity.category_id:
            raise GlossaryContentError(f"{term_id}.categoryId differs from inventory")
        concept_type = _required_text(row, "conceptType", term_id)
        if concept_type not in CONCEPT_TYPES:
            raise GlossaryContentError(f"{term_id}.conceptType is unsupported")
        review_status = _required_text(row, "reviewStatus", term_id)
        if review_status not in REVIEW_STATUSES:
            raise GlossaryContentError(f"{term_id}.reviewStatus is not releasable")
        as_of = _required_text(row, "asOfDate", term_id)
        try:
            date.fromisoformat(as_of)
        except ValueError as error:
            raise GlossaryContentError(f"{term_id}.asOfDate is invalid") from error
        normalized.append(
            {
                "termId": term_id,
                "categoryId": identity.category_id,
                "categoryName": identity.category_name,
                "canonicalNameEn": identity.canonical_name_en,
                "canonicalNameKo": identity.canonical_name_ko,
                "aliases": list(identity.aliases),
                "conceptType": concept_type,
                "oneLineDefinitionKo": _required_text(row, "oneLineDefinitionKo", term_id, minimum=18),
                "coreDefinitionKo": _required_text(row, "coreDefinitionKo", term_id, minimum=35),
                "practicalContextKo": _required_text(row, "practicalContextKo", term_id, minimum=18),
                "whyItMattersKo": _required_text(row, "whyItMattersKo", term_id, minimum=12),
                "exampleKo": _required_text(row, "exampleKo", term_id, minimum=15),
                "limitationsKo": _text_list(row, "limitationsKo", term_id, minimum_items=1),
                "sourceCodes": _text_list(
                    row, "sourceCodes", term_id, minimum_items=1, allowed=source_codes
                ),
                "jurisdictions": _text_list(
                    row, "jurisdictions", term_id, minimum_items=1, allowed=JURISDICTIONS
                ),
                "asOfDate": as_of,
                "reviewStatus": review_status,
                "reviewFlags": _text_list(row, "reviewFlags", term_id),
                "relatedTermIds": _text_list(row, "relatedTermIds", term_id),
                "formulaLatex": str(row.get("formulaLatex") or "").strip(),
                "formulaNotesKo": str(row.get("formulaNotesKo") or "").strip(),
            }
        )

    normalized.sort(key=lambda item: item["termId"])
    return {
        "formatVersion": CATALOG_FORMAT_VERSION,
        "inventorySha256": inventory.sha256,
        "asOfDate": str(catalog.get("asOfDate") or DEFAULT_AS_OF_DATE.isoformat()),
        "generationModel": str(catalog.get("generationModel") or "codex-authoring-agent"),
        "terms": normalized,
    }


def catalog_from_batches(
    inventory: Inventory,
    batches: Iterable[Mapping[str, Any]],
    *,
    generation_model: str,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for batch in batches:
        raw_items = batch.get("items")
        if not isinstance(raw_items, list) or not all(isinstance(item, dict) for item in raw_items):
            raise GlossaryContentError("Agent batch has no valid items array")
        items.extend(dict(item) for item in raw_items)
    catalog = {
        "formatVersion": CATALOG_FORMAT_VERSION,
        "inventorySha256": inventory.sha256,
        "asOfDate": DEFAULT_AS_OF_DATE.isoformat(),
        "generationModel": generation_model,
        "terms": items,
    }
    return catalog


def inventory_term_payload(term: InventoryTerm) -> dict[str, Any]:
    return {
        "termId": term.term_id,
        "categoryId": term.category_id,
        "categoryName": term.category_name,
        "canonicalNameEn": term.canonical_name_en,
        "canonicalNameKo": term.canonical_name_ko,
        "aliases": list(term.aliases),
    }


def chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    if size < 1:
        raise ValueError("chunk size must be positive")
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]
