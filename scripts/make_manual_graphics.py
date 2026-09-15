"""Generate the manual's infographic illustrations as local SVG files.

    .venv\\Scripts\\python.exe scripts\\make_manual_graphics.py

SVG rather than PNG: the graphics stay crisp at any zoom, the files are small,
and — importantly for this project — they are plain text that can be reviewed,
with no embedded binary and nothing fetched from a network.

Output: Manual/images/fig_*.svg
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "Manual" / "images"

# A light, low-saturation palette that matches the application theme.
INK = "#1b2733"
MUTED = "#5a6b7b"
ACCENT = "#1d6f8b"
ACCENT_LIGHT = "#39b3c9"
ACCENT_SOFT = "#e3eef3"
SURFACE = "#ffffff"
BORDER = "#d9dfe5"
AMBER = "#f2b705"
AMBER_SOFT = "#fff3cd"
GREEN = "#1f7a4d"
GREEN_SOFT = "#e4f3ec"
CORAL = "#d9480f"
CORAL_SOFT = "#fdece3"
VIOLET = "#5f4b9b"
VIOLET_SOFT = "#eeeaf7"

FONT = (
    "Sarabun, 'Leelawadee UI', 'Noto Sans Thai', Tahoma, "
    "'Segoe UI', system-ui, sans-serif"
)


def _shell(width: int, height: int, body: str, defs: str = "") -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"
     width="100%" role="img" font-family="{FONT}">
  <defs>
    <linearGradient id="accentGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{ACCENT_LIGHT}"/>
      <stop offset="1" stop-color="{ACCENT}"/>
    </linearGradient>
    <linearGradient id="paperGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#eef4f7"/>
    </linearGradient>
    <linearGradient id="shieldGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2b9e77"/>
      <stop offset="1" stop-color="{GREEN}"/>
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


def _card(x: int, y: int, w: int, h: int, fill: str = SURFACE, stroke: str = BORDER) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5" filter="url(#soft)"/>'
    )


def _text(
    x: int,
    y: int,
    content: str,
    *,
    size: int = 15,
    fill: str = INK,
    weight: str = "400",
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{content}</text>'
    )


def _badge(cx: int, cy: int, number: int, colour: str = CORAL) -> str:
    return (
        f'<circle cx="{cx}" cy="{cy}" r="17" fill="{colour}"/>'
        f'<text x="{cx}" y="{cy + 6}" font-size="16" font-weight="700" '
        f'fill="#ffffff" text-anchor="middle">{number}</text>'
    )


def _doc_icon(x: int, y: int, scale: float = 1.0, colour: str = ACCENT) -> str:
    """A small document glyph."""
    w, h = 34 * scale, 44 * scale
    fold = 12 * scale
    return f"""<g transform="translate({x},{y})">
    <path d="M0 6 a6 6 0 0 1 6 -6 h{w - fold - 6} l{fold} {fold}
             v{h - fold - 6} a6 6 0 0 1 -6 6 h{-(w - 12)} a6 6 0 0 1 -6 -6 z"
          fill="url(#paperGrad)" stroke="{colour}" stroke-width="2"/>
    <path d="M{w - fold} 0 v{fold} h{fold}" fill="none" stroke="{colour}"
          stroke-width="2" stroke-linejoin="round"/>
    <g stroke="{colour}" stroke-width="2" stroke-linecap="round" opacity="0.55">
      <line x1="{8 * scale}" y1="{22 * scale}" x2="{24 * scale}" y2="{22 * scale}"/>
      <line x1="{8 * scale}" y1="{29 * scale}" x2="{24 * scale}" y2="{29 * scale}"/>
      <line x1="{8 * scale}" y1="{36 * scale}" x2="{18 * scale}" y2="{36 * scale}"/>
    </g>
  </g>"""


def _magnifier(cx: int, cy: int, r: int, colour: str = ACCENT) -> str:
    return f"""<g>
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" stroke="{colour}"
            stroke-width="{max(3, r // 4)}"/>
    <line x1="{cx + int(r * 0.72)}" y1="{cy + int(r * 0.72)}"
          x2="{cx + int(r * 1.55)}" y2="{cy + int(r * 1.55)}"
          stroke="{colour}" stroke-width="{max(4, r // 3)}" stroke-linecap="round"/>
  </g>"""


# ---------------------------------------------------------------------------
# fig_concept — the design idea behind the program
# ---------------------------------------------------------------------------
def fig_concept() -> str:
    body = f"""
  <rect x="0" y="0" width="960" height="360" fill="none"/>

  <!-- your computer, containing everything -->
  <rect x="26" y="26" width="676" height="308" rx="20" fill="{ACCENT_SOFT}"
        stroke="{ACCENT}" stroke-width="2" stroke-dasharray="9 7"/>
  {_text(48, 58, "เครื่องคอมพิวเตอร์ของคุณ", size=17, fill=ACCENT, weight="700")}

  <!-- documents -->
  {_card(52, 80, 190, 226)}
  {_text(147, 110, "เอกสารของคุณ", size=15, fill=MUTED, weight="600", anchor="middle")}
  {_doc_icon(72, 132, 1.0)}
  {_doc_icon(128, 132, 1.0, ACCENT_LIGHT)}
  {_doc_icon(184, 132, 1.0)}
  {_doc_icon(72, 198, 1.0, ACCENT_LIGHT)}
  {_doc_icon(128, 198, 1.0)}
  {_doc_icon(184, 198, 1.0, ACCENT_LIGHT)}
  {_text(147, 288, "PDF · DOCX · XLSX · TXT", size=13, fill=MUTED, anchor="middle")}

  <!-- arrow -->
  <path d="M252 193 h46" stroke="{ACCENT}" stroke-width="3" marker-end="url(#arrow)"/>

  <!-- the program -->
  {_card(312, 80, 190, 226)}
  {_text(407, 110, "โปรแกรมอ่านและจัดดัชนี", size=15, fill=MUTED, weight="600", anchor="middle")}
  {_doc_icon(330, 140, 1.15, ACCENT)}
  {_magnifier(432, 176, 30)}
  {_text(407, 250, "อ่านข้อความในไฟล์", size=13, fill=MUTED, anchor="middle")}
  {_text(407, 270, "แล้วเก็บเป็นดัชนีค้นหา", size=13, fill=MUTED, anchor="middle")}

  <!-- arrow -->
  <path d="M512 193 h46" stroke="{ACCENT}" stroke-width="3" marker-end="url(#arrow)"/>

  <!-- the index -->
  {_card(572, 80, 108, 226)}
  {_text(626, 110, "ดัชนีค้นหา", size=15, fill=MUTED, weight="600", anchor="middle")}
  <g transform="translate(596,140)">
    <ellipse cx="30" cy="16" rx="30" ry="13" fill="url(#accentGrad)"/>
    <path d="M0 16 v56 a30 13 0 0 0 60 0 v-56" fill="url(#accentGrad)" opacity="0.9"/>
    <ellipse cx="30" cy="44" rx="30" ry="13" fill="#ffffff" opacity="0.28"/>
    <ellipse cx="30" cy="72" rx="30" ry="13" fill="#ffffff" opacity="0.2"/>
  </g>
  {_text(626, 260, "SQLite", size=13, fill=MUTED, anchor="middle")}
  {_text(626, 280, "เก็บในเครื่อง", size=13, fill=MUTED, anchor="middle")}

  <!-- the barrier -->
  <line x1="722" y1="40" x2="722" y2="320" stroke="{CORAL}" stroke-width="3"
        stroke-dasharray="10 8"/>

  <!-- the internet, unreachable -->
  <g opacity="0.85">
    <circle cx="848" cy="150" r="60" fill="#f2f5f7" stroke="{BORDER}" stroke-width="2"/>
    <ellipse cx="848" cy="150" rx="60" ry="24" fill="none" stroke="{BORDER}" stroke-width="2"/>
    <line x1="848" y1="90" x2="848" y2="210" stroke="{BORDER}" stroke-width="2"/>
    <path d="M792 132 q56 -22 112 0" fill="none" stroke="{BORDER}" stroke-width="2"/>
    <path d="M792 168 q56 22 112 0" fill="none" stroke="{BORDER}" stroke-width="2"/>
    <g stroke="{CORAL}" stroke-width="9" stroke-linecap="round">
      <line x1="808" y1="110" x2="888" y2="190"/>
      <line x1="888" y1="110" x2="808" y2="190"/>
    </g>
  </g>
  {_text(848, 246, "อินเทอร์เน็ต", size=15, fill=CORAL, weight="700", anchor="middle")}
  {_text(848, 270, "ไม่มีการเชื่อมต่อใด ๆ", size=13, fill=MUTED, anchor="middle")}
  {_text(848, 292, "ทั้งสิ้น", size=13, fill=MUTED, anchor="middle")}
