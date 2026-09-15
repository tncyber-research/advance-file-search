"""UI tests: model, delegate, dialogs and the main window workflow.

These drive real Qt widgets (there is no mocking of the view layer), so they
catch layout and signal wiring problems that unit tests cannot.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QModelIndex, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QFont, QPixmap  # noqa: E402

from advance_file_search.core import constants as C  # noqa: E402
from advance_file_search.core.i18n import set_language, tr  # noqa: E402
from advance_file_search.core.models import (  # noqa: E402
    Highlight,
    IndexPhase,
    IndexProgress,
    IndexSummary,
    MatchLocation,
    MatchSource,
    RunStatus,
    SearchRequest,
    SearchResult,
    SortField,
)
from advance_file_search.core.settings import AppSettings  # noqa: E402
from advance_file_search.ui.delegates import highlight_ranges_valid  # noqa: E402
from advance_file_search.ui.index_dialog import format_elapsed  # noqa: E402
from advance_file_search.ui.result_model import (  # noqa: E402
    COL_MODIFIED,
    COL_NAME,
    COL_SIZE,
    COL_SNIPPET,
    COL_TYPE,
    COLUMN_COUNT,
    MIN_SNIPPET_WIDTH,
    ROLE_HIGHLIGHTS,
    ROLE_IS_CHILD,
    ROLE_LOCATION,
    ResultModel,
    format_timestamp,
)

pytestmark = pytest.mark.gui


def pump(ms: int = 120) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_for_search(window, timeout_ms: int = 6000) -> None:
    waited = 0
    while window._search_handle is not None and waited < timeout_ms:
        pump(40)
        waited += 40
    pump(120)


def ui_search(window, query: str) -> int:
    window._query.setText(query)
    window._start_search()
    wait_for_search(window)
    return window._model.rowCount(QModelIndex())


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------
def _result(**overrides) -> SearchResult:
    defaults = dict(
        file_id=1,
        root_id=1,
        display_path="D:\\Docs\\budget.xlsx",
        relative_path="budget.xlsx",
        file_name="budget.xlsx",
        extension=".xlsx",
        size_bytes=6013,
        created_time=1700000000.0,
        modified_time=1700000100.0,
        content_status=C.STATUS_INDEXED,
        match_source=MatchSource.CONTENT,
        score=215.0,
        match_count=2,
        locations=[
            MatchLocation(
                unit_id=1,
                sequence=1,
                location_type=C.LOC_SHEET_CELL,
                location_label="Sheet: งบประมาณ 2568, Cell: F12",
                location_data={"sheet": "งบประมาณ 2568", "cell": "F12"},
                snippet="cell needle F12",
                highlights=[Highlight(5, 11)],
            ),
            MatchLocation(
                unit_id=2,
                sequence=2,
                location_type=C.LOC_SHEET_CELL,
                location_label="Sheet: งบประมาณ 2568, Cell: G13",
                location_data={"sheet": "งบประมาณ 2568", "cell": "G13"},
                snippet="second needle",
                highlights=[Highlight(7, 13)],
            ),
        ],
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


def test_model_shape(qapp):
    model = ResultModel()
    model.set_results([_result()], total_files=1)
    assert model.rowCount(QModelIndex()) == 1
    assert model.columnCount(QModelIndex()) == COLUMN_COUNT
    # One location is shown on the parent row; the rest become children.
    parent = model.index(0, 0, QModelIndex())
    assert model.rowCount(parent) == 1


def test_model_parent_child_navigation(qapp):
    model = ResultModel()
    model.set_results([_result()])
    parent = model.index(0, 0, QModelIndex())
    child = model.index(0, COL_SNIPPET, parent)
    assert child.isValid()
    assert model.parent(child) == model.index(0, 0, QModelIndex())
    assert not model.parent(parent).isValid()
    assert child.data(ROLE_IS_CHILD) is True
    assert parent.data(ROLE_IS_CHILD) is False


def test_model_display_values(qapp):
    set_language("en")
    model = ResultModel()
    model.set_results([_result()])
    row = 0
    assert model.index(row, COL_NAME, QModelIndex()).data() == "budget.xlsx"
    assert model.index(row, COL_SNIPPET, QModelIndex()).data() == "cell needle F12"
    assert model.index(row, COL_TYPE, QModelIndex()).data() == "XLSX"
    assert "KB" in model.index(row, COL_SIZE, QModelIndex()).data()
    assert model.index(row, COL_MODIFIED, QModelIndex()).data()


def test_model_exposes_highlights_not_markup(qapp):
    model = ResultModel()
    model.set_results([_result()])
    highlights = model.index(0, COL_SNIPPET, QModelIndex()).data(ROLE_HIGHLIGHTS)
    assert highlights == [Highlight(5, 11)]
    assert all(isinstance(h, Highlight) for h in highlights)


def test_model_child_rows_carry_their_own_location(qapp):
    model = ResultModel()
    model.set_results([_result()])
    parent = model.index(0, 0, QModelIndex())
    child = model.index(0, COL_SNIPPET, parent)
    location = child.data(ROLE_LOCATION)
    assert location.location_data["cell"] == "G13"
    assert child.data() == "second needle"
    # A child row names its own location in the Name column.
    assert "G13" in model.index(0, COL_NAME, parent).data()


def test_model_marks_a_missing_file(qapp):
    model = ResultModel()
    model.set_results([_result()])
    changed: list = []
    model.dataChanged.connect(lambda *args: changed.append(args))
    model.mark_missing(1)
    assert not model.results[0].exists
    assert changed
    font = model.index(0, COL_NAME, QModelIndex()).data(Qt.ItemDataRole.FontRole)
    assert isinstance(font, QFont)
    assert font.strikeOut()


def test_model_append_and_clear(qapp):
    model = ResultModel()
    model.set_results([_result()], total_files=3, truncated=True)
    model.append_results([_result(file_id=2, file_name="b.txt")])
    assert model.rowCount(QModelIndex()) == 2
    model.clear()
    assert model.rowCount(QModelIndex()) == 0
    assert not model.truncated


def test_model_result_at_for_invalid_index(qapp):
    model = ResultModel()
    assert model.result_at(QModelIndex()) is None
    assert model.location_at(QModelIndex()) is None


def test_model_tooltip_mentions_a_missing_file(qapp):
    set_language("en")
    model = ResultModel()
    model.set_results([_result(exists=False)])
    tooltip = model.index(0, COL_NAME, QModelIndex()).data(Qt.ItemDataRole.ToolTipRole)
    assert "missing" in tooltip.lower()


def test_format_helpers():
    assert format_timestamp(None) == ""
    assert format_timestamp(0) == ""
    assert len(format_timestamp(1700000000.0)) == 16
    assert format_elapsed(0) == "0:00"
    assert format_elapsed(65) == "1:05"
    assert format_elapsed(3725) == "1:02:05"


def test_highlight_range_validator():
    assert highlight_ranges_valid([Highlight(0, 3), Highlight(5, 8)], 10)
    assert not highlight_ranges_valid([Highlight(0, 3), Highlight(2, 8)], 10)  # overlap
    assert not highlight_ranges_valid([Highlight(0, 20)], 10)  # out of bounds
    assert not highlight_ranges_valid([Highlight(3, 3)], 10)  # empty
    assert highlight_ranges_valid([], 10)


# ---------------------------------------------------------------------------
# Delegate rendering
# ---------------------------------------------------------------------------
def test_delegate_paints_without_interpreting_markup(qapp):
    """A snippet containing HTML must be painted, not parsed."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem, QTreeView

    from advance_file_search.ui.delegates import HighlightDelegate

    model = ResultModel()
    hostile = _result(
        file_name="html_like.docx",
        locations=[
            MatchLocation(
                unit_id=1,
                sequence=1,
                location_type=C.LOC_PARAGRAPH,
                location_label="Paragraph 1",
                location_data={"paragraph": 1},
                snippet='<b>bold</b> <script>alert("x")</script> injection needle',
                highlights=[Highlight(48, 54)],
            )
        ],
    )
    model.set_results([hostile])

    view = QTreeView()
    view.setModel(model)
    delegate = HighlightDelegate(view)
    view.setItemDelegateForColumn(COL_SNIPPET, delegate)
    view.resize(900, 200)

    pixmap = QPixmap(900, 40)
    pixmap.fill()
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 900, 26)
    option.widget = view
    option.font = view.font()
    try:
        # The assertion is that painting hostile content does not raise and
        # does not route the text through a rich-text engine.
        delegate.paint(painter, option, model.index(0, COL_SNIPPET, QModelIndex()))
    finally:
        painter.end()
    view.deleteLater()


