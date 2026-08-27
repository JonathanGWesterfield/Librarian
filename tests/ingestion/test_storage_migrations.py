import sqlite3
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

import librarian_storage.storage as storage_module
from librarian_storage.storage import (
    SQLITE_SCHEMA_MIGRATIONS,
    SQLiteIngestionStore,
    SQLiteSchemaMigration,
    SchemaMigrationError,
    build_book_identity_key,
)


class SQLiteSchemaMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_clean_database_has_current_schema_and_complete_history(self) -> None:
        with SQLiteIngestionStore(self.database_path) as store:
            history = store.list_applied_schema_migrations()
            foreign_keys = store._connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]
            book_columns = self._columns(store._connection, "books")
            summary_columns = self._columns(store._connection, "summary_jobs")
            book_indexes = {
                row[1]
                for row in store._connection.execute(
                    "PRAGMA index_list(books)"
                ).fetchall()
            }

        self.assertEqual(
            [(migration.version, migration.name) for migration in history],
            [
                (migration.version, migration.name)
                for migration in SQLITE_SCHEMA_MIGRATIONS
            ],
        )
        self.assertTrue(
            all(
                datetime.fromisoformat(migration.applied_at).utcoffset()
                == timedelta(0)
                for migration in history
            )
        )
        self.assertEqual(foreign_keys, 1)
        self.assertIn("publisher", book_columns)
        self.assertIn("identity_key", book_columns)
        self.assertIn("idx_books_identity_key", book_indexes)
        self.assertTrue(
            {
                "current_stage",
                "current_step",
                "total_steps",
                "progress_message",
                "progress_updated_at",
            }.issubset(summary_columns)
        )

    def test_legacy_database_upgrades_and_preserves_seed_data(self) -> None:
        self._create_legacy_database()

        with SQLiteIngestionStore(self.database_path) as store:
            history = store.list_applied_schema_migrations()
            rows = store._connection.execute(
                """
                SELECT id, relative_path, title, authors_json, publisher, identity_key
                FROM books
                ORDER BY id
                """
            ).fetchall()
            summary_columns = self._columns(store._connection, "summary_jobs")
            summary_job = store._connection.execute(
                """
                SELECT id, book_id, status, current_stage, progress_updated_at
                FROM summary_jobs
                """
            ).fetchone()

        expected_identity = build_book_identity_key(
            "Legacy Foundation", ["Isaac Asimov"], None
        )
        self.assertEqual(
            rows,
            [
                (
                    "legacy-book",
                    "legacy.epub",
                    "Legacy Foundation",
                    '["Isaac Asimov"]',
                    None,
                    expected_identity,
                ),
                (
                    "malformed-authors",
                    "malformed.epub",
                    "Malformed Authors",
                    "not-json",
                    None,
                    None,
                ),
            ],
        )
        self.assertEqual(
            [(migration.version, migration.name) for migration in history],
            [
                (migration.version, migration.name)
                for migration in SQLITE_SCHEMA_MIGRATIONS
            ],
        )
        self.assertIn("progress_updated_at", summary_columns)
        self.assertEqual(
            summary_job,
            ("legacy-summary", "legacy-book", "pending", None, None),
        )

    def test_second_initialize_is_idempotent(self) -> None:
        store = SQLiteIngestionStore(self.database_path)
        try:
            store.initialize()
            first_history = store.list_applied_schema_migrations()
            store.initialize()
            second_history = store.list_applied_schema_migrations()
        finally:
            store.close()

        self.assertEqual(second_history, first_history)
        with sqlite3.connect(self.database_path) as connection:
            history_count = connection.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]
        self.assertEqual(history_count, len(SQLITE_SCHEMA_MIGRATIONS))

    def test_unknown_future_version_is_rejected_without_mutation(self) -> None:
        self._create_incompatible_history(version=999, name="future_schema")
        before = self._database_snapshot()
        store = SQLiteIngestionStore(self.database_path)

        with self.assertRaisesRegex(SchemaMigrationError, "newer or unknown"):
            store.initialize()

        self.assertIsNone(store.connection)
        self.assertEqual(self._database_snapshot(), before)

    def test_known_version_name_mismatch_is_rejected_without_mutation(self) -> None:
        self._create_incompatible_history(version=1, name="rewritten_name")
        before = self._database_snapshot()
        store = SQLiteIngestionStore(self.database_path)

        with self.assertRaisesRegex(SchemaMigrationError, "refusing to rewrite history"):
            store.initialize()

        self.assertIsNone(store.connection)
        self.assertEqual(self._database_snapshot(), before)

    def test_failed_migration_rolls_back_changes_and_history(self) -> None:
        with SQLiteIngestionStore(self.database_path):
            pass
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("CREATE TABLE migration_sentinel (value TEXT NOT NULL)")
            connection.execute("INSERT INTO migration_sentinel VALUES ('original')")

        def fail_after_writes(connection: sqlite3.Connection) -> None:
            connection.execute("UPDATE migration_sentinel SET value = 'mutated'")
            connection.execute("CREATE TABLE failed_migration_artifact (id INTEGER)")
            raise RuntimeError("injected migration failure")

        failing_registry = SQLITE_SCHEMA_MIGRATIONS + (
            SQLiteSchemaMigration(
                version=len(SQLITE_SCHEMA_MIGRATIONS) + 1,
                name="injected_failure",
                apply=fail_after_writes,
            ),
        )
        store = SQLiteIngestionStore(self.database_path)
        with patch.object(
            storage_module, "SQLITE_SCHEMA_MIGRATIONS", failing_registry
        ):
            with self.assertRaisesRegex(
                SchemaMigrationError, "injected_failure.*failed"
            ):
                store.initialize()

        self.assertIsNone(store.connection)
        with sqlite3.connect(self.database_path) as connection:
            sentinel = connection.execute(
                "SELECT value FROM migration_sentinel"
            ).fetchone()[0]
            failed_history = connection.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
                (len(SQLITE_SCHEMA_MIGRATIONS) + 1,),
            ).fetchone()[0]
            artifact = connection.execute(
                """
                SELECT COUNT(*) FROM sqlite_master
                WHERE type = 'table' AND name = 'failed_migration_artifact'
                """
            ).fetchone()[0]
        self.assertEqual(sentinel, "original")
        self.assertEqual(failed_history, 0)
        self.assertEqual(artifact, 0)

    def test_concurrent_initializers_record_each_migration_once(self) -> None:
        barrier = threading.Barrier(2)

        def initialize_store() -> list[tuple[int, str]]:
            barrier.wait()
            with SQLiteIngestionStore(self.database_path) as store:
                return [
                    (migration.version, migration.name)
                    for migration in store.list_applied_schema_migrations()
                ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            histories = list(executor.map(lambda _: initialize_store(), range(2)))

        expected = [
            (migration.version, migration.name)
            for migration in SQLITE_SCHEMA_MIGRATIONS
        ]
        self.assertEqual(histories, [expected, expected])
        with sqlite3.connect(self.database_path) as connection:
            history_count = connection.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]
        self.assertEqual(history_count, len(expected))

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }

    def _create_legacy_database(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE books (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    file_hash TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    title TEXT,
                    authors_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    discovered_at TEXT NOT NULL,
                    ingested_at TEXT,
                    chunk_started_at TEXT,
                    chunk_completed_at TEXT,
                    chunk_duration_seconds REAL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE summary_jobs (
                    id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_seconds REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(book_id, provider, model, detail)
                );
                """
            )
            rows = (
                (
                    "legacy-book",
                    "/library/legacy.epub",
                    "legacy.epub",
                    "hash-1",
                    100,
                    "Legacy Foundation",
                    '["Isaac Asimov"]',
                    "ingested",
                ),
                (
                    "malformed-authors",
                    "/library/malformed.epub",
                    "malformed.epub",
                    "hash-2",
                    200,
                    "Malformed Authors",
                    "not-json",
                    "ingested",
                ),
            )
            connection.executemany(
                """
                INSERT INTO books (
                    id, source_path, relative_path, file_hash, size_bytes, title,
                    authors_json, status, discovered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00+00:00',
                          '2026-01-01T00:00:00+00:00')
                """,
                rows,
            )
            connection.execute(
                """
                INSERT INTO summary_jobs (
                    id, book_id, provider, model, detail, status, created_at,
                    updated_at
                ) VALUES (
                    'legacy-summary', 'legacy-book', 'ollama', 'qwen', 'medium',
                    'pending', '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:00+00:00'
                )
                """
            )

    def _create_incompatible_history(self, *, version: int, name: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE sentinel (value TEXT NOT NULL);
                INSERT INTO sentinel VALUES ('preserve-me');
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                (version, name, "2026-01-01T00:00:00+00:00"),
            )

    def _database_snapshot(self) -> tuple[list[tuple[object, ...]], list[str]]:
        with sqlite3.connect(self.database_path) as connection:
            history = connection.execute(
                "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
            ).fetchall()
            objects = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master ORDER BY name"
                ).fetchall()
            ]
            sentinel = connection.execute("SELECT value FROM sentinel").fetchall()
        return [*history, *sentinel], objects


if __name__ == "__main__":
    unittest.main()
