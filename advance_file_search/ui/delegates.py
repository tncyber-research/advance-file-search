"""Item delegate that highlights query matches without rendering markup.

This is the security-critical half of snippet display.  A naive implementation
builds an HTML string like ``f"...<b>{match}</b>..."`` and hands it to a rich
text renderer — at which point ``<script>`` or ``<img>`` inside a document can
change what the application draws.

Instead, the delegate paints the snippet as **plain text** with ``QPainter``
and draws a background rectangle behind the ranges reported by the search
layer.  Document content is never parsed as markup, so there is nothing to
inject.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from advance_file_search.core.models import Highlight
from advance_file_search.ui.result_model import (
    ROLE_HIGHLIGHTS,
    ROLE_IS_CHILD,
    ROLE_RESULT,
    highlights_from,
)
from advance_file_search.ui.theme import PALETTE

_PAD_X = 4
_MAX_HIGHLIGHTS_DRAWN = 24


class HighlightDelegate(QStyledItemDelegate):
    """Draws plain text with highlighted match ranges."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._highlight_bg = QColor(PALETTE.highlight_bg)
        self._highlight_fg = QColor(PALETTE.highlight_text)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        highlights = highlights_from(index.data(ROLE_HIGHLIGHTS))
        if not highlights:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        if not text:
            super().paint(painter, option, index)
            return

        # Let the style draw the row background, selection and focus ring, then
        # take over the text itself.
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget
        )
        rect = rect.adjusted(_PAD_X, 0, -_PAD_X, 0)
        if rect.width() <= 0:
            return

        metrics = QFontMetrics(opt.font)
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        visible_len = len(elided)
        # The ellipsis replaces trailing characters, so only ranges that start
        # inside the visible span are drawn.
        drawable = [h for h in highlights if h.start < visible_len][
            :_MAX_HIGHLIGHTS_DRAWN
        ]

        painter.save()
        painter.setClipRect(rect)
        baseline_rect = QRect(rect)

        for highlight in drawable:
            start = max(0, min(highlight.start, visible_len))
            end = max(start, min(highlight.end, visible_len))
            if end <= start:
                continue
            x_start = rect.left() + metrics.horizontalAdvance(elided[:start])
            width = metrics.horizontalAdvance(elided[start:end])
            if width <= 0:
                continue
            band = QRect(
                x_start,
                baseline_rect.top() + 1,
                width,
                max(1, baseline_rect.height() - 2),
            )
            painter.fillRect(band.intersected(rect), self._highlight_bg)

        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        color = (
            opt.palette.color(QPalette.ColorRole.HighlightedText)
            if selected
            else index.data(Qt.ItemDataRole.ForegroundRole) or QColor(PALETTE.text)
        )
        if not isinstance(color, QColor):
            color = QColor(PALETTE.text)
        painter.setPen(color)
        painter.setFont(opt.font)
        # drawText renders the string literally: no markup interpretation.
        painter.drawText(
            baseline_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided,
        )

        # Redraw the highlighted glyphs in the highlight foreground so the text
        # stays legible on the yellow band.
        for highlight in drawable:
            start = max(0, min(highlight.start, visible_len))
            end = max(start, min(highlight.end, visible_len))
            if end <= start:
                continue
            x_start = rect.left() + metrics.horizontalAdvance(elided[:start])
            width = metrics.horizontalAdvance(elided[start:end])
            if width <= 0:
                continue
            segment = QRect(x_start, baseline_rect.top(), width, baseline_rect.height())
            painter.setPen(self._highlight_fg)
            painter.setClipRect(segment.intersected(rect))
            painter.drawText(
                baseline_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                elided,
            )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), 26))


#: Size of the painted open-folder button, in pixels.
OPEN_BUTTON_WIDTH = 30
OPEN_BUTTON_HEIGHT = 24


