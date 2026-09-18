"""PDF text-layer extraction with PyMuPDF.

Strict MVP policy:

* **No OCR.**  A PDF with no text layer is reported as ``no_text``, which is a
  normal outcome and not an application error.
* Encrypted PDFs are reported as ``password_protected``.  We attempt only the
  empty owner password, which is what a normal reader does to open a file that
  is encrypted but not password-protected for viewing; no password guessing.
* Embedded JavaScript, launch/URI actions, annotations with actions, embedded
  files and multimedia are never executed, followed or extracted.
"""

from __future__ import annotations

from pathlib import Path

from advance_file_search.core import constants as C
from advance_file_search.core.models import (
    ContentUnit,
    DocumentMetadata,
    ParseOutcome,
    ParseResult,
)
from advance_file_search.core.security import sanitize_exception
from advance_file_search.indexing.parsers.base import DocumentParser, clean_text


class PdfParser(DocumentParser):
    """One content unit per page."""

    name = "pdf"
    supported_extensions = frozenset({".pdf"})

    def _parse(self, path: Path, size_bytes: int) -> ParseResult:
        try:
            import pymupdf  # type: ignore[import-not-found]
        except ImportError:  # pragma: no cover - packaging guard
            try:
                import fitz as pymupdf  # type: ignore[import-not-found, no-redef]
            except ImportError:
                return ParseResult(
                    ParseOutcome.ERROR,
                    error_code=C.ERR_UNKNOWN,
                    error_message="PDF support is not available in this build",
                )

        warnings: list[str] = []
        units: list[ContentUnit] = []
        truncated = False
        total_chars = 0
        page_count = 0

        document = None
        try:
            try:
                document = pymupdf.open(str(path))
            except Exception as exc:  # noqa: BLE001 - untrusted file
                message = str(exc).lower()
                if "password" in message or "encrypt" in message:
                    return ParseResult(
                        ParseOutcome.PASSWORD_PROTECTED,
                        error_code=C.ERR_PASSWORD_PROTECTED,
                        error_message="encrypted document",
                    )
                return ParseResult(
                    ParseOutcome.CORRUPT,
                    error_code=C.ERR_CORRUPT,
                    error_message=sanitize_exception(exc),
                )

            if getattr(document, "needs_pass", False):
                # Try only the empty password: an "encrypted but freely
                # viewable" PDF opens with it.  Anything else is treated as
                # password-protected; we never guess passwords.
                try:
                    unlocked = bool(document.authenticate(""))
                except Exception:  # noqa: BLE001
                    unlocked = False
                if not unlocked:
                    return ParseResult(
                        ParseOutcome.PASSWORD_PROTECTED,
                        error_code=C.ERR_PASSWORD_PROTECTED,
                        error_message="password protected",
                    )

            page_count = int(getattr(document, "page_count", 0) or 0)
            if page_count <= 0:
                return ParseResult(
                    ParseOutcome.NO_TEXT,
                    error_code=C.ERR_NO_TEXT,
                    error_message="document has no pages",
                )

            limit = min(page_count, C.MAX_PDF_PAGES)
            if limit < page_count:
                truncated = True

            page_labels = self._page_labels(document, limit)

            for index in range(limit):
                try:
                    page = document.load_page(index)
                    # "text" mode reads the existing text layer only: no
                    # rendering, no OCR, no annotation actions.
                    raw = page.get_text("text")
                except Exception as exc:  # noqa: BLE001 - per-page resilience
                    warnings.append(C.ERR_CORRUPT)
                    del exc
                    continue
                text = clean_text(raw, limit=self.options.max_unit_text_length)
                if not text:
                    continue
                number = index + 1
                data: dict[str, object] = {"page": number}
                label = page_labels.get(index)
                if label and label != str(number):
                    data["page_label"] = label
                units.append(
                    ContentUnit(
                        sequence=number,
                        location_type=C.LOC_PAGE,
                        location_label=f"Page {number}",
                        location_data=data,
                        text=text,
                    )
                )
                total_chars += len(text)
                if total_chars > C.MAX_DOCUMENT_TEXT_CHARS:
                    truncated = True
                    break
        finally:
            if document is not None:
                try:  # noqa: SIM105 - see below
                    document.close()
                # S110/SIM105: the page text is already extracted; a
                # failure to close must not turn a good parse into an error.
                except Exception:  # noqa: BLE001, S110, SIM105
                    pass

        if truncated:
            warnings.append(C.ERR_LIMIT)

        metadata = DocumentMetadata(
            extension=".pdf", page_count=page_count, truncated=truncated
        )
        result = self._finish(units, metadata, warnings)
        if result.outcome is ParseOutcome.NO_TEXT:
            # Distinguish "scanned / image-only" from a hard failure: this is
            # an expected state with a specific user-facing message.
            result.error_code = C.ERR_NO_TEXT
            result.error_message = "no text layer (possibly scanned)"
        return result

    @staticmethod
    def _page_labels(document: object, limit: int) -> dict[int, str]:
        """Read optional page labels ("i", "ii", "A-1") when present."""
        labels: dict[int, str] = {}
        getter = getattr(document, "get_page_labels", None)
        if getter is None:
            return labels
        try:
            entries = getter()
        except Exception:  # noqa: BLE001
            return labels
        if not entries:
            return labels
        for index in range(limit):
            try:
                page = document.load_page(index)  # type: ignore[attr-defined]
                label = getattr(page, "get_label", None)
                if callable(label):
                    value = label()
                    if value:
                        labels[index] = str(value)[:32]
            except Exception:  # noqa: BLE001
                break
        return labels
