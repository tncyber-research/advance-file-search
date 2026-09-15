"""Per-format extraction against synthetic fixtures."""

from __future__ import annotations

import pytest

from advance_file_search.core import constants as C
from advance_file_search.core.models import ParseOutcome
from advance_file_search.indexing.parsers.base import (
    ParseOptions,
    build_registry,
    clean_text,
    excel_column_name,
)
from advance_file_search.indexing.parsers.txt_parser import (
    TxtParser,
    detect_encoding,
    looks_binary,
)
from advance_file_search.indexing.parsers.xlsx_parser import format_cell_value


@pytest.fixture
def registry():
    return build_registry(ParseOptions())


def _units(result):
    return result.document.units if result.document else []


def _all_text(result):
    return "\n".join(unit.text for unit in _units(result))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def test_clean_text_normalizes_whitespace_and_strips_controls():
    assert clean_text("a b") == "a\nb"
    assert clean_text("a\x00\x07b") == "a b"
    assert clean_text("a     b") == "a b"
    assert clean_text("  padded  ") == "padded"
    assert clean_text(None) == ""


def test_clean_text_removes_zero_width_marks_but_keeps_thai():
    assert clean_text("﻿งบ​ประมาณ") == "งบประมาณ"
    # Thai vowels and tone marks are combining characters and must survive.
    thai = "ที่นี่มีครุภัณฑ์"
    assert clean_text(thai) == thai


def test_clean_text_truncates_on_a_code_point_boundary():
    text = "ก" * 100
    assert len(clean_text(text, limit=10)) == 10


def test_excel_column_names():
    assert excel_column_name(1) == "A"
    assert excel_column_name(26) == "Z"
    assert excel_column_name(27) == "AA"
    assert excel_column_name(702) == "ZZ"
    assert excel_column_name(703) == "AAA"
    assert excel_column_name(0) == ""


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------
def test_txt_utf8_thai(registry, fixture_tree):
    result = registry.get(".txt").parse(fixture_tree / "txt" / "utf8_thai.txt")
    assert result.ok
    units = _units(result)
    assert units[0].location_type == C.LOC_LINE
    assert units[0].location_data["line"] == 1
    assert "งบประมาณครุภัณฑ์" in units[0].text
    # Line numbers are preserved, not renumbered.
    assert [unit.location_data["line"] for unit in units] == [1, 2, 3, 4]


def test_txt_utf8_bom_is_consumed(registry, fixture_tree):
    result = registry.get(".txt").parse(fixture_tree / "txt" / "utf8_bom.txt")
    assert result.ok
    assert result.document.metadata.encoding == "utf-8-sig"
    assert "﻿" not in _all_text(result)


def test_txt_utf16_bom_is_consumed(registry, fixture_tree):
    result = registry.get(".txt").parse(fixture_tree / "txt" / "utf16_le.txt")
    assert result.ok
    assert result.document.metadata.encoding == "utf-16"
    assert "﻿" not in _all_text(result)
    assert "รายงานผล" in _all_text(result)


def test_txt_cp874_thai_fallback(registry, fixture_tree):
    result = registry.get(".txt").parse(fixture_tree / "txt" / "thai_cp874.txt")
    assert result.ok
    assert result.document.metadata.encoding in ("cp874", "tis-620")
    assert "ทดสอบภาษาไทย" in _all_text(result)
    assert "งบประมาณ" in _all_text(result)


def test_txt_empty_file_is_no_text(registry, fixture_tree):
    result = registry.get(".txt").parse(fixture_tree / "txt" / "empty.txt")
    assert result.outcome is ParseOutcome.NO_TEXT
    assert result.error_code == C.ERR_NO_TEXT


def test_txt_binary_content_is_rejected_not_indexed_as_junk(registry, fixture_tree):
    result = registry.get(".txt").parse(fixture_tree / "txt" / "binary_disguised.txt")
    assert result.outcome is ParseOutcome.NO_TEXT


