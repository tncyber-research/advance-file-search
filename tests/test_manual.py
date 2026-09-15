"""Checks on the bundled user manual.

The manual ships with the application and is opened from inside it, so it is
held to the same offline rule as the program: no remote font, stylesheet,
script, image or endpoint of any kind.  These tests also make sure every image
it references actually exists, so a regenerated screenshot set cannot leave
broken figures behind.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANUAL_DIR = PROJECT_ROOT / "Manual"
MANUAL = MANUAL_DIR / "index.html"
IMAGES = MANUAL_DIR / "images"

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def html() -> str:
    if not MANUAL.is_file():
        pytest.skip("the manual has not been generated in this checkout")
    return MANUAL.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Offline guarantee
# ---------------------------------------------------------------------------
def test_manual_references_nothing_remote(html):
    """No absolute URL may appear in a src, href, url() or @import."""
    patterns = [
        r'src\s*=\s*["\']https?://',
        r'href\s*=\s*["\']https?://',
        r'data\s*=\s*["\']https?://',
        r"url\(\s*['\"]?https?://",
        r"@import\s+url\(\s*['\"]?https?://",
        r'srcset\s*=\s*["\'][^"\']*https?://',
    ]
    offenders = [p for p in patterns if re.search(p, html, re.IGNORECASE)]
    assert not offenders, f"remote reference found: {offenders}"


def test_manual_does_not_pull_a_web_font(html):
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


def test_manual_has_no_script(html):
    """A static document needs no script, and not having one removes a whole
    class of question about what the manual does when opened."""
    assert not re.search(r"<script\b", html, re.IGNORECASE)
    assert not re.search(r"\son\w+\s*=", html, re.IGNORECASE)


def test_manual_font_stack_prefers_sarabun_with_fallbacks(html):
    match = re.search(r"font-family:\s*([^;]+);", html)
    assert match, "the manual must declare a font stack"
    stack = match.group(1).lower()
    assert "sarabun" in stack, "Sarabun should be preferred when it is installed"
    # And it must degrade to something Windows already ships.
    assert any(
        fallback in stack
        for fallback in ("leelawadee", "tahoma", "segoe ui", "sans-serif")
    )


def test_manual_body_font_size_is_14_or_16(html):
    match = re.search(r"body\s*\{[^}]*font-size:\s*(\d+)px", html, re.DOTALL)
    assert match, "the body font size should be declared explicitly"
    assert int(match.group(1)) in (14, 15, 16)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
def _referenced_images(html: str) -> set[str]:
    found = set(re.findall(r'(?:src|data)\s*=\s*["\'](images/[^"\']+)["\']', html))
    return found


def test_every_referenced_image_exists(html):
    missing = [
        reference
        for reference in _referenced_images(html)
        if not (MANUAL_DIR / reference).is_file()
    ]
    assert not missing, f"the manual references images that do not exist: {missing}"


def test_manual_references_the_expected_figures(html):
    references = _referenced_images(html)
    assert len(references) >= 15, f"only {len(references)} figures referenced"
    # Both the screenshots and the drawn infographics are used.
    assert any(reference.endswith(".png") for reference in references)
    assert any(reference.endswith(".svg") for reference in references)


def test_screenshots_are_real_images():
    if not IMAGES.is_dir():
        pytest.skip("screenshots have not been generated")
    for image in IMAGES.glob("*.png"):
        header = image.read_bytes()[:8]
        assert header == b"\x89PNG\r\n\x1a\n", f"{image.name} is not a PNG"
        assert image.stat().st_size > 1000, f"{image.name} looks empty"


def test_figures_are_valid_svg():
    if not IMAGES.is_dir():
        pytest.skip("figures have not been generated")
    for figure in IMAGES.glob("fig_*.svg"):
        text = figure.read_text(encoding="utf-8")
        assert text.lstrip().startswith("<svg"), f"{figure.name} is not SVG"
        assert "</svg>" in text
        assert "http://" not in text.replace("http://www.w3.org/2000/svg", "")


# ---------------------------------------------------------------------------
# Content the brief asked for
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "heading",
    [
        "คำนำ วัตถุประสงค์ และประโยชน์ของโปรแกรม",
        "ความต้องการของระบบ",
        "การติดตั้งและการเปิดโปรแกรม",
        "ส่วนประกอบของหน้าจอหลัก",
        "หน้าจอย่อยและกล่องโต้ตอบ",
        "ฟังก์ชันการทำงาน",
        "ขั้นตอนการใช้งานทีละขั้น",
        "ขอบเขตของระบบ",
        "ข้อกำหนดและข้อจำกัด",
        "ปัญหาและวิธีแก้ไขเบื้องต้น",
    ],
)
def test_manual_covers_every_required_section(html, heading):
    assert heading in html, f"missing section: {heading}"


def test_manual_covers_the_introduction_topics(html):
    """The brief asked for a preface, objectives, benefits and intended use."""
    for topic in ("คำนำ", "วัตถุประสงค์", "ประโยชน์ที่ได้รับ", "แนวทางการนำโปรแกรมไปใช้"):
        assert topic in html, f"introductory topic missing: {topic}"


def test_manual_carries_the_required_credit(html):
    assert "Create by TnCyber@CS" in html
    # The brief also asked for the month and year the manual was written.
    assert re.search(r"Create by TnCyber@CS[^<]*25\d\d", html), "month and year missing"


def test_manual_numbers_the_screen_components(html):
    """Every numbered picture has a matching numbered list beside it.

    The main screen carries fourteen parts, which is more than a reader can
    follow at once, so it is explained one region at a time.
    """
    assert html.count('class="callouts"') >= 8
    for region in (
        "20_area_top.png",
        "21_area_search.png",
        "22_area_results.png",
        "23_area_actions.png",
    ):
        assert region in html, f"region capture not used: {region}"
        assert (IMAGES / region).is_file(), f"{region} has not been captured"


def test_manual_explains_the_sub_dialogs(html):
    """The brief asked for each sub-screen to be captured and explained."""
    for shot in (
        "03_indexing.png",
        "10_settings_callouts.png",
        "24_settings_search.png",
        "25_settings_privacy.png",
        "11_index_menu_callouts.png",
        "26_about.png",
    ):
        assert (IMAGES / shot).is_file(), f"{shot} has not been captured"
        assert shot in html, f"sub-dialog capture not used: {shot}"


def test_manual_shows_what_to_double_click(html):
    """Installation has to show the reader the file they are looking for."""
    assert "fig_install.svg" in html
    assert "AdvanceFileSearch.exe" in html


def test_manual_documents_the_minimum_and_recommended_specs(html):
    assert "fig_requirements.svg" in html
    for token in ("Windows 10", "Windows 11", "64 บิต", "8 กิกะไบต์", "ที่แนะนำ"):
        assert token in html, f"specification detail missing: {token}"


def test_manual_says_which_other_software_is_needed(html):
    assert "ไม่ต้องติดตั้งโปรแกรมใดเพิ่มเติม" in html
    assert "Linux" in html, "the brief asked about other operating systems"


def test_manual_states_the_privacy_position(html):
    assert "ภายในเครื่องคอมพิวเตอร์ของผู้ใช้เท่านั้น" in html
    assert "ไม่มีการเชื่อมต่อออกสู่ภายนอก" in html


def test_manual_lists_the_known_limitations(html):
    for limitation in ("OCR", ".doc", "คลาวด์", "สูตร", "รหัสผ่าน"):
        assert limitation in html, f"limitation not documented: {limitation}"


def test_manual_is_responsive(html):
    """The brief asked for a responsive page, not a fixed-width one."""
    assert 'name="viewport"' in html
    assert "@media (max-width: 1100px)" in html
    assert "@media (max-width: 640px)" in html
    # Wide tables scroll inside their own box rather than pushing the page out.
    assert 'class="tablewrap"' in html
    # ...which only holds if the stacked layout stretches its children; without
    # this the flex container sizes them to their own content and a wide table
    # drags the whole page sideways on a phone.
    pattern = r"@media \(max-width: 1100px\) \{(.*?)\n  \}"
    stacked = re.search(pattern, html, re.DOTALL)
    assert stacked and "align-items: stretch" in stacked.group(1)


def test_manual_body_font_size_is_at_least_16(html):
    """14 px turned out to be too small to read comfortably, so the floor is
    now 16 px and the rest of the type scale moved up with it."""
    match = re.search(r"body\s*\{[^}]*font-size:\s*(\d+)px", html, re.DOTALL)
    assert match, "the body font size should be declared explicitly"
    assert int(match.group(1)) >= 16, f"body text is {match.group(1)}px"


def test_manual_type_scale_moved_up_with_the_body(html):
    """Supporting text should not stay at the old size while the body grows."""
    for selector, floor in (
        (r"\.callouts b \{[^}]*font-size:\s*([\d.]+)px", 15.5),
        (r"\.callouts span \{[^}]*font-size:\s*([\d.]+)px", 14.5),
        (r"table \{[^}]*font-size:\s*([\d.]+)px", 14.5),
        (r"figcaption \{[^}]*font-size:\s*([\d.]+)px", 14),
    ):
        match = re.search(selector, html, re.DOTALL)
        assert match, f"no font size found for {selector}"
        assert float(match.group(1)) >= floor, f"{selector} is {match.group(1)}px"


def test_manual_is_in_thai(html):
    assert 'lang="th"' in html
    thai_characters = len(re.findall(r"[฀-๿]", html))
    assert thai_characters > 4000, f"only {thai_characters} Thai characters"


# ---------------------------------------------------------------------------
# Wiring into the application
# ---------------------------------------------------------------------------
def test_the_application_can_locate_the_manual():
    from advance_file_search.core import paths as pathutil

    located = pathutil.manual_path()
    assert located is not None, "manual_path() could not find the manual"
    assert located.is_file()
    assert located.name == "index.html"


def test_the_manual_menu_string_exists():
    from advance_file_search.core.i18n import LANG_ENGLISH, LANG_THAI, set_language, tr

    try:
        set_language(LANG_THAI)
        assert tr("menu.manual") == "คู่มือการใช้งาน"
        set_language(LANG_ENGLISH)
        assert tr("menu.manual") == "User Manual"
    finally:
        set_language(LANG_THAI)
