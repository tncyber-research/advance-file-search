"""Indexing progress dialog.

Shows phase, counters, elapsed time, a determinate-where-possible progress bar,
a Cancel button and an expandable problem summary.

Privacy: the "current file" line shows a path **relative to the selected root**
and extracted content is never displayed here.  Problem rows show a localized
explanation keyed by error code, not a raw parser message.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from advance_file_search.core.i18n import file_status_label, skip_reason_label, tr
from advance_file_search.core.models import (
    IndexPhase,
    IndexProgress,
    IndexSummary,
    RunStatus,
)
from advance_file_search.ui.theme import PALETTE

_PHASE_KEYS = {
    IndexPhase.IDLE: "phase.idle",
    IndexPhase.PREPARING: "phase.preparing",
    IndexPhase.SCANNING: "phase.scanning",
    IndexPhase.EXTRACTING: "phase.extracting",
    IndexPhase.REMOVING_DELETED: "phase.removing_deleted",
    IndexPhase.FINALIZING: "phase.finalizing",
    IndexPhase.DONE: "phase.done",
    IndexPhase.CANCELLED: "phase.cancelled",
    IndexPhase.FAILED: "phase.failed",
}

_COUNTER_KEYS = (
    ("index.discovered", "discovered"),
    ("index.indexed", "indexed"),
    ("index.unchanged", "unchanged"),
    ("index.no_text", "no_text"),
    ("index.skipped", "skipped"),
    ("index.failed", "failed"),
    ("index.deleted", "deleted"),
)


def format_elapsed(seconds: float) -> str:
    total = int(max(0.0, seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class IndexDialog(QDialog):
    """Modal-but-cancellable progress view for one indexing run."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{tr('index.title')} — {tr('app.title')}")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._cancel_requested = False
        self._finished = False
        self._counter_labels: dict[str, QLabel] = {}

        self._build_ui()

        # The elapsed clock ticks locally so the display keeps moving even
        # while the worker is busy inside a single large document.
        self._clock = QTimer(self)
        self._clock.setInterval(500)
        self._clock.timeout.connect(self._tick)
        self._elapsed_seconds = 0.0
        self._clock.start()

    # -- construction -----------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(14)

        self._phase_label = QLabel(tr("phase.preparing"))
        self._phase_label.setObjectName("SectionTitle")
        outer.addWidget(self._phase_label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate until a total is known
        self._bar.setTextVisible(True)
        self._bar.setFormat("%v / %m")
        self._bar.setAccessibleName(tr("index.title"))
        outer.addWidget(self._bar)

        current_row = QHBoxLayout()
        current_row.setSpacing(8)
        caption = QLabel(tr("index.current"))
        caption.setObjectName("Muted")
        current_row.addWidget(caption)
        self._current_label = QLabel("")
        self._current_label.setObjectName("Muted")
        self._current_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._current_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        current_row.addWidget(self._current_label, 1)
        outer.addLayout(current_row)

        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        for position, (key, field) in enumerate(_COUNTER_KEYS):
            row, column = divmod(position, 4)
            holder = QVBoxLayout()
            holder.setSpacing(1)
            value = QLabel("0")
            value.setObjectName("SectionTitle")
            name = QLabel(tr(key))
            name.setObjectName("Muted")
            holder.addWidget(value)
            holder.addWidget(name)
            container = QWidget()
            container.setLayout(holder)
            grid.addWidget(container, row, column)
            self._counter_labels[field] = value
        outer.addWidget(card)

        elapsed_row = QHBoxLayout()
        elapsed_caption = QLabel(tr("index.elapsed"))
        elapsed_caption.setObjectName("Muted")
        elapsed_row.addWidget(elapsed_caption)
        self._elapsed_label = QLabel("0:00")
        elapsed_row.addWidget(self._elapsed_label)
        elapsed_row.addStretch(1)
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("Muted")
        elapsed_row.addWidget(self._summary_label)
        outer.addLayout(elapsed_row)

        self._problems_button = QPushButton(tr("index.errors_heading", count=0))
        self._problems_button.setObjectName("Link")
        self._problems_button.setCheckable(True)
        self._problems_button.setEnabled(False)
        self._problems_button.toggled.connect(self._toggle_problems)
        outer.addWidget(self._problems_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._problems = QTreeWidget()
        self._problems.setColumnCount(2)
        self._problems.setHeaderLabels([tr("col.name"), tr("details.status")])
        self._problems.setRootIsDecorated(False)
        self._problems.setAlternatingRowColors(True)
        self._problems.setMinimumHeight(150)
        self._problems.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._problems.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._problems.setVisible(False)
        outer.addWidget(self._problems)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._cancel_button = QPushButton(tr("index.cancel"))
        self._cancel_button.clicked.connect(self._request_cancel)
        buttons.addWidget(self._cancel_button)
        self._close_button = QPushButton(tr("index.close"))
        self._close_button.setObjectName("Primary")
        self._close_button.setDefault(True)
        self._close_button.setVisible(False)
        self._close_button.clicked.connect(self.accept)
        buttons.addWidget(self._close_button)
        outer.addLayout(buttons)

    # -- public API -------------------------------------------------------
    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    def update_progress(self, progress: IndexProgress) -> None:
        self._elapsed_seconds = progress.elapsed_seconds
        self._phase_label.setText(tr(_PHASE_KEYS.get(progress.phase, "phase.idle")))
        self._current_label.setText(_elide(progress.current_item, 90))

        if progress.determinate and progress.discovered > 0:
            self._bar.setRange(0, max(progress.discovered, progress.processed))
            self._bar.setValue(progress.processed)
        else:
            self._bar.setRange(0, 0)

        values = {
            "discovered": progress.discovered,
            "indexed": progress.indexed,
            "unchanged": progress.unchanged,
            "no_text": progress.no_text,
            "skipped": progress.skipped,
            "failed": progress.failed,
            "deleted": progress.deleted,
        }
        for field, label in self._counter_labels.items():
            label.setText(f"{values.get(field, 0):,}")
        self._elapsed_label.setText(format_elapsed(self._elapsed_seconds))

    def show_summary(self, summary: IndexSummary) -> None:
        """Switch the dialog into its finished state."""
        self._finished = True
        self._clock.stop()
        self._elapsed_seconds = summary.elapsed_seconds

        self.update_progress(
            IndexProgress(
                phase={
                    RunStatus.COMPLETED: IndexPhase.DONE,
                    RunStatus.CANCELLED: IndexPhase.CANCELLED,
                    RunStatus.FAILED: IndexPhase.FAILED,
                }.get(summary.status, IndexPhase.DONE),
                discovered=summary.discovered,
                processed=summary.processed,
                indexed=summary.indexed,
                unchanged=summary.unchanged,
                skipped=summary.skipped,
                failed=summary.failed,
                no_text=summary.no_text,
                deleted=summary.deleted,
                elapsed_seconds=summary.elapsed_seconds,
            )
        )
        self._bar.setRange(0, 1)
        self._bar.setValue(1)

        message = {
            RunStatus.COMPLETED: tr("index.done"),
            RunStatus.CANCELLED: tr("index.done_cancelled"),
            RunStatus.FAILED: tr("index.done_failed"),
        }.get(summary.status, "")
        self._summary_label.setText(message)
        if summary.status is not RunStatus.COMPLETED:
            self._summary_label.setStyleSheet(f"color: {PALETTE.warning};")

        self._populate_problems(summary)
        self._cancel_button.setVisible(False)
        self._close_button.setVisible(True)
        self._close_button.setFocus()

    def show_error(self, message: str) -> None:
        self._finished = True
        self._clock.stop()
        self._phase_label.setText(tr("phase.failed"))
        self._summary_label.setText(message)
        self._summary_label.setStyleSheet(f"color: {PALETTE.danger};")
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        self._cancel_button.setVisible(False)
        self._close_button.setVisible(True)

    # -- internals --------------------------------------------------------
    def _populate_problems(self, summary: IndexSummary) -> None:
        self._problems.clear()
        rows = 0
        for error in summary.errors:
            item = QTreeWidgetItem(
                [
                    error.relative_path or tr("app.title"),
                    file_status_label(error.error_code),
                ]
            )
            item.setToolTip(0, error.relative_path)
            self._problems.addTopLevelItem(item)
            rows += 1

        interesting = {
            key: count
            for key, count in summary.skip_counts.items()
            if key != "not_supported" and count
        }
        for reason, count in sorted(interesting.items(), key=lambda kv: -kv[1]):
            item = QTreeWidgetItem([skip_reason_label(reason), f"{count:,}"])
            self._problems.addTopLevelItem(item)
            rows += 1

        self._problems_button.setText(tr("index.errors_heading", count=rows))
        self._problems_button.setEnabled(rows > 0)
        if rows == 0:
            self._problems_button.setText(tr("index.no_errors"))

    def _toggle_problems(self, checked: bool) -> None:
        self._problems.setVisible(checked)
        self.adjustSize()

    def _request_cancel(self) -> None:
        self._cancel_requested = True
        self._cancel_button.setEnabled(False)
        self._cancel_button.setText(tr("phase.cancelled"))
        self._phase_label.setText(tr("phase.cancelled"))

    def _tick(self) -> None:
        if self._finished:
            return
        self._elapsed_seconds += 0.5
        self._elapsed_label.setText(format_elapsed(self._elapsed_seconds))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        """Closing the window means cancel, not abandon.

        The worker keeps running until it reaches a safe point, so the dialog
        stays open until the run reports back; this prevents a second run being
        started against the same database.
        """
        if not self._finished:
            self._request_cancel()
            event.ignore()
            return
        self._clock.stop()
        super().closeEvent(event)

    def reject(self) -> None:
        if not self._finished:
            self._request_cancel()
            return
        super().reject()


def _elide(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1) :]
