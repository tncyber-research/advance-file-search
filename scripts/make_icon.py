"""Generate the application icon locally.

The icon is drawn with Qt at build time rather than downloaded or committed as
opaque bytes, so there is no remote asset and the design is reviewable as code.

    .venv\\Scripts\\python.exe scripts\\make_icon.py

Design: a document sheet with a magnifier badge over its lower-right corner —
"look inside this file".  The background is fully transparent so the icon sits
cleanly on any title bar, taskbar or Explorer background, light or dark.

Qt's own ICO writer emits a single resolution, which Windows then rescales,
and a downscaled 256 px icon looks muddy in a 16 px title bar.  This script
therefore renders each size at its native resolution — simplifying the drawing
as the canvas shrinks — and packs them into a multi-resolution ICO by writing
the container format directly.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

#: Sizes Windows asks for: title bar, small shell, taskbar, large tiles.
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

# Palette.  Deliberately a little more saturated than the UI accent so the icon
# stays legible against the grey of a taskbar.
INK_DARK = "#0f4c5c"
ACCENT_DARK = "#12697f"
ACCENT = "#1d8fa8"
ACCENT_LIGHT = "#39b3c9"
SHEET_TOP = "#ffffff"
SHEET_BOTTOM = "#eef4f7"
SHEET_EDGE = "#c2d4dc"
LINE = "#9db8c4"
LENS = "#d8f1f7"


def draw(size: int) -> QImage:
    """Render the icon at ``size`` px on a transparent canvas."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    # Everything is authored on a 256-unit grid and scaled down, so one set of
    # coordinates serves every size.
    s = size / 256.0
    tiny = size <= 24

    # A pale grey outline disappears in a 16 px title bar, so the small sizes
    # are drawn with the accent colour and heavier strokes.  The shape stays
    # identical; only the contrast changes.
    edge_colour = QColor(ACCENT_DARK if tiny else SHEET_EDGE)
    edge_width = max(1.0, (11 if tiny else 5) * s)
    line_colour = QColor(ACCENT if tiny else LINE)

    # ---- document sheet ------------------------------------------------
    # Left-leaning so the magnifier has room at the lower right.
    sheet = QRectF(34 * s, 22 * s, 132 * s, 176 * s)
    fold = 44 * s

    body = QPainterPath()
    radius = 12 * s
    body.moveTo(sheet.left() + radius, sheet.top())
    body.lineTo(sheet.right() - fold, sheet.top())
    body.lineTo(sheet.right(), sheet.top() + fold)
    body.lineTo(sheet.right(), sheet.bottom() - radius)
    body.quadTo(sheet.right(), sheet.bottom(), sheet.right() - radius, sheet.bottom())
    body.lineTo(sheet.left() + radius, sheet.bottom())
    body.quadTo(sheet.left(), sheet.bottom(), sheet.left(), sheet.bottom() - radius)
    body.lineTo(sheet.left(), sheet.top() + radius)
    body.quadTo(sheet.left(), sheet.top(), sheet.left() + radius, sheet.top())
    body.closeSubpath()

    gradient = QLinearGradient(sheet.topLeft(), sheet.bottomLeft())
    gradient.setColorAt(0.0, QColor(SHEET_TOP))
    gradient.setColorAt(1.0, QColor(SHEET_BOTTOM))
    painter.setBrush(QBrush(gradient))
    painter.setPen(QPen(edge_colour, edge_width))
    painter.drawPath(body)

    # Folded corner, drawn as a darker triangle so the sheet reads as paper.
    corner = QPainterPath()
    corner.moveTo(sheet.right() - fold, sheet.top())
    corner.lineTo(sheet.right() - fold, sheet.top() + fold)
    corner.lineTo(sheet.right(), sheet.top() + fold)
    corner.closeSubpath()
    painter.setPen(QPen(edge_colour, max(1.0, 4 * s)))
    painter.setBrush(edge_colour)
    painter.drawPath(corner)

    # ---- text lines ----------------------------------------------------
    # Below ~24 px these turn into mud, so the small sizes omit them and let
    # the silhouette do the work.
    if not tiny:
        painter.setPen(
            QPen(
                line_colour,
                max(1.0, 9 * s),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        for index, width in enumerate((78, 78, 52)):
            y = (84 + index * 26) * s
            painter.drawLine(
                QPointF(56 * s, y), QPointF((56 + width) * s, y)
            )

    # ---- magnifier -----------------------------------------------------
    centre = QPointF(160 * s, 152 * s)
    lens_radius = 62 * s
    ring_width = max(2.0, (20 if not tiny else 24) * s)

    # Punch a transparent gap around the magnifier so the ring reads clearly
    # where it overlaps the sheet, instead of merging into it.
    painter.save()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(Qt.GlobalColor.black)
    painter.drawEllipse(centre, lens_radius + ring_width * 0.9, lens_radius + ring_width * 0.9)
    painter.restore()

    # Lens glass.
    glass = QLinearGradient(
        centre.x() - lens_radius,
        centre.y() - lens_radius,
        centre.x() + lens_radius,
        centre.y() + lens_radius,
    )
    glass.setColorAt(0.0, QColor(255, 255, 255, 245))
    glass.setColorAt(1.0, QColor(LENS))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(glass))
    painter.drawEllipse(centre, lens_radius, lens_radius)

    # Handle, drawn before the ring so the ring caps it cleanly.
    handle = QLinearGradient(
        centre.x(), centre.y(), 236 * s, 228 * s
    )
    handle.setColorAt(0.0, QColor(ACCENT_DARK))
    handle.setColorAt(1.0, QColor(INK_DARK))
    painter.setPen(
        QPen(
            QBrush(handle),
            ring_width * 1.15,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    start = QPointF(
        centre.x() + lens_radius * 0.72, centre.y() + lens_radius * 0.72
    )
    painter.drawLine(start, QPointF(228 * s, 220 * s))

    # Ring.
    ring = QLinearGradient(
        centre.x() - lens_radius,
        centre.y() - lens_radius,
        centre.x() + lens_radius,
        centre.y() + lens_radius,
    )
    ring.setColorAt(0.0, QColor(ACCENT_LIGHT))
    ring.setColorAt(0.55, QColor(ACCENT))
    ring.setColorAt(1.0, QColor(ACCENT_DARK))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QBrush(ring), ring_width))
    painter.drawEllipse(centre, lens_radius, lens_radius)

    # Highlight arc on the glass; omitted at small sizes where it is noise.
    if size >= 48:
        painter.setPen(
            QPen(
                QColor(255, 255, 255, 210),
                max(1.0, 8 * s),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        arc = QRectF(
            centre.x() - lens_radius * 0.60,
            centre.y() - lens_radius * 0.60,
            lens_radius * 1.20,
            lens_radius * 1.20,
        )
        painter.drawArc(arc, 100 * 16, 70 * 16)

    painter.end()
    return image


# ---------------------------------------------------------------------------
# ICO container
# ---------------------------------------------------------------------------
def _png_bytes(image: QImage) -> bytes:
    # The QByteArray must outlive the QBuffer that wraps it; passing a
    # temporary here segfaults once Python collects it mid-write.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def write_ico(images: list[QImage], target: Path) -> None:
    """Pack images into a multi-resolution ICO.

    Each entry stores a PNG payload, which Windows Vista and later read
    directly.  The header layout is ICONDIR followed by one ICONDIRENTRY per
    image, then the payloads; a width or height byte of 0 means 256.
    """
    payloads = [_png_bytes(image) for image in images]
    count = len(payloads)
    header = struct.pack("<HHH", 0, 1, count)
    directory_size = 16 * count
    offset = len(header) + directory_size

    entries = bytearray()
    for image, payload in zip(images, payloads, strict=True):
        width = 0 if image.width() >= 256 else image.width()
        height = 0 if image.height() >= 256 else image.height()
        entries += struct.pack(
            "<BBBBHHII",
            width,
            height,
            0,  # palette size: 0 for true colour
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(payload),
            offset,
        )
        offset += len(payload)

    target.write_bytes(bytes(header) + bytes(entries) + b"".join(payloads))


def main() -> int:
    app = QApplication.instance() or QApplication([])
    target_dir = PROJECT_ROOT / "assets"
    target_dir.mkdir(parents=True, exist_ok=True)

    images = [draw(size) for size in SIZES]

    ico_path = target_dir / "app.ico"
    write_ico(images, ico_path)

    # A PNG copy is what Qt loads for the window icon; it keeps the alpha
    # channel intact across every platform style.
    for size in (256, 64, 32):
        images[SIZES.index(size)].save(str(target_dir / f"app-{size}.png"), "PNG")
    images[SIZES.index(256)].save(str(target_dir / "app.png"), "PNG")

    print(f"wrote {ico_path.name} with {len(images)} sizes: {', '.join(map(str, SIZES))}")
    print(f"  {ico_path.stat().st_size:,} bytes")
    print(f"wrote app.png, app-256.png, app-64.png, app-32.png to {target_dir}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
