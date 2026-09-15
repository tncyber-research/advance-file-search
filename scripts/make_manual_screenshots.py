"""Capture the screenshots used by the user manual, with numbered callouts.

    .venv\\Scripts\\python.exe scripts\\make_manual_screenshots.py

Every image comes from the real application driving a synthetic corpus — no
mock-ups, and no real documents.  The callout badges are drawn here rather
than in an image editor so the manual can be regenerated whenever the UI
changes, and the numbers can never drift out of step with the text.

Badge positions are derived from live widget geometry, not hard-coded pixels,
so they stay on the right controls at any window size or DPI.

Output: Manual/images/*.png
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT = PROJECT_ROOT / "Manual" / "images"
_SCRATCH = Path(tempfile.mkdtemp(prefix="afs-manual-"))
os.environ["ADVANCE_FILE_SEARCH_DATA_DIR"] = str(_SCRATCH / "appdata")

from PySide6.QtCore import QEventLoop, QPointF, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from advance_file_search.core.i18n import set_language  # noqa: E402
from advance_file_search.core.paths import ensure_app_dirs  # noqa: E402
from advance_file_search.core.settings import AppSettings  # noqa: E402
from advance_file_search.storage.migrations import open_index  # noqa: E402
from advance_file_search.ui.main_window import MainWindow  # noqa: E402
from advance_file_search.ui.result_model import COL_OPEN  # noqa: E402
from advance_file_search.ui.theme import apply_theme  # noqa: E402

WINDOW_WIDTH = 1340
WINDOW_HEIGHT = 790

BADGE_FILL = "#d9480f"
BADGE_TEXT = "#ffffff"
BADGE_RING = "#ffffff"
BADGE_RADIUS = 16


@dataclass(frozen=True)
class Callout:
    """A numbered badge, optionally with a box around the region it marks."""

    number: int
    x: int
    y: int
    box: tuple[int, int, int, int] | None = None


def pump(ms: int = 200) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def build_corpus(root: Path) -> None:
    """Synthetic Thai and English documents for the screenshots."""
    from tests.make_fixtures import write_all

    staging = root.parent / "fixtures"
    write_all(staging)
    docs = root / "เอกสารตัวอย่าง"
    docs.mkdir(parents=True, exist_ok=True)
    for group in ("txt", "pdf", "docx", "xlsx"):
        source = staging / group
        if source.exists():
            shutil.copytree(source, docs / group, dirs_exist_ok=True)

    reports = root / "รายงานประจำปี"
    reports.mkdir(exist_ok=True)
    (reports / "รายงานงบประมาณ 2568.txt").write_text(
        "รายงานงบประมาณประจำปี ๒๕๖๘\n"
        "งบประมาณครุภัณฑ์สำนักงาน รวม 1,250,000 บาท\n"
        "Annual equipment budget report for fiscal year 2568.\n"
        "อนุมัติโดยคณะกรรมการเมื่อวันที่ 14 มีนาคม 2568\n",
        encoding="utf-8",
    )
    (reports / "สรุปการจัดซื้อจัดจ้าง.txt").write_text(
        "สรุปการจัดซื้อจัดจ้าง ประจำปีงบประมาณ ๒๕๖๘\n"
        "รายการครุภัณฑ์คอมพิวเตอร์ จำนวน 12 เครื่อง\n"
        "งบประมาณที่ใช้ 480,000 บาท\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Callout drawing
# ---------------------------------------------------------------------------
def draw_callouts(pixmap: QPixmap, callouts: list[Callout]) -> QPixmap:
    result = QPixmap(pixmap)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    font = QFont()
    font.setFamilies(["Segoe UI", "Tahoma", "Arial"])
    font.setPointSizeF(11.0)
    font.setBold(True)
    painter.setFont(font)

    for callout in callouts:
        if callout.box:
            left, top, width, height = callout.box
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(BADGE_FILL), 2.2))
            painter.drawRoundedRect(QRectF(left, top, width, height), 6.0, 6.0)

        centre = QPointF(callout.x, callout.y)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BADGE_RING))
        painter.drawEllipse(centre, BADGE_RADIUS + 2.5, BADGE_RADIUS + 2.5)
        painter.setBrush(QColor(BADGE_FILL))
        painter.drawEllipse(centre, BADGE_RADIUS, BADGE_RADIUS)

        painter.setPen(QColor(BADGE_TEXT))
        painter.drawText(
            QRectF(
                centre.x() - BADGE_RADIUS,
                centre.y() - BADGE_RADIUS,
                BADGE_RADIUS * 2,
                BADGE_RADIUS * 2,
            ),
            int(Qt.AlignmentFlag.AlignCenter),
            str(callout.number),
        )

    painter.end()
    return result


def mark(
    number: int,
    widget: QWidget,
    container: QWidget,
    *,
    where: str = "left",
    outline: bool = True,
    offset: int = 0,
    clamp: bool = True,
) -> Callout:
    """Build a callout anchored to a real widget inside ``container``."""
    top_left = widget.mapTo(container, widget.rect().topLeft())
    width, height = widget.width(), widget.height()
    box = (top_left.x() - 3, top_left.y() - 3, width + 6, height + 6) if outline else None

    if where == "left":
        x, y = top_left.x() - 13 + offset, top_left.y() + height // 2
    elif where == "right":
        x, y = top_left.x() + width + 13 + offset, top_left.y() + height // 2
    elif where == "above":
        x, y = top_left.x() + width // 2 + offset, top_left.y() - 13
    else:  # below
        x, y = top_left.x() + width // 2 + offset, top_left.y() + height + 13

    if clamp:
        # Keep the badge inside the window.  A region shot turns this off: its
        # badges are meant to land in the margin the crop adds around itself.
        limit_x = container.width() - BADGE_RADIUS - 2
        limit_y = container.height() - BADGE_RADIUS - 2
        x = max(BADGE_RADIUS + 2, min(x, limit_x))
        y = max(BADGE_RADIUS + 2, min(y, limit_y))
    return Callout(number, x, y, box)


def _inside(
    number: int, widget: QWidget, container: QWidget, *, dx: int, dy: int
) -> Callout:
    """A badge placed inside a widget, with the widget outlined."""
    top_left = widget.mapTo(container, widget.rect().topLeft())
    return Callout(
        number,
        top_left.x() + dx,
        top_left.y() + dy,
        (top_left.x() - 3, top_left.y() - 3, widget.width() + 6, widget.height() + 6),
    )


def region(
    widgets: list[QWidget], container: QWidget, *, pad: int = 12
) -> tuple[int, int, int, int]:
    """The rectangle that covers every widget given, plus a margin."""
    left = top = 10**6
    right = bottom = 0
    for widget in widgets:
        origin = widget.mapTo(container, widget.rect().topLeft())
        left = min(left, origin.x())
        top = min(top, origin.y())
        right = max(right, origin.x() + widget.width())
        bottom = max(bottom, origin.y() + widget.height())
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(container.width(), right + pad)
    bottom = min(container.height(), bottom + pad)
    return left, top, right - left, bottom - top


def shift(callouts: list[Callout], origin: tuple[int, int]) -> list[Callout]:
    """Move badges from window coordinates into a cropped image."""
    dx, dy = origin
    moved = []
    for callout in callouts:
        box = None
        if callout.box:
            bx, by, bw, bh = callout.box
            box = (bx - dx, by - dy, bw, bh)
        moved.append(Callout(callout.number, callout.x - dx, callout.y - dy, box))
    return moved


def save_region(
    window: QWidget,
    name: str,
    widgets: list[QWidget],
    callouts: list[Callout],
    *,
    pad: int = 12,
    margin: tuple[int, int, int, int] = (40, 34, 40, 26),
) -> None:
    """Crop the band that holds ``widgets`` and draw ``callouts`` on it.

    The crop is pasted onto a slightly larger canvas so that badges anchored
    to the edge of a control have somewhere to sit that is not on top of the
    control's own label.
    """
    left, top, right, bottom = margin
    x, y, width, height = region(widgets, window, pad=pad)
    cropped = window.grab().copy(x, y, width, height)

    canvas = QPixmap(width + left + right, height + top + bottom)
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    painter.drawPixmap(left, top, cropped)
    painter.end()

    save(canvas, name, shift(callouts, (x - left, y - top)))

def save(pixmap: QPixmap, name: str, callouts: list[Callout] | None = None) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image = draw_callouts(pixmap, callouts) if callouts else pixmap
    target = OUTPUT / f"{name}.png"
    image.save(str(target), "PNG")
    print(f"  {target.name:32} {image.width():>5} x {image.height()}")


def crop(pixmap: QPixmap, widget: QWidget, container: QWidget, *, height: int = 0) -> QPixmap:
    origin = widget.mapTo(container, widget.rect().topLeft())
    return pixmap.copy(
        origin.x(), origin.y(), widget.width(), height or widget.height()
    )


# ---------------------------------------------------------------------------
def main() -> int:
    corpus = _SCRATCH / "ตัวอย่างเอกสาร"
    corpus.mkdir(parents=True, exist_ok=True)
    build_corpus(corpus)

    ensure_app_dirs()
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    from advance_file_search.app import _apply_window_icon

    _apply_window_icon(app)
    set_language("th")

    database, _ = open_index()
    settings = AppSettings(language="th", enable_optional_formats=True).normalize()
    window = MainWindow(database, settings)
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()
    pump(600)

    print("Capturing manual screenshots…")

    # ---- 1. first run ---------------------------------------------------
    save(window.grab(), "01_first_run")
    save(
        window.grab(),
        "01_first_run_callouts",
        [
            mark(1, window._root_combo, window, where="left"),
            mark(2, window._index_menu_button, window, where="below"),
            mark(3, window._manual_button, window, where="below"),
            mark(4, window._query, window, where="left"),
            mark(5, window._firstrun_button, window, where="right"),
        ],
    )

    # ---- 2. folder chosen, before indexing ------------------------------
    window._adopt_root(str(corpus))
    pump(500)
    save(
        window.grab(),
        "02_folder_selected",
        [
            mark(1, window._root_combo, window, where="left"),
            mark(2, window._index_status, window, where="left"),
            mark(3, window._search_button, window, where="below"),
        ],
    )

    # ---- 3. indexing progress -------------------------------------------
    from advance_file_search.core.models import IndexPhase, IndexProgress
    from advance_file_search.ui.index_dialog import IndexDialog

    dialog = IndexDialog(window)
    dialog.show()
    pump(400)
    dialog.update_progress(
        IndexProgress(
            phase=IndexPhase.EXTRACTING,
            current_item="เอกสารตัวอย่าง\\xlsx\\budget.xlsx",
            discovered=26,
            processed=18,
            indexed=15,
            skipped=1,
            failed=1,
            no_text=1,
            elapsed_seconds=6.0,
        )
    )
    pump(400)
    save(
        dialog.grab(),
        "03_indexing",
        [
            mark(1, dialog._phase_label, dialog, where="right"),
            mark(2, dialog._bar, dialog, where="left"),
            mark(3, dialog._current_label, dialog, where="left"),
            mark(4, dialog._cancel_button, dialog, where="left"),
        ],
    )
    dialog._finished = True
    dialog.accept()
    pump(250)

    # ---- build the index for real ---------------------------------------
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
    from advance_file_search.storage.repositories import Repositories

    repos = Repositories.create(database)
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    window._reload_root_combo(select=str(corpus))
    window._load_root(str(corpus))
    pump(500)

    def search(text: str) -> None:
        window._query.setText(text)
        window._start_search()
        waited = 0
        while window._search_handle is not None and waited < 8000:
            pump(50)
            waited += 50
        pump(300)

    # ---- 4. the main screen, fully labelled ------------------------------
    search("งบประมาณ")
    if window._model.rowCount() > 0:
        window._tree.setCurrentIndex(window._model.index(0, 0))
    pump(500)
    save(window.grab(), "04_main_screen")
    save(
        window.grab(),
        "04_main_screen_callouts",
        [
            mark(1, window._root_combo, window, where="left"),
            mark(2, window._index_menu_button, window, where="below"),
            mark(3, window._settings_button, window, where="below"),
            mark(4, window._manual_button, window, where="below"),
            mark(5, window._index_status, window, where="left"),
            mark(6, window._query, window, where="left"),
            mark(7, window._search_button, window, where="below"),
            mark(8, window._scope_combo, window, where="below"),
            mark(9, window._filters_toggle, window, where="below"),
            mark(10, window._results_count, window, where="above"),
            mark(11, window._sort_combo, window, where="below"),
            # Inside the table rather than beside it: the tree fills the left
            # half, so an edge-anchored badge would sit on another control.
            _inside(12, window._tree, window, dx=26, dy=30),
            mark(13, window._preview, window, where="above"),
            mark(14, window._open_button, window, where="above"),
        ],
    )

    # ---- 5. result table close-up ----------------------------------------
    table = crop(window.grab(), window._tree, window, height=min(250, window._tree.height()))
    header = window._tree.header()
    centres = [
        header.sectionPosition(column) + header.sectionSize(column) // 2
        for column in range(6)
    ]
    save(table, "05_result_table", [Callout(n + 1, centres[n], 20) for n in range(6)])

    # ---- 6. details panel close-up ---------------------------------------
    card = window._preview.parentWidget()
    details = crop(window.grab(), card, window)
    save(
        details,
        "06_details_panel",
        [
            mark(1, window._preview, card, where="right"),
            mark(2, window._details_form, card, where="right"),
        ],
    )

    # ---- 7. advanced filters ---------------------------------------------
    window._filters_toggle.setChecked(True)
    pump(500)
    save(window.grab(), "07_filters")
    panel = window._filters_panel
    filters = crop(window.grab(), panel, window)
    save(
        filters,
        "07_filters_callouts",
        [
            mark(1, window._match_case, panel, where="left"),
            mark(2, window._exact_phrase, panel, where="left"),
            mark(3, window._whole_word, panel, where="left"),
            mark(4, window._date_from, panel, where="left"),
            mark(5, window._size_min, panel, where="left"),
            mark(6, window._subfolder, panel, where="left"),
        ],
    )
    window._filters_toggle.setChecked(False)
    pump(400)

    # ---- 8. expanded locations -------------------------------------------
    search("needle")
    model = window._model
    parent = None
    for row in range(model.rowCount()):
        candidate = model.index(row, 0)
        if model.rowCount(candidate) > 0:
            parent = candidate
            break
    if parent is not None:
        window._tree.expand(parent)
        window._tree.setCurrentIndex(parent)
    pump(500)
    save(window.grab(), "08_expanded_locations")

    # ---- 9. Thai search ---------------------------------------------------
    search("ครุภัณฑ์")
    if window._model.rowCount() > 0:
        window._tree.setCurrentIndex(window._model.index(0, 0))
    pump(500)
    save(window.grab(), "09_thai_search")

    # ---- 10. settings -----------------------------------------------------
    from PySide6.QtWidgets import QTabWidget

    from advance_file_search.ui.settings_dialog import SettingsDialog

    settings_dialog = SettingsDialog(window.settings, window)
    settings_dialog.show()
    pump(500)
    save(settings_dialog.grab(), "10_settings")
    tab_bar = settings_dialog.findChild(QTabWidget).tabBar()
    save(
        settings_dialog.grab(),
        "10_settings_callouts",
        [
            mark(1, tab_bar, settings_dialog, where="above"),
            mark(2, settings_dialog._max_size, settings_dialog, where="right"),
            mark(3, settings_dialog._hidden, settings_dialog, where="right"),
            mark(4, settings_dialog._optional, settings_dialog, where="right"),
            mark(5, settings_dialog._docx_headers, settings_dialog, where="right"),
        ],
    )
    settings_dialog.reject()
    pump(250)

    # ---- 11. index menu ---------------------------------------------------
    menu = window._index_menu_button.menu()
    menu.popup(window.mapToGlobal(window._index_menu_button.pos()))
    pump(500)
    save(menu.grab(), "11_index_menu")
    # A menu entry is an action, not a widget, so its badge comes from the
    # geometry the menu reports.  The menu is narrow and its entries are full
    # of text, so the capture gets a left margin for the badges to sit in
    # rather than having them cover the labels.
    grabbed = menu.grab()
    margin = 46
    canvas = QPixmap(grabbed.width() + margin, grabbed.height())
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    painter.drawPixmap(margin, 0, grabbed)
    painter.end()
    menu_callouts = []
    for number, action in enumerate(
        (item for item in menu.actions() if item.text()), start=1
    ):
        rect = menu.actionGeometry(action)
        menu_callouts.append(
            Callout(
                number,
                margin // 2,
                rect.center().y(),
                (margin + rect.x() + 2, rect.y() + 1, rect.width() - 4, rect.height() - 2),
            )
        )
    save(canvas, "11_index_menu_callouts", menu_callouts)
    menu.close()
    pump(250)

    # ---- 12. the two row buttons ------------------------------------------
    search("งบประมาณ")
    pump(400)
    whole = window.grab()
    origin = window._tree.mapTo(window, window._tree.rect().topLeft())
    row_top = origin.y() + window._tree.header().height()
    strip = whole.copy(origin.x(), row_top, window._tree.width(), 44)

    # The column holds a folder button and a file button.  Their positions come
    # from the delegate's own geometry, and the badges go in a margin above the
    # row so that neither badge covers the button it points at.
    from PySide6.QtCore import QRect as _QRect
    from PySide6.QtWidgets import QStyleOptionViewItem as _Option

    from advance_file_search.ui import delegates as _delegates

    option = _Option()
    option.rect = _QRect(
        header.sectionPosition(COL_OPEN), 0, header.sectionSize(COL_OPEN), 44
    )
    button_rects = _delegates.RowActionsDelegate._button_rects(option)

    margin_top = 38
    canvas = QPixmap(strip.width(), strip.height() + margin_top)
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    painter.drawPixmap(0, margin_top, strip)
    painter.end()

    badges = []
    for number, action in enumerate(
        (_delegates.ACTION_REVEAL, _delegates.ACTION_OPEN), start=1
    ):
        rect = button_rects[action]
        badges.append(
            Callout(
                number,
                rect.center().x(),
                margin_top // 2,
                (rect.left() - 3, margin_top + rect.top() - 3,
                 rect.width() + 6, rect.height() + 6),
            )
        )
    save(canvas, "12_open_button", badges)

    # ---- 13. the application icon at every size ---------------------------
    sheet = QImage(600, 150, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#ffffff"))
    painter = QPainter(sheet)
    x = 30
    for size in (16, 24, 32, 48, 64):
        scaled = (
            app.windowIcon()
            .pixmap(size, size)
            .toImage()
            .scaled(size * 2, size * 2, Qt.AspectRatioMode.KeepAspectRatio)
        )
        painter.drawImage(x, 75 - scaled.height() // 2, scaled)
        x += scaled.width() + 28
    painter.end()
    save(QPixmap.fromImage(sheet), "13_app_icon")


    # ---- 20-23. the screen, one region at a time -------------------------
    # The main screen carries fourteen numbered parts, which is too many for a
    # reader to follow on one picture.  The manual walks through it in four
    # bands instead, each with its own short list.
    search("งบประมาณ")
    if window._model.rowCount() > 0:
        window._tree.setCurrentIndex(window._model.index(0, 0))
    pump(500)

    top_widgets = [
        window._root_combo,
        window._browse_button,
        window._index_menu_button,
        window._settings_button,
        window._manual_button,
        window._index_status,
    ]
    save_region(
        window,
        "20_area_top",
        top_widgets,
        [
            mark(1, window._root_combo, window, where="left", clamp=False),
            mark(2, window._browse_button, window, where="right", clamp=False),
            mark(3, window._index_status, window, where="left", offset=-12, clamp=False),
            mark(4, window._index_menu_button, window, where="above", clamp=False),
            mark(5, window._settings_button, window, where="above", clamp=False),
            mark(6, window._manual_button, window, where="above", clamp=False),
        ],
        pad=16,
    )

    search_widgets = [
        window._query,
        window._search_button,
        window._scope_combo,
        window._filters_toggle,
        window._results_count,
        window._sort_combo,
    ]
    save_region(
        window,
        "21_area_search",
        search_widgets,
        [
            mark(1, window._query, window, where="left", clamp=False),
            mark(2, window._search_button, window, where="above", clamp=False),
            mark(3, window._scope_combo, window, where="above", clamp=False),
            mark(4, window._filters_toggle, window, where="above", clamp=False),
            mark(5, window._results_count, window, where="left", offset=-12, clamp=False),
            mark(6, window._sort_combo, window, where="below", clamp=False),
        ],
        pad=14,
    )

    save_region(
        window,
        "22_area_results",
        [window._tree, window._preview],
        [
            mark(1, window._tree, window, where="above", clamp=False),
            mark(2, window._preview, window, where="above", clamp=False),
            mark(3, window._details_form, window, where="right", clamp=False),
        ],
        pad=10,
    )

    save_region(
        window,
        "23_area_actions",
        [window._open_button, window._folder_button, window._copy_button,
         window._wildcard_hint],
        [
            mark(1, window._open_button, window, where="above", clamp=False),
            mark(2, window._folder_button, window, where="above", clamp=False),
            mark(3, window._copy_button, window, where="above", clamp=False),
            mark(4, window._wildcard_hint, window, where="above", clamp=False),
        ],
        pad=14,
    )

    # ---- 24-25. the other two settings tabs ------------------------------
    settings_dialog = SettingsDialog(window.settings, window)
    settings_dialog.show()
    tabs = settings_dialog.findChild(QTabWidget)
    pump(300)

    tabs.setCurrentIndex(1)
    pump(400)
    save(
        settings_dialog.grab(),
        "24_settings_search",
        [
            mark(1, settings_dialog._result_limit, settings_dialog, where="right"),
            mark(2, settings_dialog._snippets, settings_dialog, where="right"),
            mark(3, settings_dialog._scope, settings_dialog, where="right"),
            mark(4, settings_dialog._remember_filters, settings_dialog, where="right"),
        ],
    )

    tabs.setCurrentIndex(2)
    pump(400)
    save(
        settings_dialog.grab(),
        "25_settings_privacy",
        [
            mark(1, settings_dialog._language, settings_dialog, where="right"),
            mark(2, settings_dialog._log_level, settings_dialog, where="right"),
            mark(3, settings_dialog._log_paths, settings_dialog, where="right"),
        ],
    )
    settings_dialog.reject()
    pump(250)

    # ---- 26. the About dialog -------------------------------------------
    from advance_file_search.ui.about_dialog import AboutDialog

    about = AboutDialog(window)
    about.show()
    pump(500)
    save(about.grab(), "26_about")
    about.reject()
    pump(250)

    window.close()
    pump(300)
    database.close()
    shutil.rmtree(_SCRATCH, ignore_errors=True)
    print(f"\nWrote screenshots to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
