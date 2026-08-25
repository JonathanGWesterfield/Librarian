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

    def test_chat_capability_is_documented_in_static_and_live_openapi(self) -> None:
        """Clients can discover the explicit override rule without source access."""
        spec = json.loads((REPO_ROOT / "docs" / "openapi.json").read_text())
        static_request = spec["components"]["schemas"]["ChatRequest"]
        static_response = spec["components"]["schemas"]["ChatResponse"]

        self.assertEqual(
            static_request["properties"]["answer_capability"]["enum"],
            ["quality", "lightweight", None],
        )
        self.assertIn("answer_capability", static_response["required"])
        self.assertEqual(
            static_response["properties"]["answer_capability"]["enum"],
            ["quality", "lightweight"],
        )

        live = app.openapi()
        request_schema = live["components"]["schemas"]["ChatRequest"]
        response_schema = live["components"]["schemas"]["ChatResponse"]
        self.assertIn("answer_capability", request_schema["properties"])
        self.assertIn("answer_capability", response_schema["required"])

    def test_openapi_does_not_advertise_unimplemented_chat_streaming(self) -> None:
        """Keep the client contract aligned with the synchronous chat route.

        The web UI receives one complete JSON response from ``POST /chat``.
        Do not expose an SSE route in documentation before that route exists.
        """
        static_spec = json.loads((REPO_ROOT / "docs" / "openapi.json").read_text())
        live_spec = app.openapi()

        for spec in (static_spec, live_spec):
            self.assertIn("/chat", spec["paths"])
            self.assertNotIn("/chat/stream", spec["paths"])
            self.assertNotIn("text/event-stream", json.dumps(spec))


if __name__ == "__main__":
    unittest.main()