"""
    defs = f"""    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3"
            orient="auto" markerUnits="strokeWidth">
      <path d="M0 0 L8 3 L0 6 z" fill="{ACCENT}"/>
    </marker>"""
    return _shell(960, 360, body, defs)


# ---------------------------------------------------------------------------
# fig_workflow — the four steps
# ---------------------------------------------------------------------------
def fig_workflow() -> str:
    steps = [
        (1, "เลือกโฟลเดอร์", "เลือกโฟลเดอร์หรือไดรฟ์\nภายในเครื่องที่ต้องการค้นหา", ACCENT, ACCENT_SOFT),
        (2, "พิมพ์คำค้นหา", "พิมพ์คำหรือวลี\nได้ทั้งภาษาไทยและอังกฤษ", VIOLET, VIOLET_SOFT),
        (3, "กดค้นหา", "โปรแกรมสร้างดัชนีให้อัตโนมัติ\nในครั้งแรก แล้วค้นหาให้ทันที", AMBER, AMBER_SOFT),
        (4, "เปิดไฟล์", "ดูข้อความที่ตรงกัน\nแล้วเปิดไฟล์หรือโฟลเดอร์", GREEN, GREEN_SOFT),
    ]
    parts = ['<rect x="0" y="0" width="1000" height="290" fill="none"/>']
    x = 20
    for number, title, detail, colour, soft in steps:
        parts.append(
            f'<rect x="{x}" y="40" width="214" height="210" rx="18" fill="{soft}" '
            f'stroke="{colour}" stroke-width="1.6" filter="url(#soft)"/>'
        )
        parts.append(f'<circle cx="{x + 107}" cy="40" r="25" fill="{colour}"/>')
        parts.append(
            f'<text x="{x + 107}" y="49" font-size="23" font-weight="700" '
            f'fill="#ffffff" text-anchor="middle">{number}</text>'
        )
        parts.append(
            _text(x + 107, 110, title, size=18, fill=colour, weight="700", anchor="middle")
        )
        for line_index, line in enumerate(detail.split("\n")):
            parts.append(
                _text(
                    x + 107,
                    148 + line_index * 24,
                    line,
                    size=14,
                    fill=MUTED,
                    anchor="middle",
                )
            )
        if number < 4:
            parts.append(
                f'<path d="M{x + 224} 145 h20" stroke="{BORDER}" stroke-width="3" '
                f'stroke-linecap="round"/>'
                f'<path d="M{x + 238} 138 l8 7 l-8 7" fill="none" stroke="{BORDER}" '
                f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        x += 246
    return _shell(1000, 290, "\n".join(parts))


# ---------------------------------------------------------------------------
# fig_thai — why Thai search needed a different approach
# ---------------------------------------------------------------------------
def fig_thai() -> str:
    body = f"""
  <rect x="0" y="0" width="960" height="330" fill="none"/>
  {_text(480, 34, "ทำไมการค้นหาภาษาไทยจึงต้องใช้วิธีพิเศษ", size=19, fill=INK,
         weight="700", anchor="middle")}

  <!-- the problem -->
  {_card(30, 60, 430, 230, CORAL_SOFT, CORAL)}
  {_text(56, 94, "วิธีทั่วไป (ตัดคำด้วยช่องว่าง)", size=16, fill=CORAL, weight="700")}
  <rect x="56" y="112" width="378" height="46" rx="8" fill="#ffffff" stroke="{BORDER}"/>
  {_text(70, 142, "งบประมาณครุภัณฑ์ประจำปี", size=19, fill=INK)}
  {_text(56, 186, "ภาษาไทยไม่มีช่องว่างระหว่างคำ", size=14, fill=MUTED)}
  {_text(56, 208, "ระบบจึงมองทั้งประโยคเป็น “คำเดียว”", size=14, fill=MUTED)}
  <rect x="56" y="224" width="378" height="46" rx="8" fill="#ffffff" stroke="{CORAL}"/>
  {_text(70, 243, "ค้นหา “งบประมาณ”", size=14, fill=MUTED)}
  {_text(70, 263, "→ ไม่พบผลลัพธ์ประมาณครึ่งหนึ่ง", size=14, fill=CORAL, weight="700")}

  <!-- the solution -->
  {_card(500, 60, 430, 230, GREEN_SOFT, GREEN)}
  {_text(526, 94, "วิธีที่โปรแกรมนี้ใช้ (Trigram)", size=16, fill=GREEN, weight="700")}
  <rect x="526" y="112" width="378" height="46" rx="8" fill="#ffffff" stroke="{BORDER}"/>
  <rect x="536" y="120" width="104" height="30" rx="6" fill="{AMBER_SOFT}" stroke="{AMBER}"/>
  {_text(540, 142, "งบประมาณ", size=19, fill=INK)}
  {_text(648, 142, "ครุภัณฑ์ประจำปี", size=19, fill=INK)}
  {_text(526, 186, "ทำดัชนีทีละ 3 ตัวอักษรที่ซ้อนกัน", size=14, fill=MUTED)}
  {_text(526, 208, "จึงค้นเจอคำที่อยู่กลางประโยคได้", size=14, fill=MUTED)}
  <rect x="526" y="224" width="378" height="46" rx="8" fill="#ffffff" stroke="{GREEN}"/>
  {_text(540, 243, "ค้นหา “งบประมาณ”", size=14, fill=MUTED)}
  {_text(540, 263, "→ พบครบทุกตำแหน่ง", size=14, fill=GREEN, weight="700")}

  {_text(480, 316, "ผลการทดสอบจริง: วิธีทั่วไปพบ 154 รายการ · Trigram พบ 1,882 รายการ",
         size=14, fill=MUTED, anchor="middle")}
