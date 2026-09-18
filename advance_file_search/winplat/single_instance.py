"""Single-instance guard.

Two SQLite writers must never touch the same index concurrently, so only one
instance per user is allowed.  The lock is a file in the application data
directory held open with an exclusive OS-level lock: unlike a PID file it is
released automatically if the process crashes, so a stale lock cannot leave the
application permanently unstartable.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from advance_file_search.core import paths as pathutil
from advance_file_search.logging_setup import get_logger

log = get_logger("winplat.single_instance")

LOCK_FILE_NAME = "instance.lock"

#: Bytes locked at offset 0.  Both instances must lock the *same* region for
#: the second one to be refused.
LOCK_REGION_SIZE = 1


class SingleInstance:
    """Acquires an exclusive lock for the lifetime of the process."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (pathutil.app_data_dir() / LOCK_FILE_NAME)
        self._handle: object | None = None
        self.acquired = False

    def acquire(self) -> bool:
        """Try to become the only running instance."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # If we cannot even create the directory, do not block startup.
            log.warning("instance lock unavailable | %s", exc)
            self.acquired = True
            return True

        try:
            handle = open(self.path, "a+b")  # noqa: SIM115 - the lock file stays open for the lifetime of the process
        except OSError as exc:
            log.warning("instance lock unavailable | %s", exc)
            self.acquired = True
            return True

        if not self._lock(handle):
            with contextlib.suppress(OSError):
                handle.close()
            self.acquired = False
            return False

        try:
            # Diagnostics are written *after* the locked byte.  Writing over
            # byte 0 would move the file position, and on Windows the lock is
            # tied to the region at the position it was taken from.
            handle.seek(LOCK_REGION_SIZE)
            handle.truncate(LOCK_REGION_SIZE)
            handle.write(str(os.getpid()).encode("ascii"))
            handle.flush()
        except OSError:
            pass

        self._handle = handle
        self.acquired = True
        return True

    def _lock(self, handle: object) -> bool:
        """Take an exclusive OS lock on the first byte of the file.

        ``msvcrt.locking`` locks a region starting at the *current* file
        position, and the file is opened in append mode, so the position must
        be reset to 0 first — otherwise two processes lock different regions
        and both believe they are the only instance.
        """
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)  # type: ignore[attr-defined]
                msvcrt.locking(  # type: ignore[attr-defined]
                    handle.fileno(), msvcrt.LK_NBLCK, LOCK_REGION_SIZE
                )
            else:  # pragma: no cover - development convenience
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False
        except ImportError:  # pragma: no cover
            return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)  # type: ignore[attr-defined]
                msvcrt.locking(  # type: ignore[attr-defined]
                    handle.fileno(), msvcrt.LK_UNLCK, LOCK_REGION_SIZE
                )
            else:  # pragma: no cover
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        except (OSError, ImportError):
            pass
        try:  # noqa: SIM105 - releasing the lock must never raise
            handle.close()  # type: ignore[attr-defined]
        except OSError:
            pass

    def __enter__(self) -> SingleInstance:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
