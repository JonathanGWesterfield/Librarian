"""Tests for diagnostics shared by provider subprocesses and the future broker."""

from __future__ import annotations

import unittest

from librarian_logging import safe_provider_stderr_diagnostic


class ProviderDiagnosticSafetyTests(unittest.TestCase):
    """Untrusted provider output must never become a prompt or credential leak."""

    def test_credentials_are_redacted_from_text_and_metadata_shapes(self) -> None:
        diagnostic = safe_provider_stderr_diagnostic(
            'failed authorization: Bearer hidden-token token=second-secret '
            'api_key="third-secret" sk-abcdefghijklmnopqrstuvwxyz',
            provider_name="Codex",
        )

        self.assertEqual(diagnostic.count("[redacted]"), 4)
        for secret in ("hidden-token", "second-secret", "third-secret", "abcdefghijklmnopqrstuvwxyz"):
            self.assertNotIn(secret, diagnostic)

    def test_request_content_is_omitted_instead_of_partially_redacted(self) -> None:
        diagnostic = safe_provider_stderr_diagnostic(
            "provider rejected prompt: private EPUB sentence that must not reach logs",
            provider_name="Codex",
        )

        self.assertEqual(diagnostic, "Codex stderr: [request content redacted]")

    def test_empty_bytes_and_oversized_diagnostics_have_bounded_safe_output(self) -> None:
        self.assertEqual(
            safe_provider_stderr_diagnostic(b"", provider_name="Codex"),
            "Codex did not provide stderr; check login, model access, and provider configuration.",
        )
        diagnostic = safe_provider_stderr_diagnostic(
            "x" * 12,
            provider_name="Codex",
            max_length=10,
        )
        self.assertEqual(diagnostic, "Codex stderr: xxxxxxxxxx [stderr truncated]")

    def test_invalid_diagnostic_controls_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider_name"):
            safe_provider_stderr_diagnostic("error", provider_name="")
        with self.assertRaisesRegex(ValueError, "max_length"):
            safe_provider_stderr_diagnostic("error", provider_name="Codex", max_length=0)


if __name__ == "__main__":
    unittest.main()
