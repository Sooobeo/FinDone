from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any

from tools.admin_glossary_worker import (
    CLAIM_RPC,
    COMPLETE_RPC,
    GlossaryReleaseWorker,
    materialize_authoring_files,
)
from tools.build_glossary_db import build_database


def sample_snapshot() -> dict[str, object]:
    return {
        "inventorySha256": "0" * 64,
        "categories": [
            {"categoryId": f"{index:02d}", "name": f"카테고리 {index}", "displayOrder": index - 1}
            for index in range(1, 22)
        ],
        "sources": [{"sourceCode": "S01", "title": "Official glossary", "url": "https://example.com/glossary"}],
        "terms": [{
            "termId": "FIN-01-001",
            "categoryId": "01",
            "displayOrder": 0,
            "canonicalNameEn": "Securities Firm",
            "canonicalNameKo": "증권사",
            "aliases": ["securities company"],
            "conceptType": "INSTITUTION",
            "oneLineDefinitionKo": "증권사는 증권 거래 중개와 발행 지원을 수행하는 금융기관이다.",
            "coreDefinitionKo": "증권사는 고객 주문을 중개하고 증권 발행과 인수 업무를 지원한다. 인가 범위와 관할에 따라 수행 업무가 달라진다.",
            "practicalContextKo": "기업금융, 리서치, 트레이딩과 브로커리지에서 거래 상대방이나 주관사로 참여한다.",
            "whyItMattersKo": "거래 실행과 자금조달의 핵심 접점이기 때문이다.",
            "exampleKo": "증권사가 기업의 회사채 발행을 주관하고 투자자 주문을 배분한다.",
            "limitationsKo": ["국가별 인가 체계에 따라 업무 범위가 다르다."],
            "sourceCodes": ["S01"],
            "jurisdictions": ["MULTI"],
            "asOfDate": "2026-08-12",
            "reviewStatus": "agent_reviewed",
            "reviewFlags": ["human_jurisdiction_review"],
            "relatedTermIds": [],
            "formulaLatex": "",
            "formulaNotesKo": "",
        }],
    }


class AdminGlossaryWorkerTest(unittest.TestCase):
    def test_snapshot_compiles_to_searchable_offline_pack(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            inventory, catalog, term_count = materialize_authoring_files(sample_snapshot(), directory)
            database_path = directory / "glossary.sqlite3"
            manifest = build_database(
                database_path,
                inventory_path=inventory,
                catalog_path=catalog,
                glossary_version=9,
                expected_term_count=term_count,
            )
            self.assertEqual(9, manifest["glossaryDbVersion"])
            self.assertFalse(manifest["llmRuntimeUsed"])
            self.assertEqual(1, manifest["rowCounts"]["terms"])
            self.assertEqual(21, manifest["rowCounts"]["categories"])
            database = sqlite3.connect(database_path)
            try:
                self.assertEqual(
                    ("FIN-01-001",),
                    database.execute(
                        "SELECT term_id FROM glossary_fts WHERE glossary_fts MATCH ?",
                        ('"Securities"*',),
                    ).fetchone(),
                )
                self.assertIsNone(
                    database.execute("SELECT 1 FROM terms WHERE term_id = 'FIN-01-002'").fetchone()
                )
            finally:
                database.close()

    def test_worker_uploads_supported_static_artifacts_and_exact_sizes(self) -> None:
        release_id = str(uuid.uuid4())

        class FakeClient:
            secret_key = "fake-secret"

            def __init__(self) -> None:
                self.claimed = False
                self.uploads: list[tuple[str, str, bytes, str]] = []
                self.complete_payload: dict[str, Any] | None = None

            def rpc(self, name: str, payload: dict[str, Any]) -> Any:
                if name == CLAIM_RPC:
                    if self.claimed:
                        return None
                    self.claimed = True
                    return {
                        "jobId": str(uuid.uuid4()),
                        "releaseId": release_id,
                        "glossaryDbVersion": 3,
                        "snapshot": sample_snapshot(),
                    }
                if name == COMPLETE_RPC:
                    self.complete_payload = payload
                    return {
                        "releaseId": release_id,
                        "glossaryDbVersion": 3,
                        "status": "published",
                    }
                raise AssertionError(f"unexpected RPC: {name}")

            def upload(self, bucket: str, path: str, body: bytes, mime: str) -> None:
                self.uploads.append((bucket, path, body, mime))

        client = FakeClient()
        outcome = GlossaryReleaseWorker(client, "test-worker").process_one()  # type: ignore[arg-type]
        self.assertEqual("published", outcome["status"] if outcome else None)
        self.assertEqual(
            ["application/x-sqlite3", "application/json"],
            [upload[3] for upload in client.uploads],
        )
        self.assertIsNotNone(client.complete_payload)
        assert client.complete_payload is not None
        manifest_upload = client.uploads[1][2]
        database_upload = client.uploads[0][2]
        self.assertFalse(json.loads(manifest_upload)["llmRuntimeUsed"])
        self.assertEqual(len(manifest_upload), client.complete_payload["p_manifest_byte_size"])
        self.assertEqual(len(database_upload), client.complete_payload["p_database_byte_size"])
        self.assertEqual(1, client.complete_payload["p_term_count"])
        self.assertFalse(client.complete_payload["p_output"]["llmRuntimeUsed"])


if __name__ == "__main__":
    unittest.main()