def test_txt_very_long_line_is_capped(registry, fixture_tree):
    result = registry.get(".txt").parse(fixture_tree / "txt" / "long_line.txt")
    assert result.ok
    assert C.ERR_LIMIT in result.warnings
    assert all(len(unit.text) <= C.MAX_UNIT_TEXT_LENGTH for unit in _units(result))


def test_txt_missing_file(registry, tmp_path):
    result = registry.get(".txt").parse(tmp_path / "nope.txt")
    assert result.outcome is ParseOutcome.MISSING
    assert result.error_code == C.ERR_FILE_MISSING


def test_txt_respects_the_size_limit(fixture_tree):
    parser = TxtParser(ParseOptions(max_file_size_bytes=64))
    result = parser.parse(fixture_tree / "txt" / "long_line.txt")
    assert result.outcome is ParseOutcome.TOO_LARGE
    assert result.error_code == C.ERR_TOO_LARGE


def test_txt_streams_a_large_file(tmp_path):
    big = tmp_path / "big.txt"
    with open(big, "w", encoding="utf-8") as handle:
        for index in range(60_000):
            handle.write(f"line {index} with some filler text\n")
        handle.write("needle_at_the_end\n")
    result = TxtParser(ParseOptions()).parse(big)
    assert result.ok
    assert any("needle_at_the_end" in unit.text for unit in _units(result))


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        (b"\xef\xbb\xbfhello", "utf-8-sig"),
        (b"\xff\xfeh\x00", "utf-16"),
        (b"\xfe\xff\x00h", "utf-16"),
        (b"\xff\xfe\x00\x00h", "utf-32"),
        (b"plain", ""),
    ],
)
def test_detect_encoding(prefix, expected):
    encoding, _from_bom = detect_encoding(prefix)
    assert encoding == expected


def test_looks_binary():
    assert looks_binary(b"abc\x00def")
    assert not looks_binary(b"plain ascii text")
    assert not looks_binary("ข้อความไทย".encode())
    assert not looks_binary(b"")


def test_optional_text_formats(registry, fixture_tree):
    result = registry.get(".csv").parse(fixture_tree / "txt" / "table.csv")
    assert result.ok
    assert "ครุภัณฑ์สำนักงาน" in _all_text(result)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def test_pdf_pages_are_separate_units(registry, fixture_tree):
    result = registry.get(".pdf").parse(fixture_tree / "pdf" / "english.pdf")
    assert result.ok
    units = _units(result)
    assert [unit.location_data["page"] for unit in units] == [1, 2, 3]
    assert all(unit.location_type == C.LOC_PAGE for unit in units)
    assert "pdf needle" in units[1].text


def test_pdf_thai_text(registry, fixture_tree):
    result = registry.get(".pdf").parse(fixture_tree / "pdf" / "thai.pdf")
    assert result.ok
    assert "งบประมาณครุภัณฑ์" in _all_text(result)


def test_pdf_image_only_is_no_text_not_an_error(registry, fixture_tree):
    """No OCR: a scanned PDF is an expected state with its own message."""
    result = registry.get(".pdf").parse(fixture_tree / "pdf" / "image_only.pdf")
    assert result.outcome is ParseOutcome.NO_TEXT
    assert result.error_code == C.ERR_NO_TEXT
    assert "scan" in result.error_message.lower()


def test_pdf_password_protected(registry, fixture_tree):
    result = registry.get(".pdf").parse(fixture_tree / "pdf" / "protected.pdf")
    assert result.outcome is ParseOutcome.PASSWORD_PROTECTED
    assert result.error_code == C.ERR_PASSWORD_PROTECTED
    assert not _units(result)


