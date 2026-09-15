"""Rotating file logging with privacy guards.

Two guarantees are enforced here rather than relying on call-site discipline:

1. Every record is flattened to a single sanitized line (no newlines, no
   control characters, length-capped), so document text cannot smuggle
   structure into the log.
2. Exception tracebacks are **never** written, because a parser traceback can
   carry a fragment of the document that failed.  The sanitized exception type
   and message are logged instead.

Search queries and snippets are never passed to the logger by any caller; the
:class:`PrivacyFilter` additionally drops any record explicitly marked with
``extra={"sensitive": True}``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.security import sanitize_for_log

_LOGGER_NAME = "advance_file_search"
_configured = False
_log_paths_enabled = True


class SizeRotatingFileHandler(logging.FileHandler):
    """A size-based rotating file handler with no networking dependency.

    ``logging.handlers.RotatingFileHandler`` would be the obvious choice, but
    importing ``logging.handlers`` pulls in ``socket`` and ``pickle`` at module
    level — it defines ``SocketHandler`` and ``SysLogHandler``.  That single
    import is what forces the packaged application to ship ``_socket.pyd`` and
    the OpenSSL libraries, which undermines the central claim that this program
    cannot reach the network.  Reimplementing the one behaviour actually needed
    is a few dozen lines and lets the build ship with no socket binary at all.

    Rotation renames ``application.log`` to ``application.log.1``, shifting any
    existing backups up and discarding the oldest.  Every filesystem failure is
    swallowed: logging must never take the application down.
    """

    def __init__(
        self,
        filename: str | os.PathLike[str],
        *,
        max_bytes: int = C.LOG_MAX_BYTES,
        backup_count: int = C.LOG_BACKUP_COUNT,
        encoding: str = "utf-8",
        delay: bool = True,
    ) -> None:
        super().__init__(filename, mode="a", encoding=encoding, delay=delay)
        self.max_bytes = max(0, int(max_bytes))
        self.backup_count = max(0, int(backup_count))

    # -- rotation ---------------------------------------------------------
    def _should_rotate(self, record_text: str) -> bool:
        if self.max_bytes <= 0:
            return False
        try:
            if self.stream is None:
                return os.path.getsize(self.baseFilename) + len(record_text) > self.max_bytes
            self.stream.seek(0, os.SEEK_END)
            return self.stream.tell() + len(record_text) > self.max_bytes
        except (OSError, ValueError):
            return False

    def _rotate(self) -> None:
        try:
            if self.stream is not None:
                self.stream.close()
                self.stream = None  # type: ignore[assignment]
        except (OSError, ValueError):
            self.stream = None  # type: ignore[assignment]

        if self.backup_count <= 0:
            try:
                os.remove(self.baseFilename)
            except OSError:
                pass
            return

        try:
            oldest = f"{self.baseFilename}.{self.backup_count}"
            if os.path.exists(oldest):
                os.remove(oldest)
            for index in range(self.backup_count - 1, 0, -1):
                source = f"{self.baseFilename}.{index}"
                target = f"{self.baseFilename}.{index + 1}"
                if os.path.exists(source):
                    if os.path.exists(target):
                        os.remove(target)
                    os.replace(source, target)
            if os.path.exists(self.baseFilename):
                first = f"{self.baseFilename}.1"
                if os.path.exists(first):
                    os.remove(first)
                os.replace(self.baseFilename, first)
        except OSError:
            # A locked or vanished file must not stop the application.
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record) + self.terminator
            if self._should_rotate(text):
                self._rotate()
            if self.stream is None:
                self.stream = self._open()
            self.stream.write(text)
            self.flush()
        except Exception:  # noqa: BLE001 - logging must never raise
            self.handleError(record)


class PrivacyFilter(logging.Filter):
    """Sanitize every record and strip traceback/content leakage."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "sensitive", False):
            return False
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - broken format args
            message = str(record.msg)
        record.msg = sanitize_for_log(message)
        record.args = ()
        # Never emit tracebacks: they may embed document content.
        if record.exc_info:
            exc = record.exc_info[1]
            if exc is not None:
                record.msg = sanitize_for_log(
                    f"{record.msg} | {type(exc).__name__}: {exc}"
                )
            record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class _PathRedactingFilter(logging.Filter):
    """Replace ``path=...`` fields when path logging is disabled."""

    def filter(self, record: logging.LogRecord) -> bool:
        if _log_paths_enabled:
            return True
        text = str(record.msg)
        if "path=" in text:
            parts = []
            for chunk in text.split("|"):
                stripped = chunk.strip()
                if stripped.startswith("path="):
                    parts.append(" path=<redacted>")
                else:
                    parts.append(chunk)
            record.msg = "|".join(parts)
        record.msg = str(record.msg)
        return True


def configure_logging(
    *,
    level: str = C.DEFAULT_LOG_LEVEL,
    log_paths: bool = True,
    directory: Path | None = None,
    console: bool | None = None,
    replace: bool = False,
) -> logging.Logger:
    """Install the application log handlers.

    Safe to call more than once: a repeat call only updates the level unless
    ``replace`` is set, which tears the existing handlers down first.  The
    application calls it once at startup; ``replace`` exists for tests and for
    a future "change log location" setting.
    """
    global _configured, _log_paths_enabled
    _log_paths_enabled = bool(log_paths)

    logger = logging.getLogger(_LOGGER_NAME)
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    logger.setLevel(numeric)
    logger.propagate = False

    if replace:
        for handler in list(logger.handlers):
            try:
                handler.close()
            except Exception:  # noqa: BLE001 - shutting a handler must not raise
                pass
            logger.removeHandler(handler)
        _configured = False

    if _configured:
        for handler in logger.handlers:
            handler.setLevel(numeric)
        return logger

    target_dir = directory or pathutil.logs_dir()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | v" + C.APP_VERSION + " | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    privacy = PrivacyFilter()
    redact = _PathRedactingFilter()

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_handler = SizeRotatingFileHandler(
            target_dir / C.LOG_FILE_NAME,
            max_bytes=C.LOG_MAX_BYTES,
            backup_count=C.LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(privacy)
        file_handler.addFilter(redact)
        file_handler.setLevel(numeric)
        logger.addHandler(file_handler)
    except OSError:
        # Logging must never prevent the application from starting.
        pass

    want_console = console
    if want_console is None:
        want_console = bool(os.environ.get("ADVANCE_FILE_SEARCH_DEBUG"))
    if want_console:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream.addFilter(privacy)
        stream.addFilter(redact)
        stream.setLevel(numeric)
        logger.addHandler(stream)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    _configured = True
    return logger


def get_logger(name: str = "") -> logging.Logger:
    """Return a child logger under the application namespace."""
    if not name:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def set_log_paths_enabled(enabled: bool) -> None:
    global _log_paths_enabled
    _log_paths_enabled = bool(enabled)


def log_paths_enabled() -> bool:
    return _log_paths_enabled


def safe_path_field(path: str) -> str:
    """Format a path for logging, honouring the path-logging setting."""
    if not _log_paths_enabled:
        return "path=<redacted>"
    return f"path={sanitize_for_log(path, limit=400)}"


def clear_logs(directory: Path | None = None) -> int:
    """Delete rotated log files.  Returns the number removed."""
    target_dir = directory or pathutil.logs_dir()
    removed = 0
    logger = logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        if isinstance(handler, SizeRotatingFileHandler):
            try:
                handler.close()
            except Exception:  # pragma: no cover
                pass
    try:
        for entry in target_dir.glob(C.LOG_FILE_NAME + "*"):
            try:
                entry.unlink()
                removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    return removed
