"""DOCX extraction with python-docx.

Known limitation, stated honestly in the UI: Word page numbers cannot be
determined without rendering the document through a word processor, so matches
report *paragraph* and *table cell* positions instead.

Safety policy:

* Macros are never executed (``.docm`` is out of scope entirely).
* Hyperlink targets are not followed; only the visible link text is indexed.
* Remote templates, linked images and OLE objects are never loaded.
* Body order is preserved by walking the document body XML rather than the
  separate ``paragraphs`` and ``tables`` collections, so a table appears in the
  sequence where it actually occurs.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from advance_file_search.core import constants as C
from advance_file_search.core.models import (
    ContentUnit,
    DocumentMetadata,
    ParseOutcome,
    ParseResult,
)
from advance_file_search.core.security import sanitize_exception
from advance_file_search.indexing.parsers.base import DocumentParser, clean_text

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocxParser(DocumentParser):
    """One unit per paragraph and one per non-empty table cell."""

    name = "docx"
    supported_extensions = frozenset({".docx"})

    def _parse(self, path: Path, size_bytes: int) -> ParseResult:
        try:
            import docx  # type: ignore[import-not-found]
            from docx.opc.exceptions import PackageNotFoundError  # type: ignore
            from docx.table import Table  # type: ignore
            from docx.text.paragraph import Paragraph  # type: ignore
        except ImportError:  # pragma: no cover - packaging guard
            return ParseResult(
                ParseOutcome.ERROR,
                error_code=C.ERR_UNKNOWN,
                error_message="DOCX support is not available in this build",
            )

        try:
            document = docx.Document(str(path))
        except PackageNotFoundError:
            return ParseResult(
                ParseOutcome.CORRUPT,
                error_code=C.ERR_CORRUPT,
                error_message="not a readable DOCX package",
            )
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

        warnings: list[str] = []
        units: list[ContentUnit] = []
        truncated = False
        total_chars = 0
        paragraph_number = 0
        table_number = 0
        sequence = 0

        body = document.element.body
        for child in body.iterchildren():
            if len(units) >= C.MAX_DOCX_UNITS or total_chars > C.MAX_DOCUMENT_TEXT_CHARS:
                truncated = True
                break

            tag = child.tag
            if tag == f"{_W_NS}p":
                paragraph_number += 1
                try:
                    text = clean_text(
                        Paragraph(child, document).text,
                        limit=self.options.max_unit_text_length,
                    )
                except Exception:  # noqa: BLE001 - per-element resilience
                    warnings.append(C.ERR_CORRUPT)
                    continue
                if not text:
                    continue
                sequence += 1
                units.append(
                    ContentUnit(
                        sequence=sequence,
                        location_type=C.LOC_PARAGRAPH,
                        location_label=f"Paragraph {paragraph_number}",
                        location_data={"paragraph": paragraph_number},
                        text=text,
                    )
                )
                total_chars += len(text)

            elif tag == f"{_W_NS}tbl":
                table_number += 1
                try:
                    table = Table(child, document)
                except Exception:  # noqa: BLE001
                    warnings.append(C.ERR_CORRUPT)
                    continue
                for row_index, row in enumerate(self._safe_rows(table), start=1):
                    for column_index, cell_text in enumerate(row, start=1):
                        text = clean_text(
                            cell_text, limit=self.options.max_unit_text_length
                        )
                        if not text:
                            continue
                        sequence += 1
                        units.append(
                            ContentUnit(
                                sequence=sequence,
                                location_type=C.LOC_TABLE_CELL,
                                location_label=(
                                    f"Table {table_number}, row {row_index}, "
                                    f"column {column_index}"
                                ),
                                location_data={
                                    "table": table_number,
                                    "row": row_index,
                                    "column": column_index,
                                },
                                text=text,
                            )
                        )
                        total_chars += len(text)
                        if (
                            len(units) >= C.MAX_DOCX_UNITS
                            or total_chars > C.MAX_DOCUMENT_TEXT_CHARS
                        ):
                            truncated = True
                            break
                    if truncated:
                        break

        if self.options.include_docx_headers and not truncated:
            sequence = self._extract_headers_footers(document, units, sequence, warnings)

        if truncated:
            warnings.append(C.ERR_LIMIT)

        metadata = DocumentMetadata(extension=".docx", truncated=truncated)
        return self._finish(units, metadata, warnings)

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _safe_rows(table: Any) -> Iterator[list[str]]:
        """Yield each row's cell text, tolerating malformed table XML.

        Merged cells repeat their text in python-docx; duplicates within a row
        are collapsed so a merged heading is not indexed several times.
        """
        try:
            rows = list(table.rows)
        except Exception:  # noqa: BLE001
            return
        for row in rows:
            try:
                cells = list(row.cells)
            except Exception:  # noqa: BLE001
                continue
            texts: list[str] = []
            previous = None
            for cell in cells:
                try:
                    value = cell.text
                except Exception:  # noqa: BLE001
                    value = ""
                texts.append("" if value == previous else value)
                previous = value
            yield texts

    def _extract_headers_footers(
        self,
        document: Any,
        units: list[ContentUnit],
        sequence: int,
        warnings: list[str],
    ) -> int:
        """Index header/footer text, clearly labelled as such.

        Header and footer content repeats on every page, so it is indexed once
        per section and never attributed to a paragraph number.
        """
        try:
            sections = list(document.sections)
        except Exception:  # noqa: BLE001
            return sequence
        for section_index, section in enumerate(sections, start=1):
            for attribute, location_type in (
                ("header", C.LOC_HEADER),
                ("footer", C.LOC_FOOTER),
            ):
                try:
                    part = getattr(section, attribute, None)
                    if part is None or getattr(part, "is_linked_to_previous", False):
                        continue
                    pieces = [p.text for p in part.paragraphs]
                    for table in getattr(part, "tables", []):
                        for row in self._safe_rows(table):
                            pieces.extend(row)
                except Exception:  # noqa: BLE001
                    warnings.append(C.ERR_CORRUPT)
                    continue
                text = clean_text(
                    "\n".join(piece for piece in pieces if piece),
                    limit=self.options.max_unit_text_length,
                )
                if not text:
                    continue
                sequence += 1
                units.append(
                    ContentUnit(
                        sequence=sequence,
                        location_type=location_type,
                        location_label=location_type.capitalize(),
                        location_data={"section": section_index},
                        text=text,
                    )
                )
        return sequence
