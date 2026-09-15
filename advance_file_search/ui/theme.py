"""Light theme: palette, typography and stylesheet.

Everything is defined in code.  There are no remote fonts, no downloaded
icons, no CDN stylesheets and no web view — the whole look is Qt widgets plus
the stylesheet below, all shipped inside the package.

Accessibility (handoff §11.5):

* body text contrast against the surface is above 7:1, and the muted secondary
  text above 4.5:1;
* the focus ring is a 2 px accent outline drawn in addition to any colour
  change, so focus is never communicated by colour alone;
* status is always paired with a word or an icon glyph, never colour alone;
* the base point size follows the OS font so Windows text scaling applies.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    """Low-saturation neutral surfaces with a muted teal-blue accent."""

    window: str = "#f4f6f8"
    surface: str = "#ffffff"
    surface_alt: str = "#fafbfc"
    surface_sunken: str = "#eef1f4"
    border: str = "#d9dfe5"
    border_strong: str = "#b9c3cc"

    text: str = "#1b2733"
    text_muted: str = "#5a6b7b"
    text_disabled: str = "#96a3b0"
    text_inverse: str = "#ffffff"

    accent: str = "#1d6f8b"
    accent_hover: str = "#22809f"
    accent_pressed: str = "#175A71"
    accent_soft: str = "#e3eef3"
    accent_text: str = "#124d61"

    selection: str = "#d7e8ef"
    selection_text: str = "#10323d"
    highlight_bg: str = "#ffe89a"
    highlight_text: str = "#3d2900"

    #: The match-preview well: a faint tint that separates document text from
    #: the surrounding metadata without competing with the highlight colour.
    preview_bg: str = "#f7fafb"
    preview_border: str = "#cfdde4"

    success: str = "#1f7a4d"
    warning: str = "#8a5a00"
    danger: str = "#a3352c"
    danger_soft: str = "#fbeceb"


PALETTE = Palette()

#: Floor for the base UI point size.  Thai text needs more vertical room than
#: Latin because vowels and tone marks stack above and below the base line.
BASE_POINT_SIZE: float = 11.0

#: Row height in the result table, in pixels, at the base font size.
RESULT_ROW_HEIGHT: int = 34

#: Fonts are resolved from the system by family name; nothing is downloaded.
#: Leelawadee UI is the Windows Thai UI face and is present on Windows 10/11;
#: the rest of the stack degrades gracefully.
UI_FONT_STACK = ("Segoe UI", "Leelawadee UI", "Tahoma", "Arial")
MONO_FONT_STACK = ("Consolas", "Cascadia Mono", "Courier New")


def ui_font(point_size: int = 0, *, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(list(UI_FONT_STACK))
    if point_size:
        font.setPointSize(point_size)
    font.setBold(bold)
    return font


def mono_font(point_size: int = 0) -> QFont:
    font = QFont()
    font.setFamilies(list(MONO_FONT_STACK))
    if point_size:
        font.setPointSize(point_size)
    return font


def apply_theme(app: QApplication, *, base_point_size: int = 0) -> None:
    """Install the light palette, base font and stylesheet."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(PALETTE.window))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(PALETTE.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(PALETTE.surface))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PALETTE.surface_alt))
    palette.setColor(QPalette.ColorRole.Text, QColor(PALETTE.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(PALETTE.surface))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(PALETTE.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(PALETTE.selection))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(PALETTE.selection_text))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(PALETTE.surface))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(PALETTE.text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(PALETTE.text_disabled))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(PALETTE.text_disabled),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(PALETTE.text_disabled),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(PALETTE.text_disabled),
    )
    app.setPalette(palette)

    font = ui_font(base_point_size)
    if not base_point_size:
        # Start from the platform's own UI size so Windows text scaling still
        # applies, then add a step: the default 9 pt is uncomfortably small for
        # reading Thai, whose vowels and tone marks sit above and below the
        # line and need the extra height to stay distinct.
        existing = app.font()
        base = existing.pointSizeF() if existing.pointSizeF() > 0 else 9.0
        font.setPointSizeF(max(BASE_POINT_SIZE, base + 1.5))
    app.setFont(font)

    app.setStyleSheet(stylesheet())


