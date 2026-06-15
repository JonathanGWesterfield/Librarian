import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ingestion"))

try:
    from fastapi.testclient import TestClient
    from librarian_api.main import app
except (ModuleNotFoundError, RuntimeError) as error:
    TestClient = None
    app = None
    API_IMPORT_ERROR = error
else:
    API_IMPORT_ERROR = None


@unittest.skipIf(
    TestClient is None,
    f"API dependencies are not installed: {API_IMPORT_ERROR}",
)
class IngestionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ingestion_endpoints_support_desktop_clients(self) -> None:
        """Verify the API exposes ingestion, summary, and book listing flows.
        A future Electron or Tauri app can use these endpoints instead of
        shelling out to the CLI for common ingestion actions.
        """
        run_response = self.client.post(
            "/ingestion/run",
            json={
                "books_dir": str(self.books_dir),
                "database_url": self.database_url,
                "list_epubs": True,
            },
        )

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["parsed"], 1)

        summary_response = self.client.get(
            "/ingestion/summary",
            params={"database_url": self.database_url},
        )
        books_response = self.client.get(
            "/books",
            params={"database_url": self.database_url},
        )

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(books_response.status_code, 200)
        self.assertEqual(summary_response.json()["total_books"], 1)
        self.assertEqual(books_response.json()[0]["relative_path"], "sample.epub")
