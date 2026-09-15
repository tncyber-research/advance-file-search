"""Qt model for search results.

A :class:`QAbstractItemModel` with two levels: one row per matching *file*, and
child rows for each additional matching location.  Grouping by file keeps the
list readable when one document matches many times, while expanding shows every
source location (page, paragraph, sheet/cell, line).

The model stores plain text only.  Highlight ranges travel as a custom role and
are applied by the delegate, so document content is never turned into markup.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    Qt,
)
from PySide6.QtGui import QColor, QFont

from advance_file_search.core import paths as pathutil
from advance_file_search.core.i18n import location_label, tr
from advance_file_search.core.models import (
    Highlight,
    MatchLocation,
    MatchSource,
    SearchResult,
)
from advance_file_search.ui.theme import PALETTE

#: Custom roles.
ROLE_HIGHLIGHTS = int(Qt.ItemDataRole.UserRole) + 1
ROLE_RESULT = int(Qt.ItemDataRole.UserRole) + 2
ROLE_LOCATION = int(Qt.ItemDataRole.UserRole) + 3
ROLE_IS_CHILD = int(Qt.ItemDataRole.UserRole) + 4
ROLE_SORT_VALUE = int(Qt.ItemDataRole.UserRole) + 5

COL_NAME = 0
COL_SNIPPET = 1
COL_TYPE = 2
COL_SIZE = 3
COL_MODIFIED = 4
COL_OPEN = 5
COLUMN_COUNT = 6

COLUMN_KEYS = (
    "col.name",
    "col.snippet",
    "col.type",
    "col.size",
    "col.modified",
    "col.open",
)

#: Starting widths.  The Match column stretches into whatever is left, so the
#: others are kept tight: with a wider base font and the details panel taking
#: a third of the window, generous fixed columns squeezed Match to nothing.
DEFAULT_COLUMN_WIDTHS = (250, 300, 66, 84, 134, 96)

#: No column may be dragged narrower than this.
MIN_SECTION_WIDTH = 56
#: The Match column keeps at least this much, so a snippet stays readable.
MIN_SNIPPET_WIDTH = 180

#: The source location (page, paragraph, sheet/cell, line) is no longer a
#: column: it belongs with the text it describes, so it is shown in the match
#: preview panel alongside the snippet.


def format_timestamp(value: float | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


def match_source_label(source: MatchSource) -> str:
    return {
        MatchSource.NAME: tr("result.match_source_name"),
        MatchSource.CONTENT: tr("result.match_source_content"),
        MatchSource.BOTH: tr("result.match_source_both"),
    }.get(source, "")


class ResultModel(QAbstractItemModel):
    """Two-level model: files at the top, extra match locations beneath."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._results: list[SearchResult] = []
        self._total_files = 0
        self._truncated = False

    # -- population -------------------------------------------------------
    def set_results(
        self, results: list[SearchResult], *, total_files: int = 0, truncated: bool = False
    ) -> None:
        self.beginResetModel()
        self._results = list(results)
        self._total_files = total_files or len(results)
        self._truncated = truncated
        self.endResetModel()

    def append_results(self, results: list[SearchResult], *, truncated: bool = False) -> None:
        if not results:
            self._truncated = truncated
            return
        start = len(self._results)
        self.beginInsertRows(QModelIndex(), start, start + len(results) - 1)
        self._results.extend(results)
        self.endInsertRows()
        self._truncated = truncated

    def clear(self) -> None:
        self.set_results([], total_files=0, truncated=False)

    @property
    def results(self) -> list[SearchResult]:
        return self._results

    @property
    def total_files(self) -> int:
        return self._total_files

    @property
    def truncated(self) -> bool:
        return self._truncated

    def result_at(self, index: QModelIndex) -> SearchResult | None:
        if not index.isValid():
            return None
        row = index.internalId()
        if row == 0:
            position = index.row()
        else:
            position = int(row) - 1
        if 0 <= position < len(self._results):
            return self._results[position]
        return None

    def location_at(self, index: QModelIndex) -> MatchLocation | None:
        if not index.isValid() or index.internalId() == 0:
            return None
        result = self.result_at(index)
        if result is None:
            return None
        # Child rows represent locations after the first (shown on the parent).
        position = index.row() + 1
        if 0 <= position < len(result.locations):
            return result.locations[position]
        return None

    def mark_missing(self, file_id: int) -> None:
        """Flag a result whose file has since disappeared."""
        for row, result in enumerate(self._results):
            if result.file_id == file_id:
                result.exists = False
                top = self.index(row, 0, QModelIndex())
                bottom = self.index(row, COLUMN_COUNT - 1, QModelIndex())
                self.dataChanged.emit(top, bottom)
                return

    # -- QAbstractItemModel ----------------------------------------------
    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        # Children encode their parent row + 1 in the internal id so that 0
        # unambiguously means "top level".
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, index: QModelIndex) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()
        internal = int(index.internalId())
        if internal == 0:
            return QModelIndex()
        return self.createIndex(internal - 1, 0, 0)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._results)
        if int(parent.internalId()) != 0:
            return 0
        result = self.result_at(parent)
        if result is None:
            return 0
        return max(0, len(result.locations) - 1)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        del parent
        return COLUMN_COUNT

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation is not Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole and 0 <= section < COLUMN_COUNT:
            return tr(COLUMN_KEYS[section])
        if role == Qt.ItemDataRole.TextAlignmentRole and section == COL_SIZE:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        is_child = int(index.internalId()) != 0
        result = self.result_at(index)
        if result is None:
            return None
        if is_child:
            return self._child_data(index, result, role)
        return self._file_data(index, result, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )

    # -- cell rendering ---------------------------------------------------
    def _file_data(self, index: QModelIndex, result: SearchResult, role: int) -> Any:
        column = index.column()
        best = result.best_location

        if role == ROLE_RESULT:
            return result
        if role == ROLE_IS_CHILD:
            return False
        if role == ROLE_LOCATION:
            return best
        if role == ROLE_HIGHLIGHTS:
            if column == COL_NAME:
                return list(result.name_highlights)
            if column == COL_SNIPPET and best is not None:
                return list(best.highlights)
            return []

        if role == Qt.ItemDataRole.DisplayRole:
            if column == COL_NAME:
                return result.file_name
            if column == COL_SNIPPET:
                if best is not None:
                    return best.snippet
                return result.relative_path
            if column == COL_TYPE:
                return result.extension.lstrip(".").upper()
            if column == COL_SIZE:
                return pathutil.format_size(result.size_bytes)
            if column == COL_MODIFIED:
                return format_timestamp(result.modified_time)
            # COL_OPEN is drawn by OpenFolderDelegate and has no text.
            return None

        if role == Qt.ItemDataRole.ToolTipRole:
            if column == COL_OPEN:
                # The buttons are icons, so the tooltip is what explains them.
                return tr("action.row_buttons_tooltip")
            lines = [result.display_path]
            if result.match_count:
                lines.append(
                    tr("result.match_count_one")
                    if result.match_count == 1
                    else tr("result.match_count", count=result.match_count)
                )
            lines.append(match_source_label(result.match_source))
            if not result.exists:
                lines.append(tr("result.missing"))
            return "\n".join(lines)

        if role == Qt.ItemDataRole.ForegroundRole:
            if not result.exists:
                return QColor(PALETTE.text_disabled)
            if column in (COL_TYPE, COL_SIZE, COL_MODIFIED):
                return QColor(PALETTE.text_muted)
            return QColor(PALETTE.text)

        if role == Qt.ItemDataRole.FontRole and column == COL_NAME:
            font = QFont()
            font.setBold(True)
            if not result.exists:
                font.setStrikeOut(True)
            return font

        if role == Qt.ItemDataRole.TextAlignmentRole and column == COL_SIZE:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == ROLE_SORT_VALUE:
            return self._sort_value(result, column)
        return None

    def _child_data(self, index: QModelIndex, result: SearchResult, role: int) -> Any:
        location = self.location_at(index)
        if location is None:
            return None
        column = index.column()

        if role == ROLE_RESULT:
            return result
        if role == ROLE_LOCATION:
            return location
        if role == ROLE_IS_CHILD:
            return True
        if role == ROLE_HIGHLIGHTS:
            return list(location.highlights) if column == COL_SNIPPET else []

        if role == Qt.ItemDataRole.DisplayRole:
            if column == COL_NAME:
                # A child row names its own location, so an expanded result
                # reads as a list of places the text was found.
                return location_label(location.location_type, location.location_data)
            if column == COL_SNIPPET:
                return location.snippet
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(PALETTE.text_muted)
        if role == Qt.ItemDataRole.ToolTipRole and column == COL_SNIPPET:
            return location.snippet
        return None

    @staticmethod
    def _sort_value(result: SearchResult, column: int) -> Any:
        return {
            COL_NAME: result.file_name.casefold(),
            COL_SNIPPET: result.score,
            COL_TYPE: result.extension,
            COL_SIZE: result.size_bytes,
            COL_MODIFIED: result.modified_time or 0.0,
        }.get(column, 0)


def highlights_from(value: Any) -> list[Highlight]:
    """Coerce the highlight role payload into a list of ranges."""
    if not value:
        return []
    if isinstance(value, list):
        return [h for h in value if isinstance(h, Highlight)]
    return []
