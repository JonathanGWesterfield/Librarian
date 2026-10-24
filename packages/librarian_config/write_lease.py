"""Process-wide lease for coordinated writes to user-owned Librarian config.

The lease file is deliberately beside ``config/`` rather than within it: a
cutover atomically replaces the config directory, while the lease must remain
the same inode for every cooperating writer throughout that replacement.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":  # pragma: no cover - exercised by the PowerShell launcher.
    import msvcrt
else:
    import fcntl

CONFIG_WRITE_LEASE_FILENAME = ".librarian-config-write.lock"


class ConfigurationWriteLeaseError(RuntimeError):
    """Raised when a cutover or another writer owns the configuration lease."""


@dataclass
class ConfigurationWriteLease:
    """An exclusive advisory lease retained until ``release`` is called."""

    path: Path
    _descriptor: int
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        try:
            if sys.platform == "win32":  # pragma: no cover - Windows only.
                os.lseek(self._descriptor, 0, os.SEEK_SET)
                msvcrt.locking(self._descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self._descriptor)
            self._released = True

    def __enter__(self) -> "ConfigurationWriteLease":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def acquire_configuration_write_lease(repository_root: Path) -> ConfigurationWriteLease:
    """Acquire the non-blocking lease required before changing ``config/``.

    Every Librarian script that writes the user-owned configuration uses this
    primitive.  A failed acquisition is intentional: waiting for a destructive
    cutover could make an operator mistake look like a completed configuration
    edit.
    """

    root = repository_root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise ConfigurationWriteLeaseError("configuration lease root is unavailable")
    path = root / CONFIG_WRITE_LEASE_FILENAME
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        if sys.platform == "win32":  # pragma: no cover - Windows only.
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        raise ConfigurationWriteLeaseError(
            "Librarian configuration is locked by an active cutover or configuration writer"
        ) from error
    return ConfigurationWriteLease(path=path, _descriptor=descriptor)
