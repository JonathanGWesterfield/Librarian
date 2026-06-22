import logging
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_logging import configure_cli_logging


class LoggingTests(unittest.TestCase):
    def test_cli_logging_writes_to_stdout_and_log_file(self) -> None:
        """Lock in the two places humans should see operational messages.
        Long-running scripts need live stdout progress while also preserving the
        same module-qualified messages in a local log file for later inspection.
        """
        original_handlers = list(logging.getLogger().handlers)
        stream = StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "librarian.log"
            try:
                configure_cli_logging(stream=stream, log_file=log_file, force=True)
                logging.getLogger("librarian_example.module").info("hello")
            finally:
                _restore_handlers(original_handlers)

            self.assertIn("INFO librarian_example.module: hello", stream.getvalue())
            self.assertIn(
                "INFO librarian_example.module: hello",
                log_file.read_text(encoding="utf-8"),
            )

    def test_cli_logging_can_disable_stdout_while_still_writing_file(self) -> None:
        """Protect JSON CLI output from log contamination.
        Automation commands can suppress console logging for stdout purity while
        keeping the same diagnostics available in the configured log file.
        """
        original_handlers = list(logging.getLogger().handlers)
        stream = StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "librarian.log"
            try:
                configure_cli_logging(
                    stream=stream,
                    console=False,
                    log_file=log_file,
                    force=True,
                )
                logging.getLogger("librarian_example.module").info("json safe")
            finally:
                _restore_handlers(original_handlers)

            self.assertEqual("", stream.getvalue())
            self.assertIn(
                "INFO librarian_example.module: json safe",
                log_file.read_text(encoding="utf-8"),
            )

    def test_cli_logging_includes_emitting_module_name(self) -> None:
        """Lock in the CLI log format that makes long-running scripts debuggable.
        Every operational message should include the logger/module name so users
        can tell whether output came from ingestion, summarization, evaluation,
        or another script.
        """
        original_handlers = list(logging.getLogger().handlers)
        stream = StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "librarian.log"
            try:
                configure_cli_logging(stream=stream, log_file=log_file, force=True)
                logging.getLogger("librarian_example.module").info("hello")
            finally:
                _restore_handlers(original_handlers)

        self.assertIn("INFO librarian_example.module: hello", stream.getvalue())


def _restore_handlers(original_handlers: list[logging.Handler]) -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()
    root_logger.handlers.extend(original_handlers)


if __name__ == "__main__":
    unittest.main()
