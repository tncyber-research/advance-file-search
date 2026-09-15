"""About dialog: version, privacy statement, limitations and license notices.

The privacy statement is asserted here because the release build has passed the
offline and network-monitoring acceptance tests documented in
``docs/SECURITY.md``; see ``docs/TEST_REPORT.md`` for the evidence.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.i18n import tr
from advance_file_search.winplat import windows_shell

_LICENSE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "LICENSES",
    Path(__file__).resolve().parents[3] / "LICENSES",
)


def _find_licenses_dir() -> Path | None:
    import sys

    bundle = getattr(sys, "_MEIPASS", "")
    candidates = list(_LICENSE_CANDIDATES)
    if bundle:
        candidates.insert(0, Path(bundle).parent / "LICENSES")
        candidates.insert(1, Path(bundle) / "LICENSES")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def load_license_text() -> str:
    """Read bundled third-party notices from the local LICENSES directory."""
    directory = _find_licenses_dir()
    if directory is None:
        return (
            "Third-party license notices are distributed in the LICENSES "
            "folder next to the application executable."
        )
    parts: list[str] = []
    try:
        for entry in sorted(directory.iterdir()):
            if not entry.is_file():
                continue
            try:
                body = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parts.append(f"=== {entry.name} ===\n{body.strip()}\n")
    except OSError:
        return ""
    return "\n".join(parts) if parts else ""


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("about.title"))
        self.setModal(True)
        self.setMinimumSize(600, 480)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(12)

        heading = QLabel(tr("app.title"))
        heading.setObjectName("Heading")
        layout.addWidget(heading)

        version = QLabel(
            f"{tr('app.version', version=C.APP_VERSION)}  ·  {tr('about.offline')}"
        )
        version.setObjectName("Muted")
        layout.addWidget(version)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        tabs = QTabWidget()
        tabs.addTab(self._privacy_page(), tr("settings.tab_privacy"))
        tabs.addTab(self._limitations_page(), tr("about.limitations"))
        tabs.addTab(self._licenses_page(), tr("about.licenses"))
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        # Qt supplies its own English label for a standard button; the rest of
        # this dialog is translated, so this one is too.
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("about.close"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        data_button = QPushButton(tr("about.data_folder"))
        data_button.clicked.connect(lambda: windows_shell.open_data_folder())
        buttons.addButton(data_button, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

    def _privacy_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(16, 16, 16, 16)
        statement = QLabel(tr("privacy.statement"))
        statement.setWordWrap(True)
        box.addWidget(statement)

        details = QLabel(
            "\n".join(
                [
                    "• " + tr("about.offline"),
                    f"• {tr('about.data_folder')}: {pathutil.app_data_dir()}",
                ]
            )
        )
        details.setObjectName("Muted")
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(details)
        box.addStretch(1)
        return page

    def _limitations_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(16, 16, 16, 16)
        body = QLabel(tr("about.limitations_body"))
        body.setWordWrap(True)
        box.addWidget(body)
        box.addStretch(1)
        return page

    def _licenses_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(12, 12, 12, 12)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(load_license_text())
        viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        box.addWidget(viewer)
        return page