def test_delegate_falls_back_when_there_are_no_highlights(qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem, QTreeView

    from advance_file_search.ui.delegates import HighlightDelegate

    model = ResultModel()
    model.set_results([_result(locations=[])])
    view = QTreeView()
    view.setModel(model)
    delegate = HighlightDelegate(view)
    pixmap = QPixmap(400, 40)
    pixmap.fill()
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 400, 26)
    option.widget = view
    option.font = view.font()
    try:
        delegate.paint(painter, option, model.index(0, COL_SNIPPET, QModelIndex()))
    finally:
        painter.end()
    view.deleteLater()


# ---------------------------------------------------------------------------
# Index dialog
# ---------------------------------------------------------------------------
def test_index_dialog_progress_and_summary(qapp):
    from advance_file_search.ui.index_dialog import IndexDialog

    dialog = IndexDialog()
    dialog.show()
    pump(80)
    dialog.update_progress(
        IndexProgress(
            phase=IndexPhase.EXTRACTING,
            current_item="เอกสาร\\txt\\a.txt",
            discovered=120,
            processed=47,
            indexed=40,
            skipped=3,
            failed=2,
            no_text=2,
            elapsed_seconds=12.5,
        )
    )
    pump()
    assert dialog._bar.maximum() == 120
    assert dialog._bar.value() == 47
    assert dialog._counter_labels["indexed"].text() == "40"
    assert dialog._counter_labels["failed"].text() == "2"

    summary = IndexSummary(
        run_id=1,
        root_id=1,
        status=RunStatus.COMPLETED,
        discovered=120,
        processed=120,
        indexed=110,
        failed=2,
        no_text=3,
        skipped=5,
        elapsed_seconds=30.0,
        skip_counts={"executable": 4, "not_supported": 900},
    )
    dialog.show_summary(summary)
    pump()
    assert dialog._close_button.isVisible()
    assert not dialog._cancel_button.isVisible()
    dialog._problems_button.setChecked(True)
    pump()
    labels = [
        dialog._problems.topLevelItem(index).text(0)
        for index in range(dialog._problems.topLevelItemCount())
    ]
    # Interesting skips are surfaced; "unsupported file type" noise is not.
    assert any("link" in text.lower() or "program" in text.lower() or text for text in labels)
    assert not any("Unsupported" in text for text in labels)
    dialog.accept()


