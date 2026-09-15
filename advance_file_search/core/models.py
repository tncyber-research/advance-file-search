"""Plain data models shared between the indexing, storage, search and UI layers.

These are deliberately dependency-free dataclasses: no Qt, no SQLite, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ContentUnit:
    """One searchable fragment of a document with its source location.

    ``location_label`` is a language-neutral canonical label (e.g.
    ``"Page 12"``); the UI renders a localized label from ``location_type``
    plus ``location_data`` instead of parsing this string.
    """

    sequence: int
    location_type: str
    location_label: str
    location_data: dict[str, Any]
    text: str


@dataclass(slots=True)
class DocumentMetadata:
    """Parser-reported facts about a document (never its content)."""

    extension: str
    unit_count: int = 0
    char_count: int = 0
    page_count: int | None = None
    sheet_count: int | None = None
    line_count: int | None = None
    encoding: str | None = None
    truncated: bool = False


@dataclass(slots=True)
class ParsedDocument:
    """Result of a successful extraction."""

    metadata: DocumentMetadata
    units: list[ContentUnit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return any(unit.text.strip() for unit in self.units)


class ParseOutcome(str, Enum):
    """Why extraction ended the way it did."""

    OK = "ok"
    NO_TEXT = "no_text"
    PASSWORD_PROTECTED = "password_protected"  # noqa: S105 - an outcome name, not a secret
    CORRUPT = "corrupt"
    ACCESS_DENIED = "access_denied"
    MISSING = "missing"
    TOO_LARGE = "too_large"
    UNSUPPORTED = "unsupported"
    LIMIT = "limit_exceeded"
    ERROR = "error"


@dataclass(slots=True)
class ParseResult:
    """Uniform return type for every parser; never raises to the caller."""

    outcome: ParseOutcome
    document: ParsedDocument | None = None
    error_code: str = ""
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome is ParseOutcome.OK

    def iter_units(self) -> Iterator[ContentUnit]:
        if self.document is None:
            return iter(())
        return iter(self.document.units)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
class SkipReason(str, Enum):
    NOT_SUPPORTED = "not_supported"
    EXECUTABLE = "executable"
    TEMP_FILE = "temp_file"
    HIDDEN = "hidden"
    SYSTEM = "system"
    REPARSE_POINT = "reparse_point"
    CLOUD_PLACEHOLDER = "cloud_placeholder"
    TOO_LARGE = "too_large"
    EXCLUDED_DIR = "excluded_dir"
    APP_DATA = "app_data"
    OUTSIDE_ROOT = "outside_root"
    ACCESS_DENIED = "access_denied"
    VANISHED = "vanished"
    EMPTY = "empty_file"


@dataclass(slots=True)
class ScannedFile:
    """A candidate file discovered by the scanner."""

    display_path: str
    normalized_path: str
    relative_path: str
    file_name: str
    extension: str
    size_bytes: int
    created_time: float | None
    modified_time: float


@dataclass(slots=True)
class ScanSkip:
    display_path: str
    reason: SkipReason


# ---------------------------------------------------------------------------
# Index runs
# ---------------------------------------------------------------------------
class IndexPhase(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    SCANNING = "scanning"
    EXTRACTING = "extracting"
    REMOVING_DELETED = "removing_deleted"
    FINALIZING = "finalizing"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True)
class IndexProgress:
    """Snapshot pushed from the indexing worker to the UI.

    ``current_item`` is a *relative* path so that a privacy-conscious user
    never sees a full path outside the selected root, and it is never logged.
    """

    phase: IndexPhase = IndexPhase.IDLE
    current_item: str = ""
    discovered: int = 0
    processed: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    no_text: int = 0
    deleted: int = 0
    unchanged: int = 0
    warnings: int = 0
    elapsed_seconds: float = 0.0

    @property
    def total(self) -> int:
        return self.discovered

    @property
    def determinate(self) -> bool:
        return self.discovered > 0 and self.phase in (
            IndexPhase.EXTRACTING,
            IndexPhase.REMOVING_DELETED,
            IndexPhase.FINALIZING,
        )


@dataclass(slots=True)
class IndexError:
    """A per-file failure summarized for the UI error panel."""

    relative_path: str
    error_code: str
    message: str


@dataclass(slots=True)
class IndexSummary:
    run_id: int
    root_id: int
    status: RunStatus
    discovered: int = 0
    processed: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    no_text: int = 0
    deleted: int = 0
    unchanged: int = 0
    elapsed_seconds: float = 0.0
    errors: list[IndexError] = field(default_factory=list)
    skip_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Root:
    id: int
    display_path: str
    normalized_path: str
    created_at: str
    last_index_started_at: str | None = None
    last_index_completed_at: str | None = None
    last_index_status: str | None = None
    file_count: int = 0
    available: bool = True

    @property
    def label(self) -> str:
        return self.display_path


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
class SearchScope(str, Enum):
    BOTH = "both"
    NAME_ONLY = "name"
    CONTENT_ONLY = "content"


class SortField(str, Enum):
    RELEVANCE = "relevance"
    NAME = "name"
    TYPE = "type"
    SIZE = "size"
    MODIFIED = "modified"
    PATH = "path"


class MatchSource(str, Enum):
    NAME = "name"
    CONTENT = "content"
    BOTH = "both"


@dataclass(slots=True)
class SearchFilters:
    extensions: frozenset[str] = frozenset()
    modified_after: float | None = None
    modified_before: float | None = None
    min_size_bytes: int | None = None
    max_size_bytes: int | None = None
    subfolder: str = ""

    @property
    def active(self) -> bool:
        return bool(
            self.extensions
            or self.modified_after is not None
            or self.modified_before is not None
            or self.min_size_bytes is not None
            or self.max_size_bytes is not None
            or self.subfolder
        )


@dataclass(slots=True)
class SearchRequest:
    query: str
    root_id: int
    scope: SearchScope = SearchScope.BOTH
    match_case: bool = False
    exact_phrase: bool = False
    whole_word: bool = False
    filters: SearchFilters = field(default_factory=SearchFilters)
    sort_field: SortField = SortField.RELEVANCE
    sort_descending: bool = True
    limit: int = 200
    offset: int = 0


@dataclass(slots=True)
class Highlight:
    """A [start, end) range within a snippet's plain text."""

    start: int
    end: int


@dataclass(slots=True)
class MatchLocation:
    """One matching location inside a file."""

    unit_id: int
    sequence: int
    location_type: str
    location_label: str
    location_data: dict[str, Any]
    snippet: str
    highlights: list[Highlight] = field(default_factory=list)


@dataclass(slots=True)
class SearchResult:
    file_id: int
    root_id: int
    display_path: str
    relative_path: str
    file_name: str
    extension: str
    size_bytes: int
    created_time: float | None
    modified_time: float | None
    content_status: str
    match_source: MatchSource
    score: float
    match_count: int
    name_highlights: list[Highlight] = field(default_factory=list)
    locations: list[MatchLocation] = field(default_factory=list)
    exists: bool = True
    warning: str = ""

    @property
    def best_location(self) -> MatchLocation | None:
        return self.locations[0] if self.locations else None


@dataclass(slots=True)
class SearchResponse:
    results: list[SearchResult] = field(default_factory=list)
    total_matched_files: int = 0
    truncated: bool = False
    elapsed_ms: float = 0.0
    query_warnings: list[str] = field(default_factory=list)
    cancelled: bool = False

    def __iter__(self) -> Iterator[SearchResult]:
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def extend(self, more: Iterable[SearchResult]) -> None:
        self.results.extend(more)
