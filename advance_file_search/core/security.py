"""Security gatekeeping: local-path validation, remote-drive detection,
reparse-point detection and log sanitization.

This module is the single place that decides whether a path may be indexed.
Version 1 accepts **local Windows file-system paths only**.
"""

from __future__ import annotations

import ctypes
import os
import re
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import PureWindowsPath

from advance_file_search.core import paths as pathutil
from advance_file_search.core.constants import MAX_LOGGED_MESSAGE_LENGTH

SEP = "\\"
_DOUBLE_SEP = SEP + SEP
_LONG_UNC_PREFIX = "\\\\?\\UNC\\"
_DEVICE_PREFIX = "\\\\.\\"
_GLOBALROOT_PREFIX = "\\\\?\\GLOBALROOT"

# ---------------------------------------------------------------------------
# Remote / non-file-system path rejection
# ---------------------------------------------------------------------------
#: Any URL-ish scheme is rejected outright; the app never resolves URLs.
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]{1,31}://")

#: Schemes rejected even without "//" (e.g. ``mailto:``).
_BARE_SCHEMES = (
    "http:", "https:", "ftp:", "ftps:", "sftp:", "webdav:", "dav:", "davs:",
    "file:", "smb:", "nfs:", "mailto:", "data:", "javascript:", "vbscript:",
    "ms-appx:", "shell:", "res:", "about:",
)


class PathVerdict(str, Enum):
    LOCAL = "local"
    UNC = "unc"
    REMOTE_DRIVE = "remote_drive"
    URL = "url"
    DEVICE = "device"
    NOT_FOUND = "not_found"
    NOT_A_DIRECTORY = "not_a_directory"
    EMPTY = "empty"
    NO_DRIVE = "no_drive"
    CDROM = "cdrom"
    UNKNOWN_DRIVE = "unknown_drive"


@dataclass(frozen=True)
class PathCheck:
    """Outcome of validating a user-selected root."""

    verdict: PathVerdict
    display: str
    normalized: str
    drive_type: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict is PathVerdict.LOCAL

    @property
    def is_rejected_as_remote(self) -> bool:
        return self.verdict in (
            PathVerdict.UNC,
            PathVerdict.REMOTE_DRIVE,
            PathVerdict.URL,
        )


# --- Win32 drive type ------------------------------------------------------
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6

_DRIVE_TYPE_NAMES = {
    DRIVE_UNKNOWN: "unknown",
    DRIVE_NO_ROOT_DIR: "no_root",
    DRIVE_REMOVABLE: "removable",
    DRIVE_FIXED: "fixed",
    DRIVE_REMOTE: "remote",
    DRIVE_CDROM: "cdrom",
    DRIVE_RAMDISK: "ramdisk",
}

#: Drive types accepted as "local" for indexing purposes.
_LOCAL_DRIVE_TYPES = {DRIVE_FIXED, DRIVE_REMOVABLE, DRIVE_RAMDISK}


