"""Logging configuration shared by Librarian scripts."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, TextIO

DEFAULT_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_cli_logging(
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
    force: bool = False,
) -> None:
    """Configure root logging for CLI output with module names included."""
    root_logger = logging.getLogger()
    target_stream = stream or sys.stderr
    if force:
        root_logger.handlers.clear()

    if not root_logger.handlers:
        handler = logging.StreamHandler(target_stream)
        handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
            if isinstance(handler, logging.StreamHandler):
                handler.setStream(target_stream)

    root_logger.setLevel(level)


def emit_json(payload: Any) -> None:
    """Write command payload JSON to stdout without treating it as a log line."""
    sys.stdout.write(json.dumps(payload, indent=2))
    sys.stdout.write("\n")
