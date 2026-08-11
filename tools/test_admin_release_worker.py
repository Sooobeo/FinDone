import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from tools import admin_release_worker as worker


class AdminReleaseWorkerTest(unittest.TestCase):
    def release(self) -> dict[str, object]:
        return {
            "release_id": str(uuid.uuid4()),
            "content_version": 6,
            "schema_version": 1,
        }

    def test_build_projects_revision_and_rebuilds_search(self) -> None:
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
            database_path = directory / "content.sqlite3"
            manifest_path = directory / "content-manifest.json"
            manifest = worker.build_release_bundle(
                worker.PACKAGED_DATABASE,
                database_path,
                manifest_path,
                self.release(),
                [revision],
            )

            self.assertEqual(6, manifest["contentDbVersion"])
            self.assertEqual("clean-rebuild", manifest["buildMode"])
            self.assertEqual(worker.sha256_file(database_path), manifest["sha256"])
            self.assertEqual(worker.canonical_json_bytes(manifest), manifest_path.read_bytes())
            validation = worker.validate_release_database(database_path, manifest)
            self.assertEqual("passed", validation.status)
            with closing(sqlite3.connect(database_path)) as database:
                self.assertEqual(0, database.execute("PRAGMA freelist_count").fetchone()[0])
                self.assertEqual(
                    changed_definition,
                    database.execute(
                        "SELECT definition FROM concept_cards WHERE concept_id=?",
                        (row[0],),
                    ).fetchone()[0],
                )
                self.assertIn(
                    "자동 릴리스 검증 문구",
                    database.execute(
                        "SELECT normalized_text FROM knowledge_fts WHERE element_id=?",
                        (row[1],),
                    ).fetchone()[0],
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
