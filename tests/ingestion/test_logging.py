import logging
import unittest
from io import StringIO

from librarian_logging import configure_cli_logging


class LoggingTests(unittest.TestCase):
    def test_cli_logging_includes_emitting_module_name(self) -> None:
        """Lock in the CLI log format that makes long-running scripts debuggable.
        Every operational message should include the logger/module name so users
        can tell whether output came from ingestion, summarization, evaluation,
        or another script.
        """
        original_handlers = list(logging.getLogger().handlers)
        stream = StringIO()
        try:
            configure_cli_logging(stream=stream, force=True)
            logging.getLogger("librarian_example.module").info("hello")
        finally:
            root_logger = logging.getLogger()
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)

        self.assertIn("INFO librarian_example.module: hello", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
