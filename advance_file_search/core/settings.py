"""Local JSON settings with validation and atomic writes.

Settings hold UI preferences and safety limits only.  Document content, search
queries and snippets are never written here.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.i18n import AVAILABLE_LANGUAGES, LANG_THAI

_VALID_LANGUAGES = {code for code, _ in AVAILABLE_LANGUAGES}
_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_MAX_RECENT_ROOTS = 12


@dataclass(slots=True)
class AppSettings:
    """User-adjustable preferences.  Every field has a safe default."""

    language: str = LANG_THAI
    last_root: str = ""
    recent_roots: list[str] = field(default_factory=list)

    # Indexing
    max_file_size_mb: int = C.DEFAULT_MAX_FILE_SIZE_MB
    include_hidden_files: bool = False
    enable_optional_formats: bool = False
    index_docx_headers: bool = True

    # Search
    result_limit: int = C.DEFAULT_RESULT_LIMIT
    max_snippets_per_file: int = C.MAX_SNIPPETS_PER_FILE
    default_scope: str = "both"
    remember_filters: bool = False

    # Privacy / logging
    log_file_paths: bool = True
    log_level: str = C.DEFAULT_LOG_LEVEL

    # Window geometry (base64 Qt state); not privacy sensitive.
    window_geometry: str = ""
    window_state: str = ""
    column_widths: list[int] = field(default_factory=list)

    # --- derived ---------------------------------------------------------
    @property
    def max_file_size_bytes(self) -> int:
        return int(self.max_file_size_mb) * 1024 * 1024

    @property
    def active_extensions(self) -> frozenset[str]:
        if self.enable_optional_formats:
            return C.SUPPORTED_EXTENSIONS
        return C.CORE_EXTENSIONS

    # --- validation ------------------------------------------------------
    def normalize(self) -> AppSettings:
        """Clamp every field into its valid range.  Never raises."""
        if self.language not in _VALID_LANGUAGES:
            self.language = LANG_THAI
        self.max_file_size_mb = _clamp_int(
            self.max_file_size_mb, 1, C.MAX_FILE_SIZE_LIMIT_MB, C.DEFAULT_MAX_FILE_SIZE_MB
        )
        self.result_limit = _clamp_int(
            self.result_limit, 10, C.MAX_RESULT_LIMIT, C.DEFAULT_RESULT_LIMIT
        )
        self.max_snippets_per_file = _clamp_int(
            self.max_snippets_per_file, 1, 100, C.MAX_SNIPPETS_PER_FILE
        )
        if self.default_scope not in ("both", "name", "content"):
            self.default_scope = "both"
        level = str(self.log_level or "").upper()
        self.log_level = level if level in _VALID_LOG_LEVELS else C.DEFAULT_LOG_LEVEL
        self.include_hidden_files = bool(self.include_hidden_files)
        self.enable_optional_formats = bool(self.enable_optional_formats)
        self.index_docx_headers = bool(self.index_docx_headers)
        self.log_file_paths = bool(self.log_file_paths)
        self.remember_filters = bool(self.remember_filters)

        self.last_root = pathutil.display_path(self.last_root) if self.last_root else ""
        cleaned: list[str] = []
        seen: set[str] = set()
        for entry in self.recent_roots or []:
            shown = pathutil.display_path(str(entry))
            norm = pathutil.normalized_path(shown)
            if not shown or norm in seen:
                continue
            seen.add(norm)
            cleaned.append(shown)
            if len(cleaned) >= _MAX_RECENT_ROOTS:
                break
        self.recent_roots = cleaned

        self.window_geometry = _safe_b64(self.window_geometry)
        self.window_state = _safe_b64(self.window_state)
        self.column_widths = [
            _clamp_int(w, 0, 5000, 0) for w in (self.column_widths or [])[:16]
        ]
        return self

    # --- recent roots ----------------------------------------------------
    def remember_root(self, display: str) -> None:
        shown = pathutil.display_path(display)
        if not shown:
            return
        norm = pathutil.normalized_path(shown)
        self.recent_roots = [
            entry
            for entry in self.recent_roots
            if pathutil.normalized_path(entry) != norm
        ]
        self.recent_roots.insert(0, shown)
        del self.recent_roots[_MAX_RECENT_ROOTS:]
        self.last_root = shown

    def forget_root(self, display: str) -> None:
        norm = pathutil.normalized_path(display)
        self.recent_roots = [
            entry
            for entry in self.recent_roots
            if pathutil.normalized_path(entry) != norm
        ]
        if pathutil.normalized_path(self.last_root) == norm:
            self.last_root = self.recent_roots[0] if self.recent_roots else ""


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _safe_b64(value: Any) -> str:
    """Keep only plausible base64 text; anything else is discarded."""
    text = str(value or "")
    if len(text) > 64_000:
        return ""
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    return text if all(ch in allowed for ch in text) else ""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
_FIELD_NAMES = {f.name for f in fields(AppSettings)}


def load_settings(path: Path | None = None) -> AppSettings:
    """Read settings from disk.

    A missing, unreadable or malformed file yields defaults rather than an
    error: search must always be usable.
    """
    target = path or pathutil.settings_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return AppSettings().normalize()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return AppSettings().normalize()
    if not isinstance(data, dict):
        return AppSettings().normalize()
    known = {key: value for key, value in data.items() if key in _FIELD_NAMES}
    try:
        settings = AppSettings(**known)
    except TypeError:
        settings = AppSettings()
    return settings.normalize()


def save_settings(settings: AppSettings, path: Path | None = None) -> bool:
    """Atomically write settings.  Returns False on failure (never raises)."""
    target = path or pathutil.settings_path()
    settings.normalize()
    payload = json.dumps(asdict(settings), ensure_ascii=False, indent=2, sort_keys=True)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - the handle is closed by the caller after an atomic replace
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=".settings-",
            suffix=".tmp",
            delete=False,
        )
        tmp_name = handle.name
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(tmp_name, target)
        return True
    except OSError:
        return False
