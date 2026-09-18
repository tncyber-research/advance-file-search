r"""Generate the project report's diagrams as local SVG files.

    .venv\Scripts\python.exe scripts\make_report_graphics.py

Same reasoning as the manual's graphics: SVG is plain text, reviewable, crisp
at any zoom, and fetched from nowhere.  The palette and the small drawing
helpers are imported from ``make_manual_graphics`` so the two documents stay
visually identical.

Output: Manual/images/dia_*.svg
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_manual_graphics import (  # noqa: E402
    ACCENT,
    ACCENT_LIGHT,
    ACCENT_SOFT,
    AMBER,
    AMBER_SOFT,
    BORDER,
    CORAL,
    CORAL_SOFT,
    FONT,
    GREEN,
    GREEN_SOFT,
    INK,
    MUTED,
    SURFACE,
    VIOLET,
    _doc_icon,
    _magnifier,
    _text,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "Manual" / "images"

SLATE = "#41566b"
SLATE_SOFT = "#eef2f6"


def _shell(width: int, height: int, body: str, defs: str = "") -> str:
    """SVG wrapper with the arrow markers every diagram here needs."""
    markers = "\n".join(
        f"""    <marker id="ar_{name}" markerWidth="9" markerHeight="9" refX="7.5"
            refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0 0 L7.5 3 L0 6 z" fill="{colour}"/>
    </marker>"""
        for name, colour in (
            ("accent", ACCENT),
            ("muted", MUTED),
            ("green", GREEN),
            ("amber", AMBER),
            ("coral", CORAL),
            ("violet", VIOLET),
        )
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"
     width="100%" role="img" font-family="{FONT}">
  <defs>
{markers}
    <linearGradient id="accentGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{ACCENT_LIGHT}"/>
      <stop offset="1" stop-color="{ACCENT}"/>
    </linearGradient>
    <linearGradient id="paperGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#eef4f7"/>
    </linearGradient>
    <filter id="soft" x="-25%" y="-25%" width="150%" height="150%">
      <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#1b2733"
                    flood-opacity="0.13"/>
    </filter>
{defs}
  </defs>
{body}
</svg>
"""


# --------------------------------------------------------------------------
# small building blocks
# --------------------------------------------------------------------------
def zone(x, y, w, h, label, colour, *, dash="9 7", label_size=16):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="none" '
        f'stroke="{colour}" stroke-width="2" stroke-dasharray="{dash}"/>'
        + _text(x + 18, y + 26, label, size=label_size, fill=colour, weight="700")
    )


def box(
    x,
    y,
    w,
    h,
    title,
    lines=(),
    *,
    colour=ACCENT,
    fill=SURFACE,
    title_size=15,
    line_size=13,
    shadow=True,
):
    """A rounded card with a coloured spine, a title and detail lines."""
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" '
        f'stroke="{colour}" stroke-width="1.6"'
        + (' filter="url(#soft)"/>' if shadow else "/>"),
        f'<rect x="{x}" y="{y}" width="7" height="{h}" rx="3.5" fill="{colour}"/>',
        _text(x + 20, y + 26, title, size=title_size, fill=colour, weight="700"),
    ]
    for i, line in enumerate(lines):
        out.append(_text(x + 20, y + 50 + i * 20, line, size=line_size, fill=MUTED))
    return "\n".join(out)


def pill(x, y, w, h, label, colour, fill):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h // 2}" '
        f'fill="{fill}" stroke="{colour}" stroke-width="1.4"/>'
        + _text(x + w // 2, y + h // 2 + 5, label, size=13, fill=colour,
                weight="600", anchor="middle")
    )


def arrow(x1, y1, x2, y2, colour=ACCENT, *, width=2.4, dash=None, marker=None):
    marker = marker or {
        ACCENT: "accent", MUTED: "muted", GREEN: "green",
        AMBER: "amber", CORAL: "coral", VIOLET: "violet",
    }.get(colour, "accent")
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="{colour}" '
        f'stroke-width="{width}"{d} marker-end="url(#ar_{marker})"/>'
    )


def elbow(x1, y1, x2, y2, colour=ACCENT, *, width=2.4, via_y=None, marker=None):
    """An orthogonal connector: down, across, then into the target."""
    marker = marker or {
        ACCENT: "accent", MUTED: "muted", GREEN: "green",
        AMBER: "amber", CORAL: "coral", VIOLET: "violet",
    }.get(colour, "accent")
    mid = via_y if via_y is not None else (y1 + y2) // 2
    return (
        f'<path d="M{x1} {y1} V{mid} H{x2} V{y2}" fill="none" stroke="{colour}" '
        f'stroke-width="{width}" marker-end="url(#ar_{marker})"/>'
    )


def label(x, y, text, *, size=12, fill=MUTED, anchor="middle", weight="400"):
    return _text(x, y, text, size=size, fill=fill, anchor=anchor, weight=weight)


def diamond(cx, cy, w, h, text_lines, colour=AMBER, fill=AMBER_SOFT):
    pts = f"{cx},{cy - h // 2} {cx + w // 2},{cy} {cx},{cy + h // 2} {cx - w // 2},{cy}"
    out = [
        f'<polygon points="{pts}" fill="{fill}" stroke="{colour}" stroke-width="1.8"/>'
    ]
    start = cy - (len(text_lines) - 1) * 9 + 5
    for i, line in enumerate(text_lines):
        out.append(label(cx, start + i * 18, line, size=13, fill=colour, weight="600"))
    return "\n".join(out)


