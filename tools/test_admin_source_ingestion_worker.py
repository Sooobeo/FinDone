from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock

from tools import admin_source_ingestion_worker as worker


def _write_zip(path: Path, members: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body.encode("utf-8") if isinstance(body, str) else body)


class SourceParserTests(unittest.TestCase):
    def test_normalize_text_is_stable_and_removes_control_noise(self) -> None:
        self.assertEqual("NPV = 100\n\n두 번째 줄", worker.normalize_text("  ＮＰＶ  = 100\x00\n\n\n 두 번째\t줄 "))

    def test_plain_markdown_extracts_text_and_formula_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.md"
            path.write_text("# 순현재가치\n\nNPV = 현금흐름 - 투자액\n", encoding="utf-8")
            result = worker.extract_source(path, path.name, "text/markdown")
        self.assertIn("순현재가치", result.extracted_text)
        self.assertIn("formula", {fragment.kind for fragment in result.fragments})
        self.assertFalse(result.requires_review)

    def test_html_head_without_meta_name_or_property_still_extracts(self) -> None:
        # Real pages open <head> with tags carrying neither attribute.
        page = (
            "<html><head>"
            '<meta charset="utf-8">'
            '<meta http-equiv="X-UA-Compatible" content="IE=edge">'
            '<meta name="author" content="홍길동">'
            '<meta property="article:published_time" content="2026-08-17">'
            "<title>순현재가치</title></head>"
            "<body>NPV는 미래 현금흐름을 할인한다.</body></html>"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.html"
            path.write_text(page, encoding="utf-8")
            result = worker.extract_plain_text(path, "html")
        self.assertIn("미래 현금흐름", result.extracted_text)
        self.assertEqual("홍길동", result.metadata["author"])
        self.assertEqual("2026-08-17", result.metadata["publishedAt"])

    def test_csv_extracts_bounded_table_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_text("항목,금액\n매출,100\n비용,60\n", encoding="utf-8")
            result = worker.extract_csv(path)
        self.assertEqual(3, result.metadata["rowCount"])
        self.assertEqual(2, result.metadata["maxColumnCount"])
        self.assertEqual("table", result.fragments[0].kind)
        self.assertIn("매출 100", result.extracted_text)

    def test_json_extracts_structured_records_without_losing_element_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            path.write_text(
                json.dumps(
                    {"records": [{"element_id": "ACC-01", "definition": "구조화된 정의"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = worker.extract_source(path, path.name, "application/json")
        self.assertEqual("json", result.metadata["parser"])
        self.assertEqual(1, result.metadata["recordCount"])
        self.assertIn("ACC-01", result.fragments[0].text)
        self.assertEqual("table", result.fragments[0].kind)

    def test_sqlite_extracts_read_only_tables_with_headers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.sqlite3"
            database = sqlite3.connect(path)
            database.execute("CREATE TABLE content(element_id TEXT, definition TEXT)")
            database.execute(
                "INSERT INTO content VALUES (?, ?)",
                ("ACC-01", "회계등식의 구조화된 정의"),
            )
            database.commit()
            database.close()

            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = worker.extract_source(path, path.name, "application/vnd.sqlite3")
            after = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual("sqlite3-readonly", result.metadata["parser"])
        self.assertEqual(1, result.metadata["tableCount"])
        self.assertEqual(1, result.metadata["rowCount"])
        self.assertIn("element_id\tdefinition", result.fragments[0].text)
        self.assertIn("ACC-01", result.fragments[0].text)

    def test_docx_extracts_paragraphs_and_tables_without_unzipping_to_disk(self) -> None:
        document_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:r><w:t>채권 가격</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>만기</w:t></w:r></w:p></w:tc>
          <w:tc><w:p><w:r><w:t>수익률</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        </w:body></w:document>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.docx"
            _write_zip(path, {"word/document.xml": document_xml})
            result = worker.extract_docx(path)
        self.assertEqual(1, result.metadata["paragraphCount"])
        self.assertEqual(1, result.metadata["tableCount"])
        self.assertIn("만기 수익률", result.extracted_text)

    def test_xlsx_extracts_shared_strings_values_and_formulas(self) -> None:
        workbook = """<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>"""
        shared = """<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <si><t>매출</t></si><si><t>이익</t></si></sst>"""
        sheet = """<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
          <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
          <row r="2"><c r="A2"><v>100</v></c><c r="B2"><f>A2*0.4</f><v>40</v></c></row>
        </sheetData></worksheet>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.xlsx"
            _write_zip(
                path,
                {"xl/workbook.xml": workbook, "xl/sharedStrings.xml": shared, "xl/worksheets/sheet1.xml": sheet},
            )
            result = worker.extract_xlsx(path)
        self.assertEqual(1, result.metadata["sheetCount"])
        self.assertEqual(2, result.metadata["rowCount"])
        self.assertIn("=A2*0.4 → 40", result.extracted_text)

    def test_pptx_extracts_text_by_slide(self) -> None:
        slide = """<?xml version="1.0"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><a:p><a:r><a:t>듀레이션</a:t></a:r></a:p></p:cSld></p:sld>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.pptx"
            _write_zip(path, {"ppt/slides/slide1.xml": slide})
            result = worker.extract_pptx(path)
        self.assertEqual(1, result.metadata["slideCount"])
        self.assertIn("듀레이션", result.extracted_text)
        self.assertEqual(1, result.fragments[0].locator["slide"])

    def test_rejects_zip_bombs_before_xml_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.docx"
            _write_zip(path, {"word/document.xml": b"0" * (2 * 1024 * 1024)})
            with zipfile.ZipFile(path) as archive:
                with self.assertRaisesRegex(worker.SourceWorkerError, "압축률"):
                    worker.validate_zip_archive(archive)

    def test_rejects_office_xml_entities_before_parsing(self) -> None:
        malicious = """<?xml version="1.0"?><!DOCTYPE x [<!ENTITY boom "expanded">]>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>&boom;</w:body></w:document>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.docx"
            _write_zip(path, {"word/document.xml": malicious})
            with self.assertRaisesRegex(worker.SourceWorkerError, "XML entity"):
                worker.extract_docx(path)

    def test_rejects_large_plain_text_before_loading_it_into_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.txt"
            path.write_bytes(b"12345")
            with mock.patch.object(worker, "MAX_TEXT_SOURCE_BYTES", 4):
                with self.assertRaisesRegex(worker.SourceWorkerError, "64 MiB"):
                    worker.extract_plain_text(path, "text")

    def test_rejects_extension_signature_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.pdf"
            path.write_text("not a pdf", encoding="utf-8")
            with self.assertRaisesRegex(worker.SourceWorkerError, "서명"):
                worker.detect_source_format(path, path.name, "application/pdf")

    def test_deterministic_element_matching_ranks_clear_match_first(self) -> None:
        catalog = [
            {
                "element_id": "CF-01",
                "title": "순현재가치 NPV",
                "definition_markdown": "미래 현금흐름을 할인율로 현재가치화하고 투자액을 차감한다",
            },
            {
                "element_id": "FI-01",
                "title": "채권 듀레이션",
                "definition_markdown": "금리 변화에 대한 채권 가격 민감도",
            },
        ]
        candidates = worker.match_elements(
            "순현재가치 NPV는 미래 현금흐름을 할인율로 현재가치화하고 투자액을 차감한다",
            catalog,
        )
        self.assertEqual("CF-01", candidates[0].element_id)
        self.assertGreater(candidates[0].score, 0.9)

    def test_explicit_element_id_in_new_database_forces_exact_routing(self) -> None:
        catalog = [
            {"element_id": "ACC-01", "title": "회계등식", "definition_markdown": "기존 설명"},
            {"element_id": "CF-01", "title": "현재가치", "definition_markdown": "기존 설명"},
        ]

        candidates = worker.match_elements(
            "element_id\tdefinition\nACC-01\t완전히 새로 작성된 구조화 설명",
            catalog,
        )

        self.assertEqual("ACC-01", candidates[0].element_id)
        self.assertEqual(1.0, candidates[0].score)
        self.assertIn("요소 ID", candidates[0].reason)


class FakeHTTPResponse:
    def __init__(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._headers = {key.casefold(): value for key, value in (headers or {}).items()}

    def getheader(self, name: str) -> str | None:
        return self._headers.get(name.casefold())

    def read(self, amount: int = -1) -> bytes:
        if amount < 0:
            amount = len(self._body) - self._offset
        result = self._body[self._offset : self._offset + amount]
        self._offset += len(result)
        return result


class FakeHTTPConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class URLFetchTests(unittest.TestCase):
    @staticmethod
    def _resolver_for(addresses: dict[str, list[str]], calls: list[str] | None = None):
        def resolve(host: str, port: int, **_: Any) -> list[tuple[Any, ...]]:
            if calls is not None:
                calls.append(host)
            return [
                (socket_family(ip), worker.socket.SOCK_STREAM, 6, "", (ip, port))
                for ip in addresses[host]
            ]

        return resolve

    def test_url_safety_rejects_credentials_ip_literals_and_private_dns(self) -> None:
        resolver = self._resolver_for({"private.example.com": ["10.0.0.8"]})
        with self.assertRaisesRegex(worker.SourceWorkerError, "인증정보"):
            worker.resolve_public_source_url("https://user:pass@public.example.com/file", resolver)
        with self.assertRaisesRegex(worker.SourceWorkerError, "IP 주소"):
            worker.resolve_public_source_url("https://93.184.216.34/file", resolver)
        with self.assertRaisesRegex(worker.SourceWorkerError, "사설망"):
            worker.resolve_public_source_url("https://private.example.com/file", resolver)

    def test_url_fetch_revalidates_each_redirect_and_streams_snapshot(self) -> None:
        body = "<html><head><title>NPV</title></head><body>순현재가치 NPV 설명</body></html>".encode()
        dns_calls: list[str] = []
        resolver = self._resolver_for(
            {
                "public.example.com": ["93.184.216.34"],
                "cdn.example.com": ["1.1.1.1"],
            },
            dns_calls,
        )
        connections: list[FakeHTTPConnection] = []

        def opener(parsed: Any, addresses: Any, timeout: float, context: Any) -> tuple[Any, Any]:
            del addresses, timeout, context
            connection = FakeHTTPConnection()
            connections.append(connection)
            if parsed.hostname == "public.example.com":
                return connection, FakeHTTPResponse(302, headers={"Location": "https://cdn.example.com/source"})
            return connection, FakeHTTPResponse(
                200,
                body,
                {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(body)), "ETag": "test"},
            )

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "snapshot"
            result = worker.fetch_public_url_to_path(
                "https://public.example.com/start",
                destination,
                max_bytes=1024 * 1024,
                timeout_seconds=5,
                resolver=resolver,
                opener=opener,
            )
            stored = destination.read_bytes()
        self.assertEqual(body, stored)
        self.assertEqual(hashlib.sha256(body).hexdigest(), result.sha256)
        self.assertEqual("https://cdn.example.com/source", result.final_url)
        self.assertEqual(["public.example.com", "cdn.example.com"], dns_calls)
        self.assertTrue(all(connection.closed for connection in connections))

    def test_url_fetch_rejects_compressed_response_before_writing(self) -> None:
        resolver = self._resolver_for({"public.example.com": ["93.184.216.34"]})

        def opener(*_: Any) -> tuple[Any, Any]:
            return FakeHTTPConnection(), FakeHTTPResponse(
                200,
                b"compressed",
                {"Content-Type": "text/html", "Content-Encoding": "gzip"},
            )

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "snapshot"
            with self.assertRaisesRegex(worker.SourceWorkerError, "압축된 HTTP"):
                worker.fetch_public_url_to_path(
                    "https://public.example.com/source",
                    destination,
                    max_bytes=1024,
                    timeout_seconds=5,
                    resolver=resolver,
                    opener=opener,
                )
            self.assertFalse(destination.exists())


class SupabaseSourceClientTests(unittest.TestCase):
    @mock.patch.object(worker.http.client, "HTTPSConnection")
    def test_snapshot_upload_streams_with_opaque_secret_only_in_apikey(self, connection_class: mock.Mock) -> None:
        connection = connection_class.return_value
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = b"{}"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.html"
            path.write_bytes(b"snapshot-body")
            client = worker.SupabaseSourceClient("https://project.supabase.co", "sb_secret_test", 5)
            client.upload_from_path(
                worker.SOURCE_BUCKET,
                "owner/source/snapshot.html",
                path,
                content_type="text/html",
                max_bytes=1024,
            )

        headers = {call.args[0].casefold(): call.args[1] for call in connection.putheader.call_args_list}
        self.assertEqual("sb_secret_test", headers["apikey"])
        self.assertNotIn("authorization", headers)
        self.assertEqual(b"snapshot-body", b"".join(call.args[0] for call in connection.send.call_args_list))


EMPTY_JOB_ROW: dict[str, Any] = {
    # PostgREST renders a NULL `returns public.ingestion_jobs` result as a row of
    # null columns, so an idle queue must be recognised from this shape.
    "job_id": None,
    "job_kind": None,
    "status": None,
    "source_version_id": None,
    "progress_percent": None,
    "attempt_count": None,
    "input": None,
    "output": None,
    "error_message": None,
}


class FakeSourceClient:
    def __init__(self, source_path: Path, *, filename: str = "source.txt") -> None:
        self.source_path = source_path
        self.filename = filename
        self.secret_key = "test-secret"
        self.job_id = "83000000-0000-0000-0000-000000000001"
        self.version_id = "82000000-0000-0000-0000-000000000001"
        self.object_path = f"owner/sources/file/{self.version_id}/{filename}"
        self.sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        self.claimed = False
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.rpc_calls.append((name, payload))
        if name == worker.QUEUE_CATALOG_RPC:
            return {"queuedCount": payload["p_limit"], "queued": []}
        if name == worker.CLAIM_RPC:
            if self.claimed:
                return dict(EMPTY_JOB_ROW)
            self.claimed = True
            return {
                "job_id": self.job_id,
                "source_version_id": self.version_id,
                "job_kind": "file_extract",
                "status": "running",
                "input": {"objectPath": self.object_path, "originalFilename": self.filename},
            }
        if name == worker.PROGRESS_RPC:
            return {"jobStatus": "running", "stage": payload["p_stage"]}
        if name == worker.COMPLETE_RPC:
            return {"jobStatus": "succeeded", "parseStatus": "ready"}
        if name == worker.FAIL_RPC:
            return {"jobStatus": "failed"}
        raise AssertionError(name)

    def select_one(self, table: str, **kwargs: Any) -> dict[str, Any]:
        if table != "source_versions":
            raise AssertionError(table)
        return {
            "source_version_id": self.version_id,
            "source_id": "file-test",
            "original_filename": self.filename,
            "mime_type": "text/plain",
            "byte_size": self.source_path.stat().st_size,
            "sha256": self.sha256,
            "parse_status": "extracting",
        }

    def select(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
        if table == "source_files":
            return [{
                "bucket_id": worker.SOURCE_BUCKET,
                "object_path": self.object_path,
                "original_filename": self.filename,
                "mime_type": "text/plain",
                "byte_size": self.source_path.stat().st_size,
                "sha256": self.sha256,
                "file_role": "original",
            }]
        if table == "source_versions":
            return []
        if table == "elements":
            return [{
                "element_id": "CF-01",
                "title": "순현재가치 NPV",
                "topic_name": "기업재무",
                "subtopic_name": "투자안 평가",
                "core_relation": "미래 현금흐름 할인 현재가치 투자액 차감",
                "scope_notes": "",
            }]
        if table == "concepts":
            return [{
                "element_id": "CF-01",
                "title": "순현재가치 NPV",
                "definition_markdown": "미래 현금흐름을 할인율로 현재가치화하고 투자액을 차감한다",
                "intuition_markdown": "",
            }]
        if table == "formulas":
            return [{"element_id": "CF-01", "title": "NPV", "expression_markdown": "NPV = PV - I"}]
        raise AssertionError(table)

    def download_to_path(self, bucket: str, object_path: str, destination: Path, **kwargs: Any) -> str:
        self.assert_download(bucket, object_path)
        shutil.copyfile(self.source_path, destination)
        callback = kwargs.get("on_progress")
        if callback:
            callback(self.source_path.stat().st_size, self.source_path.stat().st_size)
        return self.sha256

    def assert_download(self, bucket: str, object_path: str) -> None:
        if bucket != worker.SOURCE_BUCKET or object_path != self.object_path:
            raise AssertionError((bucket, object_path))


class FakeURLSourceClient(FakeSourceClient):
    def __init__(self, source_path: Path) -> None:
        super().__init__(source_path, filename="source.html")
        self.requested_url = "https://public.example.com/source"
        self.timeout_seconds = 5.0
        self.uploads: list[dict[str, Any]] = []

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        self.rpc_calls.append((name, payload))
        if name == worker.CLAIM_RPC:
            if self.claimed:
                return dict(EMPTY_JOB_ROW)
            self.claimed = True
            return {
                "job_id": self.job_id,
                "source_version_id": self.version_id,
                "job_kind": "url_fetch",
                "status": "running",
                "input": {"url": self.requested_url},
            }
        if name == worker.PROGRESS_RPC:
            return {"jobStatus": "running", "stage": payload["p_stage"]}
        if name == worker.COMPLETE_RPC:
            return {"jobStatus": "succeeded", "parseStatus": "ready"}
        if name == worker.FAIL_RPC:
            return {"jobStatus": "failed"}
        raise AssertionError(name)

    def select_one(self, table: str, **kwargs: Any) -> dict[str, Any]:
        if table != "source_versions":
            raise AssertionError(table)
        return {
            "source_version_id": self.version_id,
            "source_id": "url-test",
            "original_filename": None,
            "mime_type": None,
            "byte_size": None,
            "sha256": None,
            "parse_status": "fetching",
            "fetch_url": self.requested_url,
            "created_by": "84000000-0000-0000-0000-000000000001",
        }

    def upload_from_path(self, bucket: str, object_path: str, source: Path, **kwargs: Any) -> None:
        self.uploads.append({
            "bucket": bucket,
            "object_path": object_path,
            "body": source.read_bytes(),
            **kwargs,
        })


class SourceWorkerTests(unittest.TestCase):
    def test_all_null_claim_row_reads_as_an_idle_queue(self) -> None:
        self.assertIsNone(worker._rpc_object(dict(EMPTY_JOB_ROW), "claim source ingestion"))
        self.assertIsNone(worker._rpc_object([dict(EMPTY_JOB_ROW)], "claim source ingestion"))
        claimed = worker._rpc_object({**EMPTY_JOB_ROW, "status": "running"}, "claim source ingestion")
        self.assertEqual("running", (claimed or {})["status"])

    def test_worker_queues_initial_catalog_urls_once_before_claiming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "input.txt"
            source_path.write_text(
                "순현재가치 NPV는 미래 현금흐름을 할인율로 현재가치화한다.",
                encoding="utf-8",
            )
            client = FakeSourceClient(source_path)
            ingestion = worker.SourceIngestionWorker(
                client,
                "source-catalog-test",
                auto_queue_catalog=4,
            )
            self.assertIsNotNone(ingestion.process_one())
            self.assertIsNone(ingestion.process_one())

        queue_calls = [payload for name, payload in client.rpc_calls if name == worker.QUEUE_CATALOG_RPC]
        self.assertEqual(1, len(queue_calls))
        self.assertEqual(4, queue_calls[0]["p_limit"])
        self.assertFalse(queue_calls[0]["p_refresh"])
        self.assertEqual(worker.QUEUE_CATALOG_RPC, client.rpc_calls[0][0])

    def test_worker_streams_extracts_matches_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "input.txt"
            source_path.write_text(
                "순현재가치 NPV는 미래 현금흐름을 할인율로 현재가치화하고 투자액을 차감한다.\n"
                "NPV = PV - I\n",
                encoding="utf-8",
            )
            client = FakeSourceClient(source_path)
            outcome = worker.SourceIngestionWorker(client, "source-test").process_one()
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual("ready", outcome.parse_status)
        complete = next(payload for name, payload in client.rpc_calls if name == worker.COMPLETE_RPC)
        self.assertGreater(len(complete["p_fragments"]), 0)
        self.assertEqual("CF-01", complete["p_candidates"][0]["elementId"])
        self.assertFalse(complete["p_requires_review"])
        stages = [payload["p_stage"] for name, payload in client.rpc_calls if name == worker.PROGRESS_RPC]
        self.assertIn("downloading", stages)
        self.assertIn("extracting", stages)
        self.assertIn("matching", stages)
        self.assertIn("saving", stages)

    def test_worker_fails_unsupported_file_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "input.bin"
            source_path.write_bytes(b"binary")
            client = FakeSourceClient(source_path, filename="source.bin")
            with self.assertRaisesRegex(worker.SourceWorkerError, "failed safely"):
                worker.SourceIngestionWorker(client, "source-test-fail").process_one()
        fail = next(payload for name, payload in client.rpc_calls if name == worker.FAIL_RPC)
        self.assertIn("지원하지 않는 파일 형식", fail["p_error_message"])

    def test_worker_fetches_archives_extracts_and_completes_url(self) -> None:
        body = (
            "<html><head><title>순현재가치 NPV</title></head>"
            "<body>미래 현금흐름을 할인율로 현재가치화하고 투자액을 차감한다. NPV = PV - I</body></html>"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "fixture.html"
            source_path.write_bytes(body)
            client = FakeURLSourceClient(source_path)

            def fake_fetch(url: str, destination: Path, **_: Any) -> worker.URLFetchResult:
                self.assertEqual(client.requested_url, url)
                destination.write_bytes(body)
                return worker.URLFetchResult(
                    requested_url=url,
                    final_url="https://public.example.com/final",
                    redirect_chain=(url, "https://public.example.com/final"),
                    content_type="text/html",
                    original_filename="source.html",
                    byte_size=len(body),
                    sha256=hashlib.sha256(body).hexdigest(),
                    response_headers={"Content-Type": "text/html"},
                )

            with mock.patch.object(worker, "fetch_public_url_to_path", side_effect=fake_fetch):
                outcome = worker.SourceIngestionWorker(client, "source-url-test").process_one()

        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual("ready", outcome.parse_status)
        self.assertEqual(1, len(client.uploads))
        self.assertEqual(body, client.uploads[0]["body"])
        complete = next(payload for name, payload in client.rpc_calls if name == worker.COMPLETE_RPC)
        self.assertEqual("https://public.example.com/final", complete["p_extraction_metadata"]["finalUrl"])
        self.assertIn("snapshotObjectPath", complete["p_extraction_metadata"])
        stages = [payload["p_stage"] for name, payload in client.rpc_calls if name == worker.PROGRESS_RPC]
        self.assertIn("archiving", stages)
        self.assertIn("extracting", stages)


def socket_family(address: str) -> int:
    return worker.socket.AF_INET6 if ":" in address else worker.socket.AF_INET


if __name__ == "__main__":
    unittest.main()
