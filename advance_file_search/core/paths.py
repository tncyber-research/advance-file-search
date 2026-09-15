"""Windows path normalization, application data locations and long-path support.

All path handling treats input as untrusted.  Nothing here touches the network.
"""

from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path, PurePath, PureWindowsPath

from advance_file_search.core.constants import APP_NAME

SEP = "\\"
#: Windows classic MAX_PATH.  Beyond this we opt into the \\?\ prefix form.
_MAX_PATH = 259
_LONG_PREFIX = "\\\\?\\"
_LONG_UNC_PREFIX = "\\\\?\\UNC\\"
_DEVICE_PREFIX = "\\\\.\\"
_DOUBLE_SEP = SEP + SEP


# ---------------------------------------------------------------------------
# Application data locations
# ---------------------------------------------------------------------------
def app_data_dir() -> Path:
    """Return the writable per-user application data directory.

    Mutable data is never written next to the executable: the program may be
    installed under a protected directory such as ``C:\\Program Files``.
    """
    override = os.environ.get("ADVANCE_FILE_SEARCH_DATA_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def index_dir() -> Path:
    return app_data_dir() / "index"


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def settings_dir() -> Path:
    return app_data_dir() / "settings"


def temp_dir() -> Path:
    return app_data_dir() / "temp"


def backups_dir() -> Path:
    return app_data_dir() / "backups"


def database_path() -> Path:
    return index_dir() / "search_index.sqlite3"


def settings_path() -> Path:
    return settings_dir() / "settings.json"


def assets_dir() -> Path | None:
    """Locate the bundled ``assets`` directory.

    PyInstaller places data files under ``_internal`` next to the executable
    and exposes that directory as ``sys._MEIPASS``; running from source it sits
    at the project root.  Both are checked so the same code path works in
    development and in the packaged build.
    """
    candidates: list[Path] = []
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        candidates.append(Path(bundle) / "assets")
        candidates.append(Path(bundle).parent / "assets")
    here = Path(__file__).resolve()
    candidates.append(here.parents[2] / "assets")
    candidates.append(here.parents[1] / "assets")
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return None


def manual_path() -> Path | None:
    """Locate the bundled HTML user manual.

    Checked next to the executable first (where the packaged build puts it),
    then at the project root for a run from source.
    """
    candidates: list[Path] = []
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        candidates.append(Path(bundle).parent / "Manual" / "index.html")
        candidates.append(Path(bundle) / "Manual" / "index.html")
    here = Path(__file__).resolve()
    candidates.append(here.parents[2] / "Manual" / "index.html")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def asset_path(name: str) -> Path | None:
    """Return the path to a bundled asset, or ``None`` when it is absent."""
    directory = assets_dir()
    if directory is None:
        return None
    target = directory / name
    try:
        return target if target.is_file() else None
    except OSError:
        return None


def ensure_app_dirs() -> Path:
    """Create the application data tree if needed and return its root."""
    root = app_data_dir()
    for directory in (
        root,
        index_dir(),
        logs_dir(),
        settings_dir(),
        temp_dir(),
        backups_dir(),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def strip_long_prefix(raw: str) -> str:
    """Remove an extended-length or device-namespace prefix."""
    if raw.startswith(_LONG_UNC_PREFIX):
        return _DOUBLE_SEP + raw[len(_LONG_UNC_PREFIX) :]
    if raw.startswith(_LONG_PREFIX):
        return raw[len(_LONG_PREFIX) :]
    if raw.startswith(_DEVICE_PREFIX):
        return raw[len(_DEVICE_PREFIX) :]
    return raw


def display_path(raw: str | os.PathLike[str]) -> str:
    """Return a cleaned-up path suitable for display and for storage.

    Collapses redundant separators, resolves ``.``/``..`` lexically, converts
    forward slashes to backslashes and drops any extended-length prefix.  The
    original character case is preserved.
    """
    text = strip_long_prefix(str(raw).strip().strip('"'))
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("/", SEP)
    # Preserve a leading UNC double separator while collapsing the rest.
    is_unc = text.startswith(_DOUBLE_SEP)
    body = text[2:] if is_unc else text
    while _DOUBLE_SEP in body:
        body = body.replace(_DOUBLE_SEP, SEP)
    text = (_DOUBLE_SEP + body) if is_unc else body
    pure = PureWindowsPath(text)
    parts: list[str] = []
    for part in pure.parts:
        if part == ".":
            continue
        if part == "..":
            if parts and parts[-1] != ".." and not _is_anchor(parts[-1]):
                parts.pop()
                continue
            if parts and _is_anchor(parts[-1]):
                # Cannot go above the anchor; drop the component.
                continue
        parts.append(part)
    if not parts:
        return ""
    result = str(PureWindowsPath(*parts))
    # A bare drive letter should render as "D:\" not "D:".
    if len(result) == 2 and result[1] == ":":
        result += SEP
    return result


def _is_anchor(part: str) -> bool:
    return part.endswith(SEP) or part.endswith(":") or part.startswith(_DOUBLE_SEP)


def normalized_path(raw: str | os.PathLike[str]) -> str:
    """Return the canonical comparison key for a Windows path.

    Windows paths are case-insensitive, so the comparison form is casefolded
    and has no trailing separator (except for a bare drive root).  Unicode is
    normalized to NFC so that identically-rendered Thai file names compare
    equal regardless of composition form.
    """
    shown = display_path(raw)
    if not shown:
        return ""
    lowered = shown.casefold()
    if len(lowered) > 3 and lowered.endswith(SEP):
        lowered = lowered.rstrip(SEP)
    return lowered


def extended_path(raw: str | os.PathLike[str]) -> str:
    """Return a form usable by the Windows API even beyond ``MAX_PATH``.

    Only applied on Windows, only for absolute paths, and only when needed.
    """
    text = str(raw)
    if os.name != "nt":
        return text
    if text.startswith(_LONG_PREFIX) or text.startswith(_DEVICE_PREFIX):
        return text
    if len(text) <= _MAX_PATH:
        return text
    if text.startswith(_DOUBLE_SEP):
        return _LONG_UNC_PREFIX + text[2:]
    if not PureWindowsPath(text).drive:
        return text
    return _LONG_PREFIX + text


def safe_path(raw: str | os.PathLike[str]) -> Path:
    """Return a :class:`Path` that tolerates long Windows paths."""
    return Path(extended_path(str(raw)))


def relative_display_path(file_path: str, root_path: str) -> str:
    """Return ``file_path`` relative to ``root_path`` for display purposes."""
    shown_file = display_path(file_path)
    shown_root = display_path(root_path)
    norm_file = normalized_path(shown_file)
    norm_root = normalized_path(shown_root)
    if norm_root and norm_file == norm_root:
        return PureWindowsPath(shown_file).name
    prefix = norm_root if norm_root.endswith(SEP) else norm_root + SEP
    if norm_file.startswith(prefix):
        return shown_file[len(prefix) :]
    return shown_file


def is_within_root(file_path: str, root_path: str) -> bool:
    """True when ``file_path`` lies at or below ``root_path`` (lexically)."""
    norm_file = normalized_path(file_path)
    norm_root = normalized_path(root_path)
    if not norm_file or not norm_root:
        return False
    if norm_file == norm_root:
        return True
    prefix = norm_root if norm_root.endswith(SEP) else norm_root + SEP
    return norm_file.startswith(prefix)


def path_parts(raw: str) -> tuple[str, ...]:
    return PureWindowsPath(display_path(raw)).parts


def is_drive_root(raw: str) -> bool:
    pure = PureWindowsPath(display_path(raw))
    return bool(pure.drive) and pure.parts[1:] == ()


def drive_letter(raw: str) -> str:
    """Return the ``X:`` drive designator, or '' for UNC/relative paths."""
    drive = PureWindowsPath(display_path(raw)).drive
    if len(drive) == 2 and drive[1] == ":":
        return drive.upper()
    return ""


def extension_of(raw: str | PurePath) -> str:
    """Lowercased extension including the leading dot, or ''."""
    name = PureWindowsPath(str(raw)).name
    dot = name.rfind(".")
    if dot <= 0:
        return ""
    return name[dot:].casefold()


def format_size(size_bytes: int | None) -> str:
    """Human-readable file size using binary units."""
    if size_bytes is None or size_bytes < 0:
        return ""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:,.1f} {unit}"
        value /= 1024
    return ""