"""
    return _shell(960, 330, body)


# ---------------------------------------------------------------------------
# fig_privacy — the privacy guarantee
# ---------------------------------------------------------------------------
def fig_privacy() -> str:
    body = f"""
  <rect x="0" y="0" width="900" height="300" fill="none"/>

  <g transform="translate(60,50)">
    <path d="M85 0 L170 32 v78 c0 52 -36 90 -85 108 c-49 -18 -85 -56 -85 -108 V32 z"
          fill="url(#shieldGrad)" filter="url(#soft)"/>
    <path d="M52 108 l24 26 l46 -60" fill="none" stroke="#ffffff" stroke-width="13"
          stroke-linecap="round" stroke-linejoin="round"/>
  </g>

  {_text(300, 78, "ข้อมูลของคุณอยู่ในเครื่องนี้เท่านั้น", size=21, fill=INK, weight="700")}

  <g font-size="15" fill="{MUTED}">
    <circle cx="312" cy="116" r="6" fill="{GREEN}"/>
    <text x="332" y="122">ไม่อัปโหลดไฟล์ ไม่ใช้บริการคลาวด์</text>
    <circle cx="312" cy="152" r="6" fill="{GREEN}"/>
    <text x="332" y="158">ไม่ส่งข้อมูลการใช้งานหรือรายงานข้อผิดพลาด</text>
    <circle cx="312" cy="188" r="6" fill="{GREEN}"/>
    <text x="332" y="194">ไม่บันทึกคำค้นหาหรือเนื้อหาเอกสารลงไฟล์บันทึก</text>
    <circle cx="312" cy="224" r="6" fill="{GREEN}"/>
    <text x="332" y="230">ตัวโปรแกรมไม่มีไลบรารีเครือข่ายติดตั้งมาด้วยเลย</text>
    <circle cx="312" cy="260" r="6" fill="{GREEN}"/>
    <text x="332" y="266">ใช้งานได้ตามปกติแม้ตัดการเชื่อมต่ออินเทอร์เน็ต</text>
  </g>
