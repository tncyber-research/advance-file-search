"""Small custom widgets shared by the main window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

#: Width the eliding label claims to need, so it never widens its container.
_MIN_ELIDED_WIDTH = 48

SEPARATOR = "\\"
ELLIPSIS = "…"


def elide_path(path: str, metrics: QFontMetrics, available: int) -> str:
    """Shorten ``path`` to ``available`` pixels, cutting at folder boundaries.

    Qt's ``ElideMiddle`` cuts mid-component and produces things like
    ``C:\\Users\\PROXMO…lsx\\budget.xlsx`` — the ``lsx`` fragment is noise.
    Dropping whole components instead reads the way a path is meant to:

        C:\\…\\xlsx\\budget.xlsx

    The drive and the file name are always kept; intermediate folders are
    added from the right while they fit.  Falls back to character elision for
    a value with no separators (or a name too long to fit on its own).
    """
    text = str(path or "")
    if metrics.horizontalAdvance(text) <= available:
        return text

    parts = text.split(SEPARATOR)
    if len(parts) < 3:
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, available)

    head, tail = parts[0], parts[-1]
    minimal = f"{head}{SEPARATOR}{ELLIPSIS}{SEPARATOR}{tail}"
    if metrics.horizontalAdvance(minimal) > available:
        # Even drive + name does not fit; fall back to character elision so
        # something sensible is still shown.
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, available)

    # Grow from the right: the folders nearest the file are the informative
    # ones when space is short.
    kept: list[str] = []
    for part in reversed(parts[1:-1]):
        candidate = [part, *kept]
        joined = SEPARATOR.join([head, ELLIPSIS, *candidate, tail])
        if metrics.horizontalAdvance(joined) > available:
            break
        kept = candidate

    if not kept:
        return minimal
    if len(kept) == len(parts) - 2:
        return text
    return SEPARATOR.join([head, ELLIPSIS, *kept, tail])


class ElidedPathLabel(QLabel):
    """A one-line label that middle-elides a path to whatever width it has.

    Word-wrapping a Windows path does not work well in a narrow side panel: a
    path has no spaces, so it breaks at arbitrary characters, and if the label
    is ever given a notional width larger than the space it is drawn in, the
    overflow is silently clipped and whole path components disappear.

    Middle elision is both safe and more useful — it keeps the drive and the
    end of the path, which is the part that tells the user where the file is:

        C:\\Users\\…\\เอกสาร\\xlsx\\budget.xlsx

    The complete path stays available as the tooltip, through Copy Path, and
    through the context menu.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(1)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._apply_elision()

    def full_text(self) -> str:
        return self._full_text

    def _apply_elision(self) -> None:
        if not self._full_text:
            super().setText("")
            return
        metrics = QFontMetrics(self.font())
        available = max(16, self.width() - 2)
        super().setText(elide_path(self._full_text, metrics, available))

    # -- sizing -----------------------------------------------------------
    # QLabel derives both hints from the text it holds, so a long path makes
    # it demand hundreds of pixels and push the whole details panel wider than
    # the pane it lives in — at which point the text is clipped rather than
    # elided.  Reporting a small, fixed width instead lets the layout give the
    # label whatever room there is, and the elision then fits the text to it.
    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        hint = super().minimumSizeHint()
        hint.setWidth(_MIN_ELIDED_WIDTH)
        return hint

    def sizeHint(self):  # noqa: N802 - Qt naming
        hint = super().sizeHint()
        hint.setWidth(_MIN_ELIDED_WIDTH)
        return hint

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elision()