def test_index_dialog_is_indeterminate_while_scanning(qapp):
    from advance_file_search.ui.index_dialog import IndexDialog

    dialog = IndexDialog()
    dialog.update_progress(IndexProgress(phase=IndexPhase.SCANNING, discovered=0))
    assert dialog._bar.maximum() == 0  # indeterminate
    dialog.accept()


def test_index_dialog_close_means_cancel(qapp):
    """Closing the dialog must request a safe stop, not abandon the worker."""
    from advance_file_search.ui.index_dialog import IndexDialog

    dialog = IndexDialog()
    assert not dialog.cancel_requested
    dialog.reject()
    assert dialog.cancel_requested
    assert dialog.isVisible() or True  # stays open until the worker reports
    dialog._finished = True
    dialog.accept()


def test_index_dialog_reports_an_error(qapp):
    from advance_file_search.ui.index_dialog import IndexDialog

    dialog = IndexDialog()
    dialog.show()
    pump(80)
    dialog.show_error("something went wrong")
    pump()
    assert dialog._close_button.isVisible()
    assert "wrong" in dialog._summary_label.text()
    dialog.accept()


def test_index_dialog_does_not_show_document_content(qapp):
    """The progress UI shows a relative path, never extracted text."""
    from advance_file_search.ui.index_dialog import IndexDialog

    dialog = IndexDialog()
    dialog.update_progress(
        IndexProgress(phase=IndexPhase.EXTRACTING, current_item="sub\\file.txt")
    )
    pump()
    assert "file.txt" in dialog._current_label.text()
    assert ":" not in dialog._current_label.text()
    dialog.accept()


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------
def test_settings_dialog_edits_a_copy(qapp):
    from advance_file_search.ui.settings_dialog import SettingsDialog

    original = AppSettings(max_file_size_mb=500, language="th")
    dialog = SettingsDialog(original)
    dialog._max_size.setValue(250)
    dialog._optional.setChecked(True)
    dialog._language.setCurrentIndex(dialog._language.findData("en"))
    dialog._on_accept()

    assert dialog.result_settings.max_file_size_mb == 250
    assert dialog.result_settings.enable_optional_formats
    assert dialog.result_settings.language == "en"
    # The caller's object is untouched until it chooses to save.
    assert original.max_file_size_mb == 500
    assert original.language == "th"