def get_drive_type(drive: str) -> int:
    """Return the Win32 ``GetDriveTypeW`` value for e.g. ``"D:"``.

    Returns :data:`DRIVE_UNKNOWN` on non-Windows platforms so that tests can
    run anywhere without pretending a drive is local.
    """
    if os.name != "nt" or not drive:
        return DRIVE_UNKNOWN
    root = drive.rstrip(SEP) + SEP
    try:
        return int(ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
    except Exception:  # pragma: no cover - defensive
        return DRIVE_UNKNOWN


def drive_type_name(value: int) -> str:
    return _DRIVE_TYPE_NAMES.get(value, "unknown")


def looks_like_url(raw: str) -> bool:
    text = str(raw).strip().strip('"')
    if _URL_SCHEME_RE.match(text):
        return True
    lowered = text.casefold()
    return any(lowered.startswith(scheme) for scheme in _BARE_SCHEMES)


def is_unc_path(raw: str) -> bool:
    """True for ``\\\\server\\share`` style paths, including the long form."""
    text = str(raw).strip().strip('"')
    lowered = text.casefold().replace("/", SEP)
    if lowered.startswith(_LONG_UNC_PREFIX.casefold()):
        return True
    stripped = pathutil.strip_long_prefix(text).replace("/", SEP)
    return stripped.startswith(_DOUBLE_SEP)


def is_device_path(raw: str) -> bool:
    """True for Win32 device namespace paths such as ``\\\\.\\PhysicalDrive0``."""
    text = str(raw).strip().strip('"').replace("/", SEP)
    return text.startswith(_DEVICE_PREFIX) or text.casefold().startswith(
        _GLOBALROOT_PREFIX.casefold()
    )


def validate_root(raw: str, *, require_directory: bool = True) -> PathCheck:
    """Validate a user-selected search root.

    The order of checks matters: URL and UNC forms are rejected before the
    file system is touched at all, so a hostile path can never trigger an
    SMB/WebDAV connection attempt via ``os.stat``.
    """
    text = str(raw or "").strip().strip('"')
    if not text:
        return PathCheck(PathVerdict.EMPTY, "", "")

    if looks_like_url(text):
        return PathCheck(PathVerdict.URL, text, "")
    if is_device_path(text):
        return PathCheck(PathVerdict.DEVICE, text, "")
    if is_unc_path(text):
        return PathCheck(PathVerdict.UNC, pathutil.display_path(text), "")

    shown = pathutil.display_path(text)
    if not shown:
        return PathCheck(PathVerdict.EMPTY, "", "")

    if not PureWindowsPath(shown).drive:
        return PathCheck(PathVerdict.NO_DRIVE, shown, pathutil.normalized_path(shown))

    drive = pathutil.drive_letter(shown)
    if not drive:
        return PathCheck(PathVerdict.NO_DRIVE, shown, pathutil.normalized_path(shown))

    dtype = get_drive_type(drive)
    tname = drive_type_name(dtype)
    normalized = pathutil.normalized_path(shown)
    if dtype == DRIVE_REMOTE:
        return PathCheck(PathVerdict.REMOTE_DRIVE, shown, normalized, tname)
    if dtype == DRIVE_CDROM:
        return PathCheck(PathVerdict.CDROM, shown, normalized, tname)
    if os.name == "nt" and dtype not in _LOCAL_DRIVE_TYPES:
        return PathCheck(PathVerdict.UNKNOWN_DRIVE, shown, normalized, tname)

    target = pathutil.safe_path(shown)
    try:
        exists = target.exists()
    except OSError:
        exists = False
    if not exists:
        return PathCheck(PathVerdict.NOT_FOUND, shown, normalized, tname)
    if require_directory:
        try:
            is_dir = target.is_dir()
        except OSError:
            is_dir = False
        if not is_dir:
            return PathCheck(PathVerdict.NOT_A_DIRECTORY, shown, normalized, tname)

    return PathCheck(PathVerdict.LOCAL, shown, normalized, tname)


def validate_file_path(raw: str) -> PathCheck:
    """Same rules as :func:`validate_root` but for an individual file."""
    return validate_root(raw, require_directory=False)


# ---------------------------------------------------------------------------
# Reparse points / links
# ---------------------------------------------------------------------------
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_TEMPORARY = 0x100
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000


def has_attribute(st: os.stat_result | None, flag: int) -> bool:
    if st is None:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & flag)


def is_reparse_point(st: os.stat_result | None) -> bool:
    """True for symlinks, junctions and mount points.

    MVP policy: never traverse these.  It prevents recursion loops and stops
    the scan from silently escaping the selected root (or reaching a remote
    target through a link).
    """
    if st is None:
        return False
    if stat.S_ISLNK(getattr(st, "st_mode", 0)):
        return True
    return has_attribute(st, FILE_ATTRIBUTE_REPARSE_POINT)


def is_cloud_placeholder(st: os.stat_result | None) -> bool:
    """True for OneDrive-style files whose data is not present locally.

    Reading one would trigger a network download, so they are skipped.
    """
    return has_attribute(
        st, FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
    )


# ---------------------------------------------------------------------------
# Log sanitization
# ---------------------------------------------------------------------------
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_for_log(message: object, *, limit: int = MAX_LOGGED_MESSAGE_LENGTH) -> str:
    """Flatten a value into a single safe log line.

    Removes newlines (log-injection defence) and control characters, then
    truncates.  Callers are responsible for never passing document content.
    """
    text = "" if message is None else str(message)
    text = text.replace("\r", " ").replace("\n", " ")
    text = _CONTROL_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if limit > 0 and len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def sanitize_exception(exc: BaseException, *, limit: int = MAX_LOGGED_MESSAGE_LENGTH) -> str:
    """Return ``ExceptionType: short message`` with no document content.

    Parser exceptions occasionally embed a fragment of the document that
    failed; we keep the type (always safe) and the message only up to a short
    cap, having stripped control characters.
    """
    name = type(exc).__name__
    detail = sanitize_for_log(exc, limit=max(0, limit - len(name) - 2))
    return f"{name}: {detail}" if detail else name
