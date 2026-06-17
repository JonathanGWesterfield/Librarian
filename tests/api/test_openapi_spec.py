import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

try:
    from librarian_api.main import app
except (ModuleNotFoundError, RuntimeError) as error:
    app = None
    API_IMPORT_ERROR = error
else:
    API_IMPORT_ERROR = None


@unittest.skipIf(app is None, f"API dependencies are not installed: {API_IMPORT_ERROR}")
class StaticOpenApiSpecTests(unittest.TestCase):
    def test_static_openapi_spec_is_valid_and_covers_fastapi_routes(self) -> None:
        """Verify the checked-in OpenAPI contract is machine-readable.
        The spec is meant for code generators and desktop-client work, so it
        should parse cleanly and include every public route we expose today.
        """
        spec_path = REPO_ROOT / "docs" / "openapi.json"
        spec = json.loads(spec_path.read_text())

        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertEqual(spec["info"]["title"], "Librarian API")

        documented_routes = set(spec["paths"])
        runtime_routes = {
            route.path
            for route in app.routes
            if not route.path.startswith("/docs")
            and not route.path.startswith("/redoc")
            and route.path != "/openapi.json"
        }

        self.assertEqual(runtime_routes, documented_routes)


if __name__ == "__main__":
    unittest.main()
