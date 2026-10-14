"""Strict non-secret configuration for the R2 gRPC broker process.

The broker has different configuration needs from a caller: it has no target
or caller credential role, but it does need the one configured Codex model.
This document is deliberately separate from ``runtime_config`` so a broker
cannot accidentally accept a caller's credential role or a legacy
``api_key_file`` configuration reference.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from librarian_contracts.runtime_config import (
    ANSWER_CAPABILITIES,
    RUNTIME_CONFIG_VERSION,
)

_TOP_LEVEL_FIELDS = frozenset({"version", "generation"})
_GENERATION_FIELDS = frozenset({"model", "answer_capability"})


class BrokerServerConfigError(ValueError):
    """The broker's resolver-owned runtime file is malformed or unsafe."""


@dataclass(frozen=True)
class BrokerServerRuntimeConfig:
    """The only mutable, non-secret settings accepted by the gRPC broker."""

    model: str
    answer_capability: str


def build_broker_server_runtime_config(
    *, model: str, answer_capability: str
) -> BrokerServerRuntimeConfig:
    """Build and validate the resolver-owned broker runtime settings."""

    config = BrokerServerRuntimeConfig(model=model, answer_capability=answer_capability)
    _validate(config)
    return config


def serialize_broker_server_runtime_config(config: BrokerServerRuntimeConfig) -> str:
    """Render a deterministic, strict broker runtime document."""

    _validate(config)
    return json.dumps(
        {
            "version": RUNTIME_CONFIG_VERSION,
            "generation": {
                "model": config.model,
                "answer_capability": config.answer_capability,
            },
        },
        indent=2,
    ) + "\n"


def parse_broker_server_runtime_config(raw: str | bytes) -> BrokerServerRuntimeConfig:
    """Parse exactly the R2 broker document and reject all hidden fields."""

    try:
        decoded = json.loads(raw, object_pairs_hook=_reject_duplicate_fields)
    except (TypeError, json.JSONDecodeError) as error:
        raise BrokerServerConfigError("broker server configuration must be valid JSON") from error

    root = _require_object(decoded, "broker server configuration")
    _require_exact_fields(root, _TOP_LEVEL_FIELDS, "broker server configuration")
    if (
        not isinstance(root["version"], int)
        or isinstance(root["version"], bool)
        or root["version"] != RUNTIME_CONFIG_VERSION
    ):
        raise BrokerServerConfigError(
            f"broker server configuration version must be {RUNTIME_CONFIG_VERSION}"
        )
    generation = _require_object(root["generation"], "generation")
    _require_exact_fields(generation, _GENERATION_FIELDS, "generation")
    config = BrokerServerRuntimeConfig(
        model=generation["model"],
        answer_capability=generation["answer_capability"],
    )
    _validate(config)
    return config


def load_broker_server_runtime_config(path: Path) -> BrokerServerRuntimeConfig:
    """Load the fixed broker mount without following a surprising symlink."""

    try:
        raw = _read_regular_file_without_following_links(path)
    except (OSError, UnicodeError) as error:
        raise BrokerServerConfigError("could not read broker server configuration") from error
    return parse_broker_server_runtime_config(raw)


def _validate(config: BrokerServerRuntimeConfig) -> None:
    if not isinstance(config.model, str) or not config.model.strip():
        raise BrokerServerConfigError("generation.model must be a non-empty string")
    if (
        not isinstance(config.answer_capability, str)
        or config.answer_capability not in ANSWER_CAPABILITIES
    ):
        allowed = ", ".join(sorted(ANSWER_CAPABILITIES))
        raise BrokerServerConfigError(f"generation.answer_capability must be one of: {allowed}")


def _read_regular_file_without_following_links(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise BrokerServerConfigError("broker server configuration must be a regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8") as file:
            descriptor = -1
            return file.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BrokerServerConfigError(f"broker server configuration repeats field: {key}")
        result[key] = value
    return result


def _require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BrokerServerConfigError(f"{label} must be a JSON object")
    return value


def _require_exact_fields(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) == expected:
        return
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    details = []
    if missing:
        details.append(f"missing fields: {', '.join(missing)}")
    if unexpected:
        details.append(f"unexpected fields: {', '.join(unexpected)}")
    raise BrokerServerConfigError(f"{label} has invalid fields ({'; '.join(details)})")
