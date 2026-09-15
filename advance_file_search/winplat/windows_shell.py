"""Safe Windows shell integration: open a file, reveal it, copy its path.

Security rules enforced here:

* A shell command string is **never** built from a path.  Explorer is launched
  with an argument *list* through ``subprocess.Popen``, so a path containing
  quotes, ampersands or ``&&`` cannot inject a command.
* ``os.startfile`` is used to open a document with its registered handler.  It
  takes a path, not a command line, so the same injection class does not apply.
* Only regular files inside a validated local path are ever opened, and only
  in response to an explicit user action.  Nothing is auto-opened.
* Executables and scripts are refused even if the user manages to select one,
  so a malicious file name in the index cannot lead to code execution.
* No subprocess in this module runs through a shell; a privacy test asserts
  that the corresponding keyword argument appears nowhere in the source.
* Revealing a file asks the Windows shell itself
  (``SHOpenFolderAndSelectItems``), so no command line is built at all.  The
  previous implementation passed ``/select,<path>`` to ``explorer.exe`` as one
  argument; Windows quotes an argument containing a space, and Explorer then
  fails to recognise its own switch — so any path with a space (which most Thai
  folder names have) opened the wrong window.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from dataclasses import dataclass
from pathlib import PureWindowsPath

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.security import PathVerdict, validate_file_path
from advance_file_search.logging_setup import get_logger, safe_path_field

log = get_logger("winplat.shell")

#: Windows hides the console for these when launched without a window.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class ShellResult:
    ok: bool
    #: One of the ``error.*`` i18n keys, or '' on success.
    error_key: str = ""

    def __bool__(self) -> bool:
        return self.ok


def _explorer_path() -> str:
    """Absolute path to explorer.exe, never resolved from PATH.

    Resolving ``explorer.exe`` through ``PATH`` would let a writable directory
    earlier in ``PATH`` supply a different binary.
    """
    windir = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows"
    return str(PureWindowsPath(windir) / "explorer.exe")


#: ``CoInitializeEx`` results that mean COM is usable on this thread.
_S_OK = 0
_S_FALSE = 1
_RPC_E_CHANGED_MODE = -2147417850  # the thread is already in another apartment
_COINIT_APARTMENTTHREADED = 0x2

#: ``os.startfile`` raises these when no program is registered for the type.
_NO_ASSOCIATION_ERRORS = frozenset({31, 1155})  # ERROR_GEN_FAILURE, ERROR_NO_ASSOCIATION


def _select_in_explorer(path: str) -> bool:
    """Open the containing folder with ``path`` selected, via the shell API.

    Returns ``False`` if the shell refuses or the API is unavailable, so the
    caller can fall back to simply opening the folder.

    This takes the path as a string through ``SHParseDisplayName`` — there is
    no command line, so quoting and spaces cannot be misread by anything.
    """
    if os.name != "nt":  # pragma: no cover - the application is Windows-only
        return False
    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
    except (AttributeError, OSError):  # pragma: no cover - not Windows
        return False

    shell32.SHParseDisplayName.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    shell32.SHParseDisplayName.restype = ctypes.c_long
    shell32.SHOpenFolderAndSelectItems.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long

    initialised = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    if initialised not in (_S_OK, _S_FALSE, _RPC_E_CHANGED_MODE):
        return False

    item = ctypes.c_void_p()
    attributes = ctypes.c_ulong()
    try:
        parsed = shell32.SHParseDisplayName(
            str(path), None, ctypes.byref(item), 0, ctypes.byref(attributes)
        )
        if parsed != _S_OK or not item:
            return False
        # cidl = 0 with the file's own item selects it inside its parent.
        opened = shell32.SHOpenFolderAndSelectItems(item, 0, None, 0)
        return opened == _S_OK
    except OSError:
        return False
    finally:
        if item:
            ole32.CoTaskMemFree(item)
        if initialised in (_S_OK, _S_FALSE):
            ole32.CoUninitialize()


def open_file(path: str) -> ShellResult:
    """Open a document with its default Windows application."""
    check = validate_file_path(path)
    if check.verdict is PathVerdict.NOT_FOUND:
        return ShellResult(False, "error.file_missing_body")
    if check.is_rejected_as_remote:
        return ShellResult(False, "error.network_path")
    if not check.ok:
        return ShellResult(False, "error.open_failed")

    target = pathutil.safe_path(check.display)
    try:
        if not target.is_file():
            return ShellResult(False, "error.file_missing_body")
    except OSError:
        return ShellResult(False, "error.file_missing_body")

    extension = pathutil.extension_of(check.display)
    if extension in C.EXECUTABLE_EXTENSIONS:
        # The index never contains these, but refuse defensively rather than
        # hand an executable to the shell.
        log.warning("refused to open executable | %s", safe_path_field(check.display))
        return ShellResult(False, "error.open_failed")

    try:
        # os.startfile takes a path, not a command line: no shell parsing.
        os.startfile(str(target))  # noqa: S606 - path only, no shell
        return ShellResult(True)
    except OSError as exc:
        if getattr(exc, "winerror", None) in _NO_ASSOCIATION_ERRORS:
            # Nothing is registered for this type on this machine — a DOCX on a
            # PC without Word, for instance.  Rather than reporting a failure
            # the user can do nothing about, hand it to the shell's own
            # "Open with" dialog and let them choose a program.
            if _open_with_dialog(target, check.display):
                return ShellResult(True)
            return ShellResult(False, "error.no_association")
        log.warning("open failed | %s | %s", safe_path_field(check.display), exc)
        return ShellResult(False, "error.open_failed")
    except AttributeError:  # pragma: no cover - non-Windows
        return ShellResult(False, "error.open_failed")


def _open_with_dialog(target: object, shown: str) -> bool:
    """Show the Windows "Open with" chooser for a file with no association."""
    try:
        os.startfile(str(target), "openas")  # noqa: S606 - path only, no shell
        return True
    except OSError as exc:
        log.warning("open-with failed | %s | %s", safe_path_field(shown), exc)
        return False
    except (AttributeError, ValueError):  # pragma: no cover - non-Windows
        return False


def reveal_in_explorer(path: str) -> ShellResult:
    """Open File Explorer with the file selected.

    The shell is asked directly (``SHOpenFolderAndSelectItems``) rather than
    through ``explorer.exe /select,...``: the switch form has to survive
    command-line quoting, and it does not when the path contains a space.

    If the shell cannot select the item, the containing folder is opened, which
    still gets the user where they were going.
    """
    check = validate_file_path(path)
    if check.is_rejected_as_remote:
        return ShellResult(False, "error.network_path")
    if check.verdict is PathVerdict.NOT_FOUND:
        return open_containing_folder(path)
    if not check.ok:
        return ShellResult(False, "error.open_failed")

    target = pathutil.safe_path(check.display)
    try:
        exists = target.exists()
    except OSError:
        exists = False
    if not exists:
        return open_containing_folder(path)

    # The plain display path is used, not the \\?\ extended-length form,
    # which the shell namespace does not parse.
    if _select_in_explorer(check.display):
        return ShellResult(True)

    log.info("reveal fell back to the folder | %s", safe_path_field(check.display))
    return open_containing_folder(path)


def open_containing_folder(path: str) -> ShellResult:
    """Open the folder that holds ``path`` (no selection)."""
    shown = pathutil.display_path(path)
    if not shown:
        return ShellResult(False, "error.open_failed")
    folder = str(PureWindowsPath(shown).parent)
    check = validate_file_path(folder)
    if check.is_rejected_as_remote:
        return ShellResult(False, "error.network_path")
    if not check.ok:
        return ShellResult(False, "error.not_found")
    try:
        subprocess.Popen(  # noqa: S603 - fixed executable, argument list
            [_explorer_path(), check.display],
            creationflags=_NO_WINDOW,
            close_fds=True,
        )
        return ShellResult(True)
    except (OSError, ValueError) as exc:
        log.warning("open folder failed | %s", exc)
        return ShellResult(False, "error.open_failed")


def open_data_folder() -> ShellResult:
    """Open the application's own data directory."""
    directory = pathutil.ensure_app_dirs()
    try:
        subprocess.Popen(  # noqa: S603 - fixed executable, argument list
            [_explorer_path(), str(directory)],
            creationflags=_NO_WINDOW,
            close_fds=True,
        )
        return ShellResult(True)
    except (OSError, ValueError) as exc:
        log.warning("open data folder failed | %s", exc)
        return ShellResult(False, "error.open_failed")


def explorer_folder_args(path: str) -> list[str]:
    """Return the argument list used to open the folder holding ``path``.

    Exposed so a unit test can assert the arguments are a list and that no
    shell metacharacter is ever concatenated into a command string.  Selecting
    the file itself no longer goes through Explorer's command line at all; see
    :func:`_select_in_explorer`.
    """
    shown = pathutil.display_path(path)
    return [_explorer_path(), str(PureWindowsPath(shown).parent)]
