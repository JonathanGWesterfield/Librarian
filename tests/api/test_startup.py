import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_storage.storage import (
    SQLITE_SCHEMA_MIGRATIONS,
    SQLiteIngestionStore,
    SchemaMigrationError,
)

try:
    from fastapi.testclient import TestClient
    import librarian_api.main as main_module
    from librarian_api.config import Settings
except (ModuleNotFoundError, RuntimeError) as error:
    TestClient = None
    main_module = None
    API_IMPORT_ERROR = error
else:
    API_IMPORT_ERROR = None


@unittest.skipIf(
    TestClient is None,
    f"API dependencies are not installed: {API_IMPORT_ERROR}",
)
class ApiStartupMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "startup.db"
        self.database_url = f"sqlite:///{self.database_path}"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _settings(self) -> Settings:
        return Settings(
            database_url=self.database_url,
            books_dir="/books",
            host_books_dir="./tests/fixtures/epubs",
            log_file=str(Path(self.temp_dir.name) / "librarian.log"),
        )

    def test_lifespan_migrates_compatible_database_and_closes_startup_store(
        self,
    ) -> None:
        startup_store = SQLiteIngestionStore(self.database_path)
        with (
            patch.object(main_module, "get_settings", return_value=self._settings()),
            patch.object(
                main_module,
                "create_ingestion_store",
                return_value=startup_store,
            ),
        ):
            with TestClient(main_module.app) as client:
                self.assertIsNone(startup_store.connection)
                self.assertEqual(client.get("/health").status_code, 200)

        with sqlite3.connect(self.database_path) as connection:
            history = connection.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            ).fetchall()
            progress_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(summary_jobs)"
                ).fetchall()
            }
        self.assertEqual(
            history,
            [
                (migration.version, migration.name)
                for migration in SQLITE_SCHEMA_MIGRATIONS
            ],
        )
        self.assertIn("progress_updated_at", progress_columns)
        with SQLiteIngestionStore(self.database_path) as reopened_store:
            self.assertEqual(
                len(reopened_store.list_applied_schema_migrations()),
                len(SQLITE_SCHEMA_MIGRATIONS),
            )

    def test_lifespan_rejects_future_history_without_mutation(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                INSERT INTO schema_migrations
                VALUES (999, 'future_schema', '2026-01-01T00:00:00+00:00');
                CREATE TABLE sentinel (value TEXT NOT NULL);
                INSERT INTO sentinel VALUES ('preserve-me');
                """
            )
        before = self._snapshot()

        with patch.object(main_module, "get_settings", return_value=self._settings()):
            with self.assertRaisesRegex(SchemaMigrationError, "newer or unknown"):
                with TestClient(main_module.app):
                    pass

        self.assertEqual(self._snapshot(), before)

    def test_lifespan_closes_store_when_initialization_fails(self) -> None:
        failing_store = Mock()
        failing_store.initialize.side_effect = RuntimeError("startup failed")

        with (
            patch.object(main_module, "get_settings", return_value=self._settings()),
            patch.object(
                main_module,
                "create_ingestion_store",
                return_value=failing_store,
            ) as create_store,
        ):
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                with TestClient(main_module.app):
                    pass

        create_store.assert_called_once_with(self.database_url)
        failing_store.initialize.assert_called_once_with()
        failing_store.close.assert_called_once_with()

    def _snapshot(self) -> tuple[list[tuple[object, ...]], list[str]]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT version, name, applied_at FROM schema_migrations"
            ).fetchall()
            rows.extend(connection.execute("SELECT value FROM sentinel").fetchall())
            objects = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master ORDER BY name"
                ).fetchall()
            ]
        return rows, objects


if __name__ == "__main__":
    unittest.main()
