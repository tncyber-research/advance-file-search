"""Windows drive enumeration and network-drive detection.

The purpose is to make "local drives only" enforceable and explainable: the UI
can list exactly which drives may be indexed and say why the others cannot.
"""

from __future__ import annotations

import ctypes
import os
import string
from dataclasses import dataclass

from advance_file_search.core.security import (
    DRIVE_CDROM,
    DRIVE_FIXED,
    DRIVE_RAMDISK,
    DRIVE_REMOTE,
    DRIVE_REMOVABLE,
    drive_type_name,
    get_drive_type,
)

_LOCAL_TYPES = {DRIVE_FIXED, DRIVE_REMOVABLE, DRIVE_RAMDISK}


@dataclass(frozen=True)
class DriveInfo:
    letter: str  # "D:"
    root: str  # "D:\"
    type_code: int
    type_name: str
    label: str = ""

    @property
    def is_local(self) -> bool:
        return self.type_code in _LOCAL_TYPES

    @property
    def is_remote(self) -> bool:
        return self.type_code == DRIVE_REMOTE

    @property
    def is_optical(self) -> bool:
        return self.type_code == DRIVE_CDROM


def logical_drive_letters() -> list[str]:
    """Return the present drive designators, e.g. ``["C:", "D:"]``."""
    if os.name != "nt":
        return []
    try:
        mask = int(ctypes.windll.kernel32.GetLogicalDrives())
    except Exception:  # pragma: no cover - defensive
        return []
    return [
        f"{letter}:"
        for index, letter in enumerate(string.ascii_uppercase)
        if mask & (1 << index)
    ]


def volume_label(root: str) -> str:
    """Read a volume's display name, or '' when it cannot be read."""
    if os.name != "nt":
        return ""
    buffer = ctypes.create_unicode_buffer(261)
    fs_buffer = ctypes.create_unicode_buffer(261)
    try:
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root),
            buffer,
            ctypes.sizeof(buffer) // 2,
            None,
            None,
            None,
            fs_buffer,
            ctypes.sizeof(fs_buffer) // 2,
        )
    except Exception:  # pragma: no cover - defensive
        return ""
    return buffer.value if ok else ""


def list_drives(*, include_remote: bool = True) -> list[DriveInfo]:
    """Enumerate drives with their type, so the UI can label them."""
    drives: list[DriveInfo] = []
    for letter in logical_drive_letters():
        root = letter + "\\"
        code = get_drive_type(letter)
        if code == DRIVE_REMOTE and not include_remote:
            continue
        # A label is only read for local drives: querying a remote volume would
        # touch the network, which version 1 must never do.
        label = volume_label(root) if code in _LOCAL_TYPES else ""
        drives.append(
            DriveInfo(
                letter=letter,
                root=root,
                type_code=code,
                type_name=drive_type_name(code),
                label=label,
            )
        )
    return drives


def local_drives() -> list[DriveInfo]:
    return [drive for drive in list_drives() if drive.is_local]


def is_remote_drive(path: str) -> bool:
    """True when ``path`` lives on a mapped network drive."""
    from advance_file_search.core.paths import drive_letter

    letter = drive_letter(path)
    if not letter:
        return False
    return get_drive_type(letter) == DRIVE_REMOTE


def unc_target_of_drive(letter: str) -> str:
    """Return the UNC path a mapped drive points at, or ''.

    Used only for diagnostics and for explaining a rejection to the user; the
    application never connects to the returned path.
    """
    if os.name != "nt" or not letter:
        return ""
    buffer = ctypes.create_unicode_buffer(1024)
    size = ctypes.c_ulong(ctypes.sizeof(buffer) // 2)
    try:
        # WNetGetConnectionW reads the local mapping table; it does not open a
        # network session.
        result = ctypes.windll.mpr.WNetGetConnectionW(
            ctypes.c_wchar_p(letter.rstrip("\\")), buffer, ctypes.byref(size)
        )
    except Exception:  # pragma: no cover - defensive
        return ""
    return buffer.value if result == 0 else ""