def cylinder(x, y, w, h, caption, colour=ACCENT):
    ry = max(10, h // 8)
    return f"""<g>
    <path d="M{x} {y + ry} a{w // 2} {ry} 0 0 1 {w} 0 v{h - 2 * ry}
             a{w // 2} {ry} 0 0 1 {-w} 0 z" fill="url(#accentGrad)" opacity="0.92"/>
    <ellipse cx="{x + w // 2}" cy="{y + ry}" rx="{w // 2}" ry="{ry}" fill="{ACCENT_LIGHT}"/>
    {label(x + w // 2, y + h // 2 + 10, caption, size=14, fill="#ffffff", weight="700")}
  </g>"""


# ===========================================================================
# 1. dia_architecture — the whole system on one page
# ===========================================================================
def dia_architecture() -> str:
    p = ['<rect x="0" y="0" width="1040" height="700" fill="none"/>']

    p.append(zone(24, 20, 992, 168, "ฝั่งผู้ใช้ — ส่วนติดต่อผู้ใช้ (Presentation)", ACCENT))
    ui = [
        (46, "หน้าต่างหลัก", ["MainWindow", "แถบค้นหา · ตารางผลลัพธ์", "แผงรายละเอียด"]),
        (288, "กล่องโต้ตอบ", ["ความคืบหน้าดัชนี", "ตั้งค่า", "เกี่ยวกับโปรแกรม"]),
        (530, "โมเดลผลลัพธ์", ["ResultModel", "Delegate วาดเอง", "ไฮไลต์คำที่ตรงกัน"]),
        (772, "ธีมและภาษา", ["theme.py", "i18n ไทย/อังกฤษ", "ฟอนต์และขนาดตัวอักษร"]),
    ]
    for x, title, lines in ui:
        p.append(box(x, 60, 222, 110, title, lines, colour=ACCENT))

    p.append(
        zone(24, 218, 992, 200,
             "ฝั่งประมวลผล — ทำหน้าที่แทน “เซิร์ฟเวอร์” โดยอยู่ในโปรเซสเดียวกัน", VIOLET)
    )
    engine = [
        (46, "ตัวควบคุมการจัดดัชนี",
         ["IndexCoordinator", "เดินไฟล์ · ลายนิ้วมือไฟล์", "ธุรกรรมแยกต่อไฟล์"], VIOLET),
        (288, "ตัวอ่านเอกสาร",
         ["PDF / DOCX", "XLSX / TXT", "แยกเป็นหน่วยข้อความ"], GREEN),
        (530, "บริการค้นหา",
         ["SearchService", "เลือกกลยุทธ์การค้น", "ลองใหม่เมื่อชนกับการจัดดัชนี"], AMBER),
        (772, "ประมวลผลคำค้น",
         ["QueryParser", "Wildcard · การจัดอันดับ", "ตัดข้อความรอบคำที่ตรง"], CORAL),
    ]
    for x, title, lines, colour in engine:
        p.append(box(x, 258, 222, 130, title, lines, colour=colour))
    p.append(_text(994, 410, "ทำงานในเธรดเบื้องหลัง (QThread)",
                   size=12.5, fill=VIOLET, weight="600", anchor="end"))

    p.append(zone(24, 448, 992, 196, "ชั้นจัดเก็บข้อมูล — อยู่ในเครื่องของผู้ใช้ทั้งหมด", GREEN))
    p.append(box(46, 488, 222, 132, "เอกสารต้นฉบับ",
                 ["โฟลเดอร์ที่ผู้ใช้เลือก", "เปิดอ่านอย่างเดียว", "ไม่แก้ ไม่ย้าย ไม่ลบ"],
                 colour=SLATE, fill=SLATE_SOFT))
    p.append('<g transform="translate(300,496)">'
             + _doc_icon(0, 0, 0.85, ACCENT)
             + _doc_icon(46, 0, 0.85, ACCENT_LIGHT)
             + _doc_icon(92, 0, 0.85, ACCENT)
             + "</g>")
    p.append(cylinder(300, 556, 150, 60, "index.db"))
    p.append(label(375, 634, "SQLite + FTS5", size=12, fill=MUTED))
    p.append(box(530, 488, 222, 132, "การตั้งค่า",
                 ["settings.json", "ตำแหน่งหน้าต่าง", "ความกว้างคอลัมน์"], colour=ACCENT))
    p.append(box(772, 488, 222, 132, "บันทึกการทำงาน",
                 ["app.log (หมุนไฟล์)", "เก็บเฉพาะสถิติ", "ไม่มีเนื้อหาเอกสาร"], colour=AMBER))

    # Connectors live in the gaps between the zones, so that no arrow is ever
    # drawn across a label.
    p.append(arrow(150, 190, 150, 214, ACCENT, width=2.8))
    p.append(_text(166, 208, "คำสั่งจากผู้ใช้", size=12, fill=ACCENT))
    p.append(arrow(648, 214, 648, 192, AMBER, width=2.8))
    p.append(_text(664, 208, "ผลลัพธ์ผ่าน Qt signal", size=12, fill=AMBER))
    p.append(arrow(150, 420, 150, 444, VIOLET, width=2.8))
    p.append(_text(166, 438, "อ่านไฟล์", size=12, fill=VIOLET))
    p.append(arrow(399, 420, 399, 444, GREEN, width=2.8))
    p.append(_text(415, 438, "เขียนดัชนี", size=12, fill=GREEN))
    p.append(arrow(648, 444, 648, 422, AMBER, width=2.8))
    p.append(_text(664, 438, "อ่านค่าที่ตั้งไว้", size=12, fill=AMBER))

    p.append('<rect x="24" y="658" width="992" height="34" rx="17" '
             f'fill="{CORAL_SOFT}" stroke="{CORAL}" stroke-width="1.5"/>')
    p.append(label(520, 680,
                   "ขอบเขตของระบบ: ไม่มีซ็อกเก็ต ไม่มีเซิร์ฟเวอร์ ไม่มีเว็บ ไม่มีคลาวด์ "
                   "— ไม่มีข้อมูลใดออกจากเครื่องนี้", size=13, fill=CORAL, weight="700"))
    return _shell(1040, 700, "\n".join(p))


# ===========================================================================
# 2. dia_modules — the source tree as a map
# ===========================================================================
def dia_modules() -> str:
    packages = [
        ("core", "แกนกลางที่ทุกส่วนใช้ร่วมกัน", ACCENT,
         ["constants.py", "models.py", "settings.py", "security.py", "paths.py",
          "i18n.py"]),
        ("indexing", "อ่านไฟล์และสร้างดัชนี", VIOLET,
         ["coordinator.py", "scanner.py", "fingerprint.py", "parsers/pdf_parser.py",
          "parsers/docx_parser.py", "parsers/xlsx_parser.py", "parsers/txt_parser.py"]),
        ("search", "แปลคำค้นและค้นหา", AMBER,
         ["search_service.py", "query_parser.py", "wildcard.py", "ranking.py",
          "snippets.py"]),
        ("storage", "ฐานข้อมูลและสคีมา", GREEN,
         ["database.py", "migrations.py", "repositories.py", "schema.sql"]),
        ("ui", "หน้าจอทั้งหมด", CORAL,
         ["main_window.py", "result_model.py", "delegates.py", "preview.py",
          "index_dialog.py", "settings_dialog.py", "about_dialog.py", "workers.py"]),
        ("winplat", "ส่วนที่เป็นของ Windows โดยเฉพาะ", SLATE,
         ["windows_paths.py", "windows_shell.py", "single_instance.py"]),
    ]
    p = ['<rect x="0" y="0" width="1040" height="664" fill="none"/>']
    p.append(box(24, 16, 992, 62,
                 "advance_file_search — ทั้งโปรแกรมเป็นแพ็กเกจ Python เดียว",
                 ["app.py คือจุดเริ่มต้น · logging_setup.py ตั้งค่าการบันทึกการทำงาน"],
                 colour=ACCENT, title_size=16))
    for i, (name, purpose, colour, files) in enumerate(packages):
        bx = 24 + (i % 3) * 336
        by = 106 + (i // 3) * 266
        p.append(f'<rect x="{bx}" y="{by}" width="312" height="258" rx="14" '
                 f'fill="{SURFACE}" stroke="{colour}" stroke-width="1.8" '
                 f'filter="url(#soft)"/>')
        p.append(f'<path d="M{bx} {by + 46} v-32 a14 14 0 0 1 14 -14 h284 '
                 f'a14 14 0 0 1 14 14 v32 z" fill="{colour}"/>')
        p.append(_text(bx + 18, by + 31, name, size=17, fill="#ffffff", weight="700"))
        p.append(_text(bx + 18, by + 70, purpose, size=13, fill=MUTED))
        for j, filename in enumerate(files):
            fy = by + 96 + j * 20
            p.append(f'<circle cx="{bx + 24}" cy="{fy - 4}" r="3.5" fill="{colour}"/>')
            p.append(_text(bx + 36, fy, filename, size=12.5, fill=INK))
    return _shell(1040, 664, "\n".join(p))


# ===========================================================================
# 3. dia_techstack — what each technology is for
# ===========================================================================
def dia_techstack() -> str:
    rows = [
        ("Python 3.12.10", "ภาษาหลักของทั้งโปรแกรม",
         "ตรรกะทุกส่วน ไม่มีโค้ดภาษาอื่นปน", ACCENT),
        ("PySide6 6.11.2 (Qt 6)", "ชุดสร้างหน้าจอ",
         "หน้าต่าง ตาราง เธรด สัญญาณ และธีม", CORAL),
        ("SQLite 3.49 + FTS5", "ฐานข้อมูลและดัชนีข้อความเต็ม",
         "เก็บรายการไฟล์ หน่วยข้อความ และใช้ค้นหา", GREEN),
        ("ตัวแยกคำ trigram", "ทำให้ค้นภาษาไทยได้จริง",
         "ค้นคำที่อยู่กลางข้อความไทยที่ไม่เว้นวรรค", AMBER),
        ("PyMuPDF 1.26.5", "อ่านข้อความจาก PDF",
         "ดึงข้อความรายหน้า และตรวจไฟล์ที่ใส่รหัสผ่าน", VIOLET),
        ("python-docx 1.2.0", "อ่านเอกสาร Word",
         "ย่อหน้า ตาราง หัวกระดาษ ท้ายกระดาษ", VIOLET),
        ("openpyxl 3.1.5", "อ่านสมุดงาน Excel",
         "อ่านรายเซลล์ และข้ามชีตที่ซ่อนไว้", VIOLET),
        ("lxml 6.0.2", "ตัวอ่าน XML เบื้องหลัง",
         "ถูกเรียกใช้โดย python-docx และ openpyxl", MUTED),
        ("PyInstaller (onedir)", "ห่อรวมเป็นไฟล์ .exe",
         "รวม Python และไลบรารีไว้ในโฟลเดอร์เดียว", SLATE),
        ("pytest", "ชุดทดสอบอัตโนมัติ",
         "606 การทดสอบ ครอบคลุมทุกชั้นของระบบ", ACCENT),
    ]
    p = ['<rect x="0" y="0" width="1040" height="620" fill="none"/>']
    p.append(_text(24, 32, "เทคโนโลยีที่ใช้ และหน้าที่ของแต่ละอย่าง",
                   size=18, fill=INK, weight="700"))
    p.append(_text(24, 56, "ทุกอย่างติดตั้งตอนสร้างโปรแกรมเท่านั้น เวลาใช้งานจริงไม่ต้องต่ออินเทอร์เน็ต",
                   size=13, fill=MUTED))
    y = 74
    for name, role, used_for, colour in rows:
        p.append(f'<rect x="24" y="{y}" width="992" height="48" rx="11" '
                 f'fill="{SURFACE}" stroke="{BORDER}" stroke-width="1.2"/>')
        p.append(f'<rect x="24" y="{y}" width="7" height="48" rx="3.5" fill="{colour}"/>')
        p.append(_text(46, y + 30, name, size=14.5, fill=colour, weight="700"))
        p.append(f'<line x1="300" y1="{y + 10}" x2="300" y2="{y + 38}" '
                 f'stroke="{BORDER}" stroke-width="1"/>')
        p.append(_text(318, y + 30, role, size=13.5, fill=INK))
        p.append(f'<line x1="600" y1="{y + 10}" x2="600" y2="{y + 38}" '
                 f'stroke="{BORDER}" stroke-width="1"/>')
        p.append(_text(618, y + 30, used_for, size=13.5, fill=MUTED))
        y += 52
    return _shell(1040, 620, "\n".join(p))


# ===========================================================================
# 4. dia_index_flow — how one indexing run works
# ===========================================================================
def dia_index_flow() -> str:
    p = ['<rect x="0" y="0" width="1040" height="940" fill="none"/>']
    cx = 520

    p.append(pill(cx - 150, 16, 300, 42, "เริ่ม: ผู้ใช้กดค้นหา หรือสั่งอัปเดตดัชนี",
                  ACCENT, ACCENT_SOFT))
    p.append(arrow(cx, 58, cx, 84, ACCENT))

    p.append(diamond(cx, 120, 330, 72,
                     ["ยังไม่มีดัชนีของโฟลเดอร์นี้?"], AMBER))
    p.append(label(cx + 190, 112, "มีแล้ว → อัปเดตเฉพาะส่วนที่เปลี่ยน",
                   size=12, fill=MUTED, anchor="start"))
    p.append(arrow(cx, 156, cx, 184, ACCENT))

    stages = [
        (184, "1. เดินสำรวจไฟล์ (Scanner)",
         ["ไล่ดูไฟล์ในโฟลเดอร์ที่เลือกและโฟลเดอร์ย่อย", "กรองไฟล์ที่ไม่ควรแตะตั้งแต่ชั้นนี้"], VIOLET),
        (286, "2. คำนวณลายนิ้วมือไฟล์ (Fingerprint)",
         ["ขนาด + เวลาแก้ไข + เวอร์ชันตัวอ่าน", "ไม่ต้องอ่านทั้งไฟล์เพื่อรู้ว่าเปลี่ยนหรือยัง"], VIOLET),
    ]
    for y, title, lines, colour in stages:
        p.append(box(cx - 230, y, 460, 84, title, lines, colour=colour))
    p.append(arrow(cx, 268, cx, 284, VIOLET))
    p.append(arrow(cx, 370, cx, 396, VIOLET))

    p.append(diamond(cx, 434, 340, 76, ["ลายนิ้วมือตรงกับที่เก็บไว้?"], AMBER))
    p.append(arrow(cx + 170, 434, 806, 434, GREEN))
    p.append(box(806, 404, 210, 60, "ข้าม", ["นับเป็น unchanged"], colour=GREEN))
    p.append(arrow(cx, 472, cx, 498, ACCENT))
    p.append(label(cx + 24, 492, "ไม่ตรง → ต้องอ่านใหม่", size=12, fill=ACCENT, anchor="start"))

    stages2 = [
        (498, "3. เลือกตัวอ่านตามนามสกุลไฟล์",
         ["PDF → PyMuPDF · DOCX → python-docx", "XLSX → openpyxl · TXT → ตรวจรหัสอักขระเอง"], GREEN),
        (600, "4. แยกข้อความออกเป็น “หน่วย”",
         ["1 หน้า / 1 ย่อหน้า / 1 เซลล์ / 1 บรรทัด", "แต่ละหน่วยจำตำแหน่งของตัวเองไว้"], GREEN),
        (702, "5. เขียนลงฐานข้อมูลแบบทีละไฟล์",
         ["ใช้ SAVEPOINT ต่อไฟล์ — ไฟล์เสียหนึ่งไฟล์ไม่ทำให้ทั้งงานล้ม",
          "ทริกเกอร์ของ SQLite อัปเดตดัชนี FTS ให้เอง"], GREEN),
    ]
    for y, title, lines, colour in stages2:
        p.append(box(cx - 230, y, 460, 84, title, lines, colour=colour))
    p.append(arrow(cx, 582, cx, 598, GREEN))
    p.append(arrow(cx, 684, cx, 700, GREEN))
    p.append(arrow(cx, 786, cx, 812, ACCENT))

    p.append(box(cx - 230, 812, 460, 84, "6. ปิดงานและสรุปผล",
                 ["ไฟล์ที่ไม่พบในรอบนี้ = ถูกลบ → เอาออกจากดัชนี",
                  "บันทึกสถิติของรอบนี้ลงตาราง index_runs"], colour=ACCENT))

    p.append(box(24, 184, 240, 200, "กรองออกตั้งแต่ต้น",
                 ["ทางลัด (.lnk) และ junction", "ไฟล์ชั่วคราวของ Office (~$)",
                  "ไฟล์ใหญ่เกินค่าที่ตั้งไว้", "นามสกุลที่ไม่รองรับ",
                  "ไฟล์บนคลาวด์ที่ยังไม่ดาวน์โหลด", "ไม่มีการ “เปิด” ไฟล์ให้ทำงาน"],
                 colour=CORAL))
    p.append(box(776, 498, 240, 200, "ผลของแต่ละไฟล์",
                 ["indexed — อ่านข้อความได้", "unchanged — ไม่ได้แก้ไข",
                  "no_text — ไม่มีข้อความ เช่น PDF สแกน", "failed — ไฟล์เสียหรือถูกล็อก",
                  "skipped — ถูกกรองออก", "deleted — ไฟล์หายไปแล้ว"],
                 colour=SLATE, fill=SLATE_SOFT))
    p.append(label(520, 926,
                   "ยกเลิกได้ทุกเมื่อ: งานจะหยุดที่ขอบเขตของไฟล์ถัดไป ดัชนีที่ทำไปแล้วยังใช้ได้",
                   size=13, fill=VIOLET, weight="600"))
    return _shell(1040, 940, "\n".join(p))


# ===========================================================================
# 5. dia_search_flow — how one search works
# ===========================================================================
def dia_search_flow() -> str:
    p = ['<rect x="0" y="0" width="1040" height="900" fill="none"/>']
    cx = 500

    p.append(pill(cx - 160, 16, 320, 42, "ผู้ใช้พิมพ์คำค้นแล้วกดค้นหา", ACCENT, ACCENT_SOFT))
    p.append(arrow(cx, 58, cx, 84, ACCENT))

    p.append(box(cx - 240, 84, 480, 82, "1. ตรวจความปลอดภัยของคำค้น",
                 ["จำกัดความยาว 500 ตัวอักษร และไม่เกิน 24 คำ",
                  "จำกัดจำนวน wildcard ต่อคำ เพื่อไม่ให้ค้นหานานผิดปกติ"], colour=CORAL))
    p.append(arrow(cx, 166, cx, 192, ACCENT))

    p.append(box(cx - 240, 192, 480, 82, "2. แปลคำค้น (QueryParser)",
                 ["แยกวลีในเครื่องหมายคำพูด ออกจากคำเดี่ยว",
                  "อ่านสัญลักษณ์ * และ ? แล้วแปลงเป็นเงื่อนไขการเทียบ"], colour=VIOLET))
    p.append(arrow(cx, 274, cx, 306, ACCENT))

    p.append(diamond(cx, 348, 360, 80, ["คำค้นสั้นกว่า 3 ตัวอักษร?"], AMBER))
    p.append(arrow(cx - 180, 348, 274, 348, AMBER))
    p.append(box(24, 316, 250, 66, "สแกนแบบจำกัดขอบเขต",
                 ["ใช้ LIKE ที่มีเพดานจำนวนแถว"], colour=AMBER))
    p.append(arrow(cx, 388, cx, 420, ACCENT))

    p.append(box(cx - 240, 420, 480, 88, "3. ค้นจากดัชนี FTS5 (trigram)",
                 ["name_fts สำหรับชื่อไฟล์ · content_fts สำหรับเนื้อหา",
                  "trigram ทำให้ค้นคำกลางข้อความไทยที่ไม่เว้นวรรคได้"], colour=GREEN))
    p.append(elbow(149, 382, cx - 150, 420, AMBER, via_y=404))
    p.append(arrow(cx, 508, cx, 534, ACCENT))

    p.append(box(cx - 240, 534, 480, 82, "4. ตรวจเงื่อนไขละเอียดอีกชั้น",
                 ["ตรงตัวพิมพ์เล็กใหญ่ · ทั้งคำ · รูปแบบ wildcard",
                  "ทำในหน่วยความจำ เพราะ trigram ไม่แยกความต่างเหล่านี้"], colour=GREEN))
    p.append(arrow(cx, 616, cx, 642, ACCENT))

    p.append(box(cx - 240, 642, 480, 82, "5. กรองและจัดอันดับ",
                 ["กรองตามนามสกุล วันที่ ขนาด และโฟลเดอร์ย่อย",
                  "ชื่อไฟล์ที่ตรงมาก่อนเนื้อหา แล้วดูจำนวนครั้งและความใหม่"], colour=ACCENT))
    p.append(arrow(cx, 724, cx, 750, ACCENT))

    p.append(box(cx - 240, 750, 480, 82, "6. ตัดข้อความรอบคำที่ตรง แล้วส่งกลับ",
                 ["บอกตำแหน่ง: หน้า / ย่อหน้า / ชีตและเซลล์ / บรรทัด",
                  "ส่งกลับหน้าจอผ่าน Qt signal พร้อมตำแหน่งไฮไลต์"], colour=ACCENT))

    p.append(box(776, 84, 240, 190, "ทำงานในเธรดเบื้องหลัง",
                 ["หน้าจอไม่ค้างระหว่างค้นหา", "กดยกเลิกได้ตลอดเวลา",
                  "พิมพ์คำใหม่ = ยกเลิกงานเก่า", "ผลลัพธ์เก่าที่มาช้าถูกทิ้ง"],
                 colour=SLATE, fill=SLATE_SOFT))
    p.append(box(776, 534, 240, 190, "ถ้าชนกับการจัดดัชนี",
                 ["ฐานข้อมูลอาจกำลังถูกเขียนอยู่", "ระบบจะรู้ว่าเป็นข้อผิดพลาดชั่วคราว",
                  "ปิดการเชื่อมต่อของเธรดนั้น", "รอ 120 มิลลิวินาที แล้วลองใหม่ 1 ครั้ง",
                  "ผู้ใช้ไม่เห็นความผิดพลาดนี้"], colour=CORAL))
    p.append(arrow(776, 575, 744, 575, CORAL))
    return _shell(1040, 900, "\n".join(p))


# ===========================================================================
# 6. dia_ipc — how the user side and the engine side talk to each other
# ===========================================================================
def dia_ipc() -> str:
    p = ['<rect x="0" y="0" width="1040" height="660" fill="none"/>']

    p.append(zone(24, 16, 440, 300, "เธรดหน้าจอ (ฝั่งผู้ใช้)", ACCENT))
    p.append(box(46, 60, 396, 96, "MainWindow",
                 ["รับคำสั่งจากผู้ใช้ · แสดงผลลัพธ์",
                  "ห้ามทำงานหนักในเธรดนี้ มิฉะนั้นหน้าจอค้าง"], colour=ACCENT))
    p.append(box(46, 172, 396, 124, "ตัวรับสัญญาณ (slots)",
                 ["on_progress — อัปเดตแถบความคืบหน้า",
                  "on_finished — เติมผลลัพธ์ลงตาราง",
                  "on_failed — แสดงข้อความที่อ่านเข้าใจได้",
                  "ตรวจหมายเลขงานก่อนเสมอ ผลเก่าถูกทิ้ง"], colour=ACCENT))

    p.append(zone(576, 16, 440, 300, "เธรดเบื้องหลัง (ฝั่งประมวลผล)", VIOLET))
    p.append(box(598, 60, 396, 96, "SearchWorker",
                 ["เรียก SearchService แล้วส่งผลกลับ",
                  "ตรวจธงยกเลิกเป็นระยะ"], colour=AMBER))
    p.append(box(598, 172, 396, 124, "IndexWorker",
                 ["เรียก IndexCoordinator ทีละไฟล์",
                  "ส่งความคืบหน้าเป็นระยะ ไม่ส่งชื่อเนื้อหา",
                  "หยุดที่ขอบเขตไฟล์เมื่อถูกยกเลิก"], colour=VIOLET))

    # Short labels only: the gap between the two zones is 150 px wide, and a
    # label that runs under a box is worse than no label at all.
    p.append(arrow(444, 100, 596, 100, ACCENT, width=2.8))
    p.append(label(520, 90, "เริ่มงาน", size=12.5, fill=ACCENT, weight="600"))
    p.append(arrow(596, 140, 444, 140, AMBER, width=2.8))
    p.append(label(520, 130, "Qt signal", size=12.5, fill=AMBER, weight="600"))
    p.append(arrow(444, 236, 596, 236, CORAL, width=2.8))
    p.append(label(520, 226, "ยกเลิก", size=12.5, fill=CORAL, weight="600"))

    p.append(zone(24, 340, 992, 200, "ชั้นฐานข้อมูล — หนึ่งการเชื่อมต่อต่อหนึ่งเธรด", GREEN))
    p.append(box(46, 384, 300, 132, "การเชื่อมต่อของเธรดหน้าจอ",
                 ["ใช้สำหรับอ่านข้อมูลเล็ก ๆ", "เช่น สถานะดัชนี จำนวนไฟล์"], colour=ACCENT))
    p.append(box(370, 384, 300, 132, "การเชื่อมต่อของเธรดค้นหา",
                 ["อ่านอย่างเดียว", "โหมด WAL ทำให้อ่านได้ขณะมีการเขียน"], colour=AMBER))
    p.append(box(694, 384, 300, 132, "การเชื่อมต่อของเธรดจัดดัชนี",
                 ["เขียนทีละไฟล์", "ถ้าชนกัน ฝั่งอ่านจะลองใหม่หนึ่งครั้ง"], colour=VIOLET))
    p.append(arrow(196, 518, 466, 556, ACCENT))
    p.append(arrow(520, 518, 520, 556, AMBER))
    p.append(arrow(844, 518, 574, 556, VIOLET))
    p.append(cylinder(440, 560, 160, 66, "index.db (WAL)"))

    p.append(box(24, 566, 380, 76, "ผู้ใช้เปิดโปรแกรมซ้ำ",
                 ["ตัวล็อกระดับระบบยอมให้มีหน้าต่างเดียว", "ตัวที่สองจะดึงหน้าต่างเดิมขึ้นมาแทน"],
                 colour=SLATE, fill=SLATE_SOFT))
    p.append(box(636, 566, 380, 76, "การเปิดไฟล์และโฟลเดอร์",
                 ["ส่งพาธให้ Windows Shell เป็นตัวเปิด", "โปรแกรมไม่สั่งรันไฟล์เอง"],
                 colour=SLATE, fill=SLATE_SOFT))
    return _shell(1040, 660, "\n".join(p))


# ===========================================================================
# 7. dia_dataflow — where every piece of data comes from and goes
# ===========================================================================
def dia_dataflow() -> str:
    p = ['<rect x="0" y="0" width="1040" height="700" fill="none"/>']
    p.append(zone(16, 12, 900, 640, "ขอบเขตความเชื่อถือ: เครื่องคอมพิวเตอร์ของผู้ใช้", CORAL))

    p.append(box(44, 60, 210, 96, "ผู้ใช้",
                 ["เลือกโฟลเดอร์", "พิมพ์คำค้นและตัวกรอง"], colour=SLATE, fill=SLATE_SOFT))
    p.append(box(44, 300, 210, 110, "เอกสารต้นฉบับ",
                 ["PDF · DOCX · XLSX · TXT", "อ่านอย่างเดียว", "ไม่ถูกแก้ไขหรือย้าย"],
                 colour=GREEN))
    p.append(box(44, 470, 210, 110, "ค่าที่ตั้งไว้",
                 ["settings.json", "ภาษา ขนาดตัวอักษร", "ตำแหน่งหน้าต่าง"], colour=ACCENT))

    circles = [
        (420, 108, "1.0", "จัดดัชนี", VIOLET),
        (420, 350, "2.0", "ค้นหา", AMBER),
        (420, 560, "3.0", "แสดงผล", ACCENT),
    ]
    for x, y, number, name, colour in circles:
        p.append(f'<circle cx="{x}" cy="{y}" r="62" fill="{SURFACE}" stroke="{colour}" '
                 f'stroke-width="2.4" filter="url(#soft)"/>')
        p.append(label(x, y - 6, number, size=17, fill=colour, weight="700"))
        p.append(label(x, y + 20, name, size=15, fill=INK, weight="600"))

    p.append(cylinder(620, 250, 200, 100, "D1  index.db"))
    p.append(label(720, 372, "files · content_units · content_fts · name_fts",
                   size=12, fill=MUTED))
    p.append(box(620, 470, 200, 110, "D2  app.log",
                 ["เวลา · ระดับ · เหตุการณ์", "จำนวนไฟล์ · ระยะเวลา",
                  "ไม่มีข้อความในเอกสาร"], colour=AMBER))

    p.append(arrow(254, 100, 356, 100, SLATE, marker="muted"))
    p.append(label(306, 90, "โฟลเดอร์", size=12))
    p.append(arrow(254, 340, 358, 340, GREEN))
    p.append(label(306, 330, "ข้อความในไฟล์", size=12, fill=GREEN))
    p.append(arrow(254, 528, 358, 545, ACCENT))
    p.append(label(306, 520, "ค่าที่ตั้งไว้", size=12, fill=ACCENT))
    p.append(arrow(300, 128, 358, 300, GREEN, width=2))
    p.append(arrow(482, 128, 616, 250, VIOLET))
    p.append(label(576, 176, "หน่วยข้อความ + ข้อมูลไฟล์", size=12, fill=VIOLET, anchor="start"))
    p.append(arrow(616, 320, 484, 340, AMBER))
    p.append(label(548, 306, "รายการที่ตรงกัน", size=12, fill=AMBER))
    p.append(arrow(420, 412, 420, 496, ACCENT))
    p.append(label(500, 456, "ผลลัพธ์ + ข้อความรอบคำค้น", size=12, fill=ACCENT))
    p.append(arrow(358, 560, 256, 560, ACCENT))
    p.append(_text(180, 586, "บันทึกค่าที่ผู้ใช้เปลี่ยน", size=12, fill=ACCENT))
    # The log flow is routed around the outside so that it crosses no other
    # shape on its way from the indexer to the log file.
    p.append(f'<path d="M482 96 H900 V500 H826" fill="none" stroke="{AMBER}" '
             f'stroke-width="2.4" marker-end="url(#ar_amber)"/>')
    p.append(label(700, 84, "สถิติการทำงานเท่านั้น ไม่มีข้อความจากเอกสาร",
                   size=12, fill=AMBER))

    p.append(f'<line x1="916" y1="20" x2="916" y2="644" stroke="{CORAL}" '
             f'stroke-width="3" stroke-dasharray="10 8"/>')
    p.append('<g opacity="0.9">'
             f'<circle cx="978" cy="330" r="46" fill="#f2f5f7" stroke="{BORDER}" '
             f'stroke-width="2"/>'
             f'<ellipse cx="978" cy="330" rx="46" ry="18" fill="none" stroke="{BORDER}" '
             f'stroke-width="2"/>'
             f'<line x1="978" y1="284" x2="978" y2="376" stroke="{BORDER}" stroke-width="2"/>'
             f'<g stroke="{CORAL}" stroke-width="8" stroke-linecap="round">'
             f'<line x1="948" y1="300" x2="1008" y2="360"/>'
             f'<line x1="1008" y1="300" x2="948" y2="360"/></g></g>')
    p.append(label(978, 400, "ไม่มีเส้นทาง", size=12, fill=CORAL, weight="700"))
    p.append(label(978, 420, "ออกสู่ภายนอก", size=12, fill=CORAL, weight="700"))
    p.append(label(460, 676,
                   "ทุกลูกศรในแผนภาพนี้อยู่ในเครื่องเดียวกันทั้งหมด ไม่มีลูกศรใดข้ามเส้นประสีส้ม",
                   size=13, fill=CORAL, weight="600"))
    return _shell(1040, 700, "\n".join(p))


# ===========================================================================
# 8. dia_erd — the database
# ===========================================================================
def dia_erd() -> str:
    def table(x, y, w, name, rows, colour, note=""):
        h = 46 + len(rows) * 20 + (24 if note else 8)
        out = [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{SURFACE}" '
            f'stroke="{colour}" stroke-width="1.8" filter="url(#soft)"/>',
            f'<path d="M{x} {y + 40} v-28 a12 12 0 0 1 12 -12 h{w - 24} '
            f'a12 12 0 0 1 12 12 v28 z" fill="{colour}"/>',
            _text(x + 14, y + 27, name, size=14.5, fill="#ffffff", weight="700"),
        ]
        for i, (col, kind) in enumerate(rows):
            ty = y + 62 + i * 20
            out.append(_text(x + 14, ty, col, size=12.5, fill=INK))
            out.append(_text(x + w - 14, ty, kind, size=11.5, fill=MUTED, anchor="end"))
        if note:
            out.append(_text(x + 14, y + h - 10, note, size=11.5, fill=colour))
        return "\n".join(out), h

    p = ['<rect x="0" y="0" width="1100" height="760" fill="none"/>']

    t, _ = table(24, 20, 268, "roots — โฟลเดอร์ที่ถูกจัดดัชนี", [
        ("id", "PK"), ("display_path", "TEXT"), ("normalized_path", "UNIQUE"),
        ("last_index_completed_at", "TEXT"), ("last_index_status", "TEXT"),
        ("file_count", "INTEGER"),
    ], ACCENT)
    p.append(t)

    t, _ = table(24, 250, 268, "index_runs — ประวัติการจัดดัชนี", [
        ("id", "PK"), ("root_id", "FK → roots"), ("started_at / finished_at", "TEXT"),
        ("mode", "update / rebuild"), ("files_indexed", "INTEGER"),
        ("files_unchanged", "INTEGER"), ("files_failed", "INTEGER"),
        ("elapsed_seconds", "REAL"),
    ], SLATE)
    p.append(t)

    t, _ = table(24, 520, 268, "app_meta — ข้อมูลของฐานข้อมูลเอง", [
        ("key", "PK"), ("value", "TEXT"),
    ], MUTED, note="เก็บเลขเวอร์ชันของสคีมา")
    p.append(t)

    t, _ = table(372, 20, 316, "files — หนึ่งแถวต่อหนึ่งไฟล์", [
        ("id", "PK"), ("root_id", "FK → roots"), ("display_path", "TEXT"),
        ("relative_path / file_name", "TEXT"), ("file_name_folded", "ใช้ค้นแบบไม่สนตัวพิมพ์"),
        ("extension · size_bytes", "TEXT · INT"), ("created_time · modified_time", "REAL"),
        ("fingerprint", "ใช้ตรวจว่าไฟล์เปลี่ยนหรือยัง"),
        ("content_status", "indexed / no_text / failed"),
        ("unit_count · char_count", "INTEGER"), ("error_code", "TEXT"),
        ("error_message_sanitized", "ข้อความที่ล้างข้อมูลแล้ว"),
    ], VIOLET, note="UNIQUE (root_id, normalized_path) + ดัชนีช่วยค้น 6 ตัว")
    p.append(t)

    t, _ = table(372, 380, 316, "content_units — หน่วยข้อความ", [
        ("id", "PK"), ("file_id", "FK → files"), ("sequence", "ลำดับในไฟล์"),
        ("location_type", "page / paragraph / cell / line"),
        ("location_label", "ข้อความที่แสดงให้ผู้ใช้"),
        ("location_json", "ตำแหน่งแบบละเอียด"), ("text", "ข้อความจริงของหน่วยนี้"),
    ], GREEN, note="ข้อความของเอกสารถูกเก็บที่นี่ที่เดียว")
    p.append(t)

    t, _ = table(768, 250, 308, "content_fts — ดัชนีข้อความเต็ม", [
        ("text", "FTS5 external content"), ("content=", "content_units"),
        ("tokenize=", "trigram"),
    ], AMBER, note="ทำให้ค้นคำกลางข้อความไทยได้")
    p.append(t)

    t, _ = table(768, 60, 308, "name_fts — ดัชนีชื่อไฟล์", [
        ("file_name", "FTS5 external content"), ("relative_path", "FTS5"),
        ("content=", "files"), ("tokenize=", "trigram"),
    ], AMBER, note="ค้นเฉพาะชื่อไฟล์ได้โดยไม่แตะเนื้อหา")
    p.append(t)

    p.append(box(768, 470, 308, 160, "ทริกเกอร์ 6 ตัว",
                 ["AFTER INSERT / DELETE / UPDATE", "ของทั้ง files และ content_units",
                  "อัปเดตดัชนี FTS ให้ตรงเสมอ", "โปรแกรมจึงไม่ต้องจำว่าต้องซิงก์เอง",
                  "ลดโอกาสที่ดัชนีจะเพี้ยน"], colour=CORAL))

    p.append(arrow(292, 90, 368, 90, ACCENT))
    p.append(label(330, 80, "1 : N", size=12, fill=ACCENT))
    p.append(arrow(292, 300, 368, 190, SLATE, marker="muted"))
    p.append(arrow(530, 300, 530, 376, VIOLET))
    p.append(label(576, 344, "1 : N", size=12, fill=VIOLET))
    p.append(arrow(692, 440, 764, 360, AMBER))
    p.append(_text(700, 232, "ซิงก์ด้วยทริกเกอร์อัตโนมัติ", size=12, fill=AMBER))
    p.append(arrow(692, 160, 764, 140, AMBER))
    p.append(label(460, 742,
                   "หลักการเดียวกันทั้งฐานข้อมูล: ข้อความเก็บครั้งเดียว ดัชนีชี้กลับมาที่ข้อความนั้น "
                   "และทุกคำสั่ง SQL ใช้พารามิเตอร์เสมอ", size=13, fill=MUTED))
    return _shell(1100, 760, "\n".join(p))


# ===========================================================================
# 9. dia_ux — the screen, as a designed layout
# ===========================================================================
def dia_ux() -> str:
    p = ['<rect x="0" y="0" width="1100" height="700" fill="none"/>']
    p.append(f'<rect x="24" y="20" width="700" height="470" rx="14" fill="{SURFACE}" '
             f'stroke="{BORDER}" stroke-width="2" filter="url(#soft)"/>')
    p.append(f'<path d="M24 62 v-28 a14 14 0 0 1 14 -14 h672 a14 14 0 0 1 14 14 v28 z" '
             f'fill="{ACCENT}"/>')
    p.append(_magnifier(48, 40, 11, "#ffffff"))
    p.append(_text(72, 46, "Advance File Search", size=14, fill="#ffffff", weight="700"))

    p.append(f'<rect x="40" y="76" width="668" height="44" rx="10" fill="{ACCENT_SOFT}" '
             f'stroke="{BORDER}"/>')
    p.append(_text(56, 104, "โฟลเดอร์ที่ค้นหา  ▾", size=12.5, fill=MUTED))
    p.append(pill(470, 86, 106, 26, "ตั้งค่า", ACCENT, SURFACE))
    p.append(pill(586, 86, 112, 26, "คู่มือการใช้งาน", ACCENT, SURFACE))

    p.append(f'<rect x="40" y="132" width="500" height="42" rx="10" fill="{SURFACE}" '
             f'stroke="{ACCENT}" stroke-width="1.6"/>')
    p.append(_text(58, 158, "พิมพ์คำค้นหา…", size=13, fill=MUTED))
    p.append(pill(552, 132, 156, 42, "ค้นหา", "#ffffff", ACCENT))

    p.append(f'<rect x="40" y="186" width="668" height="32" rx="8" fill="{SLATE_SOFT}" '
             f'stroke="{BORDER}"/>')
    p.append(_text(56, 207, "ตัวกรอง: นามสกุล · วันที่ · ขนาด · โฟลเดอร์ย่อย   ▾",
                   size=12, fill=MUTED))

    p.append(f'<rect x="40" y="230" width="410" height="240" rx="10" fill="{SURFACE}" '
             f'stroke="{BORDER}"/>')
    p.append(f'<rect x="40" y="230" width="410" height="30" rx="10" fill="{ACCENT_SOFT}"/>')
    for tx, header in ((52, "ชื่อไฟล์"), (172, "ข้อความที่ตรง"),
                       (292, "ชนิด"), (336, "ขนาด"), (392, "แก้ไข"),
                       (428, "เปิด")):
        p.append(_text(tx, 250, header, size=11, fill=ACCENT, weight="700"))
    for r in range(6):
        ry = 268 + r * 32
        if r % 2:
            p.append(f'<rect x="41" y="{ry - 12}" width="408" height="32" fill="#fafcfd"/>')
        p.append(f'<rect x="52" y="{ry - 6}" width="104" height="8" rx="4" fill="{BORDER}"/>')
        p.append(f'<rect x="172" y="{ry - 6}" width="100" height="8" rx="4" fill="{ACCENT_SOFT}"/>')
        p.append(f'<rect x="292" y="{ry - 6}" width="30" height="8" rx="4" fill="{BORDER}"/>')
        p.append(f'<rect x="336" y="{ry - 6}" width="40" height="8" rx="4" fill="{BORDER}"/>')
        p.append(f'<rect x="392" y="{ry - 6}" width="24" height="8" rx="4" fill="{BORDER}"/>')
        p.append(f'<rect x="424" y="{ry - 13}" width="22" height="18" rx="5" '
                 f'fill="{ACCENT_SOFT}" stroke="{ACCENT}" stroke-width="1"/>')

    p.append(f'<rect x="462" y="230" width="246" height="240" rx="10" fill="{SURFACE}" '
             f'stroke="{BORDER}"/>')
    p.append(_text(476, 252, "รายละเอียดไฟล์", size=12.5, fill=ACCENT, weight="700"))
    for i in range(4):
        p.append(f'<rect x="476" y="{266 + i * 18}" width="{200 - i * 22}" height="7" '
                 f'rx="3.5" fill="{BORDER}"/>')
    p.append(f'<rect x="476" y="348" width="218" height="106" rx="9" fill="{AMBER_SOFT}" '
             f'stroke="{AMBER}" stroke-width="1.2"/>')
    p.append(_text(488, 368, "ข้อความที่ตรงกับคำค้น", size=11.5, fill=AMBER, weight="700"))
    for i in range(3):
        p.append(f'<rect x="488" y="{380 + i * 16}" width="{194 - i * 30}" height="7" '
                 f'rx="3.5" fill="#e8c87a"/>')
    p.append(f'<rect x="528" y="380" width="46" height="7" rx="3.5" fill="{AMBER}"/>')
    p.append(f'<rect x="506" y="396" width="38" height="7" rx="3.5" fill="{AMBER}"/>')
    p.append(_text(488, 444, "หน้า 3 · ย่อหน้า 12", size=11, fill=MUTED))

    # Badges sit clear of every label they point at, never on top of one.
    badges = [
        (20, 40, 1), (20, 98, 2), (20, 153, 3), (20, 202, 4),
        (54, 452, 5), (436, 452, 6), (694, 244, 7), (686, 358, 8),
    ]
    for bx, by, n in badges:
        p.append(f'<circle cx="{bx}" cy="{by}" r="15" fill="{CORAL}" stroke="#ffffff" '
                 f'stroke-width="2"/>')
        p.append(label(bx, by + 5, str(n), size=13, fill="#ffffff", weight="700"))

    notes = [
        (1, "แถบชื่อเรื่องพร้อมไอคอน", "บอกว่าโปรแกรมคืออะไร แม้ย่อลงบนแถบงาน"),
        (2, "แถวเลือกโฟลเดอร์และเมนู", "งานที่ทำครั้งเดียวถูกดันขึ้นบนสุด"),
        (3, "ช่องค้นหาและปุ่มค้นหา", "จุดที่ผู้ใช้มองหาก่อนเสมอ จึงเด่นที่สุด"),
        (4, "ตัวกรองแบบพับเก็บได้", "ไม่รบกวนผู้ใช้ทั่วไป แต่มีให้เมื่อต้องการ"),
        (5, "ตารางผลลัพธ์", "เรียงจากซ้าย: ชื่อ → ข้อความ → ข้อมูลไฟล์"),
        (6, "ปุ่มเปิดโฟลเดอร์", "ไอคอนเล็ก ไม่แย่งความสนใจจากผลลัพธ์"),
        (7, "แผงรายละเอียด", "ข้อมูลของไฟล์ที่เลือก ไม่พูดซ้ำกับตาราง"),
        (8, "กล่องข้อความที่ตรงกัน", "พื้นหลังต่างจากส่วนอื่น และไฮไลต์คำที่ค้น"),
    ]
    y = 24
    for n, title, detail in notes:
        p.append(f'<circle cx="{758}" cy="{y + 14}" r="14" fill="{CORAL}"/>')
        p.append(label(758, y + 19, str(n), size=13, fill="#ffffff", weight="700"))
        p.append(_text(782, y + 12, title, size=13.5, fill=INK, weight="700"))
        p.append(_text(782, y + 32, detail, size=12, fill=MUTED))
        y += 58
    p.append(box(24, 510, 1052, 150, "หลักที่ใช้ตัดสินใจเรื่องหน้าตา",
                 ["ลำดับสายตา: คำถามของผู้ใช้ (ค้นอะไร) มาก่อนคำตอบ (เจออะไร) เสมอ",
                  "ทุกอย่างที่แสดงต้องอธิบายตัวเองได้ — ไอคอนที่ไม่มีข้อความต้องมีคำอธิบายเมื่อชี้ค้าง",
                  "ไม่ซ้ำข้อมูล: สิ่งที่ตารางบอกแล้ว แผงรายละเอียดไม่พูดซ้ำ",
                  "สีใช้เพื่อสื่อความหมาย ไม่ใช่เพื่อความสวย: ส้ม = ต้องระวัง, เขียว = สำเร็จ",
                  "รองรับสองภาษาเต็มรูปแบบ และตัวอักษรใหญ่พอสำหรับการอ่านนาน ๆ"],
                 colour=ACCENT))
    return _shell(1100, 700, "\n".join(p))


# ===========================================================================
# 10. dia_test — the test suite at a glance
# ===========================================================================
def dia_test() -> str:
    modules = [
        ("การแปลคำค้นและ wildcard", 74, VIOLET),
        ("การค้นหา", 73, AMBER),
        ("ความเป็นส่วนตัว", 63, GREEN),
        ("ตัวอ่านเอกสาร", 58, GREEN),
        ("หน้าจอ", 57, CORAL),
        ("รายงานสรุปโครงการ", 44, VIOLET),
        ("การเดินไฟล์และจัดดัชนี", 43, GREEN),
        ("ความปลอดภัย", 38, CORAL),
        ("ฐานข้อมูล", 35, ACCENT),
        ("การจัดวางหน้าจอ", 31, CORAL),
        ("การทำงานร่วมกันทั้งระบบ", 30, ACCENT),
        ("การจัดการพาธ", 27, SLATE),
        ("คู่มือการใช้งาน", 33, ACCENT),
    ]
    p = ['<rect x="0" y="0" width="1040" height="680" fill="none"/>']
    tiles = [
        ("605", "การทดสอบผ่าน", GREEN, GREEN_SOFT),
        ("0", "การทดสอบล้มเหลว", GREEN, GREEN_SOFT),
        ("41", "ตรวจไฟล์ที่แพ็กแล้ว", ACCENT, ACCENT_SOFT),
        ("95", "ตรวจหน้าจอจริง", ACCENT, ACCENT_SOFT),
        ("14", "ข้อบกพร่องที่พบและแก้", AMBER, AMBER_SOFT),
    ]
    x = 24
    for value, caption, colour, soft in tiles:
        p.append(f'<rect x="{x}" y="16" width="188" height="86" rx="14" fill="{soft}" '
                 f'stroke="{colour}" stroke-width="1.6"/>')
        p.append(label(x + 94, 58, value, size=30, fill=colour, weight="700"))
        p.append(label(x + 94, 84, caption, size=12.5, fill=MUTED))
        x += 198

    p.append(_text(24, 142, "จำนวนการทดสอบแยกตามด้านที่ตรวจ",
                   size=16, fill=INK, weight="700"))
    y = 164
    scale = 640 / 74
    for name, count, colour in modules:
        p.append(_text(312, y + 22, name, size=13, fill=INK, anchor="end"))
        width = int(count * scale)
        p.append(f'<rect x="326" y="{y + 6}" width="{width}" height="24" rx="7" '
                 f'fill="{colour}" opacity="0.88"/>')
        p.append(_text(326 + width + 12, y + 24, str(count), size=13, fill=colour,
                       weight="700"))
        y += 36
    p.append(f'<line x1="326" y1="160" x2="326" y2="{y}" stroke="{BORDER}" '
             f'stroke-width="1.4"/>')
    p.append(label(520, 662,
                   "ทุกเอกสารที่ใช้ทดสอบถูกสร้างขึ้นใหม่ตอนรัน ไม่มีเอกสารจริงอยู่ในชุดทดสอบ",
                   size=13, fill=MUTED))
    return _shell(1040, 680, "\n".join(p))


# ===========================================================================
# 11. dia_timeline — how the work was planned and carried out
# ===========================================================================
def dia_timeline() -> str:
    phases = [
        ("1", "วางแผนและตัดสินใจ",
         ["อ่านข้อกำหนดทั้งหมด", "ทดลองเรื่องภาษาไทยก่อน", "บันทึกเป็นเอกสาร ADR"], ACCENT),
        ("2", "แกนกลางและข้อมูล",
         ["สคีมาและชั้นข้อมูล", "กฎความปลอดภัยของพาธ", "บันทึกที่ไม่เก็บเนื้อหา"], VIOLET),
        ("3", "ตัวอ่านเอกสาร",
         ["PDF · DOCX · XLSX · TXT", "สัญญาผลลัพธ์ร่วมกัน", "รับมือไฟล์เสียและล็อก"], GREEN),
        ("4", "การค้นหา",
         ["แปลคำค้น · wildcard", "จัดอันดับ · ตัดข้อความ", "ทางเลือกสำหรับคำสั้น"], AMBER),
        ("5", "หน้าจอ",
         ["หน้าต่างและกล่องโต้ตอบ", "งานเบื้องหลังกันจอค้าง", "สองภาษาเต็มรูปแบบ"], CORAL),
        ("6", "ทดสอบและแพ็กเกจ",
         ["ชุดทดสอบอัตโนมัติ", "ตรวจความปลอดภัย", "สร้าง .exe แล้วตรวจซ้ำ"], SLATE),
    ]
    p = ['<rect x="0" y="0" width="1040" height="470" fill="none"/>']
    p.append(f'<line x1="60" y1="96" x2="980" y2="96" stroke="{BORDER}" stroke-width="4"/>')
    x = 20
    for number, title, lines, colour in phases:
        cx = x + 78
        p.append(f'<circle cx="{cx}" cy="96" r="26" fill="{colour}" stroke="#ffffff" '
                 f'stroke-width="4"/>')
        p.append(label(cx, 103, number, size=19, fill="#ffffff", weight="700"))
        p.append(box(x, 142, 156, 150, title, [], colour=colour, title_size=13))
        for i, line in enumerate(lines):
            p.append(_text(x + 16, 196 + i * 24, line, size=11.5, fill=MUTED))
        x += 168
    p.append(box(24, 320, 992, 126, "หลักที่ยึดตลอดทั้งโครงการ",
                 ["ตัดสินใจเรื่องยากก่อน: เรื่องภาษาไทยถูกพิสูจน์ด้วยการทดลองจริงก่อนเขียนโปรแกรมจริง",
                  "เขียนการทดสอบไปพร้อมกับโค้ด ไม่ใช่ทิ้งไว้ท้ายสุด",
                  "ทุกการตัดสินใจที่มีข้อแลกเปลี่ยน ถูกบันทึกไว้เป็นเอกสาร ADR พร้อมเหตุผล",
                  "ความเป็นส่วนตัวเป็นข้อกำหนดที่ทดสอบได้ ไม่ใช่คำสัญญาในเอกสาร"],
                 colour=ACCENT))
    return _shell(1040, 470, "\n".join(p))


# ===========================================================================
# 12. dia_versions — what changed after the first report
# ===========================================================================
def dia_versions() -> str:
    rounds = [
        ("รอบที่ 1", "ระบบพื้นฐานครบตามข้อกำหนด", ACCENT,
         ["ค้นไทย/อังกฤษด้วย FTS5", "จัดดัชนีแบบเพิ่มทีละส่วน",
          "ตัวกรอง · การจัดอันดับ · ตำแหน่งที่พบ", "แพ็กเป็น .exe และตรวจครบ",
          "ชุดทดสอบ 493 รายการ"]),
        ("รอบที่ 2", "ปรับหน้าจอตามที่ผู้ใช้ขอ", VIOLET,
         ["ไอคอนโปรแกรมหลายความละเอียด", "ย้ายตำแหน่งที่พบไปอยู่กับข้อความ",
          "กล่องพรีวิวข้อความพร้อมไฮไลต์", "เพิ่มคอลัมน์ปุ่มเปิดโฟลเดอร์",
          "ตัวอักษรใหญ่ขึ้น", "ค้นหาแล้วสร้าง/อัปเดตดัชนีให้เอง",
          "ชุดทดสอบ 525 รายการ"]),
        ("รอบที่ 3", "ขัดรายละเอียดและเพิ่มเอกสาร", GREEN,
         ["ย่อปุ่มเปิดโฟลเดอร์ให้เป็นไอคอนเล็ก", "เปลี่ยนเมนูเป็นคู่มือการใช้งาน",
          "คู่มือ HTML พร้อมภาพประกอบ", "แก้บั๊กค้นหาชนกับการจัดดัชนี",
          "รายงานสรุปโครงการฉบับนี้"]),
        ("รอบที่ 4", "ปรับคู่มือตามข้อกำหนดใหม่", AMBER,
         ["คู่มือรองรับจอทุกขนาด", "ตัวอักษรขนาด 16 จุด",
          "แยกอธิบายหน้าจอเป็นส่วน ๆ", "ภาพประกอบแบบสามมิติ",
          "แปลปุ่มปิดในกล่องเกี่ยวกับ", "แก้ป้ายกำกับที่สื่อความไม่ตรง"]),
        ("รอบที่ 5", "แก้ตามผลการใช้งานจริง", CORAL,
         ["แก้เปิดโฟลเดอร์ที่ชื่อมีเว้นวรรค", "ใช้ Shell API แทนบรรทัดคำสั่ง",
          "พรีวิวดึงบรรทัดข้างเคียงมาด้วย", "เพิ่มปุ่มเปิดไฟล์ประจำแถว",
          "ไม่มีโปรแกรม → เปิดด้วย (Open with)", "ชุดทดสอบ 620 รายการ"]),
    ]
    p = ['<rect x="0" y="0" width="1040" height="430" fill="none"/>']
    x = 13
    for title, subtitle, colour, items in rounds:
        p.append(f'<rect x="{x}" y="40" width="190" height="312" rx="16" fill="{SURFACE}" '
                 f'stroke="{colour}" stroke-width="1.8" filter="url(#soft)"/>')
        p.append(f'<path d="M{x} 88 v-32 a16 16 0 0 1 16 -16 h158 '
                 f'a16 16 0 0 1 16 16 v32 z" fill="{colour}"/>')
        p.append(_text(x + 16, 74, title, size=14, fill="#ffffff", weight="700"))
        p.append(_text(x + 16, 110, subtitle, size=11, fill=colour, weight="600"))
        for i, item in enumerate(items):
            iy = 142 + i * 28
            p.append(f'<circle cx="{x + 26}" cy="{iy - 5}" r="7.5" fill="{colour}" '
                     f'opacity="0.16"/>')
            p.append(f'<path d="M{x + 22} {iy - 5} l3 4 l6 -8" fill="none" '
                     f'stroke="{colour}" stroke-width="2" stroke-linecap="round" '
                     f'stroke-linejoin="round"/>')
            p.append(_text(x + 38, iy, item, size=10.5, fill=INK))
        x += 203
    p.append(label(520, 398,
                   "เลขเวอร์ชันภายในโปรแกรมยังเป็น 1.0.0 — ทั้งห้ารอบคือการพัฒนาต่อเนื่อง"
                   "ก่อนส่งมอบ ไม่ใช่การออกรุ่นใหม่ให้ผู้ใช้ติดตั้งทับ",
                   size=13, fill=MUTED))
    return _shell(1040, 430, "\n".join(p))


# ===========================================================================
def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figures = {
        "dia_architecture": dia_architecture(),
        "dia_modules": dia_modules(),
        "dia_techstack": dia_techstack(),
        "dia_index_flow": dia_index_flow(),
        "dia_search_flow": dia_search_flow(),
        "dia_ipc": dia_ipc(),
        "dia_dataflow": dia_dataflow(),
        "dia_erd": dia_erd(),
        "dia_ux": dia_ux(),
        "dia_test": dia_test(),
        "dia_timeline": dia_timeline(),
        "dia_versions": dia_versions(),
    }
    for name, markup in figures.items():
        target = OUTPUT / f"{name}.svg"
        target.write_text(markup, encoding="utf-8")
        print(f"  {target.name:24} {len(markup):>7,} bytes")
    print(f"\nWrote {len(figures)} diagrams to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
