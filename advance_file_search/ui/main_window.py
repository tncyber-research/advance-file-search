"""Main application window.

Layout follows handoff §11.2: a root selector and index-status bar, a search
bar with collapsible advanced filters, a grouped result tree with a details
panel, and an action row.

Threading: every database operation that could take more than a few
milliseconds runs in a worker thread (see ``ui.workers``).  The UI thread only
builds widgets and reacts to signals.
"""

from __future__ import annotations

import contextlib
import time
from datetime import datetime, timedelta
from pathlib import PureWindowsPath

from PySide6.QtCore import QDate, QModelIndex, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.i18n import (
    file_status_label,
    set_language,
    tr,
)
from advance_file_search.core.models import (
    IndexProgress,
    IndexSummary,
    Root,
    RunStatus,
    SearchFilters,
    SearchRequest,
    SearchResponse,
    SearchScope,
    SortField,
)
from advance_file_search.core.security import PathVerdict, validate_root
from advance_file_search.core.settings import AppSettings, save_settings
from advance_file_search.logging_setup import get_logger, set_log_paths_enabled
from advance_file_search.storage.database import Database, DatabaseError
from advance_file_search.storage.repositories import Repositories
from advance_file_search.ui.about_dialog import AboutDialog
from advance_file_search.ui.delegates import HighlightDelegate, RowActionsDelegate
from advance_file_search.ui.index_dialog import IndexDialog
from advance_file_search.ui.preview import MatchPreview
from advance_file_search.ui.result_model import (
    COL_MODIFIED,
    COL_NAME,
    COL_OPEN,
    COL_SIZE,
    COL_SNIPPET,
    COL_TYPE,
    COLUMN_COUNT,
    DEFAULT_COLUMN_WIDTHS,
    MIN_SECTION_WIDTH,
    MIN_SNIPPET_WIDTH,
    ROLE_IS_CHILD,
    ROLE_LOCATION,
    ROLE_RESULT,
    ResultModel,
    format_timestamp,
    match_source_label,
)
from advance_file_search.ui.settings_dialog import SettingsDialog
from advance_file_search.ui.theme import RESULT_ROW_HEIGHT
from advance_file_search.ui.widgets import ElidedPathLabel
from advance_file_search.ui.workers import IndexWorker, SearchWorker, WorkerHandle
from advance_file_search.winplat import windows_shell
from advance_file_search.winplat.windows_paths import unc_target_of_drive

log = get_logger("ui.main")

#: Delay before a keystroke triggers a search, in milliseconds.
SEARCH_DEBOUNCE_MS = 260

#: How often an explicit search may trigger a background index refresh, per
#: root.  Without a throttle, pressing Search repeatedly would re-scan the
#: whole folder tree each time.
AUTO_REFRESH_INTERVAL_SECONDS = 20.0

_VERDICT_MESSAGES = {
    PathVerdict.UNC: "error.network_path",
    PathVerdict.URL: "error.network_path",
    PathVerdict.DEVICE: "error.device_path",
    PathVerdict.NOT_FOUND: "error.not_found",
    PathVerdict.NOT_A_DIRECTORY: "error.not_a_directory",
    PathVerdict.CDROM: "error.cdrom",
    PathVerdict.UNKNOWN_DRIVE: "error.unknown_drive",
    PathVerdict.NO_DRIVE: "error.no_drive",
    PathVerdict.EMPTY: "error.no_root",
}

#: Rows of the details panel, in order.  Relative path and file type are
#: deliberately absent: both are already columns in the result table, and
#: repeating them pushes down the information that is not.
_DETAIL_FIELDS = (
    "details.full_path",
    "details.size",
    "details.created",
    "details.modified",
    "details.match_source",
)

_SORT_FIELDS = (
    (SortField.RELEVANCE, "search.sort_relevance"),
    (SortField.NAME, "search.sort_name"),
    (SortField.MODIFIED, "search.sort_modified"),
    (SortField.SIZE, "search.sort_size"),
    (SortField.TYPE, "search.sort_type"),
    (SortField.PATH, "search.sort_path"),
)


