import sqlite3
import json
import shutil
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from tools import admin_release_worker as worker


class IdleClaimShapeTest(unittest.TestCase):
    def test_all_null_job_row_reads_as_an_idle_queue(self) -> None:
        empty = {"job_id": None, "status": None, "release_id": None}
        self.assertIsNone(worker._rpc_object(dict(empty), "claim"))
        self.assertIsNone(worker._rpc_object([dict(empty)], "claim"))
        claimed = worker._rpc_object({**empty, "status": "running"}, "claim")
        self.assertEqual("running", (claimed or {})["status"])


class AdminReleaseWorkerTest(unittest.TestCase):
    def release(self) -> dict[str, object]:
        packaged = json.loads(worker.PACKAGED_MANIFEST.read_text(encoding="utf-8"))
        return {
            "release_id": str(uuid.uuid4()),
            "content_version": int(packaged["contentDbVersion"]) + 1,
            "schema_version": worker.SCHEMA_VERSION,
        }

    def release_ready_base(self, directory: Path) -> Path:
        base = directory / "release-ready-base.sqlite3"
        shutil.copyfile(worker.PACKAGED_DATABASE, base)
        with closing(sqlite3.connect(base)) as database:
            database.execute(
                "UPDATE metadata SET value='release_ready' WHERE key='concept_question_release_status'"
            )
            database.commit()
        return base

    def candidate_base(self, directory: Path) -> Path:
        base = directory / "candidate-base.sqlite3"
        shutil.copyfile(worker.PACKAGED_DATABASE, base)
        with closing(sqlite3.connect(base)) as database:
            database.execute(
                "UPDATE metadata SET value='candidate' WHERE key='concept_question_release_status'"
            )
            database.commit()
        return base

    def test_concept_revision_requires_question_model_rerun(self) -> None:
        with closing(sqlite3.connect(worker.PACKAGED_DATABASE)) as database:
            row = database.execute(
                """SELECT concept_id,element_id,title,definition,intuition,scope_notes
                   FROM concept_cards ORDER BY concept_id LIMIT 1"""
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        changed_definition = row[3] + " 자동 릴리스 검증 문구"
        revision = {
            "revision_id": str(uuid.uuid4()),
            "entity_type": "concept",
            "entity_key": row[0],
            "revision_number": 2,
            "operation": "update",
            "content_hash": "a" * 64,
            "snapshot": {
                "concept_id": row[0],
                "element_id": row[1],
                "title": row[2],
                "definition_markdown": changed_definition,
                "intuition_markdown": row[4],
                "learning_notes_markdown": row[5],
            },
        }

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            base_database = self.release_ready_base(directory)
            database_path = directory / "content.sqlite3"
            manifest_path = directory / "content-manifest.json"
            with self.assertRaisesRegex(worker.ReleaseWorkerError, "human review"):
                worker.build_release_bundle(
                    base_database,
                    database_path,
                    manifest_path,
                    self.release(),
                    [revision],
                )

    def test_candidate_question_bank_blocks_stable_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            base_database = self.candidate_base(directory)
            with self.assertRaisesRegex(worker.ReleaseWorkerError, "human review"):
                worker.build_release_bundle(
                    base_database,
                    directory / "content.sqlite3",
                    directory / "content-manifest.json",
                    self.release(),
                    [],
                )

    def test_distractor_revision_fails_instead_of_being_silently_ignored(self) -> None:
        revision = {
            "revision_id": str(uuid.uuid4()),
            "entity_type": "distractor",
            "entity_key": str(uuid.uuid4()),
            "revision_number": 1,
            "operation": "update",
            "content_hash": "b" * 64,
            "snapshot": {},
        }
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            with self.assertRaisesRegex(worker.ReleaseWorkerError, "distractor"):
                worker.build_release_bundle(
                    worker.PACKAGED_DATABASE,
                    directory / "content.sqlite3",
                    directory / "content-manifest.json",
                    self.release(),
                    [revision],
                )


if __name__ == "__main__":
    unittest.main()
