"""Path normalization and formatting."""

from __future__ import annotations

import pytest

from advance_file_search.core import paths as pathutil


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("D:/a//b/../c", "D:\\a\\c"),
        ("D:\\a\\.\\b", "D:\\a\\b"),
        ("d:", "d:\\"),
        ("D:\\", "D:\\"),
        ("  \"D:\\Docs\"  ", "D:\\Docs"),
        ("\\\\?\\D:\\x\\y", "D:\\x\\y"),
        ("D:\\a\\b\\..\\..\\c", "D:\\c"),
        ("", ""),
        ("D:\\\\\\a", "D:\\a"),
    ],
)
def test_display_path(raw, expected):
    assert pathutil.display_path(raw) == expected


def test_display_path_preserves_unc_double_separator():
    assert pathutil.display_path("//server//share//file") == "\\\\server\\share\\file"


def test_display_path_cannot_escape_the_anchor():
    # ".." above a drive root must not produce a relative or parent path.
    assert pathutil.display_path("D:\\..\\..\\secret") == "D:\\secret"


def test_normalized_path_is_case_insensitive_and_trims_separator():
    assert pathutil.normalized_path("D:\\A\\B\\") == "d:\\a\\b"
    assert pathutil.normalized_path("d:\\a\\b") == pathutil.normalized_path("D:\\A\\B")


def test_normalized_path_keeps_drive_root_separator():
    assert pathutil.normalized_path("D:\\") == "d:\\"


def test_normalized_path_unicode_nfc():
    # A Thai string in decomposed form must normalize to the same key.
    import unicodedata

    composed = "D:\\งบประมาณ"
    decomposed = unicodedata.normalize("NFD", composed)
    assert pathutil.normalized_path(composed) == pathutil.normalized_path(decomposed)


def test_relative_display_path():
    assert pathutil.relative_display_path("D:\\a\\b\\c.txt", "D:\\a") == "b\\c.txt"
    assert pathutil.relative_display_path("D:\\a\\c.txt", "D:\\A\\") == "c.txt"
    assert pathutil.relative_display_path("D:\\a", "D:\\a") == "a"
    # Outside the root: the full path is returned rather than a wrong relative.
    assert pathutil.relative_display_path("E:\\x.txt", "D:\\a") == "E:\\x.txt"


@pytest.mark.parametrize(
    ("candidate", "root", "expected"),
    [
        ("D:\\a\\b.txt", "D:\\a", True),
        ("D:\\a", "D:\\a", True),
        ("D:\\ab\\c.txt", "D:\\a", False),  # prefix must be a path component
        ("D:\\b\\c.txt", "D:\\a", False),
        ("d:\\A\\B.TXT", "D:\\a", True),
        ("D:\\a\\b.txt", "", False),
    ],
)
def test_is_within_root(candidate, root, expected):
    assert pathutil.is_within_root(candidate, root) is expected


def test_extension_of():
    assert pathutil.extension_of("X:\\a\\B.TXT") == ".txt"
    assert pathutil.extension_of("archive.tar.gz") == ".gz"
    assert pathutil.extension_of("noext") == ""
    assert pathutil.extension_of(".hidden") == ""


def test_is_drive_root_and_letter():
    assert pathutil.is_drive_root("d:\\") is True
    assert pathutil.is_drive_root("d:\\x") is False
    assert pathutil.drive_letter("d:\\x") == "D:"
    assert pathutil.drive_letter("\\\\server\\share") == ""


def test_extended_path_only_applied_when_needed():
    short = "D:\\short.txt"
    assert pathutil.extended_path(short) == short
    long_path = "D:\\" + ("x" * 300) + ".txt"
    extended = pathutil.extended_path(long_path)
    assert extended.startswith("\\\\?\\") or extended == long_path


def test_format_size():
    assert pathutil.format_size(0) == "0 B"
    assert pathutil.format_size(1536) == "1.5 KB"
    assert pathutil.format_size(None) == ""
    assert pathutil.format_size(-1) == ""
    assert "GB" in pathutil.format_size(10**10)


def test_app_data_dir_respects_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ADVANCE_FILE_SEARCH_DATA_DIR", str(tmp_path / "custom"))
    assert pathutil.app_data_dir() == tmp_path / "custom"


def test_ensure_app_dirs_creates_tree():
    root = pathutil.ensure_app_dirs()
    for directory in (
        pathutil.index_dir(),
        pathutil.logs_dir(),
        pathutil.settings_dir(),
        pathutil.temp_dir(),
        pathutil.backups_dir(),
    ):
        assert directory.is_dir()
    assert root.is_dir()
