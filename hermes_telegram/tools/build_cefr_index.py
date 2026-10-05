"""Cache factual headword levels from Oxford's official downloadable PDF."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

SOURCE_URL = "https://www.oxfordlearnersdictionaries.com/external/pdf/wordlists/oxford-3000-5000/The_Oxford_5000.pdf"


def extract(pdf: bytes) -> dict[str, str]:
    from pypdf import PdfReader
    entries = {}
    reader = PdfReader(BytesIO(pdf))
    for page in reader.pages:
        for line in (page.extract_text() or "").splitlines():
            line = line.strip()
            if not re.search(r"\b(?:B2|C1)\b", line):
                continue
            match = re.match(r"([A-Za-z][A-Za-z '-]*?)(?:[12¹²])?\s+(?:\([^)]*\)\s*)?(?:n\.|v\.|adj\.|adv\.|prep\.|conj\.|pron\.|det\.|number\b|exclam\.).*?\b(B2|C1)\b", line)
            if not match:
                continue
            lemma = match[1].strip().casefold()
            if not re.fullmatch(r"[a-z][a-z -]{0,79}", lemma):
                continue
            levels = re.findall(r"\b(?:B2|C1)\b", line)
            level = "B2" if "B2" in levels else "C1"
            if entries.get(lemma) != "B2":
                entries[lemma] = level
    if len(entries) < 1800 or entries.get("yield") != "C1" or entries.get("investor") != "B2":
        raise ValueError("Official PDF extraction did not match the expected lexical content")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf-copy", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute() or (args.pdf_copy and not args.pdf_copy.is_absolute()):
        parser.error("Cache paths must be absolute")
    request = Request(SOURCE_URL, headers={"User-Agent": "FinDone-personal-vocabulary/1.0"})
    with urlopen(request, timeout=30) as response:
        if response.geturl() != SOURCE_URL:
            raise ValueError("Unexpected official word-list redirect")
        pdf = response.read(5_000_001)
    if len(pdf) > 5_000_000 or not pdf.startswith(b"%PDF"):
        raise ValueError("Invalid official PDF download")
    entries = extract(pdf)
    result = {"schema_version": 1, "source_name": "Oxford 5000 (additional B2-C1 headwords)",
              "source_url": SOURCE_URL, "source_sha256": hashlib.sha256(pdf).hexdigest(),
              "cached_at": datetime.now(timezone.utc).isoformat(), "entries": dict(sorted(entries.items()))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.pdf_copy:
        args.pdf_copy.parent.mkdir(parents=True, exist_ok=True)
        args.pdf_copy.write_bytes(pdf)
    print("Official advanced lexical entries cached:", len(entries))
    print("Levels:", {level: sum(value == level for value in entries.values()) for level in ("B2", "C1")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
