"""Logging configuration shared by Librarian runtimes."""

from __future__ import annotations

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TextIO

DEFAULT_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
LOG_FILE_ENV = "LIBRARIAN_LOG_FILE"
DEFAULT_LOG_FILE = Path(__file__).resolve().parents[2] / "logs/librarian.log"
DEFAULT_MAX_LOG_BYTES = 5_000_000
DEFAULT_BACKUP_COUNT = 3


def configure_logging(
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
    console: bool = True,
    file_enabled: bool = True,
    log_file: str | Path | None = None,
    force: bool = False,
) -> None:
    """Configure root logging for stdout and the shared local log file."""
    root_logger = logging.getLogger()
    if force:
        _clear_handlers(root_logger)

    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
    _configure_console_handler(root_logger, formatter, stream=stream, enabled=console)
    _configure_file_handler(
        root_logger,
        formatter,
        enabled=file_enabled,
        log_file=_resolve_log_file(log_file),
    )

    root_logger.setLevel(level)


def _configure_console_handler(
    root_logger: logging.Logger,
    formatter: logging.Formatter,
    *,
    stream: TextIO | None,
    enabled: bool,
) -> None:
    handler = _find_librarian_handler(root_logger, "_librarian_console_handler")
    if not enabled:
        _remove_handler(root_logger, handler)
        return

    target_stream = stream or sys.stdout
    if handler is None:
        handler = logging.StreamHandler(target_stream)
        setattr(handler, "_librarian_console_handler", True)
        root_logger.addHandler(handler)
    elif isinstance(handler, logging.StreamHandler):
        handler.setStream(target_stream)

    handler.setFormatter(formatter)


def _configure_file_handler(
    root_logger: logging.Logger,
    formatter: logging.Formatter,
    *,
    enabled: bool,
    log_file: Path,
) -> None:
    handler = _find_librarian_handler(root_logger, "_librarian_file_handler")
    if not enabled:
        _remove_handler(root_logger, handler)
        return

    log_file.parent.mkdir(parents=True, exist_ok=True)
    current_path = Path(getattr(handler, "_librarian_log_file", "")) if handler else None
    if handler is None or current_path != log_file:
        _remove_handler(root_logger, handler)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=DEFAULT_MAX_LOG_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
        setattr(handler, "_librarian_file_handler", True)
        setattr(handler, "_librarian_log_file", log_file)
        root_logger.addHandler(handler)

    handler.setFormatter(formatter)


def _resolve_log_file(log_file: str | Path | None) -> Path:
    if log_file is not None:
        return Path(log_file).expanduser()
    configured = os.environ.get(LOG_FILE_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_LOG_FILE


def _find_librarian_handler(
    root_logger: logging.Logger,
    marker_attribute: str,
) -> logging.Handler | None:
    for handler in root_logger.handlers:
        if getattr(handler, marker_attribute, False):
            return handler
    return None


def _remove_handler(
    root_logger: logging.Logger,
    handler: logging.Handler | None,
) -> None:
    if handler is None:
        return
    root_logger.removeHandler(handler)
    handler.close()


def _clear_handlers(root_logger: logging.Logger) -> None:
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        if _is_librarian_handler(handler):
            handler.close()


def _is_librarian_handler(handler: logging.Handler) -> bool:
    return bool(
        getattr(handler, "_librarian_console_handler", False)
        or getattr(handler, "_librarian_file_handler", False)
    )


def configure_cli_logging(
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
    console: bool = True,
    file_enabled: bool = True,
    log_file: str | Path | None = None,
    force: bool = False,
) -> None:
    """Compatibility wrapper for scripts that configure Librarian logging."""
    configure_logging(
        level=level,
        stream=stream,
        console=console,
        file_enabled=file_enabled,
        log_file=log_file,
        force=force,
    )


def emit_json(payload: Any) -> None:
    """Write command payload JSON to stdout without treating it as a log line."""
    sys.stdout.write(json.dumps(payload, indent=2))
    sys.stdout.write("\n")
