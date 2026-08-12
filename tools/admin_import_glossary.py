#!/usr/bin/env python3
"""Import the validated authored glossary into the private Supabase Admin tables."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.admin_import_supabase import normalize_supabase_url, resolve_supabase_url
from tools.glossary_content import (
    DEFAULT_CATALOG,
    DEFAULT_INVENTORY,
    GlossaryContentError,
    canonical_json_bytes,
    load_catalog,
    parse_inventory,
    sha256_bytes,
)


class GlossaryImportError(RuntimeError):
    """Raised when the verified glossary cannot be imported safely."""


def build_snapshot(inventory_path: Path, catalog_path: Path) -> dict[str, Any]:
    inventory = parse_inventory(inventory_path)
    catalog = load_catalog(catalog_path, inventory=inventory)
    order_by_id = {term.term_id: term.display_order for term in inventory.terms}
    return {
        "formatVersion": 1,
        "inventorySha256": inventory.sha256,
        "catalogSha256": sha256_bytes(canonical_json_bytes(catalog)),
        "generationModel": catalog["generationModel"],
        "categories": [
            {
                "categoryId": category.category_id,
                "name": category.name,
                "displayOrder": category.display_order,
            }
            for category in inventory.categories
        ],
        "sources": [
            {
                "sourceCode": source.source_code,
                "title": source.title,
                "url": source.url,
            }
            for source in inventory.sources
        ],
        "terms": [
            {**term, "displayOrder": order_by_id[term["termId"]]}
            for term in catalog["terms"]
        ],
    }


def call_import(
    snapshot: dict[str, Any],
    *,
    base_url: str,
    secret_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    secret = secret_key.strip()
    if not secret:
        raise GlossaryImportError(
            "SUPABASE_SECRET_KEY is missing. Supply it through the current process environment."
        )
    body = json.dumps(
        {"p_snapshot": snapshot},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        normalize_supabase_url(base_url) + "/rest/v1/rpc/import_glossary_snapshot",
        data=body,
        method="POST",
        headers={
            "apikey": secret,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as response:
            response_body = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(8192).decode("utf-8", errors="replace")
        raise GlossaryImportError(
            f"Supabase glossary import failed with HTTP {error.code}: {detail[:2000]}"
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise GlossaryImportError(f"Could not reach Supabase glossary import RPC: {error}") from error
    if len(response_body) > 1024 * 1024:
        raise GlossaryImportError("Supabase glossary import response exceeded the safety limit")
    try:
        result = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlossaryImportError("Supabase glossary import returned invalid JSON") from error
    if not isinstance(result, dict):
        raise GlossaryImportError("Supabase glossary import returned an unexpected response")
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    snapshot = build_snapshot(args.inventory, args.catalog)
    summary = {
        "categories": len(snapshot["categories"]),
        "sources": len(snapshot["sources"]),
        "terms": len(snapshot["terms"]),
        "inventorySha256": snapshot["inventorySha256"],
        "catalogSha256": snapshot["catalogSha256"],
    }
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    result = call_import(
        snapshot,
        base_url=resolve_supabase_url(),
        secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
        timeout_seconds=args.timeout,
    )
    print(json.dumps({"snapshot": summary, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GlossaryContentError, GlossaryImportError, OSError, ValueError) as error:
        print(f"Glossary import stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
