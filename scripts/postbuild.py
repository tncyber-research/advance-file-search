"""Post-process a PyInstaller onedir build.

    .venv\\Scripts\\python.exe scripts\\postbuild.py "dist\\Advance File Search"

Two jobs:

1. **Surface the user-facing files.**  PyInstaller 6 places every data file
   under ``_internal\\``.  The documented distribution layout puts ``LICENSES``
   and ``README.txt`` next to the executable where a person will actually find
   them, so they are copied up.  The copies inside ``_internal`` are left in
   place because the About dialog resolves either location.

2. **Remove the networking binaries.**  ``_socket.pyd``, ``_ssl.pyd`` and the
   async I/O extensions are pulled in by PyInstaller as part of the standard
   library, not by anything this application imports.  Deleting them turns
   "we do not open sockets" from a convention into a property of the artefact:
   the modules cannot be imported because they are not there.

   Pass ``--keep-network`` to skip step 2 while diagnosing a problem.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Copied from _internal to the top level of the distribution.
SURFACE = ("LICENSES", "Manual", "README.txt", "PRIVACY.txt")

#: Standard-library extension modules that provide network access.  None of
#: them is imported by this application; a privacy test asserts that.
NETWORK_BINARIES = (
    "_socket.pyd",
    "_ssl.pyd",
    "_asyncio.pyd",
    "_overlapped.pyd",
    "select.pyd",
    "libssl-3.dll",
    "libcrypto-3.dll",
    "libssl-1_1.dll",
    "libcrypto-1_1.dll",
)

#: Qt shared libraries that arrive as *transitive* dependencies of modules we
#: already excluded at the binding level.  ``PySide6.QtNetwork`` is excluded,
#: so no Python code can use it — but ``Qt6Network.dll`` is still bundled
#: because ``Qt6Qml.dll``, ``Qt6Quick.dll`` and ``Qt6Pdf.dll`` link against it.
#: Those three are themselves unused (this is a plain QtWidgets application),
#: so removing the whole group removes the network library with them and makes
#: the offline guarantee a property of the artefact rather than a convention.
#:
#: Anything listed here must be verified by actually running the build; the
#: acceptance test in scripts/test_packaged_build.py does that.
UNUSED_QT_BINARIES = (
    "Qt6Network.dll",
    "Qt6Qml.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlMeta.dll",
    "Qt6QmlWorkerScript.dll",
    "Qt6Quick.dll",
    "Qt6QuickControls2.dll",
    "Qt6QuickTemplates2.dll",
    "Qt6QuickWidgets.dll",
    "Qt6Pdf.dll",
    "Qt6VirtualKeyboard.dll",
    "qtuiotouchplugin.dll",
)


def surface_user_files(root: Path) -> list[str]:
    internal = root / "_internal"
    moved: list[str] = []
    for name in SURFACE:
        source = internal / name
        if not source.exists():
            source = PROJECT_ROOT / name
        if not source.exists():
            continue
        target = root / name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink()
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        moved.append(name)
    return moved


def _remove_all(root: Path, names: tuple[str, ...]) -> tuple[list[str], int]:
    removed: list[str] = []
    freed = 0
    for name in names:
        for candidate in root.rglob(name):
            try:
                size = candidate.stat().st_size
                candidate.unlink()
            except OSError as exc:
                print(f"  could not remove {candidate.name}: {exc}")
                continue
            removed.append(str(candidate.relative_to(root)))
            freed += size
    return removed, freed


def strip_network_binaries(root: Path) -> tuple[list[str], int]:
    return _remove_all(root, NETWORK_BINARIES)


def strip_unused_qt(root: Path) -> tuple[list[str], int]:
    return _remove_all(root, UNUSED_QT_BINARIES)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    keep_network = "--keep-network" in argv
    if not args:
        print(__doc__)
        return 2

    root = Path(args[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}")
        return 2

    print(f"Post-processing {root}\n")

    moved = surface_user_files(root)
    print(f"  surfaced to the top level : {', '.join(moved) if moved else 'nothing'}")

    if keep_network:
        print("  network binaries          : kept (--keep-network)")
    else:
        removed, freed = strip_network_binaries(root)
        qt_removed, qt_freed = strip_unused_qt(root)
        if removed:
            print(f"  removed network binaries  : {len(removed)} ({freed / 1024:,.0f} KB)")
            for name in removed:
                print(f"      - {name}")
        else:
            print("  network binaries          : none were bundled")
        if qt_removed:
            print(
                f"  removed unused Qt modules : {len(qt_removed)} "
                f"({qt_freed / 1024 / 1024:,.1f} MB)"
            )
            for name in qt_removed:
                print(f"      - {name}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
