"""Application-wide constants and safety limits.

Every tunable limit lives here (or in settings) rather than being scattered as
magic numbers through the codebase.  See docs/decisions/ for rationale.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
APP_NAME: Final[str] = "Advance File Search"
APP_SLUG: Final[str] = "AdvanceFileSearch"
APP_VERSION: Final[str] = "1.0.0"
APP_ORG: Final[str] = "Advance File Search"

#: Bumped whenever a parser changes in a way that requires re-extraction.
PARSER_VERSION: Final[int] = 1

#: Database schema version implemented by storage/migrations.py.
SCHEMA_VERSION: Final[int] = 1

# ---------------------------------------------------------------------------
# Supported file types
# ---------------------------------------------------------------------------
#: Required MVP formats.  Matching is always case-insensitive.
CORE_EXTENSIONS: Final[frozenset[str]] = frozenset({".pdf", ".docx", ".xlsx", ".txt"})

#: Low-risk optional plain-text formats, opt-in via settings.
OPTIONAL_TEXT_EXTENSIONS: Final[frozenset[str]] = frozenset({".md", ".csv", ".log"})

SUPPORTED_EXTENSIONS: Final[frozenset[str]] = CORE_EXTENSIONS | OPTIONAL_TEXT_EXTENSIONS

#: Never processed, regardless of settings.  Defence in depth: the indexer does
#: not execute anything, but we also refuse to even read these.
EXECUTABLE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".exe", ".dll", ".sys", ".msi", ".com", ".scr", ".cpl", ".ocx", ".drv",
        ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf",
        ".wsh", ".hta", ".jar", ".msc", ".pif", ".reg", ".lnk", ".url", ".scf",
        ".docm", ".xlsm", ".xltm", ".dotm", ".pptm",
    }
)

# ---------------------------------------------------------------------------
# Scanning exclusions
# ---------------------------------------------------------------------------
#: Directory names skipped anywhere in the tree (case-insensitive compare).
EXCLUDED_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {
        "$recycle.bin",
        "system volume information",
        "$windows.~bt",
        "$windows.~ws",
        "recovery",
        "config.msi",
        "node_modules",
        "__pycache__",
        ".git",
        ".svn",
        ".hg",
    }
)

#: Top-level directory names skipped when the selected root is a drive root.
EXCLUDED_DRIVE_ROOT_DIRS: Final[frozenset[str]] = frozenset(
    {
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "perflogs",
        "msocache",
        "$recycle.bin",
        "system volume information",
    }
)

#: File-name prefixes that mark transient Office lock files.
TEMP_FILE_PREFIXES: Final[tuple[str, ...]] = ("~$", ".~lock.")

# ---------------------------------------------------------------------------
# Safety limits (section 16 of the handoff)
# ---------------------------------------------------------------------------
MAX_QUERY_LENGTH: Final[int] = 500
MAX_QUERY_TERMS: Final[int] = 24
MAX_WILDCARDS_PER_TERM: Final[int] = 6
DEFAULT_RESULT_LIMIT: Final[int] = 200
MAX_RESULT_LIMIT: Final[int] = 5000
MAX_SNIPPETS_PER_FILE: Final[int] = 10
MAX_SNIPPET_LENGTH: Final[int] = 500
SNIPPET_CONTEXT_CHARS: Final[int] = 130
MAX_LOGGED_MESSAGE_LENGTH: Final[int] = 1000

#: Default maximum size of a file we will attempt to parse.
DEFAULT_MAX_FILE_SIZE_MB: Final[int] = 500
#: Hard ceiling for the configurable value above.
MAX_FILE_SIZE_LIMIT_MB: Final[int] = 4096

#: Per-format extracted-unit text caps.
MAX_UNIT_TEXT_LENGTH: Final[int] = 200_000
MAX_CELL_TEXT_LENGTH: Final[int] = 100_000
MAX_TXT_LINE_LENGTH: Final[int] = 100_000
MAX_PDF_PAGES: Final[int] = 20_000
MAX_DOCX_UNITS: Final[int] = 200_000
MAX_XLSX_CELLS: Final[int] = 500_000
MAX_TXT_LINES: Final[int] = 2_000_000

#: Total extracted characters accepted from a single document.
MAX_DOCUMENT_TEXT_CHARS: Final[int] = 40_000_000

#: TXT lines are grouped into blocks of this many lines for indexing, keeping
#: the FTS row count sane while preserving the first line number of the block.
TXT_LINES_PER_BLOCK: Final[int] = 1

# ---------------------------------------------------------------------------
# Indexing behaviour
# ---------------------------------------------------------------------------
#: Files committed per transaction batch.
INDEX_COMMIT_BATCH_SIZE: Final[int] = 25
#: Content units buffered before flushing to SQLite for one file.
UNIT_INSERT_CHUNK: Final[int] = 500
#: Progress signal throttle, in milliseconds.
PROGRESS_EMIT_INTERVAL_MS: Final[int] = 120

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE_NAME: Final[str] = "application.log"
LOG_MAX_BYTES: Final[int] = 5 * 1024 * 1024
LOG_BACKUP_COUNT: Final[int] = 3
DEFAULT_LOG_LEVEL: Final[str] = "INFO"

# ---------------------------------------------------------------------------
# Content status values stored in files.content_status
# ---------------------------------------------------------------------------
STATUS_INDEXED: Final[str] = "indexed"
STATUS_NO_TEXT: Final[str] = "no_text"
STATUS_SKIPPED: Final[str] = "skipped"
STATUS_FAILED: Final[str] = "failed"
STATUS_STALE: Final[str] = "stale"

# ---------------------------------------------------------------------------
# Location types stored in content_units.location_type
# ---------------------------------------------------------------------------
LOC_PAGE: Final[str] = "page"
LOC_PARAGRAPH: Final[str] = "paragraph"
LOC_TABLE_CELL: Final[str] = "table_cell"
LOC_SHEET_CELL: Final[str] = "sheet_cell"
LOC_LINE: Final[str] = "line"
LOC_HEADER: Final[str] = "header"
LOC_FOOTER: Final[str] = "footer"

# ---------------------------------------------------------------------------
# Error codes surfaced to the UI (mapped to localized messages in core.i18n)
# ---------------------------------------------------------------------------
ERR_NO_TEXT: Final[str] = "no_text"
ERR_PASSWORD_PROTECTED: Final[str] = "password_protected"  # noqa: S105 - an error code, not a secret
ERR_ACCESS_DENIED: Final[str] = "access_denied"
ERR_FILE_MISSING: Final[str] = "file_missing"
ERR_TOO_LARGE: Final[str] = "too_large"
ERR_CORRUPT: Final[str] = "corrupt"
ERR_UNSUPPORTED: Final[str] = "unsupported"
ERR_ENCODING: Final[str] = "encoding_warning"
ERR_DISK_FULL: Final[str] = "disk_full"
ERR_NETWORK_PATH: Final[str] = "network_path"
ERR_LIMIT: Final[str] = "limit_exceeded"
ERR_UNKNOWN: Final[str] = "unknown"
