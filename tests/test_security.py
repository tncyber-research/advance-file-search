"""Local-only path enforcement, reparse-point policy and log sanitization."""

from __future__ import annotations

import os

import pytest

from advance_file_search.core import security
from advance_file_search.core.security import PathVerdict, validate_root

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Network / non-file-system rejection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        "\\\\server\\share",
        "\\\\server\\share\\folder",
        "//server/share",
        "\\\\?\\UNC\\server\\share",
        "\\\\127.0.0.1\\c$",
        "\\\\localhost\\share\\docs",
    ],
)
def test_unc_paths_are_rejected(raw):
    check = validate_root(raw)
    assert not check.ok
    assert check.is_rejected_as_remote
    assert security.is_unc_path(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "http://example.com/docs",
        "https://example.com/docs",
        "ftp://files.example.com/",
        "sftp://host/path",
        "webdav://host/share",
        "file:///C:/Users",
        "smb://host/share",
        "mailto:user@example.com",
        "javascript:alert(1)",
        "data:text/plain;base64,QQ==",
        "shell:MyComputerFolder",
    ],
)
def test_url_like_paths_are_rejected(raw):
    check = validate_root(raw)
    assert not check.ok
    assert check.verdict is PathVerdict.URL
    assert security.looks_like_url(raw)


@pytest.mark.parametrize(
    "raw",
    ["\\\\.\\PhysicalDrive0", "\\\\.\\C:", "\\\\?\\GLOBALROOT\\Device\\Harddisk0"],
)
def test_device_namespace_is_rejected(raw):
    check = validate_root(raw)
    assert not check.ok
    assert check.verdict is PathVerdict.DEVICE


def test_empty_path_is_rejected():
    assert validate_root("").verdict is PathVerdict.EMPTY
    assert validate_root("   ").verdict is PathVerdict.EMPTY


def test_relative_path_is_rejected():
    assert validate_root("Documents\\reports").verdict is PathVerdict.NO_DRIVE


def test_remote_drive_is_rejected(monkeypatch):
    """A mapped network drive must be refused, not silently indexed."""
    monkeypatch.setattr(security, "get_drive_type", lambda drive: security.DRIVE_REMOTE)
    check = validate_root("Q:\\share")
    assert check.verdict is PathVerdict.REMOTE_DRIVE
    assert check.is_rejected_as_remote
    assert check.drive_type == "remote"


def test_cdrom_is_rejected(monkeypatch):
    monkeypatch.setattr(security, "get_drive_type", lambda drive: security.DRIVE_CDROM)
    assert validate_root("E:\\").verdict is PathVerdict.CDROM


def test_local_directory_is_accepted(tmp_path):
    check = validate_root(str(tmp_path))
    assert check.ok
    assert check.verdict is PathVerdict.LOCAL


def test_missing_local_directory_reports_not_found(tmp_path):
    check = validate_root(str(tmp_path / "does-not-exist"))
    assert check.verdict is PathVerdict.NOT_FOUND