def draw_folder_glyph(painter: QPainter, rect: QRectF, colour: QColor) -> None:
    """Draw a small folder outline inside ``rect``.

    Hand-drawn rather than loaded from an icon file: it keeps the button
    crisp at any DPI, needs no asset, and matches the accent colour exactly.
    """
    width = rect.width()
    height = rect.height()
    radius = max(1.0, width * 0.10)

    # Back panel with the raised tab on the left.
    body = QPainterPath()
    tab_width = width * 0.42
    tab_height = height * 0.16
    body.moveTo(rect.left() + radius, rect.top() + tab_height)
    body.lineTo(rect.left() + tab_width * 0.62, rect.top() + tab_height)
    body.lineTo(rect.left() + tab_width * 0.82, rect.top())
    body.lineTo(rect.right() - radius, rect.top())
    body.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
    body.lineTo(rect.right(), rect.bottom() - radius)
    body.quadTo(rect.right(), rect.bottom(), rect.right() - radius, rect.bottom())
    body.lineTo(rect.left() + radius, rect.bottom())
    body.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - radius)
    body.lineTo(rect.left(), rect.top() + tab_height + radius)
    body.quadTo(
        rect.left(), rect.top() + tab_height, rect.left() + radius, rect.top() + tab_height
    )
    body.closeSubpath()

    pen = QPen(colour, max(1.0, height * 0.075))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(body)

    # The line across the front flap, which is what makes it read as a folder
    # rather than a plain box at this size.
    flap = rect.top() + height * 0.42
    painter.drawLine(
        QPointF(rect.left() + width * 0.02, flap),
        QPointF(rect.right() - width * 0.02, flap),
    )


def draw_file_glyph(painter: QPainter, rect: QRectF, colour: QColor) -> None:
    """Draw a small document outline inside ``rect``.

    Drawn rather than loaded for the same reason as the folder: it stays crisp
    at any DPI and follows the theme colour exactly.
    """
    width = rect.width()
    height = rect.height()
    fold = min(width, height) * 0.34

    sheet = QPainterPath()
    sheet.moveTo(rect.left(), rect.top())
    sheet.lineTo(rect.right() - fold, rect.top())
    sheet.lineTo(rect.right(), rect.top() + fold)
    sheet.lineTo(rect.right(), rect.bottom())
    sheet.lineTo(rect.left(), rect.bottom())
    sheet.closeSubpath()

    pen = QPen(colour, max(1.0, height * 0.075))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(sheet)

    # The folded corner: without it the shape reads as a plain rectangle.
    painter.drawLine(
        QPointF(rect.right() - fold, rect.top()),
        QPointF(rect.right() - fold, rect.top() + fold),
    )
    painter.drawLine(
        QPointF(rect.right() - fold, rect.top() + fold),
        QPointF(rect.right(), rect.top() + fold),
    )

    # Two text lines, so it reads as a document at 24 px.
    for offset in (0.62, 0.80):
        y = rect.top() + height * offset
        painter.drawLine(
            QPointF(rect.left() + width * 0.18, y),
            QPointF(rect.right() - width * 0.18, y),
        )


#: Gap between the two buttons in the Open column.
OPEN_BUTTON_GAP = 6

#: Which button a point falls on.
ACTION_REVEAL = "reveal"
ACTION_OPEN = "open"