"""
    return _shell(900, 300, body)


# ---------------------------------------------------------------------------
# fig_scope — what is and is not supported
# ---------------------------------------------------------------------------
def fig_scope() -> str:
    supported = [
        "ไฟล์ PDF ที่มีชั้นข้อความ",
        "ไฟล์ Word (.docx)",
        "ไฟล์ Excel (.xlsx)",
        "ไฟล์ข้อความ (.txt)",
        "เลือกเพิ่มได้: .md .csv .log",
        "ค้นหาทั้งชื่อไฟล์และเนื้อหา",
        "ภาษาไทยและภาษาอังกฤษ",
        "ไดรฟ์และโฟลเดอร์ภายในเครื่อง",
    ]
    unsupported = [
        "PDF ที่เป็นภาพสแกน (ไม่มี OCR)",
        "ไฟล์ .doc และ .xls รูปแบบเก่า",
        "ไฟล์ที่มีรหัสผ่านป้องกัน",
        "ไดรฟ์เครือข่าย NAS และ UNC",
        "คลาวด์ เช่น OneDrive ที่ยังไม่ดาวน์โหลด",
        "ค้นหาด้วย AI หรือถาม-ตอบ",
        "คำนวณสูตรใน Excel ใหม่",
        "เลขหน้าที่แน่นอนของไฟล์ Word",
    ]
    parts = ['<rect x="0" y="0" width="960" height="400" fill="none"/>']
    parts.append(_card(24, 20, 448, 360, GREEN_SOFT, GREEN))
    parts.append(
        f'<circle cx="64" cy="62" r="20" fill="{GREEN}"/>'
        f'<path d="M55 62 l6 7 l12 -15" fill="none" stroke="#ffffff" stroke-width="4" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )
    parts.append(_text(96, 70, "รองรับ", size=19, fill=GREEN, weight="700"))
    for index, item in enumerate(supported):
        y = 112 + index * 33
        parts.append(f'<circle cx="60" cy="{y - 5}" r="5" fill="{GREEN}"/>')
        parts.append(_text(78, y, item, size=15, fill=INK))

    parts.append(_card(488, 20, 448, 360, CORAL_SOFT, CORAL))
    parts.append(
        f'<circle cx="528" cy="62" r="20" fill="{CORAL}"/>'
        f'<g stroke="#ffffff" stroke-width="4" stroke-linecap="round">'
        f'<line x1="521" y1="55" x2="535" y2="69"/>'
        f'<line x1="535" y1="55" x2="521" y2="69"/></g>'
    )
    parts.append(_text(560, 70, "ไม่รองรับในเวอร์ชัน 1", size=19, fill=CORAL, weight="700"))
    for index, item in enumerate(unsupported):
        y = 112 + index * 33
        parts.append(f'<circle cx="524" cy="{y - 5}" r="5" fill="{CORAL}"/>')
        parts.append(_text(542, y, item, size=15, fill=INK))
    return _shell(960, 400, "\n".join(parts))


# ---------------------------------------------------------------------------
# fig_requirements — machine specification
# ---------------------------------------------------------------------------
def fig_requirements() -> str:
    rows = [
        ("ระบบปฏิบัติการ", "Windows 10 / 11 (64-bit)", "Windows 11 (64-bit)"),
        ("หน่วยประมวลผล", "2 แกน", "4 แกนขึ้นไป"),
        ("หน่วยความจำ", "8 GB", "8–16 GB"),
        ("พื้นที่ว่าง", "3–5 GB", "5–20 GB"),
        ("ชนิดดิสก์", "HDD หรือ SSD", "SSD"),
        ("การ์ดจอ", "ไม่จำเป็น", "ไม่จำเป็น"),
        ("Python", "ไม่ต้องติดตั้ง", "ไม่ต้องติดตั้ง"),
        ("อินเทอร์เน็ต", "ไม่ต้องใช้", "ไม่ต้องใช้"),
    ]
    parts = ['<rect x="0" y="0" width="900" height="420" fill="none"/>']
    parts.append(_card(20, 20, 860, 380))

    parts.append(f'<rect x="20" y="20" width="860" height="56" rx="14" fill="{ACCENT_SOFT}"/>')
    parts.append(f'<rect x="20" y="60" width="860" height="16" fill="{ACCENT_SOFT}"/>')
    parts.append(_text(52, 55, "รายการ", size=16, fill=ACCENT, weight="700"))
    parts.append(_text(392, 55, "ขั้นต่ำ", size=16, fill=ACCENT, weight="700"))
    parts.append(_text(652, 55, "แนะนำ", size=16, fill=ACCENT, weight="700"))
    parts.append(f'<line x1="20" y1="76" x2="880" y2="76" stroke="{BORDER}" stroke-width="1.5"/>')

    for index, (label, minimum, recommended) in enumerate(rows):
        y = 112 + index * 38
        if index % 2 == 1:
            parts.append(
                f'<rect x="21" y="{y - 26}" width="858" height="38" fill="#fafbfc"/>'
            )
        parts.append(_text(52, y, label, size=15, fill=MUTED, weight="600"))
        parts.append(_text(392, y, minimum, size=15, fill=INK))
        parts.append(_text(652, y, recommended, size=15, fill=INK))
        if index < len(rows) - 1:
            parts.append(
                f'<line x1="40" y1="{y + 12}" x2="860" y2="{y + 12}" '
                f'stroke="{BORDER}" stroke-width="1"/>'
            )
    return _shell(900, 420, "\n".join(parts))


# ---------------------------------------------------------------------------
# fig_locations — how a match location is reported per format
# ---------------------------------------------------------------------------
def fig_locations() -> str:
    entries = [
        ("PDF", "หน้า 12", ACCENT, "ระบุเลขหน้า"),
        ("DOCX", "ย่อหน้า 24", VIOLET, "ย่อหน้า หรือ ตาราง/แถว/คอลัมน์"),
        ("XLSX", "ชีต: งบประมาณ, เซลล์: F12", GREEN, "ชื่อชีตและตำแหน่งเซลล์"),
        ("TXT", "บรรทัด 135", AMBER, "เลขบรรทัด"),
    ]
    parts = ['<rect x="0" y="0" width="960" height="300" fill="none"/>']
    y = 24
    for name, example, colour, detail in entries:
        parts.append(_card(24, y, 912, 56))
        parts.append(f'<rect x="24" y="{y}" width="8" height="56" rx="4" fill="{colour}"/>')
        parts.append(_text(56, y + 35, name, size=17, fill=colour, weight="700"))
        parts.append(
            f'<rect x="140" y="{y + 13}" width="300" height="30" rx="8" '
            f'fill="{ACCENT_SOFT}" stroke="{BORDER}"/>'
        )
        parts.append(_text(156, y + 34, example, size=15, fill=INK, weight="600"))
        parts.append(_text(468, y + 35, detail, size=15, fill=MUTED))
        y += 68
    return _shell(960, 300, "\n".join(parts))


# ---------------------------------------------------------------------------
# Shared bits for the dimensional ("3D-ish") figures added for the manual
# ---------------------------------------------------------------------------
DEPTH_DEFS = f"""    <linearGradient id="solidBlue" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#5ec3d8"/>
      <stop offset="1" stop-color="{ACCENT}"/>
    </linearGradient>
    <linearGradient id="solidGreen" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#57c69a"/>
      <stop offset="1" stop-color="{GREEN}"/>
    </linearGradient>
    <linearGradient id="solidAmber" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#ffd166"/>
      <stop offset="1" stop-color="#e0a500"/>
    </linearGradient>
    <linearGradient id="solidViolet" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#8f7ccc"/>
      <stop offset="1" stop-color="{VIOLET}"/>
    </linearGradient>
    <linearGradient id="solidCoral" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#f08a5d"/>
      <stop offset="1" stop-color="{CORAL}"/>
    </linearGradient>
    <radialGradient id="glossy" cx="0.32" cy="0.26" r="0.75">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
    <filter id="lift" x="-40%" y="-40%" width="180%" height="190%">
      <feDropShadow dx="0" dy="7" stdDeviation="9" flood-color="#1b2733"
                    flood-opacity="0.18"/>
    </filter>"""

SOLIDS = {
    ACCENT: "solidBlue",
    GREEN: "solidGreen",
    AMBER: "solidAmber",
    VIOLET: "solidViolet",
    CORAL: "solidCoral",
}


def _orb(cx: int, cy: int, r: int, colour: str) -> str:
    """A rounded, lit sphere — the base shape of the cartoon icons below."""
    gradient = SOLIDS.get(colour, "solidBlue")
    return (
        f'<g filter="url(#lift)">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{gradient})"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#glossy)"/>'
        f"</g>"
    )


def _slab(x: int, y: int, w: int, h: int, colour: str, *, depth: int = 9) -> str:
    """A card with a visible thickness, so it reads as an object, not a box."""
    gradient = SOLIDS.get(colour, "solidBlue")
    return (
        f'<g filter="url(#lift)">'
        f'<rect x="{x + depth // 2}" y="{y + depth}" width="{w}" height="{h}" rx="18" '
        f'fill="{colour}" opacity="0.25"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" '
        f'fill="url(#{gradient})"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="url(#glossy)"/>'
        f"</g>"
    )


def _magnifier_icon(cx: int, cy: int, scale: float = 1.0) -> str:
    r = int(22 * scale)
    return f"""<g>
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" opacity="0.9"/>
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#ffffff"
            stroke-width="{max(3, int(5 * scale))}"/>
    <circle cx="{cx - r // 3}" cy="{cy - r // 3}" r="{max(3, r // 4)}"
            fill="#ffffff" opacity="0.8"/>
    <line x1="{cx + int(r * 0.72)}" y1="{cy + int(r * 0.72)}"
          x2="{cx + int(r * 1.6)}" y2="{cy + int(r * 1.6)}"
          stroke="#ffffff" stroke-width="{max(4, int(7 * scale))}"
          stroke-linecap="round"/>
  </g>"""



def _pin_icon(cx: int, cy: int, scale: float = 1.0) -> str:
    """A map pin, for "this is where the match is"."""
    w = 18 * scale
    return f"""<g fill="#ffffff">
    <path d="M{cx} {cy - w} a{w} {w} 0 0 1 {w} {w} c0 {w * 0.9} -{w} {w * 1.7} -{w} {w * 1.7}
             s-{w} -{w * 0.8} -{w} -{w * 1.7} a{w} {w} 0 0 1 {w} -{w} z"/>
    <circle cx="{cx}" cy="{cy}" r="{w * 0.34}" fill="#2f5d70"/>
  </g>"""


def _shield_icon(cx: int, cy: int, scale: float = 1.0) -> str:
    """A shield with a tick, for the privacy promise."""
    w = 20 * scale
    return f"""<g>
    <path d="M{cx} {cy - w} l{w * 0.86} {w * 0.34} v{w * 0.7}
             c0 {w * 0.75} -{w * 0.5} {w * 1.1} -{w * 0.86} {w * 1.25}
             c-{w * 0.36} -{w * 0.15} -{w * 0.86} -{w * 0.5} -{w * 0.86} -{w * 1.25}
             v-{w * 0.7} z" fill="#ffffff"/>
    <path d="M{cx - w * 0.34} {cy + w * 0.05} l{w * 0.26} {w * 0.3} l{w * 0.55} -{w * 0.62}"
          fill="none" stroke="#2f7a5a" stroke-width="{max(2, 3 * scale)}"
          stroke-linecap="round" stroke-linejoin="round"/>
  </g>"""


def _thai_icon(cx: int, cy: int, scale: float = 1.0) -> str:
    """A Thai letter on a disc, for the language capability."""
    r = 20 * scale
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff"/>'
        f'<text x="{cx}" y="{cy + r * 0.42}" font-size="{r * 1.25}" font-weight="700" '
        f'fill="#5f4b9b" text-anchor="middle">ก</text>'
    )


# ---------------------------------------------------------------------------
# fig_objectives — what the program is for, and what it gives the reader
# ---------------------------------------------------------------------------
def fig_objectives() -> str:
    cards = [
        ("ค้นเนื้อหา ไม่ใช่แค่ชื่อไฟล์", "อ่านข้อความข้างในเอกสาร\nแล้วค้นได้ทั้งฉบับ",
         ACCENT, "search"),
        ("รองรับภาษาไทยเต็มรูปแบบ", "ค้นคำที่อยู่กลางข้อความ\nที่ไม่เว้นวรรคได้",
         VIOLET, "thai"),
        ("บอกตำแหน่งที่พบ", "หน้า · ย่อหน้า · เซลล์\n· บรรทัด", AMBER, "pin"),
        ("ข้อมูลไม่ออกจากเครื่อง", "ไม่มีการเชื่อมต่อ\nออกสู่ภายนอก", GREEN, "shield"),
    ]
    parts = ['<rect x="0" y="0" width="1000" height="330" fill="none"/>']
    x = 24
    for title, detail, colour, icon in cards:
        # Amber is too light to carry white type; that card uses dark text.
        ink = INK if colour == AMBER else "#ffffff"
        parts.append(_slab(x, 40, 220, 226, colour))
        parts.append(
            f'<circle cx="{x + 110}" cy="100" r="34" fill="#ffffff" opacity="0.18"/>'
        )
        if icon == "search":
            parts.append(_magnifier_icon(x + 104, 94, 0.62))
        elif icon == "thai":
            parts.append(_thai_icon(x + 110, 100, 0.85))
        elif icon == "pin":
            parts.append(_pin_icon(x + 110, 98, 0.95))
        else:
            parts.append(_shield_icon(x + 110, 100, 0.95))
        parts.append(
            _text(x + 110, 168, title, size=14.5, fill=ink, weight="700",
                  anchor="middle")
        )
        for index, line in enumerate(detail.split("\n")):
            parts.append(
                _text(x + 110, 198 + index * 22, line, size=12.5, fill=ink,
                      anchor="middle")
            )
        x += 238
    parts.append(
        _text(500, 306,
              "วัตถุประสงค์: ให้ผู้ใช้ค้นเอกสารที่ต้องการพบได้เร็ว โดยที่เอกสารยังอยู่ในเครื่องเช่นเดิม",
              size=13.5, fill=MUTED, anchor="middle")
    )
    return _shell(1000, 330, "\n".join(parts), DEPTH_DEFS)


# ---------------------------------------------------------------------------
# fig_usecases — who this is for
# ---------------------------------------------------------------------------
def fig_usecases() -> str:
    groups = [
        ("งานสารบรรณและงานธุรการ", ["ค้นหนังสือราชการจากเลขที่หนังสือ",
                                     "ค้นระเบียบและประกาศที่เคยออก",
                                     "ตรวจสอบว่าเคยมีเอกสารลักษณะนี้แล้วหรือยัง"], ACCENT),
        ("งานงบประมาณและพัสดุ", ["ค้นรายการครุภัณฑ์จากชื่อหรือราคา",
                                  "ค้นตัวเลขในไฟล์ Excel ได้ถึงระดับเซลล์",
                                  "ตรวจย้อนหลังว่าเคยจัดซื้อรายการใดไว้"], VIOLET),
        ("งานวิชาการและงานวิจัย", ["ค้นคำสำคัญในเอกสารอ้างอิงจำนวนมาก",
                                    "ค้นข้อความในไฟล์ PDF ที่มีข้อความ",
                                    "รวบรวมเอกสารที่กล่าวถึงหัวข้อเดียวกัน"], GREEN),
    ]
    parts = ['<rect x="0" y="0" width="1000" height="330" fill="none"/>']
    x = 24
    for title, lines, colour in groups:
        parts.append(
            f'<rect x="{x}" y="30" width="304" height="270" rx="18" fill="{SURFACE}" '
            f'stroke="{colour}" stroke-width="1.6" filter="url(#lift)"/>'
        )
        parts.append(_orb(x + 48, 68, 23, colour))
        parts.append(
            _text(x + 48, 76, "✓", size=21, fill="#ffffff", weight="700",
                  anchor="middle")
        )
        parts.append(_text(x + 82, 75, title, size=15, fill=colour, weight="700"))
        tint = ACCENT_SOFT if colour == ACCENT else "#f5f7fa"
        for index, line in enumerate(lines):
            y = 130 + index * 54
            parts.append(
                f'<rect x="{x + 20}" y="{y - 22}" width="264" height="44" rx="11" '
                f'fill="{tint}"/>'
            )
            parts.append(f'<circle cx="{x + 40}" cy="{y}" r="7" fill="{colour}"/>')
            parts.append(_text(x + 58, y + 5, line, size=12.5, fill=INK))
        parts.append(
            _text(x + 152, 284, "เอกสารทั้งหมดยังอยู่ในเครื่องของหน่วยงาน",
                  size=11.5, fill=MUTED, anchor="middle")
        )
        x += 324
    return _shell(1000, 330, "\n".join(parts), DEPTH_DEFS)


# ---------------------------------------------------------------------------
# fig_install — what the distribution folder looks like, and how to start
# ---------------------------------------------------------------------------
def fig_install() -> str:
    entries = [
        ("AdvanceFileSearch.exe", "ไฟล์สำหรับเปิดโปรแกรม", True),
        ("_internal", "ส่วนประกอบภายใน ห้ามลบ", False),
        ("LICENSES", "สัญญาอนุญาตของซอฟต์แวร์ที่ใช้", False),
        ("Manual", "คู่มือการใช้งานและรายงานโครงการ", False),
        ("README.txt", "คำอธิบายโดยย่อ", False),
        ("PRIVACY.txt", "คำแถลงความเป็นส่วนตัว", False),
    ]
    parts = ['<rect x="0" y="0" width="1000" height="400" fill="none"/>']

    # A window-shaped panel listing what the folder actually contains.
    parts.append(
        f'<rect x="24" y="26" width="580" height="348" rx="16" fill="{SURFACE}" '
        f'stroke="{BORDER}" stroke-width="1.6" filter="url(#lift)"/>'
    )
    parts.append(
        '<path d="M24 74 v-32 a16 16 0 0 1 16 -16 h548 a16 16 0 0 1 16 16 v32 z" '
        'fill="#eef2f6"/>'
    )
    for index, colour in enumerate(("#f2725c", "#f3c14a", "#5cc48a")):
        parts.append(f'<circle cx="{48 + index * 20}" cy="50" r="6" fill="{colour}"/>')
    parts.append(
        _text(126, 55, "dist  ›  Advance File Search", size=13, fill=MUTED)
    )

    y = 96
    for name, note, highlight in entries:
        if highlight:
            parts.append(
                f'<rect x="40" y="{y - 20}" width="548" height="46" rx="10" '
                f'fill="{ACCENT_SOFT}" stroke="{ACCENT}" stroke-width="1.4"/>'
            )
        # icon: a folder for directories, the application glyph for the exe
        if name.endswith(".exe"):
            parts.append(_orb(70, y + 2, 16, ACCENT))
            parts.append(_magnifier_icon(66, -2 + y, 0.36))
        elif "." in name:
            parts.append(_doc_icon(58, y - 16, 0.6, MUTED))
        else:
            parts.append(
                f'<path d="M56 {y - 14} h20 l6 7 h22 a5 5 0 0 1 5 5 v18 '
                f'a5 5 0 0 1 -5 5 h-48 a5 5 0 0 1 -5 -5 v-25 a5 5 0 0 1 5 -5 z" '
                f'fill="{AMBER_SOFT}" stroke="{AMBER}" stroke-width="1.6"/>'
            )
        parts.append(
            _text(112, y + 5, name, size=14, fill=ACCENT if highlight else INK,
                  weight="700" if highlight else "400")
        )
        parts.append(_text(330, y + 5, note, size=12.5, fill=MUTED))
        y += 46

    steps = [
        ("1", "คัดลอกทั้งโฟลเดอร์", "วางไว้ที่ใดก็ได้ในเครื่อง เช่น ไดรฟ์ D", ACCENT),
        ("2", "ดับเบิลคลิกที่ไฟล์ .exe", "ไม่ต้องติดตั้ง ไม่ต้องใช้สิทธิ์ผู้ดูแลระบบ", VIOLET),
        ("3", "เริ่มใช้งานได้ทันที", "ไม่ต้องเชื่อมต่ออินเทอร์เน็ต", GREEN),
    ]
    y = 40
    for number, title, detail, colour in steps:
        parts.append(_slab(632, y, 344, 96, colour, depth=7))
        parts.append(
            f'<circle cx="{678}" cy="{y + 48}" r="24" fill="#ffffff" opacity="0.22"/>'
        )
        parts.append(
            _text(678, y + 56, number, size=24, fill="#ffffff", weight="700",
                  anchor="middle")
        )
        parts.append(_text(716, y + 42, title, size=15, fill="#ffffff", weight="700"))
        parts.append(_text(716, y + 68, detail, size=12.5, fill="#ffffff"))
        y += 116
    return _shell(1000, 400, "\n".join(parts), DEPTH_DEFS)


# ---------------------------------------------------------------------------
# fig_troubleshoot — the four questions users actually ask
# ---------------------------------------------------------------------------
def fig_troubleshoot() -> str:
    pairs = [
        ("ค้นแล้วไม่พบเอกสารที่รู้ว่ามีอยู่",
         "กด “อัปเดตดัชนี” แล้วค้นใหม่ · ตรวจว่าเลือกโฟลเดอร์ถูกต้อง", AMBER),
        ("ไฟล์ PDF ค้นข้อความไม่เจอ",
         "อาจเป็นไฟล์จากการสแกน ซึ่งเป็นภาพทั้งหน้า ระบบไม่มี OCR", CORAL),
        ("โปรแกรมขอให้เลือกโฟลเดอร์ใหม่",
         "โฟลเดอร์เดิมถูกย้ายหรือลบ ให้เลือกตำแหน่งปัจจุบันอีกครั้ง", VIOLET),
        ("ค้นช้ากว่าปกติ",
         "คำค้นสั้นกว่า 3 ตัวอักษรจะไม่ใช้ดัชนี ลองพิมพ์ให้ยาวขึ้น", ACCENT),
    ]
    parts = ['<rect x="0" y="0" width="1000" height="392" fill="none"/>']
    y = 22
    for question, answer, colour in pairs:
        parts.append(
            f'<rect x="24" y="{y}" width="952" height="72" rx="16" fill="{SURFACE}" '
            f'stroke="{BORDER}" stroke-width="1.4" filter="url(#lift)"/>'
        )
        parts.append(_orb(70, y + 36, 23, colour))
        parts.append(
            _text(70, y + 44, "?", size=24, fill="#ffffff", weight="700",
                  anchor="middle")
        )
        parts.append(_text(112, y + 32, question, size=14.5, fill=INK, weight="700"))
        parts.append(_text(112, y + 56, answer, size=13, fill=MUTED))
        y += 84
    parts.append(
        _text(500, 376,
              "หากยังไม่หาย ให้ใช้คำสั่ง “สร้างดัชนีใหม่ทั้งหมด” ซึ่งปลอดภัยเสมอ "
              "เพราะดัชนีสร้างขึ้นใหม่ได้จากเอกสารเดิม",
              size=13, fill=MUTED, anchor="middle")
    )
    return _shell(1000, 392, "\n".join(parts), DEPTH_DEFS)


# ---------------------------------------------------------------------------
def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figures = {
        "fig_concept": fig_concept(),
        "fig_workflow": fig_workflow(),
        "fig_thai": fig_thai(),
        "fig_privacy": fig_privacy(),
        "fig_scope": fig_scope(),
        "fig_requirements": fig_requirements(),
        "fig_locations": fig_locations(),
        "fig_objectives": fig_objectives(),
        "fig_usecases": fig_usecases(),
        "fig_install": fig_install(),
        "fig_troubleshoot": fig_troubleshoot(),
    }
    for name, markup in figures.items():
        target = OUTPUT / f"{name}.svg"
        target.write_text(markup, encoding="utf-8")
        print(f"  {target.name:26} {len(markup):>6,} bytes")
    print(f"\nWrote {len(figures)} figures to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
