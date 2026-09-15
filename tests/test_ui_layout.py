"""Tests for the reworked result table, details panel and auto-indexing.

Covers the changes that removed the Location column and the Update Index
button, added the Open column and the match-preview panel, and made searching
build or refresh the index by itself.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QRect, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QFontMetrics, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QPushButton, QStyleOptionViewItem  # noqa: E402

from advance_file_search.core import constants as C  # noqa: E402
from advance_file_search.core.i18n import set_language, tr  # noqa: E402
from advance_file_search.core.models import Highlight, MatchLocation, SearchScope  # noqa: E402
from advance_file_search.ui import delegates
from advance_file_search.ui.delegates import RowActionsDelegate  # noqa: E402
from advance_file_search.ui.preview import MatchPreview  # noqa: E402
from advance_file_search.ui.result_model import (  # noqa: E402
    COL_NAME,
    COL_OPEN,
    COL_SNIPPET,
    ROLE_LOCATION,
    ResultModel,
)
from advance_file_search.ui.widgets import ElidedPathLabel, elide_path  # noqa: E402

# Reuse the window fixtures and helpers rather than duplicating them.
from tests.test_ui import (  # noqa: E402,F401
    _result,
    pump,
    ready_window,
    ui_search,
    wait_for_search,
    window,
)

pytestmark = pytest.mark.gui


#: x coordinates that land on each of the two row buttons inside
#: ``_button_option``'s 110-px cell: the pair is centred, so the middle of the
#: cell is the gap between them.
FOLDER_BUTTON_X = 35
FILE_BUTTON_X = 72


def _mouse(kind: QEvent.Type, x: int = FOLDER_BUTTON_X, y: int = 15) -> QMouseEvent:
    return QMouseEvent(
        kind,
        QPoint(x, y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _button_option() -> QStyleOptionViewItem:
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 110, 30)
    return option


# ---------------------------------------------------------------------------
# Match preview panel
# ---------------------------------------------------------------------------
def test_preview_shows_location_and_highlights_the_query(qapp):
    preview = MatchPreview()
    preview.set_location(
        MatchLocation(
            unit_id=1,
            sequence=1,
            location_type=C.LOC_SHEET_CELL,
            location_label="",
            location_data={"sheet": "งบประมาณ 2568", "cell": "F12"},
            snippet="cell needle F12",
            highlights=[Highlight(5, 11)],
        )
    )
    assert preview.has_content()
    assert preview.preview_text() == "cell needle F12"
    assert "F12" in preview.location_text()
    assert preview.highlighted_fragments() == ["needle"]


def test_preview_highlight_is_formatting_not_markup(qapp):
    """A document containing HTML must not be rendered as HTML."""
    hostile = '<b>bold</b> <script>alert("x")</script> injection needle'
    preview = MatchPreview()
    preview.set_location(
        MatchLocation(
            unit_id=1,
            sequence=1,
            location_type=C.LOC_PARAGRAPH,
            location_label="",
            location_data={"paragraph": 1},
            snippet=hostile,
            highlights=[Highlight(hostile.index("needle"), hostile.index("needle") + 6)],
        )
    )
    # The tags survive as literal characters, which is only possible if the
    # text was never parsed as markup.
    assert preview.preview_text() == hostile
    assert "<script>" in preview.preview_text()
    assert preview.highlighted_fragments() == ["needle"]


def test_preview_clamps_out_of_range_highlights(qapp):
    preview = MatchPreview()
    preview.set_location(
        MatchLocation(
            unit_id=1,
            sequence=1,
            location_type=C.LOC_LINE,
            location_label="",
            location_data={"line": 1},
            snippet="short",
            highlights=[Highlight(0, 500), Highlight(-5, 2), Highlight(3, 3)],
        )
    )
    assert preview.preview_text() == "short"


def test_preview_reports_additional_locations(qapp):
    set_language("en")
    preview = MatchPreview()
    location = MatchLocation(
        unit_id=1,
        sequence=1,
        location_type=C.LOC_LINE,
        location_label="",
        location_data={"line": 7},
        snippet="one needle here",
        highlights=[Highlight(4, 10)],
    )
    preview.set_location(location, extra_locations=4)
    assert preview.extra_locations_shown()
    assert "4" in preview._more.text()
    preview.set_location(location, extra_locations=0)
    assert not preview.extra_locations_shown()


def test_preview_message_and_clear_states(qapp):
    preview = MatchPreview()
    preview.show_message("nothing to preview")
    assert not preview.has_content()
    preview.clear()
    assert not preview.has_content()


def test_preview_thai_text_is_preserved_exactly(qapp):
    thai = "งบประมาณครุภัณฑ์ประจำปี ๒๕๖๘"
    preview = MatchPreview()
    preview.set_location(
        MatchLocation(
            unit_id=1,
            sequence=1,
            location_type=C.LOC_LINE,
            location_label="",
            location_data={"line": 1},
            snippet=thai,
            highlights=[Highlight(0, 8)],
        )
    )
    assert preview.preview_text() == thai
    assert preview.highlighted_fragments() == ["งบประมาณ"]


def test_name_only_match_explains_the_empty_preview(ready_window):
    set_language("en")
    ready_window._scope_combo.setCurrentIndex(
        ready_window._scope_combo.findData(SearchScope.NAME_ONLY)
    )
    found = ui_search(ready_window, "thai")
    if found:
        ready_window._tree.setCurrentIndex(
            ready_window._model.index(0, 0, QModelIndex())
        )
        pump(150)
        assert not ready_window._preview.has_content()
        assert ready_window._preview.message_shown()
    ready_window._scope_combo.setCurrentIndex(0)


def test_selecting_a_child_row_previews_that_location(ready_window):
    ui_search(ready_window, "needle")
    model = ready_window._model
    parent = next(
        (
            model.index(row, 0, QModelIndex())
            for row in range(model.rowCount(QModelIndex()))
            if model.rowCount(model.index(row, 0, QModelIndex())) > 0
        ),
        None,
    )
    if parent is None:
        pytest.skip("no result in this corpus has more than one location")
    ready_window._tree.expand(parent)
    pump(150)
    ready_window._tree.setCurrentIndex(model.index(0, COL_SNIPPET, parent))
    pump(200)
    location = model.index(0, COL_SNIPPET, parent).data(ROLE_LOCATION)
    assert ready_window._preview.preview_text() == location.snippet


def test_child_rows_name_their_location(ready_window):
    ui_search(ready_window, "needle")
    model = ready_window._model
    parent = next(
        (
            model.index(row, 0, QModelIndex())
            for row in range(model.rowCount(QModelIndex()))
            if model.rowCount(model.index(row, 0, QModelIndex())) > 0
        ),
        None,
    )
    if parent is None:
        pytest.skip("no result in this corpus has more than one location")
    assert model.index(0, COL_NAME, parent).data()


# ---------------------------------------------------------------------------
# Details panel
# ---------------------------------------------------------------------------
def test_details_omits_relative_path_and_type(ready_window):
    """Both are already columns in the table; repeating them wastes the panel."""
    ui_search(ready_window, "needle")
    ready_window._tree.setCurrentIndex(ready_window._model.index(0, 0, QModelIndex()))
    pump(150)
    assert "details.relative_path" not in ready_window._detail_rows
    assert "details.type" not in ready_window._detail_rows
    assert "details.full_path" in ready_window._detail_rows
    assert "details.size" in ready_window._detail_rows
    assert "details.modified" in ready_window._detail_rows


def test_details_path_is_elided_but_complete_on_hover(ready_window):
    ui_search(ready_window, "needle")
    ready_window._tree.setCurrentIndex(ready_window._model.index(0, 0, QModelIndex()))
    pump(250)
    label = ready_window._path_value
    result = ready_window._model.results[0]
    assert isinstance(label, ElidedPathLabel)
    assert label.full_text() == result.display_path
    assert label.toolTip() == result.display_path
    metrics = QFontMetrics(label.font())
    assert metrics.horizontalAdvance(label.text()) <= label.width() + 2


def test_details_clear_resets_the_path(ready_window):
    ui_search(ready_window, "needle")
    ready_window._tree.setCurrentIndex(ready_window._model.index(0, 0, QModelIndex()))
    pump(150)
    assert ready_window._path_value.full_text()
    ready_window._clear_details()
    assert ready_window._path_value.full_text() == ""


# ---------------------------------------------------------------------------
# Path elision
# ---------------------------------------------------------------------------
def test_elide_path_cuts_at_folder_boundaries(qapp):
    from PySide6.QtGui import QFont

    metrics = QFontMetrics(QFont())
    path = "C:\\Users\\someone\\Documents\\Projects\\2568\\reports\\budget.xlsx"
    full_width = metrics.horizontalAdvance(path)

    assert elide_path(path, metrics, full_width + 20) == path

    short = elide_path(path, metrics, full_width // 2)
    assert short.startswith("C:")
    assert short.endswith("budget.xlsx")
    assert "…" in short
    # Whatever survives is whole components, never a fragment of one.
    kept = [part for part in short.split("\\") if part != "…"]
    original = path.split("\\")
    assert all(part in original for part in kept)


def test_elide_path_keeps_the_drive_and_the_file_name(qapp):
    from PySide6.QtGui import QFont

    metrics = QFontMetrics(QFont())
    path = "D:\\" + "\\".join(f"folder{index}" for index in range(20)) + "\\report.pdf"
    result = elide_path(path, metrics, 200)
    assert result.startswith("D:")
    assert result.endswith("report.pdf")
    assert metrics.horizontalAdvance(result) <= 202


def test_elide_path_handles_a_value_without_separators(qapp):
    from PySide6.QtGui import QFont

    metrics = QFontMetrics(QFont())
    result = elide_path("x" * 400, metrics, 120)
    assert "…" in result
    assert metrics.horizontalAdvance(result) <= 122


def test_eliding_label_never_demands_width(qapp):
    """The label must not be able to widen the panel it sits in."""
    label = ElidedPathLabel("C:\\" + "\\".join(["verylongfoldername"] * 12) + "\\f.txt")
    assert label.minimumSizeHint().width() <= 64
    assert label.sizeHint().width() <= 64


# ---------------------------------------------------------------------------
# Open-folder column
# ---------------------------------------------------------------------------
def test_open_column_button_reveals_the_file(ready_window, monkeypatch):
    from advance_file_search.winplat import windows_shell

    ui_search(ready_window, "needle")
    revealed: list[str] = []
    monkeypatch.setattr(
        windows_shell,
        "reveal_in_explorer",
        lambda path: revealed.append(path) or windows_shell.ShellResult(True),
    )

    delegate = ready_window._open_delegate
    index = ready_window._model.index(0, COL_OPEN, QModelIndex())
    option = _button_option()
    assert delegate.editorEvent(
        _mouse(QEvent.Type.MouseButtonPress), ready_window._model, option, index
    )
    assert delegate.editorEvent(
        _mouse(QEvent.Type.MouseButtonRelease), ready_window._model, option, index
    )
    assert revealed == [ready_window._model.results[0].display_path]


def test_open_column_click_outside_the_button_does_nothing(ready_window, monkeypatch):
    from advance_file_search.winplat import windows_shell

    ui_search(ready_window, "needle")
    revealed: list[str] = []
    monkeypatch.setattr(
        windows_shell,
        "reveal_in_explorer",
        lambda path: revealed.append(path) or windows_shell.ShellResult(True),
    )
    delegate = ready_window._open_delegate
    index = ready_window._model.index(0, COL_OPEN, QModelIndex())
    option = _button_option()
    # Well outside the padded button rectangle.
    assert not delegate.editorEvent(
        _mouse(QEvent.Type.MouseButtonPress, x=200, y=15),
        ready_window._model,
        option,
        index,
    )
    assert not revealed


def test_open_column_buttons_are_inert_for_a_missing_file(qapp):
    model = ResultModel()
    model.set_results([_result(exists=False)])
    delegate = RowActionsDelegate()
    fired: list[object] = []
    delegate.clicked.connect(fired.append)
    delegate.open_clicked.connect(fired.append)
    index = model.index(0, COL_OPEN, QModelIndex())
    for x in (FOLDER_BUTTON_X, FILE_BUTTON_X):
        assert not delegate.editorEvent(
            _mouse(QEvent.Type.MouseButtonPress, x=x), model, _button_option(), index
        )
    assert not fired


def test_open_file_button_opens_the_row_file(ready_window, monkeypatch):
    """The second button opens the document itself, not its folder."""
    from advance_file_search.winplat import windows_shell

    ui_search(ready_window, "needle")
    opened: list[str] = []
    monkeypatch.setattr(
        windows_shell,
        "open_file",
        lambda path: opened.append(path) or windows_shell.ShellResult(True),
    )

    delegate = ready_window._open_delegate
    index = ready_window._model.index(0, COL_OPEN, QModelIndex())
    option = _button_option()
    assert delegate.editorEvent(
        _mouse(QEvent.Type.MouseButtonPress, x=FILE_BUTTON_X),
        ready_window._model,
        option,
        index,
    )
    assert delegate.editorEvent(
        _mouse(QEvent.Type.MouseButtonRelease, x=FILE_BUTTON_X),
        ready_window._model,
        option,
        index,
    )
    assert opened == [ready_window._model.results[0].display_path]


def test_the_two_row_buttons_do_not_overlap(qapp):
    option = _button_option()
    rects = RowActionsDelegate._button_rects(option)
    folder = rects[delegates.ACTION_REVEAL]
    document = rects[delegates.ACTION_OPEN]
    assert folder.right() < document.left(), "the buttons must not touch"
    assert folder.width() == document.width()
    # Both stay inside the cell.
    assert folder.left() >= option.rect.left()
    assert document.right() <= option.rect.right()


def test_the_open_column_explains_both_buttons(qapp):
    model = ResultModel()
    model.set_results([_result()])
    tooltip = model.index(0, COL_OPEN, QModelIndex()).data(
        Qt.ItemDataRole.ToolTipRole
    )
    assert tooltip and len(str(tooltip).splitlines()) == 2


def test_open_column_has_no_buttons_on_child_rows(qapp):
    model = ResultModel()
    model.set_results([_result()])
    delegate = RowActionsDelegate()
    parent = model.index(0, 0, QModelIndex())
    child = model.index(0, COL_OPEN, parent)
    for x in (FOLDER_BUTTON_X, FILE_BUTTON_X):
        assert not delegate.editorEvent(
            _mouse(QEvent.Type.MouseButtonPress, x=x), model, _button_option(), child
        )


def test_open_column_is_the_last_column(ready_window):
    set_language("en")
    header = ready_window._model.headerData(COL_OPEN, Qt.Orientation.Horizontal)
    assert header == tr("col.open")


def test_location_column_is_gone(ready_window):
    set_language("en")
    headers = {
        ready_window._model.headerData(column, Qt.Orientation.Horizontal)
        for column in range(ready_window._model.columnCount(QModelIndex()))
    }
    assert tr("col.location") not in headers
    assert tr("col.snippet") in headers


# ---------------------------------------------------------------------------
# Auto-indexing on search
# ---------------------------------------------------------------------------
def test_there_is_no_update_index_button(window):
    """Indexing is driven by searching, not by a button the user must find."""
    assert not hasattr(window, "_index_button")
    labels = {button.text() for button in window.findChildren(QPushButton)}
    assert tr("index.create") not in labels
    assert tr("index.update") not in labels


def test_search_controls_are_enabled_before_an_index_exists(window, corpus):
    window._adopt_root(str(corpus))
    pump(150)
    assert window._query.isEnabled()
    assert window._search_button.isEnabled()
    assert window._current_root is None or window._current_root.file_count == 0


def test_pressing_search_builds_the_index_then_searches(window, corpus):
    """The point of removing the button: one action does both."""
    window._adopt_root(str(corpus))
    pump(150)
    window._query.setText("needle")

    closed: list[int] = []

    def close_when_done() -> None:
        dialog = window._index_dialog
        if dialog is not None and dialog.isVisible() and dialog._finished:
            dialog.accept()
            closed.append(1)

    timer = QTimer()
    timer.timeout.connect(close_when_done)
    timer.start(150)
    try:
        window._search_now()
        waited = 0
        while (
            window._index_handle is not None
            and window._index_handle.running
            and waited < 90_000
        ):
            pump(100)
            waited += 100
        pump(500)
    finally:
        timer.stop()

    assert closed, "the indexing dialog never reported completion"
    assert window._current_root is not None
    assert window._current_root.file_count > 0
    wait_for_search(window)
    assert window._model.rowCount(QModelIndex()) > 0


def _drain_index(window, timeout_ms: int = 60_000) -> None:
    waited = 0
    while (
        window._index_handle is not None
        and window._index_handle.running
        and waited < timeout_ms
    ):
        pump(100)
        waited += 100
    pump(300)


def test_a_later_search_refreshes_the_index_in_the_background(ready_window):
    ready_window._last_auto_refresh.clear()
    ready_window._query.setText("needle")
    ready_window._search_now()
    wait_for_search(ready_window)

    # Results are available immediately; the refresh runs behind them.
    assert ready_window._model.rowCount(QModelIndex()) > 0
    _drain_index(ready_window)
    assert ready_window._index_handle is None
    assert not ready_window._index_activity.isVisible()


def test_background_refresh_does_not_disable_the_search_box(ready_window):
    ready_window._last_auto_refresh.clear()
    ready_window._query.setText("needle")
    ready_window._search_now()
    pump(80)
    # Whether or not the refresh is still running, typing must stay possible.
    assert ready_window._query.isEnabled()
    _drain_index(ready_window)


def test_background_refresh_is_throttled(ready_window):
    """Pressing Search repeatedly must not re-scan the folder every time."""
    ready_window._last_auto_refresh.clear()
    ready_window._query.setText("needle")
    ready_window._search_now()
    wait_for_search(ready_window)
    _drain_index(ready_window)

    stamps = dict(ready_window._last_auto_refresh)
    assert stamps, "the first search should have recorded a refresh"
    ready_window._search_now()
    wait_for_search(ready_window)
    assert ready_window._last_auto_refresh == stamps


def test_search_without_a_root_does_nothing(window):
    window._query.setText("anything")
    window._search_now()
    pump(200)
    assert window._model.rowCount(QModelIndex()) == 0
    assert window._index_handle is None


def test_forced_refresh_clears_the_throttle(ready_window, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(
        type(ready_window),
        "_start_index",
        lambda self, *, rebuild: started.append(rebuild),
    )
    ready_window._last_auto_refresh["stale"] = 1.0
    ready_window._force_index_refresh()
    assert started == [False]


def test_typing_does_not_trigger_indexing(ready_window):
    """Debounced typing must never re-scan; only an explicit search may."""
    ready_window._last_auto_refresh.clear()
    ready_window._query.setText("need")
    pump(600)  # longer than the debounce interval
    wait_for_search(ready_window)
    assert ready_window._last_auto_refresh == {}
    assert ready_window._index_handle is None