class RowActionsDelegate(QStyledItemDelegate):
    """Draws two compact icon buttons per row: open the folder, open the file.

    A real ``QPushButton`` per row would mean two widgets per visible result
    and a persistent editor for each; painting the buttons and handling the
    click in :meth:`editorEvent` costs nothing per row and scrolls smoothly.

    They are icons, not labelled buttons: full captions needed a column wide
    enough to unbalance the table, and the row already says which file it
    belongs to.  The meaning is carried by the tooltip and the column header.

    They are drawn only on file rows, and disabled when the file is gone, so
    the controls never promise something they cannot do.
    """

    #: Emitted with the row's result when the folder button is activated.
    clicked = Signal(object)
    #: Emitted with the row's result when the file button is activated.
    open_clicked = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pressed: tuple[tuple[int, int], str] | None = None
        self._hover: tuple[tuple[int, int], str] | None = None

    # -- geometry ---------------------------------------------------------
    @staticmethod
    def _button_rects(option: QStyleOptionViewItem) -> dict[str, QRect]:
        """Two fixed-size buttons, centred in the cell as a pair.

        Sizing a button from the cell made it grow with the column and look
        clumsy; constant sizes keep every row identical however the user drags
        the header.  When the column is dragged too narrow for both, the pair
        shrinks rather than overlapping.
        """
        cell = QRect(option.rect)
        available = max(16, cell.width() - 8)
        width = min(OPEN_BUTTON_WIDTH, max(14, (available - OPEN_BUTTON_GAP) // 2))
        height = min(OPEN_BUTTON_HEIGHT, max(14, cell.height() - 4))
        total = width * 2 + OPEN_BUTTON_GAP
        left = cell.left() + (cell.width() - total) // 2
        top = cell.top() + (cell.height() - height) // 2
        return {
            ACTION_REVEAL: QRect(left, top, width, height),
            ACTION_OPEN: QRect(left + width + OPEN_BUTTON_GAP, top, width, height),
        }

    @classmethod
    def _action_at(cls, option: QStyleOptionViewItem, position: QPointF) -> str | None:
        for action, rect in cls._button_rects(option).items():
            if rect.contains(position.toPoint()):
                return action
        return None

    def _key(self, index: QModelIndex) -> tuple[int, int]:
        return (int(index.internalId()), index.row())

    def _is_actionable(self, index: QModelIndex) -> bool:
        if index.data(ROLE_IS_CHILD):
            return False
        result = index.data(ROLE_RESULT)
        return result is not None and bool(getattr(result, "exists", True))

    # -- painting ---------------------------------------------------------
    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        result = index.data(ROLE_RESULT)
        if result is None or index.data(ROLE_IS_CHILD):
            return

        enabled = self._is_actionable(index)
        key = self._key(index)
        rects = self._button_rects(option)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for action, rect in rects.items():
            if not enabled:
                background = QColor(PALETTE.surface_sunken)
                border = QColor(PALETTE.border)
                glyph = QColor(PALETTE.text_disabled)
            elif self._pressed == (key, action):
                background = QColor(PALETTE.accent_pressed)
                border = QColor(PALETTE.accent_pressed)
                glyph = QColor(PALETTE.text_inverse)
            elif self._hover == (key, action):
                background = QColor(PALETTE.accent)
                border = QColor(PALETTE.accent_pressed)
                glyph = QColor(PALETTE.text_inverse)
            else:
                background = QColor(PALETTE.accent_soft)
                border = QColor(PALETTE.border_strong)
                glyph = QColor(PALETTE.accent_text)

            painter.setBrush(background)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(QRectF(rect), 5.0, 5.0)

            if action == ACTION_REVEAL:
                draw_folder_glyph(painter, QRectF(rect).adjusted(7.5, 6.0, -7.5, -5.0), glyph)
            else:
                draw_file_glyph(painter, QRectF(rect).adjusted(8.5, 5.0, -8.5, -5.0), glyph)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(
            max(size.width(), OPEN_BUTTON_WIDTH * 2 + OPEN_BUTTON_GAP + 10),
            max(size.height(), OPEN_BUTTON_HEIGHT + 4),
        )

    # -- interaction ------------------------------------------------------
    def editorEvent(
        self,
        event: QEvent,
        model: object,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        if not index.isValid():
            return False
        kind = event.type()
        key = self._key(index)

        if kind == QEvent.Type.MouseMove:
            action = self._action_at(option, event.position())
            new_hover = (key, action) if action else None
            if new_hover != self._hover:
                self._hover = new_hover
            return False

        if not self._is_actionable(index):
            return False

        if kind == QEvent.Type.MouseButtonPress:
            action = self._action_at(option, event.position())
            if event.button() == Qt.MouseButton.LeftButton and action:
                self._pressed = (key, action)
                return True
            return False

        if kind == QEvent.Type.MouseButtonRelease:
            pressed = self._pressed
            self._pressed = None
            action = self._action_at(option, event.position())
            if pressed is not None and action and pressed == (key, action):
                result = index.data(ROLE_RESULT)
                if result is not None:
                    if action == ACTION_REVEAL:
                        self.clicked.emit(result)
                    else:
                        self.open_clicked.emit(result)
                return True
            return False

        if kind == QEvent.Type.MouseButtonDblClick:
            # Swallow it so a double-click on a button does not also trigger
            # the tree's own "open the file" action.
            return self._action_at(option, event.position()) is not None

        return False

    def clear_hover(self) -> None:
        self._hover = None
        self._pressed = None


#: The previous name, kept so existing imports do not break.
OpenFolderDelegate = RowActionsDelegate


def highlight_ranges_valid(highlights: list[Highlight], text_length: int) -> bool:
    """Sanity check used by tests: ranges must be ordered and in bounds."""
    previous_end = -1
    for highlight in highlights:
        if highlight.start < 0 or highlight.end > text_length:
            return False
        if highlight.start >= highlight.end:
            return False
        if highlight.start < previous_end:
            return False
        previous_end = highlight.end
    return True
