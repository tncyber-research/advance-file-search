"""Checks on the bundled project report.

The report sits beside the user manual in ``Manual\\`` and ships with the
application, so it is held to the same offline rule: no remote font,
stylesheet, script, image or endpoint of any kind.  Unlike the manual it is
deliberately *not* linked from the program's interface, and one test pins that
down so a future change does not quietly add a button for it.

The content tests are deliberately about the brief — every section the report
was asked to contain, and the figures each one needs — rather than about
prose, which is free to be rewritten.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANUAL_DIR = PROJECT_ROOT / "Manual"
REPORT = MANUAL_DIR / "report.html"
IMAGES = MANUAL_DIR / "images"

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def html() -> str:
    if not REPORT.is_file():
        pytest.skip("the project report has not been generated in this checkout")
    return REPORT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Offline guarantee
# ---------------------------------------------------------------------------
def test_report_references_nothing_remote(html):
    patterns = [
        r'src\s*=\s*["\']https?://',
        r'href\s*=\s*["\']https?://',
        r'data\s*=\s*["\']https?://',
        r"url\(\s*['\"]?https?://",
        r"@import\s+url\(\s*['\"]?https?://",
        r'srcset\s*=\s*["\'][^"\']*https?://',
        r'(?:src|href)\s*=\s*["\']//',
    ]
    offenders = [p for p in patterns if re.search(p, html, re.IGNORECASE)]
    assert not offenders, f"remote reference found: {offenders}"


def test_report_does_not_pull_a_web_font(html):
    lowered = html.lower()
    for forbidden in (
        "fonts.googleapis",
        "fonts.gstatic",
        "@font-face",
        "cdn.",
        "cdnjs",
        "jsdelivr",
        "unpkg",
        "bootstrapcdn",
    ):
        assert forbidden not in lowered, f"web font or CDN reference: {forbidden}"


def test_report_has_no_script(html):
    assert not re.search(r"<script\b", html, re.IGNORECASE)
    assert not re.search(r"\son\w+\s*=", html, re.IGNORECASE)


def test_report_font_stack_prefers_sarabun_with_fallbacks(html):
    match = re.search(r"font-family:\s*([^;]+);", html)
    assert match, "the report must declare a font stack"
    stack = match.group(1).lower()
    assert "sarabun" in stack
    assert any(
        fallback in stack
        for fallback in ("leelawadee", "tahoma", "segoe ui", "sans-serif")
    )


def test_report_body_font_size_is_14_or_16(html):
    match = re.search(r"body\s*\{[^}]*font-size:\s*(\d+)px", html, re.DOTALL)
    assert match, "the body font size should be declared explicitly"
    assert int(match.group(1)) in (14, 15, 16)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _referenced_images(html: str) -> set[str]:
    return set(re.findall(r'(?:src|data)\s*=\s*["\'](images/[^"\']+)["\']', html))


def test_every_referenced_image_exists(html):
    missing = [
        reference
        for reference in _referenced_images(html)
        if not (MANUAL_DIR / reference).is_file()
    ]
    assert not missing, f"the report references images that do not exist: {missing}"


@pytest.mark.parametrize(
    "diagram",
    [
        "dia_architecture.svg",
        "dia_modules.svg",
        "dia_techstack.svg",
        "dia_index_flow.svg",
        "dia_search_flow.svg",
        "dia_ipc.svg",
        "dia_dataflow.svg",
        "dia_erd.svg",
        "dia_ux.svg",
        "dia_test.svg",
        "dia_timeline.svg",
        "dia_versions.svg",
    ],
)
def test_report_uses_each_diagram(html, diagram):
    """Every diagram the brief asked for is drawn and actually referenced."""
    assert (IMAGES / diagram).is_file(), f"{diagram} has not been generated"
    assert diagram in html, f"{diagram} exists but the report does not use it"


def test_diagrams_are_valid_svg():
    if not IMAGES.is_dir():
        pytest.skip("diagrams have not been generated")
    diagrams = sorted(IMAGES.glob("dia_*.svg"))
    assert diagrams, "no diagrams found"
    for diagram in diagrams:
        text = diagram.read_text(encoding="utf-8")
        assert text.lstrip().startswith("<svg"), f"{diagram.name} is not SVG"
        assert "</svg>" in text
        # The namespace is the only http:// allowed anywhere in these files.
        assert "http" not in text.replace("http://www.w3.org/2000/svg", "")


def test_report_shows_numbered_screenshots(html):
    """The brief asked for screen captures with numbered callouts, referenced
    from the prose by number."""
    for shot in (
        "01_first_run_callouts.png",
        "04_main_screen_callouts.png",
        "05_result_table.png",
        "06_details_panel.png",
        "07_filters_callouts.png",
        "10_settings_callouts.png",
        "11_index_menu_callouts.png",
    ):
        assert (IMAGES / shot).is_file(), f"{shot} has not been captured"
        assert shot in html, f"{shot} is not used by the report"
    assert html.count('class="callouts"') >= 6


# ---------------------------------------------------------------------------
# Content the brief asked for
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "heading",
    [
        "ภาพรวมโครงการ",
        "แนวคิดและแผนการพัฒนา",
        "หลักการทำงานของแต่ละฟังก์ชัน",
        "เทคโนโลยีที่ใช้",
        "โครงสร้างการทำงานโดยรวม",
        "ผังการทำงานของแต่ละฟังก์ชัน",
        "ผังการเชื่อมต่อ",
        "ผังการไหลของข้อมูล",
        "การออกแบบ UX/UI",
        "การออกแบบและโครงสร้างฐานข้อมูล",
        "อธิบายทุกเมนูและทุกฟังก์ชัน",
        "ขอบเขตการทำงาน ข้อจำกัด และสเปคเครื่อง",
        "รายงานผลการทดสอบระบบ",
        "การปรับปรุงหลังรายงานฉบับแรก",
    ],
)
def test_report_covers_every_required_section(html, heading):
    assert heading in html, f"missing section: {heading}"


def test_report_carries_the_required_credit(html):
    assert "Create by TnCyber@CS 2026" in html


def test_report_documents_the_tech_stack_in_detail(html):
    for technology in (
        "Python 3.12",
        "PySide6",
        "SQLite",
        "FTS5",
        "trigram",
        "PyMuPDF",
        "python-docx",
        "openpyxl",
        "lxml",
        "PyInstaller",
        "pytest",
    ):
        assert technology in html, f"tech stack entry missing: {technology}"


def test_report_describes_the_database_tables(html):
    for table in (
        "roots",
        "files",
        "content_units",
        "content_fts",
        "name_fts",
        "index_runs",
        "app_meta",
    ):
        assert table in html, f"database table not described: {table}"


def test_report_states_the_specs(html):
    for token in ("Windows 10", "Windows 11", "4 GB", "8 GB", "64-bit"):
        assert token in html, f"specification detail missing: {token}"


def test_report_includes_the_test_results(html):
    """The measured numbers, not just the claim that testing happened."""
    for token in ("619", "41", "620"):
        assert token in html, f"test figure missing: {token}"


def test_report_records_the_revisions(html):
    for token in ("รอบที่ 1", "รอบที่ 2", "รอบที่ 3", "1.0.0"):
        assert token in html, f"revision history detail missing: {token}"


def test_report_is_explicit_that_there_is_no_server(html):
    """The brief asked for a server/client diagram.  This system has no
    server, and the report has to say so rather than invent one."""
    assert "ไม่มีเซิร์ฟเวอร์" in html


def test_report_is_in_thai(html):
    assert 'lang="th"' in html
    thai_characters = len(re.findall(r"[฀-๿]", html))
    assert thai_characters > 6000, f"only {thai_characters} Thai characters"


# ---------------------------------------------------------------------------
# Wiring (and deliberate lack of it)
# ---------------------------------------------------------------------------
def test_the_report_is_not_linked_from_the_application():
    """The owner asked for the report to ship but not to appear in the UI."""
    ui = PROJECT_ROOT / "advance_file_search" / "ui"
    offenders = [
        source.name
        for source in ui.glob("*.py")
        if "report.html" in source.read_text(encoding="utf-8")
    ]
    assert not offenders, f"the UI links to the report: {offenders}"


def test_the_report_ships_with_the_build():
    """It lives in Manual/, which the spec and the verifier already cover."""
    spec = (PROJECT_ROOT / "build" / "AdvanceFileSearch.spec").read_text(
        encoding="utf-8"
    )
    assert "Manual" in spec, "the Manual folder is not bundled by the spec"
    assert REPORT.parent.name == "Manual"
