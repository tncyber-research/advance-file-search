"""Match-preview panel: a few lines of the document text around the match.

The panel is deliberately styled as a distinct well (tinted background, accent
edge) so it reads as *content taken from the document* rather than as more
metadata about the file.

Security note: the text is inserted with ``setPlainText`` and the highlight is
applied through ``QTextCursor`` + ``QTextCharFormat``.  No markup is ever
parsed, so a document containing ``<script>`` or ``<img>`` is displayed as
those literal characters and cannot influence what is rendered.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from advance_file_search.core.i18n import location_label, tr
from advance_file_search.core.models import Highlight, MatchLocation
from advance_file_search.ui.theme import PALETTE

#: Visible height of the text area, in lines.  Four rather than three: with
#: the neighbouring units now folded into a short snippet, three lines left a
#: half-visible fourth line at the bottom, which reads as broken rather than as
#: "there is more".
PREVIEW_LINES = 4


class MatchPreview(QFrame):
    """Shows the source location and the matching text, with highlights."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PreviewCard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 9, 12, 10)
        outer.setSpacing(5)

        self._caption = QLabel(tr("details.match_preview"))
        self._caption.setObjectName("PreviewCaption")
        outer.addWidget(self._caption)

        # The location gets its own full-width line.  Sharing the caption's row
        # clipped it: "Sheet: งบประมาณ 2568, Cell: F12" is longer than the
        # space left over, and the cell reference is the part that matters.
        self._location = QLabel("")
        self._location.setObjectName("PreviewLocation")
        self._location.setWordWrap(True)
        self._location.setTextFormat(Qt.TextFormat.PlainText)
        self._location.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        outer.addWidget(self._location)

        self._text = QTextEdit()
        self._text.setObjectName("PreviewText")
        self._text.setReadOnly(True)
        self._text.setFrameShape(QFrame.Shape.NoFrame)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._text.setVerticalScrollBarPolicy(
            self._text.verticalScrollBarPolicy()
        )
        self._text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._text.setFixedHeight(self._text_height())
        outer.addWidget(self._text)

        self._empty = QLabel(tr("details.no_match_preview"))
        self._empty.setObjectName("PreviewEmpty")
        self._empty.setWordWrap(True)
        outer.addWidget(self._empty)

        self._more = QLabel("")
        self._more.setObjectName("PreviewLocation")
        self._more.setVisible(False)
        outer.addWidget(self._more)

        self.clear()

    # -- geometry ---------------------------------------------------------
    def _text_height(self) -> int:
        metrics = self._text.fontMetrics()
        # Line spacing times the visible line count, plus the document margin.
        return metrics.lineSpacing() * PREVIEW_LINES + 12

    def refresh_metrics(self) -> None:
        """Recompute the height after a font change."""
        self._text.setFixedHeight(self._text_height())

    # -- content ----------------------------------------------------------
    def clear(self) -> None:
        self._location.setText("")
        self._text.clear()
        self._text.setVisible(False)
        self._more.setVisible(False)
        self._empty.setText(tr("details.no_match_preview"))
        self._empty.setVisible(True)

    def show_message(self, message: str) -> None:
        """Display an explanatory line instead of a snippet."""
        self._location.setText("")
        self._text.clear()
        self._text.setVisible(False)
        self._more.setVisible(False)
        self._empty.setText(message)
        self._empty.setVisible(True)

    def set_location(
        self, location: MatchLocation, *, extra_locations: int = 0
    ) -> None:
        """Render one matching location and highlight the query inside it."""
        self._empty.setVisible(False)
        self._text.setVisible(True)
        self._location.setText(
            location_label(location.location_type, location.location_data)
        )
        self._set_text(location.snippet, location.highlights)

        if extra_locations > 0:
            self._more.setText(tr("result.more_locations", count=extra_locations))
            self._more.setVisible(True)
        else:
            self._more.setVisible(False)

    def _set_text(self, text: str, highlights: list[Highlight]) -> None:
        # setPlainText does not interpret markup: document content is inert.
        self._text.setPlainText(text or "")
        if not highlights:
            return

        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(PALETTE.highlight_bg))
        highlight_format.setForeground(QColor(PALETTE.highlight_text))
        highlight_format.setFontWeight(QFont.Weight.DemiBold)

        document_length = len(self._text.toPlainText())
        cursor = QTextCursor(self._text.document())
        for highlight in highlights:
            start = max(0, min(int(highlight.start), document_length))
            end = max(start, min(int(highlight.end), document_length))
            if end <= start:
                continue
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(highlight_format)

        # Leave the view at the top; the snippet is already centred on the
        # first match by the search layer.
        self._text.moveCursor(QTextCursor.MoveOperation.Start)

    # -- introspection for tests -----------------------------------------
    def preview_text(self) -> str:
        return self._text.toPlainText()

    def location_text(self) -> str:
        return self._location.text()

    def has_content(self) -> bool:
        # isVisibleTo rather than isVisible: it reports whether the text area
        # is switched on, independently of whether this panel has been shown
        # yet, which is what callers and tests actually want to know.
        return self._text.isVisibleTo(self) and bool(self._text.toPlainText())

    def extra_locations_shown(self) -> bool:
        return self._more.isVisibleTo(self)

    def message_shown(self) -> bool:
        return self._empty.isVisibleTo(self)

    def highlighted_fragments(self) -> list[str]:
        """Return the text of every highlighted run.

        Used by tests to prove the highlight lands on the query, and that the
        highlight is character formatting rather than injected markup.
        """
        fragments: list[str] = []
        document = self._text.document()
        target = QColor(PALETTE.highlight_bg)
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    background = fragment.charFormat().background().color()
                    if background == target:
                        fragments.append(fragment.text())
                iterator += 1
            block = block.next()
        return fragments