class MainWindow(QMainWindow):
    """The application's only top-level window."""

    def __init__(self, db: Database, settings: AppSettings) -> None:
        super().__init__()
        self.db = db
        self.repos = Repositories.create(db)
        self.settings = settings

        self._current_root: Root | None = None
        self._index_handle: WorkerHandle | None = None
        self._search_handle: WorkerHandle | None = None
        self._index_dialog: IndexDialog | None = None
        self._loaded_offset = 0
        self._last_response: SearchResponse | None = None

        # Auto-indexing state.  There is no Update Index button any more:
        # searching builds the index when it is missing and refreshes it in the
        # background when it is not.
        self._background_index = False
        self._pending_query_after_index = False
        self._last_auto_refresh: dict[str, float] = {}
        self._adjusting_columns = False

        self.setWindowTitle(tr("app.title"))
        self.setMinimumSize(1040, 640)
        # A first run with no saved geometry gets a size the table actually
        # fits in, rather than whatever the layout's sizeHint produces.
        self.resize(1400, 840)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._start_search)

        self._build_ui()
        self._build_shortcuts()
        self._restore_geometry()
        self._restore_last_root()
        self._refresh_enabled_state()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 10)
        outer.setSpacing(10)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_root_bar())
        outer.addWidget(self._build_search_bar())
        self._filters_panel = self._build_filters_panel()
        outer.addWidget(self._filters_panel)
        outer.addWidget(self._build_results_area(), 1)
        outer.addWidget(self._build_action_bar())

        self.setCentralWidget(central)
        self.statusBar().showMessage(tr("privacy.statement"))

    def _build_header(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(8)

        title = QLabel(tr("app.title"))
        title.setObjectName("SectionTitle")
        row.addWidget(title)

        offline = QLabel(tr("about.offline"))
        offline.setObjectName("StatusPill")
        offline.setToolTip(tr("privacy.statement"))
        row.addWidget(offline)
        row.addStretch(1)

        self._index_menu_button = QToolButton()
        self._index_menu_button.setText(tr("index.status_label").rstrip(":"))
        self._index_menu_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        menu = QMenu(self._index_menu_button)
        self._action_update = menu.addAction(tr("index.update"))
        self._action_update.triggered.connect(lambda: self._start_index(rebuild=False))
        self._action_rebuild = menu.addAction(tr("index.rebuild"))
        self._action_rebuild.triggered.connect(self._confirm_rebuild)
        self._action_delete = menu.addAction(tr("index.delete"))
        self._action_delete.triggered.connect(self._confirm_delete)
        menu.addSeparator()
        open_data = menu.addAction(tr("index.open_data_folder"))
        open_data.triggered.connect(lambda: windows_shell.open_data_folder())
        menu.addSeparator()
        # About keeps the privacy statement and the third-party licence
        # notices, so it stays reachable even though the toolbar button it used
        # to occupy now opens the manual.
        about_action = menu.addAction(tr("menu.about"))
        about_action.triggered.connect(self._open_about)
        self._index_menu_button.setMenu(menu)
        row.addWidget(self._index_menu_button)

        self._settings_button = QToolButton()
        self._settings_button.setText(tr("menu.settings"))
        self._settings_button.clicked.connect(self._open_settings)
        row.addWidget(self._settings_button)

        self._manual_button = QToolButton()
        self._manual_button.setText(tr("menu.manual"))
        self._manual_button.setToolTip(tr("menu.manual_tooltip"))
        self._manual_button.clicked.connect(self._open_manual)
        row.addWidget(self._manual_button)
        return bar

    def _build_root_bar(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        label = QLabel(tr("root.label"))
        label.setObjectName("Muted")
        grid.addWidget(label, 0, 0)

        self._root_combo = QComboBox()
        self._root_combo.setEditable(False)
        self._root_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._root_combo.setAccessibleName(tr("root.label"))
        self._root_combo.setToolTip(tr("root.recent"))
        self._root_combo.activated.connect(self._on_root_selected)
        grid.addWidget(self._root_combo, 0, 1)

        # Kept as an attribute so the manual's capture script can point at it;
        # the first-run panel has a button with the same label, and telling the
        # two apart by text alone is fragile.
        self._browse_button = QPushButton(tr("root.select"))
        self._browse_button.clicked.connect(self._choose_root)
        self._browse_button.setAccessibleName(tr("root.dialog_title"))
        grid.addWidget(self._browse_button, 0, 2)

        status_label = QLabel(tr("index.status_label"))
        status_label.setObjectName("Muted")
        grid.addWidget(status_label, 1, 0)

        self._index_status = QLabel(tr("index.status_none"))
        self._index_status.setObjectName("Muted")
        self._index_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        grid.addWidget(self._index_status, 1, 1, 1, 2)

        grid.setColumnStretch(1, 1)
        return card

    def _build_search_bar(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(8)

        self._query = QLineEdit()
        self._query.setObjectName("SearchBox")
        self._query.setPlaceholderText(tr("search.placeholder"))
        self._query.setClearButtonEnabled(True)
        self._query.setMaxLength(C.MAX_QUERY_LENGTH)
        self._query.setAccessibleName(tr("search.placeholder"))
        self._query.setToolTip(tr("search.wildcard_help"))
        self._query.textChanged.connect(self._on_query_changed)
        # Enter and the Search button go through _search_now, which builds or
        # refreshes the index first.  Debounced typing does not: re-scanning the
        # folder on every keystroke would be unusable.
        self._query.returnPressed.connect(self._search_now)
        row.addWidget(self._query, 1)

        self._search_button = QPushButton(tr("search.button"))
        self._search_button.setObjectName("Primary")
        self._search_button.setToolTip(tr("index.auto_hint"))
        self._search_button.clicked.connect(self._search_now)
        row.addWidget(self._search_button)

        self._scope_combo = QComboBox()
        self._scope_combo.addItem(tr("search.scope_both"), SearchScope.BOTH)
        self._scope_combo.addItem(tr("search.scope_name"), SearchScope.NAME_ONLY)
        self._scope_combo.addItem(tr("search.scope_content"), SearchScope.CONTENT_ONLY)
        default_scope = {
            "both": SearchScope.BOTH,
            "name": SearchScope.NAME_ONLY,
            "content": SearchScope.CONTENT_ONLY,
        }.get(self.settings.default_scope, SearchScope.BOTH)
        self._scope_combo.setCurrentIndex(max(0, self._scope_combo.findData(default_scope)))
        self._scope_combo.setAccessibleName(tr("search.scope"))
        self._scope_combo.currentIndexChanged.connect(self._on_filters_changed)
        row.addWidget(self._scope_combo)

        self._filters_toggle = QToolButton()
        self._filters_toggle.setText(tr("search.advanced") + " ▾")
        self._filters_toggle.setCheckable(True)
        self._filters_toggle.toggled.connect(self._toggle_filters)
        row.addWidget(self._filters_toggle)
        return card

    def _build_filters_panel(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        card.setVisible(False)
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)

        self._match_case = QCheckBox(tr("search.match_case"))
        self._match_case.toggled.connect(self._on_filters_changed)
        grid.addWidget(self._match_case, 0, 0)

        self._exact_phrase = QCheckBox(tr("search.exact_phrase"))
        self._exact_phrase.toggled.connect(self._on_filters_changed)
        grid.addWidget(self._exact_phrase, 0, 1)

        self._whole_word = QCheckBox(tr("search.whole_word"))
        self._whole_word.toggled.connect(self._on_filters_changed)
        grid.addWidget(self._whole_word, 0, 2)

        types_label = QLabel(tr("search.file_types"))
        types_label.setObjectName("Muted")
        grid.addWidget(types_label, 1, 0)
        types_row = QHBoxLayout()
        types_row.setSpacing(10)
        self._type_boxes: dict[str, QCheckBox] = {}
        for extension in sorted(C.SUPPORTED_EXTENSIONS):
            box = QCheckBox(extension)
            box.toggled.connect(self._on_filters_changed)
            self._type_boxes[extension] = box
            types_row.addWidget(box)
        types_row.addStretch(1)
        holder = QWidget()
        holder.setLayout(types_row)
        grid.addWidget(holder, 1, 1, 1, 4)

        from_label = QLabel(tr("search.modified_from"))
        from_label.setObjectName("Muted")
        grid.addWidget(from_label, 2, 0)
        self._date_from = self._make_date_edit()
        grid.addWidget(self._date_from, 2, 1)

        to_label = QLabel(tr("search.modified_to"))
        to_label.setObjectName("Muted")
        grid.addWidget(to_label, 2, 2)
        self._date_to = self._make_date_edit()
        grid.addWidget(self._date_to, 2, 3)

        size_min_label = QLabel(tr("search.size_min"))
        size_min_label.setObjectName("Muted")
        grid.addWidget(size_min_label, 3, 0)
        self._size_min = QSpinBox()
        self._size_min.setRange(0, 1024 * 1024)
        self._size_min.setSpecialValueText(" ")
        self._size_min.setAccessibleName(tr("search.size_min"))
        self._size_min.valueChanged.connect(self._on_filters_changed)
        grid.addWidget(self._size_min, 3, 1)

        size_max_label = QLabel(tr("search.size_max"))
        size_max_label.setObjectName("Muted")
        grid.addWidget(size_max_label, 3, 2)
        self._size_max = QSpinBox()
        self._size_max.setRange(0, 1024 * 1024)
        self._size_max.setSpecialValueText(" ")
        self._size_max.setAccessibleName(tr("search.size_max"))
        self._size_max.valueChanged.connect(self._on_filters_changed)
        grid.addWidget(self._size_max, 3, 3)

        sub_label = QLabel(tr("search.subfolder"))
        sub_label.setObjectName("Muted")
        grid.addWidget(sub_label, 4, 0)
        self._subfolder = QLineEdit()
        self._subfolder.setPlaceholderText(tr("root.placeholder"))
        self._subfolder.setAccessibleName(tr("search.subfolder"))
        self._subfolder.textChanged.connect(self._on_filters_changed)
        grid.addWidget(self._subfolder, 4, 1, 1, 3)
        pick = QPushButton(tr("root.select"))
        pick.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        pick.clicked.connect(self._choose_subfolder)
        grid.addWidget(pick, 4, 4, Qt.AlignmentFlag.AlignLeft)

        clear = QPushButton(tr("search.clear_filters"))
        clear.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        clear.clicked.connect(self._clear_filters)
        grid.addWidget(clear, 5, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)

        grid.setColumnStretch(4, 1)
        return card

    def _make_date_edit(self) -> QDateEdit:
        """A date field whose minimum doubles as "no filter".

        ``specialValueText`` renders the minimum as blank, so an unset range
        reads as empty rather than as a misleading 1980 date.
        """
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        edit.setMinimumDate(QDate(1980, 1, 1))
        edit.setMaximumDate(QDate(2200, 12, 31))
        edit.setSpecialValueText(" ")
        edit.setDate(edit.minimumDate())
        edit.setAccessibleName(tr("search.modified_from"))
        edit.dateChanged.connect(self._on_filters_changed)
        return edit

    def _build_results_area(self) -> QWidget:
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_first_run_page())
        self._stack.addWidget(self._build_results_page())
        return self._stack

    def _build_first_run_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("Card")
        box = QVBoxLayout(page)
        box.setContentsMargins(40, 40, 40, 40)
        box.setSpacing(14)
        box.addStretch(1)

        heading = QLabel(tr("firstrun.heading"))
        heading.setObjectName("Heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(heading)

        body = QLabel(tr("firstrun.body"))
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setMaximumWidth(620)
        box.addWidget(body, 0, Qt.AlignmentFlag.AlignCenter)

        steps = QLabel(
            "\n".join([tr("firstrun.step1"), tr("firstrun.step2"), tr("firstrun.step3")])
        )
        steps.setObjectName("Muted")
        box.addWidget(steps, 0, Qt.AlignmentFlag.AlignCenter)

        self._firstrun_button = QPushButton(tr("root.select"))
        self._firstrun_button.setObjectName("Primary")
        self._firstrun_button.clicked.connect(self._choose_root)
        box.addWidget(self._firstrun_button, 0, Qt.AlignmentFlag.AlignCenter)

        self._firstrun_note = QLabel("")
        self._firstrun_note.setObjectName("Hint")
        self._firstrun_note.setWordWrap(True)
        self._firstrun_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self._firstrun_note, 0, Qt.AlignmentFlag.AlignCenter)
        box.addStretch(2)
        return page

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        self._results_count = QLabel(tr("search.results_count", count=0))
        self._results_count.setObjectName("SectionTitle")
        header.addWidget(self._results_count)
        self._results_timing = QLabel("")
        self._results_timing.setObjectName("Muted")
        header.addWidget(self._results_timing)

        # Shown while a background index refresh is running, so the user knows
        # the list may still change.
        self._index_activity = QLabel("")
        self._index_activity.setObjectName("StatusPill")
        self._index_activity.setVisible(False)
        header.addWidget(self._index_activity)
        header.addStretch(1)

        sort_label = QLabel(tr("search.sort"))
        sort_label.setObjectName("Muted")
        header.addWidget(sort_label)
        self._sort_combo = QComboBox()
        for field, key in _SORT_FIELDS:
            self._sort_combo.addItem(tr(key), field)
        self._sort_combo.setAccessibleName(tr("search.sort"))
        self._sort_combo.currentIndexChanged.connect(self._on_filters_changed)
        header.addWidget(self._sort_combo)

        self._load_more = QPushButton(tr("search.load_more"))
        self._load_more.setVisible(False)
        self._load_more.clicked.connect(self._load_next_page)
        header.addWidget(self._load_more)
        box.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._model = ResultModel(self)
        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        # Taller rows: the larger base font needs the room, and Thai vowels
        # and tone marks are clipped at the default height.
        self._tree.setStyleSheet(f"QTreeView::item {{ min-height: {RESULT_ROW_HEIGHT}px; }}")
        self._tree.setAllColumnsShowFocus(True)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.setItemDelegateForColumn(COL_NAME, HighlightDelegate(self._tree))
        self._tree.setItemDelegateForColumn(COL_SNIPPET, HighlightDelegate(self._tree))

        # The Open column holds two painted buttons rather than real
        # QPushButtons per row; see RowActionsDelegate.
        self._open_delegate = RowActionsDelegate(self._tree)
        self._open_delegate.clicked.connect(self._reveal_result)
        self._open_delegate.open_clicked.connect(self._open_result)
        self._tree.setItemDelegateForColumn(COL_OPEN, self._open_delegate)
        self._tree.setMouseTracking(True)  # so the button can show a hover state

        self._tree.setAccessibleName(tr("search.results_count", count=0))
        header_view = self._tree.header()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_view.setStretchLastSection(False)
        header_view.setMinimumSectionSize(MIN_SECTION_WIDTH)
        for column, width in enumerate(DEFAULT_COLUMN_WIDTHS):
            self._tree.setColumnWidth(column, width)
        # Match takes the slack.  Its own minimum is enforced separately,
        # because a stretched section otherwise collapses to the header's
        # global minimum and shows three characters of the snippet.
        header_view.setSectionResizeMode(COL_SNIPPET, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(COL_OPEN, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(COL_OPEN, DEFAULT_COLUMN_WIDTHS[COL_OPEN])
        header_view.sectionResized.connect(self._keep_snippet_readable)
        self._tree.selectionModel().currentChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._tree)

        splitter.addWidget(self._build_details_panel())
        # The details panel now carries the match preview and the full path, so
        # it needs more room than it did when it held only metadata.
        splitter.setSizes([900, 420])
        self._splitter = splitter
        box.addWidget(splitter, 1)

        self._empty_label = QLabel(tr("search.empty"))
        self._empty_label.setObjectName("Muted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setVisible(False)
        box.addWidget(self._empty_label)
        return page

    @Slot(int, int, int)
    def _keep_snippet_readable(self, index: int, old: int, new: int) -> None:
        """Stop the other columns from squeezing Match out of existence.

        The Match column stretches, so widening a neighbour takes space from
        it.  When it would drop below a readable width the neighbour gives the
        difference back instead.
        """
        del old, new
        if index == COL_SNIPPET or self._adjusting_columns:
            return
        if self._tree.columnWidth(COL_SNIPPET) >= MIN_SNIPPET_WIDTH:
            return

        # Clamp to the width that still leaves Match its minimum, rather than
        # subtracting the shortfall: the requested width can be far larger
        # than the view, and a single delta would not converge.
        viewport = self._tree.viewport().width()
        others = sum(
            self._tree.columnWidth(column)
            for column in range(COLUMN_COUNT)
            if column not in (COL_SNIPPET, index)
        )
        allowed = max(MIN_SECTION_WIDTH, viewport - others - MIN_SNIPPET_WIDTH)
        if self._tree.columnWidth(index) <= allowed:
            return
        self._adjusting_columns = True
        try:
            self._tree.setColumnWidth(index, allowed)
        finally:
            self._adjusting_columns = False

    def _build_details_panel(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(300)
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(10)

        heading = QLabel(tr("details.heading"))
        heading.setObjectName("SectionTitle")
        box.addWidget(heading)

        # The matching text sits at the top of the panel: it is what the user
        # is actually looking for, and it no longer has a column of its own.
        self._preview = MatchPreview()
        box.addWidget(self._preview)

        self._details_placeholder = QLabel(tr("details.none"))
        self._details_placeholder.setObjectName("Muted")
        self._details_placeholder.setWordWrap(True)
        box.addWidget(self._details_placeholder)

        # A two-column label/value grid.  Every value is one line: the path is
        # middle-elided rather than wrapped, so the panel stays compact and
        # nothing can be clipped at a narrow width.
        self._details_form = QWidget()
        form = QGridLayout(self._details_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        form.setColumnStretch(1, 1)

        self._detail_rows: dict[str, tuple[QLabel, QLabel]] = {}
        for row, key in enumerate(_DETAIL_FIELDS):
            caption = QLabel(tr(key))
            caption.setObjectName("Muted")
            caption.setAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            if key == "details.full_path":
                value: QLabel = ElidedPathLabel()
            else:
                value = QLabel("")
                value.setTextFormat(Qt.TextFormat.PlainText)
                value.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
            value.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            form.addWidget(caption, row, 0)
            form.addWidget(value, row, 1)
            self._detail_rows[key] = (caption, value)

        self._path_value = self._detail_rows["details.full_path"][1]
        self._details_form.setVisible(False)
        box.addWidget(self._details_form)
        box.addStretch(1)

        self._details_warning = QLabel("")
        self._details_warning.setObjectName("WarningPill")
        self._details_warning.setWordWrap(True)
        self._details_warning.setVisible(False)
        box.addWidget(self._details_warning)
        return card

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(8)

        self._open_button = QPushButton(tr("action.open_file"))
        self._open_button.clicked.connect(self._open_selected_file)
        row.addWidget(self._open_button)

        self._folder_button = QPushButton(tr("action.open_folder"))
        self._folder_button.clicked.connect(self._reveal_selected_file)
        row.addWidget(self._folder_button)

        self._copy_button = QPushButton(tr("action.copy_path"))
        self._copy_button.clicked.connect(self._copy_selected_path)
        row.addWidget(self._copy_button)
        row.addStretch(1)

        self._wildcard_hint = QLabel(tr("search.wildcard_help"))
        self._wildcard_hint.setObjectName("Hint")
        row.addWidget(self._wildcard_hint)
        return bar

    def _build_shortcuts(self) -> None:
        focus_search = QAction(self)
        focus_search.setShortcut(QKeySequence.StandardKey.Find)
        focus_search.triggered.connect(self._focus_search)
        self.addAction(focus_search)

        open_action = QAction(self)
        open_action.setShortcut(QKeySequence(Qt.Key.Key_Return))
        open_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self._tree.addAction(open_action)
        open_action.triggered.connect(self._open_selected_file)

        reveal_action = QAction(self)
        reveal_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        reveal_action.triggered.connect(self._reveal_selected_file)
        self.addAction(reveal_action)

        copy_action = QAction(self)
        copy_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_action.triggered.connect(self._copy_selected_path)
        self.addAction(copy_action)

        refresh_action = QAction(self)
        refresh_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        refresh_action.triggered.connect(self._force_index_refresh)
        self.addAction(refresh_action)

        filters_action = QAction(self)
        filters_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        filters_action.triggered.connect(
            lambda: self._filters_toggle.setChecked(not self._filters_toggle.isChecked())
        )
        self.addAction(filters_action)

    # ------------------------------------------------------------------
    # root handling
    # ------------------------------------------------------------------
    def _choose_root(self) -> None:
        start = self.settings.last_root or str(pathutil.safe_path("C:\\"))
        chosen = QFileDialog.getExistingDirectory(
            self,
            tr("root.dialog_title"),
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if not chosen:
            return
        self._adopt_root(chosen)

    def _adopt_root(self, raw_path: str) -> None:
        """Validate and select a root, refusing anything non-local."""
        check = validate_root(raw_path)
        if not check.ok:
            self._show_path_rejection(check)
            return

        if pathutil.is_drive_root(check.display):
            answer = QMessageBox.question(
                self,
                tr("confirm.drive_scan_title"),
                tr("confirm.drive_scan_body", drive=check.display),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return

        self.settings.remember_root(check.display)
        save_settings(self.settings)
        self._reload_root_combo(select=check.display)
        self._load_root(check.display)

    def _show_path_rejection(self, check: object) -> None:
        verdict = getattr(check, "verdict", PathVerdict.EMPTY)
        display = getattr(check, "display", "")
        if verdict is PathVerdict.REMOTE_DRIVE:
            target = unc_target_of_drive(pathutil.drive_letter(display))
            message = tr("error.remote_drive", path=display)
            if target:
                message = f"{message}\n({target})"
        else:
            message = tr(_VERDICT_MESSAGES.get(verdict, "error.not_found"))
        QMessageBox.warning(self, tr("error.title"), message)
        log.info("root rejected | verdict=%s", getattr(verdict, "value", verdict))

    def _reload_root_combo(self, *, select: str = "") -> None:
        self._root_combo.blockSignals(True)
        self._root_combo.clear()
        try:
            indexed = {
                pathutil.normalized_path(root.display_path): root
                for root in self.repos.roots.list_all()
            }
        except DatabaseError:
            indexed = {}

        entries: list[str] = []
        for path in self.settings.recent_roots:
            entries.append(path)
        for root in indexed.values():
            if pathutil.normalized_path(root.display_path) not in {
                pathutil.normalized_path(entry) for entry in entries
            }:
                entries.append(root.display_path)

        if not entries:
            self._root_combo.addItem(tr("root.placeholder"), "")
        for path in entries:
            check = validate_root(path)
            label = path if check.ok else f"{path}  {tr('root.unavailable')}"
            self._root_combo.addItem(label, path)
            position = self._root_combo.count() - 1
            if not check.ok:
                self._root_combo.setItemData(
                    position,
                    tr(_VERDICT_MESSAGES.get(check.verdict, "error.not_found")),
                    Qt.ItemDataRole.ToolTipRole,
                )
        if select:
            index = self._root_combo.findData(select)
            if index < 0:
                index = next(
                    (
                        position
                        for position in range(self._root_combo.count())
                        if pathutil.normalized_path(
                            str(self._root_combo.itemData(position) or "")
                        )
                        == pathutil.normalized_path(select)
                    ),
                    -1,
                )
            if index >= 0:
                self._root_combo.setCurrentIndex(index)
        self._root_combo.blockSignals(False)

    @Slot(int)
    def _on_root_selected(self, index: int) -> None:
        path = str(self._root_combo.itemData(index) or "")
        if not path:
            return
        check = validate_root(path)
        if not check.ok:
            self._show_path_rejection(check)
            return
        self._load_root(check.display)

    def _restore_last_root(self) -> None:
        self._reload_root_combo(select=self.settings.last_root)
        if not self.settings.last_root:
            self._stack.setCurrentIndex(0)
            return
        check = validate_root(self.settings.last_root)
        if check.ok:
            self._load_root(check.display)
        else:
            self._stack.setCurrentIndex(0)
            self._firstrun_note.setText(
                tr(_VERDICT_MESSAGES.get(check.verdict, "error.not_found"))
            )

    def _load_root(self, display: str) -> None:
        try:
            root = self.repos.roots.find_by_path(display)
        except DatabaseError as exc:
            log.warning("could not read root | %s", exc)
            root = None
        self._current_root = root
        self.settings.last_root = display
        self._update_index_status(display, root)
        self._model.clear()
        self._clear_details()
        if root is None or root.file_count == 0:
            self._stack.setCurrentIndex(0)
            self._firstrun_note.setText(tr("search.no_index"))
        else:
            self._stack.setCurrentIndex(1)
            self._populate_type_filter(root.id)
            if self._query.text().strip():
                self._start_search()
        self._refresh_enabled_state()

    def _update_index_status(self, display: str, root: Root | None) -> None:
        if root is None or root.file_count == 0:
            self._index_status.setText(
                f"{tr('index.status_none')}  ·  {tr('index.auto_hint')}"
            )
            return
        status_text = {
            RunStatus.COMPLETED.value: tr("index.status_ready"),
            RunStatus.CANCELLED.value: tr("index.status_cancelled"),
            RunStatus.FAILED.value: tr("index.status_failed"),
            RunStatus.RUNNING.value: tr("index.status_running"),
        }.get(root.last_index_status or "", tr("index.status_none"))
        when = _format_iso(root.last_index_completed_at) or tr("index.never")
        self._index_status.setText(
            f"{status_text}  ·  {tr('index.files_count', count=root.file_count)}"
            f"  ·  {tr('index.updated', when=when)}"
        )

    def _populate_type_filter(self, root_id: int) -> None:
        """Enable only the file-type checkboxes that exist in this index."""
        try:
            present = {extension for extension, _ in self.repos.files.extensions_for_root(root_id)}
        except DatabaseError:
            present = set()
        for extension, box in self._type_boxes.items():
            available = extension in present
            box.setEnabled(available)
            if not available and box.isChecked():
                box.setChecked(False)
            box.setToolTip("" if available else tr("search.no_index"))

    # ------------------------------------------------------------------
    # indexing
    # ------------------------------------------------------------------
    def _start_index(self, *, rebuild: bool) -> None:
        if self._index_handle is not None and self._index_handle.running:
            return
        path = str(self._root_combo.currentData() or self.settings.last_root or "")
        check = validate_root(path)
        if not check.ok:
            self._show_path_rejection(check)
            return

        self._cancel_search()
        self._background_index = False
        dialog = IndexDialog(self)
        self._index_dialog = dialog

        worker = IndexWorker(
            str(self.db.path), check.display, self.settings, rebuild=rebuild
        )
        handle = WorkerHandle(worker)
        self._index_handle = handle
        worker.progress.connect(self._on_index_progress)
        worker.finished.connect(self._on_index_finished)
        worker.failed.connect(self._on_index_failed)

        # A local timer forwards the dialog's cancel request to the worker,
        # because the dialog cannot touch the worker thread directly.
        watcher = QTimer(dialog)
        watcher.setInterval(150)
        watcher.timeout.connect(
            lambda: worker.cancel() if dialog.cancel_requested else None
        )
        watcher.start()

        self._refresh_enabled_state()
        handle.start()
        dialog.exec()

    @Slot(object)
    def _on_index_progress(self, progress: object) -> None:
        if self._index_dialog is not None and isinstance(progress, IndexProgress):
            self._index_dialog.update_progress(progress)

    @Slot(object)
    def _on_index_finished(self, summary: object) -> None:
        if not isinstance(summary, IndexSummary):
            return
        if self._index_dialog is not None:
            self._index_dialog.show_summary(summary)
        self._finish_index_worker()
        path = str(self._root_combo.currentData() or self.settings.last_root or "")
        if path:
            self._last_auto_refresh[pathutil.normalized_path(path)] = time.monotonic()
            self._reload_root_combo(select=path)
            self._load_root(pathutil.display_path(path))

        # A search that triggered the first index build runs as soon as the
        # index exists, so the user does not have to press Search twice.
        if self._pending_query_after_index:
            self._pending_query_after_index = False
            if self._query.text().strip() and self._current_root is not None:
                self._start_search()

    @Slot(str)
    def _on_index_failed(self, message_key: str) -> None:
        self._pending_query_after_index = False
        if self._index_dialog is not None:
            self._index_dialog.show_error(tr(message_key))
        self._finish_index_worker()

    def _finish_index_worker(self) -> None:
        handle = self._index_handle
        self._index_handle = None
        if handle is not None:
            handle.stop()
        self._refresh_enabled_state()

    def _force_index_refresh(self) -> None:
        """Manual update (F5 / index menu), bypassing the refresh throttle."""
        path = str(self._root_combo.currentData() or self.settings.last_root or "")
        if path:
            self._last_auto_refresh.pop(pathutil.normalized_path(path), None)
        self._start_index(rebuild=False)

    def _confirm_rebuild(self) -> None:
        count = self._current_root.file_count if self._current_root else 0
        answer = QMessageBox.question(
            self,
            tr("confirm.rebuild_title"),
            tr("confirm.rebuild_body", count=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._start_index(rebuild=True)

    def _confirm_delete(self) -> None:
        root = self._current_root
        if root is None:
            return
        answer = QMessageBox.question(
            self,
            tr("confirm.delete_title"),
            tr("confirm.delete_body", count=root.file_count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        try:
            self.repos.roots.delete(root.id)
            self.db.vacuum()
        except DatabaseError as exc:
            log.error("delete index failed | %s", exc)
            QMessageBox.warning(self, tr("error.title"), tr("error.unexpected"))
            return
        self.settings.forget_root(root.display_path)
        save_settings(self.settings)
        self._current_root = None
        self._model.clear()
        self._reload_root_combo(select=self.settings.last_root)
        self._restore_last_root()
        self._refresh_enabled_state()

    # ------------------------------------------------------------------
    # searching
    # ------------------------------------------------------------------
    @Slot(str)
    def _on_query_changed(self, text: str) -> None:
        if not text.strip():
            self._debounce.stop()
            self._cancel_search()
            self._model.clear()
            self._update_result_header(None)
            self._reset_status_message()
            return
        self._debounce.start()

    def _on_filters_changed(self, *_args: object) -> None:
        if self._query.text().strip():
            self._debounce.start()

    def _current_filters(self) -> SearchFilters:
        extensions = frozenset(
            extension for extension, box in self._type_boxes.items() if box.isChecked()
        )
        modified_after: float | None = None
        modified_before: float | None = None
        if self._date_from.date() > self._date_from.minimumDate():
            modified_after = _date_to_epoch(self._date_from.date(), end_of_day=False)
        if self._date_to.date() > self._date_to.minimumDate():
            modified_before = _date_to_epoch(self._date_to.date(), end_of_day=True)
        min_size = self._size_min.value() * 1024 if self._size_min.value() else None
        max_size = self._size_max.value() * 1024 if self._size_max.value() else None

        subfolder = self._subfolder.text().strip()
        if (
            subfolder
            and self._current_root is not None
            and not pathutil.is_within_root(
                subfolder, self._current_root.display_path
            )
        ):
            subfolder = ""
        return SearchFilters(
            extensions=extensions,
            modified_after=modified_after,
            modified_before=modified_before,
            min_size_bytes=min_size,
            max_size_bytes=max_size,
            subfolder=subfolder,
        )

    # -- auto-indexing ----------------------------------------------------
    def _search_now(self) -> None:
        """Entry point for an explicit search (button press or Enter).

        Indexing is no longer a separate button the user has to remember.
        Pressing Search makes sure the index is usable first:

        * **no index yet** — build it, with the progress dialog, then search;
        * **index exists** — search immediately against what is already there,
          and refresh it in the background so the next result set is current.

        Searching against the existing index first matters: a user who just
        typed a query wants results now, not after a scan of their documents
        folder.  If the background refresh actually changes something, the
        search is re-run and the list updates itself.
        """
        query = self._query.text().strip()
        if not query:
            return

        path = str(self._root_combo.currentData() or self.settings.last_root or "")
        check = validate_root(path)
        if not check.ok:
            if path:
                self._show_path_rejection(check)
            else:
                self.statusBar().showMessage(tr("error.no_root"), 5000)
            return

        if self._index_handle is not None and self._index_handle.running:
            return

        root = self._current_root
        if root is None or root.file_count == 0:
            # First search for this folder: the index has to exist before there
            # is anything to search, so this one is worth waiting for.
            self.statusBar().showMessage(tr("index.auto_first_run"), 8000)
            self._pending_query_after_index = True
            self._start_index(rebuild=False)
            return

        self._start_search()
        self._maybe_refresh_index(check.display)

    def _maybe_refresh_index(self, root_display: str) -> None:
        """Run a quiet incremental update, if one is not already due.

        Throttled so repeatedly pressing Search does not re-scan the folder
        every time; an update that finds nothing costs a `stat` per file, but
        that is still real work on a large tree.
        """
        if self._index_handle is not None and self._index_handle.running:
            return
        now = time.monotonic()
        key = pathutil.normalized_path(root_display)
        last = self._last_auto_refresh.get(key, 0.0)
        if now - last < AUTO_REFRESH_INTERVAL_SECONDS:
            return
        self._last_auto_refresh[key] = now

        worker = IndexWorker(str(self.db.path), root_display, self.settings, rebuild=False)
        handle = WorkerHandle(worker)
        self._index_handle = handle
        self._background_index = True
        worker.finished.connect(self._on_background_index_finished)
        worker.failed.connect(self._on_background_index_failed)
        self._index_activity.setText(tr("index.auto_checking"))
        self._index_activity.setVisible(True)
        handle.start()

    @Slot(object)
    def _on_background_index_finished(self, summary: object) -> None:
        self._background_index = False
        self._index_activity.setVisible(False)
        self._finish_index_worker()
        if not isinstance(summary, IndexSummary):
            return

        path = str(self._root_combo.currentData() or self.settings.last_root or "")
        if path:
            self._reload_root_combo(select=path)
            with contextlib.suppress(DatabaseError):
                self._current_root = self.repos.roots.find_by_path(
                    pathutil.display_path(path)
                )
            if self._current_root is not None:
                self._update_index_status(
                    self._current_root.display_path, self._current_root
                )
                self._populate_type_filter(self._current_root.id)

        changed = summary.indexed + summary.deleted
        if changed and self._query.text().strip():
            # The index moved under the results that are on screen; re-run the
            # search so the user is not looking at a stale list.
            self.statusBar().showMessage(
                tr("index.auto_updated", changed=changed), 5000
            )
            self._start_search()
        self._refresh_enabled_state()

    @Slot(str)
    def _on_background_index_failed(self, message_key: str) -> None:
        self._background_index = False
        self._index_activity.setVisible(False)
        self._finish_index_worker()
        # A failed background refresh is not worth interrupting the user for:
        # the existing index is still searchable and the message is transient.
        log.warning("background index refresh failed | key=%s", message_key)

    def _start_search(self, *, offset: int = 0) -> None:
        self._debounce.stop()
        query = self._query.text().strip()
        root = self._current_root
        if root is None:
            if query:
                self.statusBar().showMessage(tr("error.no_root"), 5000)
            return
        if not query:
            return

        self._cancel_search()
        self._loaded_offset = offset
        request = SearchRequest(
            query=query,
            root_id=root.id,
            scope=self._scope_combo.currentData() or SearchScope.BOTH,
            match_case=self._match_case.isChecked(),
            exact_phrase=self._exact_phrase.isChecked(),
            whole_word=self._whole_word.isChecked(),
            filters=self._current_filters(),
            sort_field=self._sort_combo.currentData() or SortField.RELEVANCE,
            sort_descending=True,
            limit=self.settings.result_limit,
            offset=offset,
        )
        worker = SearchWorker(str(self.db.path), request)
        handle = WorkerHandle(worker)
        self._search_handle = handle
        worker.finished.connect(self._on_search_finished)
        worker.failed.connect(self._on_search_failed)
        self._search_button.setEnabled(False)
        handle.start()

    def _cancel_search(self) -> None:
        handle = self._search_handle
        self._search_handle = None
        if handle is not None:
            handle.stop(wait_ms=3000)

    @Slot(object)
    def _on_search_finished(self, response: object) -> None:
        self._search_button.setEnabled(True)
        handle = self._search_handle
        self._search_handle = None
        if handle is not None:
            handle.thread.quit()
            handle.thread.wait(2000)
        if not isinstance(response, SearchResponse):
            return

        self._last_response = response
        # Clear any stale warning first: a later clean search must not leave
        # the previous query's complaint on screen.
        self._reset_status_message()
        if response.query_warnings:
            self._report_query_warnings(response.query_warnings)

        if self._loaded_offset > 0:
            self._model.append_results(response.results, truncated=response.truncated)
        else:
            self._model.set_results(
                response.results,
                total_files=response.total_matched_files,
                truncated=response.truncated,
            )
            if response.results:
                first = self._model.index(0, 0, QModelIndex())
                self._tree.setCurrentIndex(first)
        self._update_result_header(response)
        self._stack.setCurrentIndex(1)

    @Slot(str)
    def _on_search_failed(self, message_key: str) -> None:
        self._search_button.setEnabled(True)
        self._search_handle = None
        self.statusBar().showMessage(tr(message_key), 6000)

    def _reset_status_message(self) -> None:
        """Return the status bar to the standing privacy statement."""
        self.statusBar().clearMessage()
        self.statusBar().showMessage(tr("privacy.statement"))

    def _report_query_warnings(self, warnings: list[str]) -> None:
        messages: list[str] = []
        for code in warnings:
            if code == "query_too_long":
                messages.append(tr("error.query_too_long", max=C.MAX_QUERY_LENGTH))
            elif code == "query_too_complex":
                messages.append(tr("error.query_too_complex"))
            elif code == "query_empty":
                messages.append(tr("error.query_empty"))
            elif code == "db_error":
                messages.append(tr("error.unexpected"))
            # "short_term_scan" is informational: the fallback path was used,
            # which is normal for a one- or two-character query.
        if messages:
            self.statusBar().showMessage("  ".join(messages), 7000)

    def _update_result_header(self, response: SearchResponse | None) -> None:
        if response is None:
            self._results_count.setText(tr("search.results_count", count=0))
            self._results_timing.setText("")
            self._load_more.setVisible(False)
            self._empty_label.setVisible(False)
            return
        shown = self._model.rowCount(QModelIndex())
        if response.truncated or shown < response.total_matched_files:
            self._results_count.setText(
                tr(
                    "search.results_truncated",
                    shown=shown,
                    total=response.total_matched_files,
                )
            )
        else:
            self._results_count.setText(
                tr("search.results_count", count=response.total_matched_files)
            )
        self._results_timing.setText(tr("search.elapsed", ms=response.elapsed_ms))
        self._load_more.setVisible(bool(response.truncated))
        self._empty_label.setVisible(response.total_matched_files == 0)
        self._tree.setAccessibleName(
            tr("search.results_count", count=response.total_matched_files)
        )

    def _load_next_page(self) -> None:
        shown = self._model.rowCount(QModelIndex())
        self._start_search(offset=shown)

    # ------------------------------------------------------------------
    # selection, details and actions
    # ------------------------------------------------------------------
    def _selected_result(self) -> object | None:
        index = self._tree.currentIndex()
        if not index.isValid():
            return None
        return index.data(ROLE_RESULT)

    @Slot(QModelIndex, QModelIndex)
    def _on_selection_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        del previous
        result = current.data(ROLE_RESULT) if current.isValid() else None
        if result is None:
            self._clear_details()
        else:
            # Selecting one of the expanded location rows previews that
            # specific match rather than the file's best one.
            location = current.data(ROLE_LOCATION) if current.data(ROLE_IS_CHILD) else None
            self._show_details(result, location)
        self._refresh_enabled_state()

    def _clear_details(self) -> None:
        self._details_placeholder.setVisible(True)
        self._details_form.setVisible(False)
        for caption, value in self._detail_rows.values():
            if isinstance(value, ElidedPathLabel):
                value.set_full_text("")
            else:
                value.setText("")
            caption.setVisible(True)
            value.setVisible(True)
        self._details_warning.setVisible(False)
        self._preview.show_message(tr("details.no_selection_preview"))

    def _show_details(self, result: object, location: object | None = None) -> None:
        """Fill the details panel for ``result``.

        ``location`` selects which match to preview; when a child row is
        selected it is that row's location, otherwise the best one.

        Relative path and file type are deliberately absent: both are already
        visible in the result table, and repeating them pushes the information
        that is *not* in the table further down.
        """
        path = getattr(result, "display_path", "")
        values = {
            "details.full_path": path,
            "details.size": pathutil.format_size(getattr(result, "size_bytes", 0)),
            "details.created": format_timestamp(getattr(result, "created_time", None)),
            "details.modified": format_timestamp(getattr(result, "modified_time", None)),
            "details.match_source": match_source_label(result.match_source),
        }
        # Plain text only: a file name is untrusted input like any other, so
        # the details panel never renders it as rich text.
        for key, (caption, label) in self._detail_rows.items():
            text = values.get(key, "")
            if isinstance(label, ElidedPathLabel):
                label.set_full_text(text)
            else:
                label.setText(text)
            caption.setVisible(bool(text))
            label.setVisible(bool(text))
        self._details_form.setVisible(True)
        self._details_placeholder.setVisible(False)

        self._update_preview(result, location)

        warning = ""
        if not getattr(result, "exists", True):
            warning = tr("result.missing")
        elif getattr(result, "warning", ""):
            warning = file_status_label(result.warning)
        self._details_warning.setText(warning)
        self._details_warning.setVisible(bool(warning))

    def _update_preview(self, result: object, location: object | None) -> None:
        locations = list(getattr(result, "locations", []) or [])
        chosen = location if location is not None else (locations[0] if locations else None)
        if chosen is None:
            # A name-only match has no document text to show; say so rather
            # than leaving an empty box that looks broken.
            self._preview.show_message(tr("details.no_match_preview"))
            return
        remaining = max(0, len(locations) - 1)
        self._preview.set_location(chosen, extra_locations=remaining)

    @Slot(QModelIndex)
    def _on_double_click(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        if self._model.rowCount(index) > 0 and index.column() == COL_NAME:
            self._tree.setExpanded(index, not self._tree.isExpanded(index))
            return
        self._open_selected_file()

    def _open_selected_file(self) -> None:
        self._open_result(self._selected_result())

    @Slot(object)
    def _open_result(self, result: object) -> None:
        """Open ``result`` with whatever Windows has registered for it.

        Called by the action-bar button, by a double-click, and by the per-row
        Open-file button.  When nothing is registered for the type, the shell
        layer falls back to the "Open with" chooser rather than failing, so a
        machine without Word can still read a .docx in something else.
        """
        if result is None:
            return
        path = getattr(result, "display_path", "")
        outcome = windows_shell.open_file(path)
        if not outcome.ok:
            self._handle_shell_failure(outcome.error_key, result)

    def _reveal_selected_file(self) -> None:
        result = self._selected_result()
        if result is not None:
            self._reveal_result(result)

    @Slot(object)
    def _reveal_result(self, result: object) -> None:
        """Open File Explorer at the folder holding ``result``.

        Called both by the action-bar button and by the per-row Open button.
        """
        if result is None:
            return
        outcome = windows_shell.reveal_in_explorer(getattr(result, "display_path", ""))
        if not outcome.ok:
            self._handle_shell_failure(outcome.error_key, result)

    def _copy_selected_path(self) -> None:
        result = self._selected_result()
        if result is None:
            return
        path = getattr(result, "display_path", "")
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(path)
            self.statusBar().showMessage(tr("action.copy_path"), 2500)

    def _handle_shell_failure(self, error_key: str, result: object) -> None:
        if error_key == "error.file_missing_body":
            self._model.mark_missing(getattr(result, "file_id", -1))
            self._show_details(result)
            answer = QMessageBox.question(
                self,
                tr("error.file_missing_title"),
                tr("error.file_missing_body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer is QMessageBox.StandardButton.Yes:
                self._start_index(rebuild=False)
            return
        QMessageBox.warning(self, tr("error.title"), tr(error_key or "error.open_failed"))

    def _show_context_menu(self, position: object) -> None:
        index = self._tree.indexAt(position)  # type: ignore[arg-type]
        if not index.isValid():
            return
        self._tree.setCurrentIndex(index)
        result = index.data(ROLE_RESULT)
        if result is None:
            return
        exists = bool(getattr(result, "exists", True))

        menu = QMenu(self._tree)
        open_action = menu.addAction(tr("action.open_file"))
        open_action.setEnabled(exists)
        open_action.triggered.connect(self._open_selected_file)
        reveal = menu.addAction(tr("action.open_folder"))
        reveal.setEnabled(exists)
        reveal.triggered.connect(self._reveal_selected_file)
        menu.addSeparator()
        menu.addAction(tr("action.copy_path")).triggered.connect(self._copy_selected_path)
        menu.addAction(tr("action.copy_name")).triggered.connect(
            lambda: self._copy_text(getattr(result, "file_name", ""))
        )
        menu.addAction(tr("action.copy_folder_path")).triggered.connect(
            lambda: self._copy_text(
                str(PureWindowsPath(getattr(result, "display_path", "")).parent)
            )
        )
        if not exists:
            menu.addSeparator()
            menu.addAction(tr("action.update_index")).triggered.connect(
                lambda: self._start_index(rebuild=False)
            )
        menu.exec(self._tree.viewport().mapToGlobal(position))  # type: ignore[arg-type]

    def _copy_text(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and text:
            clipboard.setText(text)
            self.statusBar().showMessage(tr("action.copy_path"), 2000)

    # ------------------------------------------------------------------
    # misc UI plumbing
    # ------------------------------------------------------------------
    def _toggle_filters(self, checked: bool) -> None:
        self._filters_panel.setVisible(checked)
        self._filters_toggle.setText(tr("search.advanced") + (" ▴" if checked else " ▾"))

    def _clear_filters(self) -> None:
        for box in self._type_boxes.values():
            box.setChecked(False)
        self._match_case.setChecked(False)
        self._exact_phrase.setChecked(False)
        self._whole_word.setChecked(False)
        self._date_from.setDate(self._date_from.minimumDate())
        self._date_to.setDate(self._date_to.minimumDate())
        self._size_min.setValue(0)
        self._size_max.setValue(0)
        self._subfolder.clear()

    def _choose_subfolder(self) -> None:
        root = self._current_root
        start = root.display_path if root else self.settings.last_root
        chosen = QFileDialog.getExistingDirectory(
            self, tr("search.subfolder"), start, QFileDialog.Option.ShowDirsOnly
        )
        if not chosen:
            return
        shown = pathutil.display_path(chosen)
        if root is not None and not pathutil.is_within_root(shown, root.display_path):
            QMessageBox.warning(self, tr("error.title"), tr("skip.outside_root"))
            return
        self._subfolder.setText(shown)

    def _focus_search(self) -> None:
        self._query.setFocus()
        self._query.selectAll()

    def _refresh_enabled_state(self) -> None:
        # A background refresh must not lock the UI: the user can keep typing
        # and searching against the index that already exists.
        blocking = (
            self._index_handle is not None
            and self._index_handle.running
            and not self._background_index
        )
        has_index = self._current_root is not None and self._current_root.file_count > 0
        has_root = bool(self._root_combo.currentData())

        # Searching is enabled as soon as a folder is chosen, because pressing
        # Search is now what creates the index.
        self._query.setEnabled(has_root and not blocking)
        self._search_button.setEnabled(has_root and not blocking)
        self._scope_combo.setEnabled(has_root and not blocking)
        self._filters_toggle.setEnabled(has_index and not blocking)
        self._action_update.setEnabled(has_root and not blocking)
        self._action_rebuild.setEnabled(has_index and not blocking)
        self._action_delete.setEnabled(has_index and not blocking)

        result = self._selected_result()
        exists = bool(result is not None and getattr(result, "exists", True))
        self._open_button.setEnabled(exists)
        self._folder_button.setEnabled(exists)
        self._copy_button.setEnabled(result is not None)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != int(SettingsDialog.DialogCode.Accepted):
            return
        updated = dialog.result_settings
        language_changed = updated.language != self.settings.language
        reindex_needed = dialog.reindex_needed
        self.settings = updated
        save_settings(self.settings)
        set_log_paths_enabled(self.settings.log_file_paths)
        if language_changed:
            set_language(self.settings.language)
            QMessageBox.information(
                self, tr("settings.title"), tr("settings.restart_note")
            )
        if reindex_needed:
            answer = QMessageBox.question(
                self,
                tr("index.update"),
                tr("confirm.rebuild_body", count=self._current_root.file_count if self._current_root else 0),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is QMessageBox.StandardButton.Yes:
                self._start_index(rebuild=True)

    def _open_about(self) -> None:
        AboutDialog(self).exec()

    def _open_manual(self) -> None:
        """Open the bundled HTML user manual in the default browser.

        The manual is a local file with no remote references of any kind — the
        fonts are system families, the images are files next to it, and there
        is no script or stylesheet fetched from anywhere.  Handing a local
        path to the shell is the same operation as opening a search result.
        """
        manual = pathutil.manual_path()
        if manual is None:
            QMessageBox.information(self, tr("error.title"), tr("error.manual_missing"))
            return
        outcome = windows_shell.open_file(str(manual))
        if not outcome.ok:
            QMessageBox.warning(self, tr("error.title"), tr("error.manual_failed"))

    # -- geometry ---------------------------------------------------------
    def _restore_geometry(self) -> None:
        from PySide6.QtCore import QByteArray

        if self.settings.window_geometry:
            with contextlib.suppress(ValueError, TypeError):
                self.restoreGeometry(
                    QByteArray.fromBase64(self.settings.window_geometry.encode("ascii"))
                )
        if self.settings.column_widths:
            for column, width in enumerate(self.settings.column_widths):
                if column < COLUMN_COUNT and width > 0:
                    self._tree.setColumnWidth(column, width)

    def _save_geometry(self) -> None:
        self.settings.window_geometry = bytes(
            self.saveGeometry().toBase64()
        ).decode("ascii")
        self.settings.column_widths = [
            self._tree.columnWidth(column) for column in range(COLUMN_COUNT)
        ]

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        """Stop workers before the window and its database go away."""
        self._debounce.stop()
        self._cancel_search()
        handle = self._index_handle
        if handle is not None and handle.running:
            handle.stop(wait_ms=10_000)
        self._index_handle = None
        self._save_geometry()
        save_settings(self.settings)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
def _format_iso(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return str(value)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def _date_to_epoch(date: QDate, *, end_of_day: bool) -> float:
    native = datetime(date.year(), date.month(), date.day())
    if end_of_day:
        native = native + timedelta(days=1) - timedelta(seconds=1)
    return native.timestamp()


# Unused-import guards for columns referenced only by the layout constants.
_ = (COL_MODIFIED, COL_SIZE, COL_TYPE)