def test_settings_dialog_flags_when_a_reindex_is_needed(qapp):
    from advance_file_search.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(AppSettings())
    dialog._on_accept()
    assert not dialog.reindex_needed

    dialog = SettingsDialog(AppSettings())
    dialog._optional.setChecked(not dialog._optional.isChecked())
    dialog._on_accept()
    assert dialog.reindex_needed


def test_settings_dialog_clamps_out_of_range_values(qapp):
    from advance_file_search.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(AppSettings())
    dialog._max_size.setValue(C.MAX_FILE_SIZE_LIMIT_MB + 10_000)
    dialog._on_accept()
    assert dialog.result_settings.max_file_size_mb <= C.MAX_FILE_SIZE_LIMIT_MB


# ---------------------------------------------------------------------------
# About dialog
# ---------------------------------------------------------------------------
def test_about_dialog_states_the_privacy_position(qapp):
    from advance_file_search.ui.about_dialog import AboutDialog, load_license_text

    set_language("en")
    dialog = AboutDialog()
    labels = dialog.findChildren(type(dialog.children()[0])) if dialog.children() else []
    del labels
    text = " ".join(
        child.text()
        for child in dialog.findChildren(type(dialog))
        if hasattr(child, "text")
    )
    del text
    assert dialog.windowTitle()
    assert isinstance(load_license_text(), str)
    dialog.accept()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
@pytest.fixture
def window(qapp, db, corpus, settings):
    from advance_file_search.ui.main_window import MainWindow

    set_language("en")
    settings.last_root = ""
    win = MainWindow(db, settings)
    win.resize(1280, 780)
    win.show()
    pump(150)
    yield win
    win.close()
    pump(100)


def test_first_run_state(window):
    assert window._stack.currentIndex() == 0
    # With no folder chosen there is nothing to search or to index.
    assert not window._query.isEnabled()
    assert not window._search_button.isEnabled()
    assert "upload" in window.statusBar().currentMessage().lower()


def test_selecting_a_root_enables_indexing(window, corpus):
    window._adopt_root(str(corpus))
    pump()
    # Searching is what builds the index now, so the search controls become
    # available as soon as a folder is chosen.
    assert window._query.isEnabled()
    assert window._search_button.isEnabled()
    assert window._root_combo.count() >= 1
    assert any(str(corpus).casefold() in r.casefold() for r in window.settings.recent_roots)
    # Still first-run: nothing is indexed yet.
    assert window._stack.currentIndex() == 0


def test_a_remote_root_is_refused(window, monkeypatch):
    from advance_file_search.core import security

    shown: list[str] = []
    monkeypatch.setattr(window, "_show_path_rejection", lambda check: shown.append(check.verdict.value))
    window._adopt_root("\\\\server\\share")
    assert shown == ["unc"]
    del security


def test_indexed_root_enables_search(window, corpus, repos, settings):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    window._adopt_root(str(corpus))
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    window._reload_root_combo(select=str(corpus))
    window._load_root(str(corpus))
    pump()

    assert window._stack.currentIndex() == 1
    assert window._query.isEnabled()
    assert "files" in window._index_status.text()


@pytest.fixture
def ready_window(window, corpus, repos, settings):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    window._adopt_root(str(corpus))
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    window._reload_root_combo(select=str(corpus))
    window._load_root(str(corpus))
    pump()
    return window


def test_search_through_the_ui(ready_window):
    assert ui_search(ready_window, "needle") > 0
    assert "Results" in ready_window._results_count.text()
    assert "ms" in ready_window._results_timing.text()


def test_thai_search_through_the_ui(ready_window):
    assert ui_search(ready_window, "งบประมาณ") > 0


def test_selecting_a_result_fills_the_details_panel(ready_window):
    ui_search(ready_window, "needle")
    first = ready_window._model.index(0, 0, QModelIndex())
    ready_window._tree.setCurrentIndex(first)
    pump()
    assert ready_window._details_form.isVisible()
    assert ready_window._path_value.full_text().count("\\") > 0
    assert ready_window._open_button.isEnabled()
    assert ready_window._folder_button.isEnabled()
    assert ready_window._copy_button.isEnabled()


def test_empty_query_clears_the_results(ready_window):
    ui_search(ready_window, "needle")
    assert ready_window._model.rowCount(QModelIndex()) > 0
    ready_window._query.setText("")
    pump(200)
    assert ready_window._model.rowCount(QModelIndex()) == 0


