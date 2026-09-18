"""XLSX extraction with openpyxl in read-only, data-only mode.

Granularity decision (see ``docs/decisions/0003-xlsx-granularity.md``): one
content unit per non-empty cell, so a match can be reported down to the exact
cell.  Row context for the snippet is reconstructed at search time from the
neighbouring cells of the same row, which avoids duplicating every value twice
in the index.

Safety policy:

* ``data_only=True`` — the **cached result** stored in the file is indexed and
  formulas are never recalculated.  A workbook saved by a tool that did not
  cache results will therefore have empty formula cells; this is documented.
* ``read_only=True`` streams worksheets instead of loading the whole workbook.
* External workbook links are never resolved; macros are never executed
  (``.xlsm`` is out of scope).
* Charts, images and drawing text are ignored in MVP.
* Hidden worksheets are skipped; hidden rows/columns are still indexed because
  they hold real data.
"""

from __future__ import annotations

import datetime as _dt
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
from advance_file_search.indexing.parsers.base import (
    DocumentParser,
    clean_text,
    excel_column_name,
)


def format_cell_value(value: Any) -> str:
    """Render a cell value the way a user would expect to search for it.

    Numbers keep their significant digits without float noise, dates use an
    unambiguous ISO form, and booleans use Excel's own TRUE/FALSE spelling.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
            return ""
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return repr(round(value, 10)).rstrip("0").rstrip(".")
    if isinstance(value, _dt.datetime):
        if value.hour or value.minute or value.second:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    if isinstance(value, _dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, _dt.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, _dt.timedelta):
        return str(value)
    return str(value)


class XlsxParser(DocumentParser):
    """One content unit per non-empty cell of each visible worksheet."""

    name = "xlsx"
    supported_extensions = frozenset({".xlsx"})

    def _parse(self, path: Path, size_bytes: int) -> ParseResult:
        try:
            import openpyxl  # type: ignore[import-not-found]
            from openpyxl.utils.exceptions import InvalidFileException  # type: ignore
        except ImportError:  # pragma: no cover - packaging guard
            return ParseResult(
                ParseOutcome.ERROR,
                error_code=C.ERR_UNKNOWN,
                error_message="XLSX support is not available in this build",
            )

        workbook = None
        try:
            try:
                workbook = openpyxl.load_workbook(
                    str(path),
                    read_only=True,
                    data_only=True,
                    keep_links=False,
                    rich_text=False,
                )
            except InvalidFileException:
                return ParseResult(
                    ParseOutcome.CORRUPT,
                    error_code=C.ERR_CORRUPT,
                    error_message="not a readable XLSX workbook",
                )
            except Exception as exc:  # noqa: BLE001 - untrusted file
                message = str(exc).lower()
                if "password" in message or "encrypt" in message:
                    return ParseResult(
                        ParseOutcome.PASSWORD_PROTECTED,
                        error_code=C.ERR_PASSWORD_PROTECTED,
                        error_message="encrypted workbook",
                    )
                return ParseResult(
                    ParseOutcome.CORRUPT,
                    error_code=C.ERR_CORRUPT,
                    error_message=sanitize_exception(exc),
                )

            warnings: list[str] = []
            units: list[ContentUnit] = []
            truncated = False
            sequence = 0
            cell_budget = C.MAX_XLSX_CELLS
            total_chars = 0
            sheet_count = 0

            for worksheet in workbook.worksheets:
                if getattr(worksheet, "sheet_state", "visible") != "visible":
                    continue
                sheet_count += 1
                # The real Unicode sheet name is preserved in location data;
                # only display length is capped.
                sheet_name = str(getattr(worksheet, "title", "") or "")
                try:
                    rows = worksheet.iter_rows(values_only=True)
                except Exception:  # noqa: BLE001
                    warnings.append(C.ERR_CORRUPT)
                    continue

                row_index = 0
                for row in rows:
                    row_index += 1
                    if row is None:
                        continue
                    for column_index, value in enumerate(row, start=1):
                        if value is None:
                            continue
                        rendered = format_cell_value(value)
                        if not rendered.strip():
                            continue
                        text = clean_text(rendered, limit=C.MAX_CELL_TEXT_LENGTH)
                        if not text:
                            continue
                        cell_budget -= 1
                        if cell_budget <= 0 or total_chars > C.MAX_DOCUMENT_TEXT_CHARS:
                            truncated = True
                            break
                        sequence += 1
                        coordinate = f"{excel_column_name(column_index)}{row_index}"
                        units.append(
                            ContentUnit(
                                sequence=sequence,
                                location_type=C.LOC_SHEET_CELL,
                                location_label=f"Sheet: {sheet_name}, Cell: {coordinate}",
                                location_data={
                                    "sheet": sheet_name,
                                    "cell": coordinate,
                                    "row": row_index,
                                    "column": column_index,
                                    "type": type(value).__name__,
                                },
                                text=text,
                            )
                        )
                        total_chars += len(text)
                    if truncated:
                        break
                if truncated:
                    break

            if truncated:
                warnings.append(C.ERR_LIMIT)

            metadata = DocumentMetadata(
                extension=".xlsx", sheet_count=sheet_count, truncated=truncated
            )
            return self._finish(units, metadata, warnings)
        finally:
            if workbook is not None:
                try:  # noqa: SIM105 - see below
                    workbook.close()
                # S110/SIM105: the cells are already read; closing is
                # cleanup and must not fail the parse.
                except Exception:  # noqa: BLE001, S110, SIM105
                    pass
