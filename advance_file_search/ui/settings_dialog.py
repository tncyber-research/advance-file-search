"""Settings dialog: indexing limits, search defaults, privacy and logging."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from advance_file_search.core import constants as C
from advance_file_search.core.i18n import AVAILABLE_LANGUAGES, tr
from advance_file_search.core.settings import AppSettings
from advance_file_search.logging_setup import clear_logs
from advance_file_search.winplat import windows_shell


class SettingsDialog(QDialog):
    """Edits a copy of :class:`AppSettings`; the caller saves on accept."""

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{tr('settings.title')} — {tr('app.title')}")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._original = settings
        # Edits apply to a copy; the caller persists it only on accept.
        self.result_settings = _copy(settings)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._build_indexing_tab(), tr("settings.tab_indexing"))
        tabs.addTab(self._build_search_tab(), tr("settings.tab_search"))
        tabs.addTab(self._build_privacy_tab(), tr("settings.tab_privacy"))
        layout.addWidget(tabs)

        buttons = QDialogButtonBox()
        save = buttons.addButton(tr("settings.save"), QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("Primary")
        buttons.addButton(tr("settings.cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- tabs -------------------------------------------------------------
    def _build_indexing_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        self._max_size = QSpinBox()
        self._max_size.setRange(1, C.MAX_FILE_SIZE_LIMIT_MB)
        self._max_size.setSingleStep(50)
        self._max_size.setSuffix(" MB")
        self._max_size.setValue(self.result_settings.max_file_size_mb)
        self._max_size.setAccessibleName(tr("settings.max_file_size"))
        form.addRow(tr("settings.max_file_size"), self._max_size)

        self._hidden = QCheckBox(tr("settings.include_hidden"))
        self._hidden.setChecked(self.result_settings.include_hidden_files)
        form.addRow("", self._hidden)

        self._optional = QCheckBox(tr("settings.optional_formats"))
        self._optional.setChecked(self.result_settings.enable_optional_formats)
        form.addRow("", self._optional)

        self._docx_headers = QCheckBox(tr("settings.docx_headers"))
        self._docx_headers.setChecked(self.result_settings.index_docx_headers)
        form.addRow("", self._docx_headers)

        note = QLabel(
            "\n".join(
                [
                    tr("about.limitations") + ":",
                    tr("about.limitations_body"),
                ]
            )
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _build_search_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        self._result_limit = QSpinBox()
        self._result_limit.setRange(10, C.MAX_RESULT_LIMIT)
        self._result_limit.setSingleStep(50)
        self._result_limit.setValue(self.result_settings.result_limit)
        form.addRow(tr("settings.result_limit"), self._result_limit)

        self._snippets = QSpinBox()
        self._snippets.setRange(1, 100)
        self._snippets.setValue(self.result_settings.max_snippets_per_file)
        form.addRow(tr("settings.snippets_per_file"), self._snippets)

        self._scope = QComboBox()
        self._scope.addItem(tr("search.scope_both"), "both")
        self._scope.addItem(tr("search.scope_name"), "name")
        self._scope.addItem(tr("search.scope_content"), "content")
        index = self._scope.findData(self.result_settings.default_scope)
        self._scope.setCurrentIndex(max(0, index))
        form.addRow(tr("search.scope"), self._scope)

        # Labelled for what it does: the old label said "advanced filters",
        # which read as a switch for the filters themselves.
        self._remember_filters = QCheckBox(tr("settings.remember_filters"))
        self._remember_filters.setChecked(self.result_settings.remember_filters)
        form.addRow("", self._remember_filters)

        hint = QLabel(tr("search.wildcard_help"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        form.addRow(hint)
        return page

    def _build_privacy_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        statement = QLabel(tr("privacy.statement"))
        statement.setWordWrap(True)
        statement.setObjectName("Hint")
        layout.addWidget(statement)

        form = QFormLayout()
        form.setSpacing(10)

        self._language = QComboBox()
        for code, label in AVAILABLE_LANGUAGES:
            self._language.addItem(label, code)
        language_index = self._language.findData(self.result_settings.language)
        self._language.setCurrentIndex(max(0, language_index))
        form.addRow(tr("settings.language"), self._language)

        self._log_level = QComboBox()
        for level in ("INFO", "WARNING", "ERROR", "DEBUG"):
            self._log_level.addItem(level, level)
        level_index = self._log_level.findData(self.result_settings.log_level)
        self._log_level.setCurrentIndex(max(0, level_index))
        form.addRow(tr("settings.log_level"), self._log_level)

        self._log_paths = QCheckBox(tr("settings.log_paths"))
        self._log_paths.setChecked(self.result_settings.log_file_paths)
        form.addRow("", self._log_paths)
        layout.addLayout(form)

        actions = QHBoxLayout()
        open_logs = QPushButton(tr("settings.open_logs"))
        open_logs.clicked.connect(lambda: windows_shell.open_data_folder())
        actions.addWidget(open_logs)
        clear = QPushButton(tr("settings.clear_logs"))
        clear.setObjectName("Danger")
        clear.clicked.connect(self._clear_logs)
        actions.addWidget(clear)
        actions.addStretch(1)
        layout.addLayout(actions)

        note = QLabel(tr("settings.restart_note"))
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # -- actions ----------------------------------------------------------
    def _clear_logs(self) -> None:
        removed = clear_logs()
        QMessageBox.information(
            self,
            tr("settings.clear_logs"),
            f"{tr('settings.clear_logs')}: {removed}",
        )

    def _on_accept(self) -> None:
        settings = self.result_settings
        settings.max_file_size_mb = self._max_size.value()
        settings.include_hidden_files = self._hidden.isChecked()
        settings.enable_optional_formats = self._optional.isChecked()
        settings.index_docx_headers = self._docx_headers.isChecked()
        settings.result_limit = self._result_limit.value()
        settings.max_snippets_per_file = self._snippets.value()
        settings.default_scope = str(self._scope.currentData() or "both")
        settings.remember_filters = self._remember_filters.isChecked()
        settings.language = str(self._language.currentData() or settings.language)
        settings.log_level = str(self._log_level.currentData() or settings.log_level)
        settings.log_file_paths = self._log_paths.isChecked()
        settings.normalize()
        self.accept()

    @property
    def reindex_needed(self) -> bool:
        """True when a changed setting alters what would be indexed."""
        before = self._original
        after = self.result_settings
        return (
            before.enable_optional_formats != after.enable_optional_formats
            or before.include_hidden_files != after.include_hidden_files
            or before.max_file_size_mb != after.max_file_size_mb
            or before.index_docx_headers != after.index_docx_headers
        )


def _copy(settings: AppSettings) -> AppSettings:
    """Shallow copy with independent list fields."""
    clone = AppSettings(
        language=settings.language,
        last_root=settings.last_root,
        recent_roots=list(settings.recent_roots),
        max_file_size_mb=settings.max_file_size_mb,
        include_hidden_files=settings.include_hidden_files,
        enable_optional_formats=settings.enable_optional_formats,
        index_docx_headers=settings.index_docx_headers,
        result_limit=settings.result_limit,
        max_snippets_per_file=settings.max_snippets_per_file,
        default_scope=settings.default_scope,
        remember_filters=settings.remember_filters,
        log_file_paths=settings.log_file_paths,
        log_level=settings.log_level,
        window_geometry=settings.window_geometry,
        window_state=settings.window_state,
        column_widths=list(settings.column_widths),
    )
    return clone