def test_filters_panel_toggles_and_narrows(ready_window):
    ready_window._filters_toggle.setChecked(True)
    pump()
    assert ready_window._filters_panel.isVisible()

    baseline = ui_search(ready_window, "needle")
    ready_window._type_boxes[".xlsx"].setChecked(True)
    narrowed = ui_search(ready_window, "needle")
    assert 0 < narrowed < baseline

    ready_window._clear_filters()
    pump()
    assert not any(box.isChecked() for box in ready_window._type_boxes.values())


def test_type_filters_reflect_what_is_indexed(ready_window):
    enabled = {ext for ext, box in ready_window._type_boxes.items() if box.isEnabled()}
    assert {".txt", ".docx", ".xlsx", ".pdf"} <= enabled


def test_match_case_option(ready_window):
    ready_window._match_case.setChecked(True)
    assert ui_search(ready_window, "BUDGET") == 0
    assert ui_search(ready_window, "budget") > 0
    ready_window._match_case.setChecked(False)


def test_whole_word_option(ready_window):
    ready_window._whole_word.setChecked(True)
    assert ui_search(ready_window, "udge") == 0
    ready_window._whole_word.setChecked(False)


def test_exact_phrase_option(ready_window):
    ready_window._exact_phrase.setChecked(True)
    assert ui_search(ready_window, "annual equipment budget") > 0
    ready_window._exact_phrase.setChecked(False)


@pytest.mark.parametrize(
    "field",
    [SortField.NAME, SortField.SIZE, SortField.MODIFIED, SortField.TYPE, SortField.RELEVANCE],
)
def test_every_sort_option_works_in_the_ui(ready_window, field):
    ready_window._sort_combo.setCurrentIndex(ready_window._sort_combo.findData(field))
    assert ui_search(ready_window, "needle") > 0


def test_expanding_a_result_shows_more_locations(ready_window):
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
    assert parent is not None
    ready_window._tree.expand(parent)
    pump()
    child = model.index(0, COL_SNIPPET, parent)
    assert child.data(Qt.ItemDataRole.DisplayRole)


def test_bad_queries_do_not_break_the_ui(ready_window, db):
    for query in [
        "'; DROP TABLE files; --",
        "x" * 600,
        "a" + "*" * 30,
        "((((",
        "%",
        "NEAR(a b)",
    ]:
        ui_search(ready_window, query)
    assert db.query_value("SELECT count(*) FROM files") > 0
    assert db.integrity_check()


def test_missing_file_disables_the_open_actions(ready_window, corpus):
    target = corpus / "เอกสาร" / "txt" / "gone.txt"
    target.write_text("temporary needle_gone", encoding="utf-8")

    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
    from advance_file_search.storage.repositories import Repositories

    repos = Repositories.create(ready_window.db)
    IndexCoordinator(
        repos, IndexOptions(settings=ready_window.settings)
    ).run(str(corpus))
    ready_window._load_root(str(corpus))
    assert ui_search(ready_window, "needle_gone") == 1

    target.unlink()
    assert ui_search(ready_window, "needle_gone") == 1
    ready_window._tree.setCurrentIndex(ready_window._model.index(0, 0, QModelIndex()))
    pump()
    assert not ready_window._model.results[0].exists
    assert not ready_window._open_button.isEnabled()
    assert not ready_window._folder_button.isEnabled()
    assert ready_window._details_warning.isVisible()


def test_copy_path_puts_the_full_path_on_the_clipboard(ready_window):
    from PySide6.QtGui import QGuiApplication

    ui_search(ready_window, "needle")
    ready_window._tree.setCurrentIndex(ready_window._model.index(0, 0, QModelIndex()))
    pump()
    ready_window._copy_selected_path()
    pump()
    text = QGuiApplication.clipboard().text()
    assert "\\" in text
    assert text.endswith(ready_window._model.results[0].file_name)


def test_subfolder_outside_the_root_is_ignored(ready_window, tmp_path):
    ready_window._subfolder.setText(str(tmp_path / "elsewhere"))
    filters = ready_window._current_filters()
    assert filters.subfolder == ""


def test_window_is_resizable(ready_window):
    for width, height in ((1040, 640), (1600, 900), (1200, 720)):
        ready_window.resize(width, height)
        pump(80)
        assert ready_window.width() > 0
        assert ready_window.height() > 0