def test_file_is_rejected_as_root(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")
    assert validate_root(str(target)).verdict is PathVerdict.NOT_A_DIRECTORY
    # The same path is fine when a file is expected.
    assert security.validate_file_path(str(target)).ok


def test_url_check_happens_before_filesystem_access(monkeypatch):
    """A hostile path must never reach os.stat, which could open a session."""
    called = []

    def tripwire(*args, **kwargs):
        called.append(args)
        raise AssertionError("filesystem was touched for a remote path")

    monkeypatch.setattr(os.path, "exists", tripwire)
    monkeypatch.setattr(os, "stat", tripwire)
    for raw in ("\\\\evil-server\\share", "http://evil/x", "\\\\.\\PhysicalDrive0"):
        assert not validate_root(raw).ok
    assert not called


# ---------------------------------------------------------------------------
# Reparse points and attributes
# ---------------------------------------------------------------------------
class _FakeStat:
    def __init__(self, attributes: int = 0, mode: int = 0) -> None:
        self.st_file_attributes = attributes
        self.st_mode = mode


def test_reparse_point_detection():
    assert security.is_reparse_point(_FakeStat(security.FILE_ATTRIBUTE_REPARSE_POINT))
    assert not security.is_reparse_point(_FakeStat(0))
    assert not security.is_reparse_point(None)


def test_cloud_placeholder_detection():
    assert security.is_cloud_placeholder(
        _FakeStat(security.FILE_ATTRIBUTE_RECALL_ON_OPEN)
    )
    assert security.is_cloud_placeholder(
        _FakeStat(security.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)
    )
    assert not security.is_cloud_placeholder(_FakeStat(0))


def test_attribute_helpers():
    st = _FakeStat(security.FILE_ATTRIBUTE_HIDDEN | security.FILE_ATTRIBUTE_SYSTEM)
    assert security.has_attribute(st, security.FILE_ATTRIBUTE_HIDDEN)
    assert security.has_attribute(st, security.FILE_ATTRIBUTE_SYSTEM)
    assert not security.has_attribute(st, security.FILE_ATTRIBUTE_TEMPORARY)


@pytest.mark.skipif(os.name != "nt", reason="Windows symlink semantics")
def test_symlink_directory_is_detected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks requires elevation or developer mode")
    st = os.stat(link, follow_symlinks=False)
    assert security.is_reparse_point(st)


# ---------------------------------------------------------------------------
# Log sanitization
# ---------------------------------------------------------------------------
def test_sanitize_removes_newlines_and_control_characters():
    result = security.sanitize_for_log("first\nsecond\r\nthird\x00\x07")
    assert "\n" not in result
    assert "\r" not in result
    assert "\x00" not in result
    assert "first second third" in result


def test_sanitize_truncates():
    result = security.sanitize_for_log("y" * 5000, limit=50)
    assert len(result) == 50
    assert result.endswith("…")


def test_sanitize_collapses_whitespace_runs():
    assert security.sanitize_for_log("a     b") == "a b"


def test_sanitize_handles_none_and_objects():
    assert security.sanitize_for_log(None) == ""
    assert security.sanitize_for_log(12345) == "12345"


def test_sanitize_exception_keeps_type_and_bounds_message():
    exc = ValueError("document text: " + "z" * 4000)
    result = security.sanitize_exception(exc, limit=80)
    assert result.startswith("ValueError")
    assert len(result) <= 80


def test_sanitize_exception_with_empty_message():
    assert security.sanitize_exception(RuntimeError()) == "RuntimeError"


# ---------------------------------------------------------------------------
# Opening a file the machine has no program for
# ---------------------------------------------------------------------------
def _no_association_error() -> OSError:
    """The error Windows raises when nothing is registered for a type."""
    error = OSError("no application is associated with this file")
    error.winerror = 1155
    return error


def test_open_file_falls_back_to_the_open_with_dialog(tmp_path, monkeypatch):
    """A .docx on a PC without Word should offer a choice, not an error."""
    from advance_file_search.winplat import windows_shell

    document = tmp_path / "รายงาน งบประมาณ.docx"
    document.write_bytes(b"PK\x03\x04")

    calls: list[tuple[str, str]] = []

    def fake_startfile(path, operation=""):
        calls.append((str(path), operation))
        if not operation:
            raise _no_association_error()

    monkeypatch.setattr(windows_shell.os, "startfile", fake_startfile, raising=False)
    outcome = windows_shell.open_file(str(document))

    assert outcome.ok, "the user should get the chooser, not a failure"
    assert [operation for _, operation in calls] == ["", "openas"]


def test_open_file_reports_a_clear_reason_when_even_open_with_fails(
    tmp_path, monkeypatch
):
    from advance_file_search.winplat import windows_shell

    document = tmp_path / "report.xyz"
    document.write_text("x", encoding="utf-8")

    def always_fails(path, operation=""):
        raise _no_association_error()

    monkeypatch.setattr(windows_shell.os, "startfile", always_fails, raising=False)
    outcome = windows_shell.open_file(str(document))

    assert not outcome.ok
    assert outcome.error_key == "error.no_association"


def test_open_file_still_reports_other_failures_as_open_failed(tmp_path, monkeypatch):
    from advance_file_search.winplat import windows_shell

    document = tmp_path / "report.txt"
    document.write_text("x", encoding="utf-8")

    def denied(path, operation=""):
        error = OSError("access is denied")
        error.winerror = 5
        raise error

    monkeypatch.setattr(windows_shell.os, "startfile", denied, raising=False)
    outcome = windows_shell.open_file(str(document))

    assert not outcome.ok
    assert outcome.error_key == "error.open_failed"


# ---------------------------------------------------------------------------
# Revealing a file whose path contains spaces
# ---------------------------------------------------------------------------
def test_reveal_uses_the_shell_api_with_the_real_path(tmp_path, monkeypatch):
    """The path reaches the shell exactly as it is — spaces, Thai and all."""
    from advance_file_search.winplat import windows_shell

    folder = tmp_path / "เอกสาร ราชการ 2568"
    folder.mkdir()
    document = folder / "รายงาน งบประมาณ ประจำปี.txt"
    document.write_text("ทดสอบ", encoding="utf-8")

    seen: list[str] = []
    monkeypatch.setattr(
        windows_shell,
        "_select_in_explorer",
        lambda path: seen.append(path) or True,
    )
    outcome = windows_shell.reveal_in_explorer(str(document))

    assert outcome.ok
    assert len(seen) == 1
    assert seen[0].endswith("รายงาน งบประมาณ ประจำปี.txt")
    assert " " in seen[0], "the space must survive: it is what used to break"


def test_reveal_opens_the_folder_when_the_shell_cannot_select(tmp_path, monkeypatch):
    from advance_file_search.winplat import windows_shell

    folder = tmp_path / "เอกสาร ราชการ"
    folder.mkdir()
    document = folder / "บันทึกข้อความ.txt"
    document.write_text("x", encoding="utf-8")

    monkeypatch.setattr(windows_shell, "_select_in_explorer", lambda path: False)
    opened: list[str] = []
    monkeypatch.setattr(
        windows_shell,
        "open_containing_folder",
        lambda path: opened.append(path) or windows_shell.ShellResult(True),
    )

    assert windows_shell.reveal_in_explorer(str(document)).ok
    assert opened == [str(document)]