def stylesheet() -> str:
    p = PALETTE
    return f"""
/* ---------- base ---------- */
QWidget {{
    color: {p.text};
}}
QMainWindow, QDialog {{
    background: {p.window};
}}
QToolTip {{
    background: {p.surface};
    color: {p.text};
    border: 1px solid {p.border_strong};
    padding: 4px 6px;
}}

/* ---------- panels ---------- */
QFrame#Card {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QFrame#Divider {{
    background: {p.border};
    max-height: 1px;
    border: none;
}}
QLabel#SectionTitle {{
    font-weight: 600;
    color: {p.text};
}}
QLabel#Muted, QLabel#Hint {{
    color: {p.text_muted};
}}
QLabel#Heading {{
    font-size: 17pt;
    font-weight: 600;
    color: {p.text};
}}
QLabel#StatusPill {{
    background: {p.accent_soft};
    color: {p.accent_text};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 2px 10px;
}}

/* ---------- match preview panel ---------- */
/* A visually distinct well, so it reads as "this is text from the document"
   rather than as more metadata. */
QFrame#PreviewCard {{
    background: {p.preview_bg};
    border: 1px solid {p.preview_border};
    border-left: 3px solid {p.accent};
    border-radius: 6px;
}}
QLabel#PreviewCaption {{
    color: {p.accent_text};
    font-weight: 600;
}}
QLabel#PreviewLocation {{
    color: {p.text_muted};
}}
QTextEdit#PreviewText {{
    background: transparent;
    border: none;
    padding: 0px;
    color: {p.text};
}}
QLabel#PreviewEmpty {{
    color: {p.text_disabled};
    font-style: italic;
}}
QLabel#WarningPill {{
    background: {p.danger_soft};
    color: {p.danger};
    border: 1px solid {p.danger};
    border-radius: 10px;
    padding: 2px 10px;
}}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {p.selection};
    selection-color: {p.selection_text};
}}
QLineEdit#SearchBox {{
    padding: 8px 12px;
    font-size: 11pt;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {p.accent};
    padding: 4px 7px;
}}
QLineEdit#SearchBox:focus {{
    padding: 7px 11px;
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateEdit:disabled {{
    background: {p.surface_sunken};
    color: {p.text_disabled};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    selection-background-color: {p.selection};
    selection-color: {p.selection_text};
    outline: none;
}}

/* ---------- buttons ---------- */
QPushButton {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 20px;
}}
QPushButton:hover {{
    background: {p.surface_alt};
    border-color: {p.accent};
}}
QPushButton:pressed {{
    background: {p.surface_sunken};
}}
QPushButton:focus {{
    border: 2px solid {p.accent};
    padding: 5px 13px;
}}
QPushButton:disabled {{
    background: {p.surface_sunken};
    color: {p.text_disabled};
    border-color: {p.border};
}}
QPushButton#Primary {{
    background: {p.accent};
    color: {p.text_inverse};
    border: 1px solid {p.accent_pressed};
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {p.accent_hover};
}}
QPushButton#Primary:pressed {{
    background: {p.accent_pressed};
}}
QPushButton#Primary:focus {{
    border: 2px solid {p.accent_text};
    padding: 5px 13px;
}}
QPushButton#Primary:disabled {{
    background: {p.border};
    color: {p.text_disabled};
    border-color: {p.border};
}}
QPushButton#Danger {{
    color: {p.danger};
    border-color: {p.danger};
}}
QPushButton#Danger:hover {{
    background: {p.danger_soft};
}}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {p.accent};
    padding: 2px 4px;
    text-decoration: underline;
}}
QPushButton#Link:focus {{
    border: 2px solid {p.accent};
    border-radius: 4px;
    padding: 0px 2px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
}}
QToolButton:hover {{
    background: {p.surface_alt};
    border-color: {p.border};
}}
QToolButton:focus {{
    border: 2px solid {p.accent};
}}
QToolButton::menu-indicator {{
    width: 0px;
}}

/* ---------- checkboxes ---------- */
QCheckBox, QRadioButton {{
    spacing: 7px;
    padding: 2px;
}}
QCheckBox:focus, QRadioButton:focus {{
    border: 1px dotted {p.accent};
    border-radius: 3px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {p.border_strong};
    background: {p.surface};
}}
QCheckBox::indicator {{
    border-radius: 3px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {p.accent};
    border-color: {p.accent_pressed};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {p.accent};
}}

/* ---------- result table ---------- */
QTreeView, QTableView, QListView {{
    background: {p.surface};
    alternate-background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
    selection-background-color: {p.selection};
    selection-color: {p.selection_text};
    outline: none;
}}
QTreeView::item, QTableView::item {{
    padding: 4px 2px;
    border: none;
}}
QTreeView::item:selected, QTableView::item:selected {{
    background: {p.selection};
    color: {p.selection_text};
}}
QTreeView::item:focus {{
    border: 1px solid {p.accent};
}}
QTreeView::branch:has-children:closed {{
    image: none;
    border-image: none;
}}
QHeaderView::section {{
    background: {p.surface_sunken};
    color: {p.text_muted};
    border: none;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
    padding: 6px 8px;
    font-weight: 600;
}}
QHeaderView::section:hover {{
    background: {p.accent_soft};
    color: {p.accent_text};
}}

/* ---------- progress ---------- */
QProgressBar {{
    background: {p.surface_sunken};
    border: 1px solid {p.border};
    border-radius: 6px;
    height: 16px;
    text-align: center;
    color: {p.text};
}}
QProgressBar::chunk {{
    background: {p.accent};
    border-radius: 5px;
}}

/* ---------- tabs ---------- */
QTabWidget::pane {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {p.text_muted};
    padding: 7px 16px;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {p.surface};
    color: {p.text};
    border-color: {p.border};
    border-bottom-color: {p.surface};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    color: {p.text};
}}
QTabBar::tab:focus {{
    border: 2px solid {p.accent};
}}

/* ---------- group box ---------- */
QGroupBox {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: {p.text_muted};
    font-weight: 600;
}}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.text_muted};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p.text_muted};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ---------- menus ---------- */
QMenu {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 14px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {p.accent_soft};
    color: {p.accent_text};
}}
QMenu::item:disabled {{
    color: {p.text_disabled};
}}
QMenu::separator {{
    height: 1px;
    background: {p.border};
    margin: 4px 8px;
}}

/* ---------- splitter ---------- */
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 6px;
}}
QSplitter::handle:vertical {{
    height: 6px;
}}
QSplitter::handle:hover {{
    background: {p.accent_soft};
}}

/* ---------- status bar ---------- */
QStatusBar {{
    background: {p.surface};
    border-top: 1px solid {p.border};
    color: {p.text_muted};
}}
QStatusBar::item {{
    border: none;
}}
"""
