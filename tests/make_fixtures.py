"""Generate synthetic test documents.

No real or confidential document is ever committed to this repository.  Every
fixture here is built from invented Thai and English text at test time.

Run directly to (re)create the fixture tree:

    python -m tests.make_fixtures [target_dir]
"""

from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

THAI_PARAGRAPH = "งบประมาณครุภัณฑ์ประจำปี ๒๕๖๘ ของสำนักงานอธิการบดี"
THAI_SENTENCE_2 = "รายงานผลการดำเนินงานไตรมาสที่สองของคณะวิศวกรรมศาสตร์"
ENGLISH_PARAGRAPH = "Annual equipment budget report for fiscal year 2568."
MIXED_LINE = "Budget งบประมาณ 1,250,000 บาท approved on 2025-03-14"


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------
def write_txt_files(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    created: dict[str, Path] = {}

    utf8 = directory / "utf8_thai.txt"
    utf8.write_text(
        "\n".join(
            [
                "บรรทัดที่หนึ่ง " + THAI_PARAGRAPH,
                "line two " + ENGLISH_PARAGRAPH,
                MIXED_LINE,
                THAI_SENTENCE_2,
            ]
        ),
        encoding="utf-8",
    )
    created["utf8"] = utf8

    bom = directory / "utf8_bom.txt"
    bom.write_text("BOM header\n" + THAI_PARAGRAPH, encoding="utf-8-sig")
    created["utf8_bom"] = bom

    utf16 = directory / "utf16_le.txt"
    utf16.write_text("UTF-16 " + THAI_SENTENCE_2, encoding="utf-16")
    created["utf16"] = utf16

    cp874 = directory / "thai_cp874.txt"
    cp874.write_bytes("ทดสอบภาษาไทย รหัส cp874\nงบประมาณ".encode("cp874"))
    created["cp874"] = cp874

    long_line = directory / "long_line.txt"
    long_line.write_text("x" * 250_000 + " needle_in_long_line", encoding="utf-8")
    created["long_line"] = long_line

    empty = directory / "empty.txt"
    empty.write_bytes(b"")
    created["empty"] = empty

    binary = directory / "binary_disguised.txt"
    binary.write_bytes(bytes(range(0, 32)) * 300)
    created["binary"] = binary

    csv = directory / "table.csv"
    csv.write_text(
        "ชื่อ,จำนวน,ราคา\nครุภัณฑ์สำนักงาน,3,45000\nEquipment,2,12000\n",
        encoding="utf-8",
    )
    created["csv"] = csv

    return created


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def write_docx_files(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    created: dict[str, Path] = {}
    try:
        import docx
    except ImportError:  # pragma: no cover
        return created

    document = docx.Document()
    document.add_paragraph(THAI_PARAGRAPH)
    document.add_paragraph(ENGLISH_PARAGRAPH)
    document.add_paragraph("")  # empty paragraph must be skipped
    table = document.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "หัวข้อ"
    table.cell(0, 1).text = "จำนวน"
    table.cell(0, 2).text = "หมายเหตุ"
    table.cell(1, 0).text = "ครุภัณฑ์คอมพิวเตอร์"
    table.cell(1, 1).text = "12"
    table.cell(1, 2).text = "table needle"
    document.add_paragraph(THAI_SENTENCE_2)
    section = document.sections[0]
    section.header.paragraphs[0].text = "หัวกระดาษ header needle"
    section.footer.paragraphs[0].text = "ท้ายกระดาษ footer needle"
    paragraph = document.add_paragraph()
    run = paragraph.add_run("คลิกที่นี่")
    del run
    path = directory / "report_thai.docx"
    document.save(str(path))
    created["basic"] = path

    blank = docx.Document()
    blank_path = directory / "empty.docx"
    blank.save(str(blank_path))
    created["empty"] = blank_path

    corrupt = directory / "corrupt.docx"
    corrupt.write_bytes(b"PK\x03\x04 this is not a real docx package")
    created["corrupt"] = corrupt

    # A DOCX whose paragraph text contains HTML-like markup, to prove snippets
    # are escaped rather than rendered.
    injection = docx.Document()
    injection.add_paragraph('<b>bold</b> <script>alert("x")</script> injection needle')
    injection_path = directory / "html_like.docx"
    injection.save(str(injection_path))
    created["html_like"] = injection_path

    return created


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def write_xlsx_files(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    created: dict[str, Path] = {}
    try:
        import openpyxl
    except ImportError:  # pragma: no cover
        return created

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "งบประมาณ 2568"
    sheet["A1"] = "รายการ"
    sheet["B1"] = "จำนวน"
    sheet["C1"] = "ราคา"
    sheet["A2"] = "ครุภัณฑ์สำนักงาน"
    sheet["B2"] = 3
    sheet["C2"] = 45000
    sheet["F12"] = "cell needle F12"
    sheet["G13"] = 1234.5
    second = workbook.create_sheet("English Sheet")
    second["A1"] = "Equipment"
    second["A2"] = ENGLISH_PARAGRAPH
    hidden = workbook.create_sheet("HiddenSheet")
    hidden["A1"] = "hidden sheet needle"
    hidden.sheet_state = "hidden"
    path = directory / "budget.xlsx"
    workbook.save(str(path))
    created["basic"] = path

    # Formula with a cached result: openpyxl cannot write a cached value, so
    # this file intentionally demonstrates the documented limitation that a
    # formula with no cached result yields no indexed text.
    formula = openpyxl.Workbook()
    fsheet = formula.active
    fsheet["A1"] = 10
    fsheet["A2"] = 20
    fsheet["A3"] = "=SUM(A1:A2)"
    formula_path = directory / "formula.xlsx"
    formula.save(str(formula_path))
    created["formula"] = formula_path

    blank = openpyxl.Workbook()
    blank_path = directory / "empty.xlsx"
    blank.save(str(blank_path))
    created["empty"] = blank_path

    large = openpyxl.Workbook()
    lsheet = large.active
    lsheet.title = "Large"
    for row in range(1, 401):
        lsheet.cell(row=row, column=1, value=f"row {row} value")
        lsheet.cell(row=row, column=2, value=row * 7)
    lsheet.cell(row=400, column=3, value="large needle")
    large_path = directory / "large.xlsx"
    large.save(str(large_path))
    created["large"] = large_path

    corrupt = directory / "corrupt.xlsx"
    corrupt.write_bytes(b"not a zip at all")
    created["corrupt"] = corrupt

    return created


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def write_pdf_files(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    created: dict[str, Path] = {}
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        try:
            import fitz as pymupdf  # type: ignore[no-redef]
        except ImportError:
            return created

    document = pymupdf.open()
    for index, body in enumerate(
        [
            "Page one. " + ENGLISH_PARAGRAPH,
            "Page two with a pdf needle.",
            "Page three.",
        ],
        start=1,
    ):
        page = document.new_page()
        page.insert_text((72, 100), f"Page {index}", fontsize=14)
        page.insert_text((72, 130), body, fontsize=11)
    path = directory / "english.pdf"
    document.save(str(path))
    document.close()
    created["english"] = path

    # Thai text needs a font with Thai glyphs; PyMuPDF's built-in CJK/Thai
    # support varies, so the Thai PDF is written using a Base-14 font with a
    # Unicode escape fallback and verified by the test that reads it back.
    document = pymupdf.open()
    page = document.new_page()
    try:
        page.insert_text((72, 100), THAI_PARAGRAPH, fontsize=12, fontname="thai")
    except Exception:
        writer = pymupdf.TextWriter(page.rect)
        try:
            font = pymupdf.Font("notos")
        except Exception:
            font = pymupdf.Font("helv")
        writer.append((72, 100), THAI_PARAGRAPH, font=font, fontsize=12)
        writer.write_text(page)
    thai_path = directory / "thai.pdf"
    document.save(str(thai_path))
    document.close()
    created["thai"] = thai_path

    # Image-only PDF: a page with a raster image and no text layer at all.
    document = pymupdf.open()
    page = document.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64))
    pixmap.set_rect(pixmap.irect, (200, 200, 200))
    page.insert_image(pymupdf.Rect(72, 72, 200, 200), pixmap=pixmap)
    scanned_path = directory / "image_only.pdf"
    document.save(str(scanned_path))
    document.close()
    created["image_only"] = scanned_path

    # Encrypted PDF requiring a user password.
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), "secret content", fontsize=12)
    protected_path = directory / "protected.pdf"
    document.save(
        str(protected_path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    document.close()
    created["protected"] = protected_path

    corrupt = directory / "corrupt.pdf"
    corrupt.write_bytes(b"%PDF-1.7\n garbage that is not a pdf body \n%%EOF")
    created["corrupt"] = corrupt

    return created


# ---------------------------------------------------------------------------
# Hostile / edge-case inputs
# ---------------------------------------------------------------------------
def write_hostile_files(directory: Path) -> dict[str, Path]:
    """Inputs that must be skipped or fail safely, never executed."""
    directory.mkdir(parents=True, exist_ok=True)
    created: dict[str, Path] = {}

    # A "zip bomb"-shaped DOCX: a tiny archive that inflates hugely.
    bomb = directory / "inflating.docx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "A" * 20_000_000)
    created["zip_bomb"] = bomb

    # Executable content that must never be processed.
    for name, payload in (
        ("payload.exe", b"MZ" + b"\x00" * 128),
        ("script.bat", b"@echo off\r\necho should never run\r\n"),
        ("macro.docm", b"PK\x03\x04macro-enabled"),
    ):
        target = directory / name
        target.write_bytes(payload)
        created[name] = target

    # Office lock file that must be skipped.
    lock = directory / "~$report_thai.docx"
    lock.write_bytes(b"\x00" * 64)
    created["lock"] = lock

    # SQL/FTS metacharacters in a file name.  Windows forbids " * ? < > | : \ /
    # in a name, so the fixture uses every hostile character that is legal.
    weird = directory / "quote'and; drop table-- 100% (a) [b] & #1.txt"
    weird.write_text("metacharacter needle", encoding="utf-8")
    created["weird_name"] = weird

    # Text file whose *content* contains SQL and FTS metacharacters.
    injection = directory / "injection_content.txt"
    injection.write_text(
        "'; DROP TABLE files; --\n"
        'NEAR(a b) OR "x" AND y*\n'
        "<script>alert('xss')</script>\n"
        "injection needle\n",
        encoding="utf-8",
    )
    created["injection_content"] = injection

    return created


def write_all(target: Path) -> dict[str, dict[str, Path]]:
    return {
        "txt": write_txt_files(target / "txt"),
        "docx": write_docx_files(target / "docx"),
        "xlsx": write_xlsx_files(target / "xlsx"),
        "pdf": write_pdf_files(target / "pdf"),
        "hostile": write_hostile_files(target / "hostile"),
    }


if __name__ == "__main__":
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/generated")
    made = write_all(destination)
    for group, files in made.items():
        print(f"{group}: {len(files)} files")
        for key, path in files.items():
            size = path.stat().st_size if path.exists() else -1
            print(f"   {key:20} {path.name:40} {size:>12,} bytes")
    del struct