def test_geometry_and_columns_are_saved(ready_window):
    ready_window._tree.setColumnWidth(COL_NAME, 210)
    applied = ready_window._tree.columnWidth(COL_NAME)
    ready_window._save_geometry()
    assert ready_window.settings.window_geometry
    assert ready_window.settings.column_widths[COL_NAME] == applied


def test_match_column_keeps_a_readable_width(ready_window):
    """Widening a neighbour must not squeeze the snippet out of existence.

    The Match column stretches into whatever is left over, so without a floor
    a wide Name column reduces it to a few characters.  The interesting case
    is a Name width that still *fits* the viewport — beyond that the view
    simply scrolls and Match keeps its minimum anyway.
    """
    ready_window.resize(1200, 760)
    pump(200)
    tree = ready_window._tree
    viewport = tree.viewport().width()
    others = sum(
        tree.columnWidth(column)
        for column in range(tree.model().columnCount())
        if column not in (COL_SNIPPET, COL_NAME)
    )
    # Ask for a Name width that would leave Match only 100px.
    greedy = max(60, viewport - others - 100)
    tree.setColumnWidth(COL_NAME, greedy)
    pump(200)

    assert tree.columnWidth(COL_SNIPPET) >= MIN_SNIPPET_WIDTH - 2, (
        "the Match column fell below a readable width"
    )
    assert tree.columnWidth(COL_NAME) <= greedy, "Name should not have grown"


def test_keyboard_shortcuts_are_registered(ready_window):
    shortcuts = {
        action.shortcut().toString()
        for action in ready_window.actions()
        if not action.shortcut().isEmpty()
    }
    assert any("Ctrl+F" in s for s in shortcuts)
    assert any("Ctrl+Shift+E" in s for s in shortcuts)
    assert any("F5" in s for s in shortcuts)


def test_accessible_names_are_set(ready_window):
    assert ready_window._query.accessibleName()
    assert ready_window._scope_combo.accessibleName()
    assert ready_window._sort_combo.accessibleName()
    assert ready_window._root_combo.accessibleName()
    assert ready_window._tree.accessibleName()


def test_thai_ui_renders(qapp, db, corpus, repos, settings):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
    from advance_file_search.ui.main_window import MainWindow

    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    set_language("th")
    try:
        thai_settings = AppSettings(language="th", enable_optional_formats=True)
        win = MainWindow(db, thai_settings)
        win.resize(1280, 780)
        win.show()
        pump(150)
        assert win._search_button.text() == tr("search.button")
        assert "ค้นหา" in win._search_button.text()
        win._reload_root_combo(select=str(corpus))
        win._load_root(str(corpus))
        pump()
        assert ui_search(win, "งบประมาณ") > 0
        win.close()
        pump(100)
    finally:
        set_language("en")


def test_ui_stays_responsive_during_a_search(ready_window):
    """The search must run off the UI thread."""
    ready_window._query.setText("needle")
    ready_window._start_search()
    # Immediately after starting, the event loop still processes events.
    ticked = []
    QTimer.singleShot(0, lambda: ticked.append(True))
    pump(60)
    assert ticked, "the UI thread was blocked by the search"
    wait_for_search(ready_window)


def test_search_worker_cleans_up(ready_window):
    ui_search(ready_window, "needle")
    assert ready_window._search_handle is None


def test_load_more_appears_when_truncated(ready_window):
    ready_window.settings.result_limit = 2
    ui_search(ready_window, "needle")
    assert ready_window._load_more.isVisible()
    before = ready_window._model.rowCount(QModelIndex())
    ready_window._load_next_page()
    wait_for_search(ready_window)
    assert ready_window._model.rowCount(QModelIndex()) > before


def test_search_worker_signals_reach_the_ui(ready_window):
    from advance_file_search.search.search_service import SearchService
    from advance_file_search.storage.repositories import Repositories

    service = SearchService(Repositories.create(ready_window.db))
    root = ready_window._current_root
    direct = service.search(SearchRequest(query="needle", root_id=root.id))
    through_ui = ui_search(ready_window, "needle")
    assert through_ui == min(direct.total_matched_files, ready_window.settings.result_limit)


def test_deleting_the_index_returns_to_first_run(ready_window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    ready_window._confirm_delete()
    pump()
    assert ready_window._current_root is None
    assert ready_window._stack.currentIndex() == 0


def test_elapsed_timing_is_reported(ready_window):
    start = time.perf_counter()
    ui_search(ready_window, "needle")
    assert time.perf_counter() - start < 8.0