def test_pdf_corrupt_fails_safely(registry, fixture_tree):
    result = registry.get(".pdf").parse(fixture_tree / "pdf" / "corrupt.pdf")
    assert result.outcome is ParseOutcome.CORRUPT
    assert result.error_code == C.ERR_CORRUPT


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def test_docx_paragraphs_and_tables(registry, fixture_tree):
    result = registry.get(".docx").parse(fixture_tree / "docx" / "report_thai.docx")
    assert result.ok
    units = _units(result)
    paragraphs = [u for u in units if u.location_type == C.LOC_PARAGRAPH]
    cells = [u for u in units if u.location_type == C.LOC_TABLE_CELL]
    assert paragraphs and cells

    assert paragraphs[0].location_data == {"paragraph": 1}
    assert "งบประมาณครุภัณฑ์" in paragraphs[0].text

    cell = next(u for u in cells if "table needle" in u.text)
    assert cell.location_data == {"table": 1, "row": 2, "column": 3}


def test_docx_preserves_body_order(registry, fixture_tree):
    """A table must appear in sequence where it occurs, not after all text."""
    result = registry.get(".docx").parse(fixture_tree / "docx" / "report_thai.docx")
    types = [u.location_type for u in _units(result)]
    first_cell = types.index(C.LOC_TABLE_CELL)
    # There is a paragraph before the table and another after it.
    assert C.LOC_PARAGRAPH in types[:first_cell]
    assert C.LOC_PARAGRAPH in types[first_cell:]


def test_docx_empty_paragraphs_are_skipped(registry, fixture_tree):
    result = registry.get(".docx").parse(fixture_tree / "docx" / "report_thai.docx")
    assert all(unit.text.strip() for unit in _units(result))


def test_docx_headers_and_footers_are_labelled(registry, fixture_tree):
    result = registry.get(".docx").parse(fixture_tree / "docx" / "report_thai.docx")
    kinds = {unit.location_type for unit in _units(result)}
    assert C.LOC_HEADER in kinds
    assert C.LOC_FOOTER in kinds


def test_docx_headers_can_be_disabled(fixture_tree):
    from advance_file_search.indexing.parsers.docx_parser import DocxParser

    parser = DocxParser(ParseOptions(include_docx_headers=False))
    result = parser.parse(fixture_tree / "docx" / "report_thai.docx")
    kinds = {unit.location_type for unit in _units(result)}
    assert C.LOC_HEADER not in kinds


def test_docx_empty_document_is_no_text(registry, fixture_tree):
    result = registry.get(".docx").parse(fixture_tree / "docx" / "empty.docx")
    assert result.outcome is ParseOutcome.NO_TEXT


def test_docx_corrupt_fails_safely(registry, fixture_tree):
    result = registry.get(".docx").parse(fixture_tree / "docx" / "corrupt.docx")
    assert result.outcome is ParseOutcome.CORRUPT


def test_docx_html_like_text_is_kept_literal(registry, fixture_tree):
    """Markup in a document is data; it is never interpreted."""
    result = registry.get(".docx").parse(fixture_tree / "docx" / "html_like.docx")
    assert result.ok
    text = _all_text(result)
    assert "<script>" in text
    assert "<b>bold</b>" in text


def test_docx_inflating_archive_does_not_exhaust_memory(registry, fixture_tree):
    """A tiny archive that inflates hugely must fail, not consume the machine."""
    result = registry.get(".docx").parse(fixture_tree / "hostile" / "inflating.docx")
    assert result.outcome in (ParseOutcome.CORRUPT, ParseOutcome.LIMIT)
    assert not _units(result)


def test_docm_has_no_parser(registry):
    """Macro-enabled documents are out of scope and get no parser at all."""
    assert registry.get(".docm") is None
    assert registry.get(".xlsm") is None
    assert registry.get(".doc") is None
    assert registry.get(".xls") is None


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def test_xlsx_cells_carry_sheet_and_coordinate(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "budget.xlsx")
    assert result.ok
    units = _units(result)
    target = next(unit for unit in units if "cell needle" in unit.text)
    assert target.location_type == C.LOC_SHEET_CELL
    assert target.location_data["cell"] == "F12"
    assert target.location_data["sheet"] == "งบประมาณ 2568"
    assert target.location_data["row"] == 12
    assert target.location_data["column"] == 6


