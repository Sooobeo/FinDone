#!/usr/bin/env python3
"""Parse every Supabase migration and pgTAP test before deployment.

This is a fast, Docker-free syntax gate.  It complements (and does not replace)
``supabase db reset`` and ``supabase test db`` against a real PostgreSQL stack.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]


def validate_sql_tree(root: Path = ROOT) -> list[tuple[Path, int]]:
    paths = sorted((root / "supabase" / "migrations").glob("*.sql"))
    paths += sorted((root / "supabase" / "tests").rglob("*.sql"))
    if not paths:
        raise ValueError("no Supabase SQL files found")

    results: list[tuple[Path, int]] = []
    for path in paths:
        statements = parse_sql(path.read_text(encoding="utf-8"))
        if not statements:
            raise ValueError(f"{path.relative_to(root)} contains no SQL statements")
        results.append((path, len(statements)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()

    for path, statement_count in validate_sql_tree(args.root.resolve()):
        print(f"{path.relative_to(args.root.resolve())}: {statement_count} statements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
