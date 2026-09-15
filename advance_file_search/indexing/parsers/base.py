"""Parser contract and shared helpers.

Every indexed document is untrusted input.  Parsers therefore:

* never execute macros, scripts or embedded actions;
* never resolve hyperlinks, external workbook links or remote templates;
* never extract embedded files;
* return a :class:`ParseResult` instead of raising, so one bad document cannot
  abort an indexing run;
* enforce per-format unit and character caps from ``core.constants``.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from advance_file_search.core import constants as C
from advance_file_search.core.models import (
    ContentUnit,
    DocumentMetadata,
    ParsedDocument,
    ParseOutcome,
    ParseResult,
)
from advance_file_search.core.paths import safe_path
from advance_file_search.core.security import sanitize_exception

#: Characters that carry no search value but bloat the index.
_WS_RUN = re.compile(r"[ \t ​﻿]{2,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
#: Unicode line/paragraph separators normalized to "\n".
_LINE_SEPS = re.compile(r"[  \v\f\r]")
#: Invisible formatting marks removed from indexed text.
_ZERO_WIDTH = {
    ord(ch): None
    for ch in ("﻿", "​", "‌", "‍", "⁠", "­")
}


@dataclass(frozen=True)
class ParseOptions:
    """Per-run parser tuning derived from user settings."""

    max_file_size_bytes: int = C.DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024
    include_docx_headers: bool = True
    max_unit_text_length: int = C.MAX_UNIT_TEXT_LENGTH


def clean_text(raw: str | None, *, limit: int = C.MAX_UNIT_TEXT_LENGTH) -> str:
    """Normalize extracted text for indexing.

    Strips control characters (which would corrupt display and FTS tokenizing)
    and collapses whitespace runs, while leaving every printable character —
    including the full Thai range and combining marks — untouched.  Truncation
    is done on a character boundary; Python strings are code points, so a
    surrogate pair can never be split here.
    """
    if not raw:
        return ""
    text = _LINE_SEPS.sub("\n", str(raw))
    text = _CONTROL.sub(" ", text)
    # Zero-width marks are invisible but break substring matching, so they are
    # dropped rather than preserved.  Thai combining marks are NOT in this set.
    text = text.translate(_ZERO_WIDTH)
    text = _WS_RUN.sub(" ", text)
    text = text.strip()
    if limit > 0 and len(text) > limit:
        text = text[:limit].rstrip()
    return text


def excel_column_name(index: int) -> str:
    """1-based column index -> Excel column letters ("A", "AA", ...)."""
    if index < 1:
        return ""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


class DocumentParser(ABC):
    """Base class for format-specific extractors."""

    #: Lowercased extensions (with dot) this parser handles.
    supported_extensions: frozenset[str] = frozenset()
    #: Human-readable name used in decision records and diagnostics.
    name: str = "parser"

    def __init__(self, options: ParseOptions | None = None) -> None:
        self.options = options or ParseOptions()

    # -- public entry point ----------------------------------------------
    def parse(self, file_path: str | Path) -> ParseResult:
        """Extract a document, converting every failure into a result.

        This is the only method the indexer calls.  It guarantees no exception
        escapes, so a corrupt or hostile document can never stop a run.

        The path is converted to the extended-length form first: without it a
        document more than 260 characters deep fails to open and would be
        reported as missing rather than indexed.
        """
        path = safe_path(file_path)
        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            return ParseResult(
                ParseOutcome.MISSING, error_code=C.ERR_FILE_MISSING, error_message="missing"
            )
        except PermissionError:
            return ParseResult(
                ParseOutcome.ACCESS_DENIED,
                error_code=C.ERR_ACCESS_DENIED,
                error_message="access denied",
            )
        except OSError as exc:
            return ParseResult(
                ParseOutcome.ERROR,
                error_code=C.ERR_UNKNOWN,
                error_message=sanitize_exception(exc),
            )

        if self.options.max_file_size_bytes and size > self.options.max_file_size_bytes:
            return ParseResult(
                ParseOutcome.TOO_LARGE, error_code=C.ERR_TOO_LARGE, error_message="too large"
            )
        if size == 0:
            return ParseResult(
                ParseOutcome.NO_TEXT, error_code=C.ERR_NO_TEXT, error_message="empty file"
            )

        try:
            return self._parse(path, size)
        except MemoryError:
            return ParseResult(
                ParseOutcome.LIMIT,
                error_code=C.ERR_LIMIT,
                error_message="document exceeded available memory",
            )
        except (FileNotFoundError, NotADirectoryError):
            return ParseResult(
                ParseOutcome.MISSING, error_code=C.ERR_FILE_MISSING, error_message="missing"
            )
        except PermissionError:
            return ParseResult(
                ParseOutcome.ACCESS_DENIED,
                error_code=C.ERR_ACCESS_DENIED,
                error_message="access denied",
            )
        except OSError as exc:
            return ParseResult(
                ParseOutcome.ERROR,
                error_code=C.ERR_UNKNOWN,
                error_message=sanitize_exception(exc),
            )
        except Exception as exc:  # noqa: BLE001 - untrusted input, must not escape
            return ParseResult(
                ParseOutcome.CORRUPT,
                error_code=C.ERR_CORRUPT,
                error_message=sanitize_exception(exc),
            )

    # -- subclass hook ----------------------------------------------------
    @abstractmethod
    def _parse(self, path: Path, size_bytes: int) -> ParseResult:
        """Extract units.  May raise; :meth:`parse` converts to a result."""

    # -- helpers for subclasses ------------------------------------------
    def _finish(
        self,
        units: list[ContentUnit],
        metadata: DocumentMetadata,
        warnings: list[str],
    ) -> ParseResult:
        """Package units into a result, reporting ``no_text`` when empty."""
        metadata.unit_count = len(units)
        metadata.char_count = sum(len(unit.text) for unit in units)
        document = ParsedDocument(metadata=metadata, units=units, warnings=list(warnings))
        if not units:
            return ParseResult(
                ParseOutcome.NO_TEXT,
                document=document,
                error_code=C.ERR_NO_TEXT,
                error_message="no extractable text",
                warnings=list(warnings),
            )
        return ParseResult(ParseOutcome.OK, document=document, warnings=list(warnings))


class ParserRegistry:
    """Maps an extension to the parser that handles it."""

    def __init__(self, parsers: Iterable[DocumentParser]) -> None:
        self._by_extension: dict[str, DocumentParser] = {}
        for parser in parsers:
            for extension in parser.supported_extensions:
                self._by_extension[extension.casefold()] = parser

    def get(self, extension: str) -> DocumentParser | None:
        return self._by_extension.get(extension.casefold())

    def supported(self) -> frozenset[str]:
        return frozenset(self._by_extension)

    def __iter__(self) -> Iterator[DocumentParser]:
        seen: set[int] = set()
        for parser in self._by_extension.values():
            if id(parser) not in seen:
                seen.add(id(parser))
                yield parser


def build_registry(options: ParseOptions | None = None) -> ParserRegistry:
    """Construct the default registry for the enabled formats."""
    from advance_file_search.indexing.parsers.docx_parser import DocxParser
    from advance_file_search.indexing.parsers.pdf_parser import PdfParser
    from advance_file_search.indexing.parsers.txt_parser import TxtParser
    from advance_file_search.indexing.parsers.xlsx_parser import XlsxParser

    opts = options or ParseOptions()
    return ParserRegistry(
        [TxtParser(opts), PdfParser(opts), DocxParser(opts), XlsxParser(opts)]
    )