def test_xlsx_thai_sheet_name_is_preserved_exactly(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "budget.xlsx")
    sheets = {unit.location_data["sheet"] for unit in _units(result)}
    assert "งบประมาณ 2568" in sheets
    assert "English Sheet" in sheets


def test_xlsx_hidden_sheets_are_skipped(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "budget.xlsx")
    assert "hidden sheet needle" not in _all_text(result)
    sheets = {unit.location_data["sheet"] for unit in _units(result)}
    assert "HiddenSheet" not in sheets


def test_xlsx_empty_cells_are_skipped(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "budget.xlsx")
    assert all(unit.text.strip() for unit in _units(result))


def test_xlsx_numbers_are_searchable_as_written(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "budget.xlsx")
    text = _all_text(result)
    assert "45000" in text
    assert "1234.5" in text


def test_xlsx_formula_without_cached_value_yields_no_text(registry, fixture_tree):
    """Documented limitation: formulas are not recalculated.

    openpyxl cannot write a cached result, so this workbook's SUM cell has no
    stored value and is therefore not indexed.
    """
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "formula.xlsx")
    text = _all_text(result)
    assert "10" in text and "20" in text
    assert "=SUM" not in text
    assert "30" not in text


def test_xlsx_large_sheet(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "large.xlsx")
    assert result.ok
    assert len(_units(result)) > 400
    assert any("large needle" in unit.text for unit in _units(result))


def test_xlsx_empty_workbook_is_no_text(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "empty.xlsx")
    assert result.outcome is ParseOutcome.NO_TEXT


def test_xlsx_corrupt_fails_safely(registry, fixture_tree):
    result = registry.get(".xlsx").parse(fixture_tree / "xlsx" / "corrupt.xlsx")
    assert result.outcome is ParseOutcome.CORRUPT


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (True, "TRUE"),
        (False, "FALSE"),
        (42, "42"),
        (42.0, "42"),
        (1234.5, "1234.5"),
        (float("nan"), ""),
        (float("inf"), ""),
        ("ข้อความ", "ข้อความ"),
    ],
)
def test_format_cell_value(value, expected):
    assert format_cell_value(value) == expected


def test_format_cell_value_dates():
    import datetime as dt

    assert format_cell_value(dt.date(2025, 3, 14)) == "2025-03-14"
    assert format_cell_value(dt.datetime(2025, 3, 14)) == "2025-03-14"
    assert format_cell_value(dt.datetime(2025, 3, 14, 9, 30)) == "2025-03-14 09:30:00"
    assert format_cell_value(dt.time(9, 30)) == "09:30:00"


# ---------------------------------------------------------------------------
# Registry and safe-failure contract
# ---------------------------------------------------------------------------
def test_registry_matches_extensions_case_insensitively(registry):
    assert registry.get(".PDF") is registry.get(".pdf")
    assert registry.get(".DocX") is registry.get(".docx")


def test_no_parser_raises_for_any_fixture(registry, fixture_tree):
    """The parser contract: parse() never raises, whatever the input."""
    for group in ("txt", "pdf", "docx", "xlsx", "hostile"):
        directory = fixture_tree / group
        if not directory.exists():
            continue
        for entry in directory.iterdir():
            parser = registry.get(entry.suffix.casefold())
            if parser is None:
                continue
            result = parser.parse(entry)  # must not raise
            assert result.outcome in set(ParseOutcome)


def test_parser_handles_a_directory_passed_as_a_file(registry, tmp_path):
    directory = tmp_path / "folder.txt"
    directory.mkdir()
    result = registry.get(".txt").parse(directory)
    assert not result.ok
