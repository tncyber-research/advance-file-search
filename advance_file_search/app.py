"""Application entry point.

Startup sequence:

1. create the application data directories;
2. load settings and configure privacy-filtered logging;
3. acquire the single-instance lock (two writers must never share the index);
4. open and migrate the index database, verifying FTS5 support;
5. show the main window.

There is no network code anywhere in this path: no update check, no telemetry,
no remote asset loading.  Qt is also told not to use any network-backed
platform integration.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Qt environment hardening applied before QtWidgets is imported.
#: * Disable the accessibility bridge's D-Bus/remote paths (no effect on
#:   Windows Narrator, which uses the native UIA bridge).
#: * Never ask Qt to fetch anything over a network.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from advance_file_search.core import constants as C  # noqa: E402
from advance_file_search.core import paths as pathutil  # noqa: E402
from advance_file_search.core.i18n import set_language, tr  # noqa: E402
from advance_file_search.core.settings import load_settings  # noqa: E402
from advance_file_search.logging_setup import configure_logging, get_logger  # noqa: E402
from advance_file_search.storage.database import (  # noqa: E402
    DatabaseError,
    fts5_available,
)
from advance_file_search.storage.migrations import (  # noqa: E402
    IncompatibleIndexError,
    open_index,
)
from advance_file_search.storage.repositories import Repositories  # noqa: E402
from advance_file_search.ui.main_window import MainWindow  # noqa: E402
from advance_file_search.ui.theme import apply_theme  # noqa: E402
from advance_file_search.winplat.single_instance import SingleInstance  # noqa: E402


def _cleanup_temp_dir() -> None:
    """Remove leftovers from a previous crash.

    The application prefers in-memory extraction and does not normally write
    temporary plaintext, but the directory is swept on every launch so nothing
    can linger after an abnormal exit.
    """
    directory = pathutil.temp_dir()
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                import shutil

                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            continue


def _apply_window_icon(app: QApplication) -> None:
    """Set the icon shown in the title bar, taskbar and Alt-Tab switcher.

    The multi-resolution ``app.ico`` is preferred so Windows can pick the size
    it needs; the PNGs are a fallback.  Every candidate is a bundled local
    file — nothing is fetched.  A missing icon is not worth failing startup
    over, so the application simply runs with the platform default.
    """
    from PySide6.QtGui import QIcon

    icon = QIcon()
    for name in ("app.ico", "app-256.png", "app-64.png", "app-32.png", "app.png"):
        path = pathutil.asset_path(name)
        if path is None:
            continue
        candidate = QIcon(str(path))
        if not candidate.isNull():
            # Merge the PNG sizes into the ICO so every requested size has a
            # natively rendered pixmap rather than a rescaled one.
            for size in candidate.availableSizes():
                icon.addPixmap(candidate.pixmap(size))
    if not icon.isNull():
        app.setWindowIcon(icon)


def run_selftest(folder: str) -> int:
    """Index ``folder`` and run a few searches, printing the outcome.

    A packaged, windowed application is otherwise very hard to verify: the
    release build has no console and cannot be driven from a script.  This
    diagnostic mode exercises the real bundled parsers, the real SQLite build
    and the real search path, so a release candidate can be checked on the
    machine it will run on.  It is also what to ask a user to run when
    something misbehaves in the field.

    Writes to a scratch data directory, never to the user's index.  No GUI is
    created and nothing is left behind.
    """
    import shutil
    import tempfile

    from advance_file_search.core.models import SearchRequest
    from advance_file_search.core.settings import AppSettings
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
    from advance_file_search.search.search_service import SearchService
    from advance_file_search.storage.database import fts5_available
    from advance_file_search.storage.migrations import open_index
    from advance_file_search.storage.repositories import Repositories

    failures: list[str] = []

    def check(label: str, ok: bool, extra: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label} {extra}".rstrip())
        if not ok:
            failures.append(label)

    print(f"Advance File Search {C.APP_VERSION} self-test")
    print(f"  frozen : {bool(getattr(sys, 'frozen', False))}")
    print(f"  python : {sys.version.split()[0]}")
    print(f"  folder : {folder}\n")

    check("SQLite has FTS5", fts5_available())

    scratch = Path(tempfile.mkdtemp(prefix="afs-selftest-"))
    try:
        database, migration = open_index(scratch / "selftest.sqlite3")
        try:
            check("index schema created", migration.created)
            repos = Repositories.create(database)

            check("trigram tokenizer available", _probe_trigram(database))

            settings = AppSettings(enable_optional_formats=True).normalize()
            summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(folder)
            print(
                f"\n  discovered={summary.discovered} indexed={summary.indexed} "
                f"no_text={summary.no_text} failed={summary.failed} "
                f"skipped={summary.skipped} in {summary.elapsed_seconds:.2f}s\n"
            )
            check("indexing completed", summary.status.value == "completed")
            check("at least one file indexed", summary.indexed > 0)

            root = repos.roots.find_by_path(folder)
            if root is None:
                check("root recorded", False)
            else:
                service = SearchService(repos)
                for label, query in (
                    ("ASCII search", "the"),
                    ("Thai search", "ก"),
                ):
                    response = service.search(
                        SearchRequest(query=query, root_id=root.id, limit=5)
                    )
                    print(
                        f"  {label:14} {query!r:6} -> "
                        f"{response.total_matched_files} files "
                        f"({response.elapsed_ms:.1f} ms)"
                    )
                check("search ran without error", True)
                check("database integrity", database.integrity_check())
                extensions = dict(repos.files.extensions_for_root(root.id))
                print(f"  file types indexed: {extensions}")
        finally:
            database.close()
    except Exception as exc:  # noqa: BLE001 - report rather than traceback
        check(f"self-test raised {type(exc).__name__}", False, str(exc)[:200])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print()
    if failures:
        print(f"SELF-TEST FAILED ({len(failures)}): {', '.join(failures)}")
        return 1
    print("SELF-TEST PASSED")
    return 0


def _probe_trigram(database: object) -> bool:
    try:
        database.execute(  # type: ignore[attr-defined]
            "CREATE VIRTUAL TABLE _probe USING fts5(x, tokenize='trigram')"
        )
        database.execute("DROP TABLE _probe")  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)

    if "--selftest" in args:
        position = args.index("--selftest")
        target = args[position + 1] if len(args) > position + 1 else str(Path.cwd())
        pathutil.ensure_app_dirs()
        configure_logging(level="INFO", log_paths=True, console=False)
        return run_selftest(target)

    pathutil.ensure_app_dirs()
    settings = load_settings()
    set_language(settings.language)

    debug = "--debug" in args or bool(os.environ.get("ADVANCE_FILE_SEARCH_DEBUG"))
    configure_logging(
        level="DEBUG" if debug else settings.log_level,
        log_paths=settings.log_file_paths,
        console=debug,
    )
    log = get_logger("app")
    log.info(
        "starting | version=%s | python=%s | frozen=%s",
        C.APP_VERSION,
        sys.version.split()[0],
        bool(getattr(sys, "frozen", False)),
    )
    _cleanup_temp_dir()

    QApplication.setApplicationName(C.APP_NAME)
    QApplication.setApplicationVersion(C.APP_VERSION)
    QApplication.setOrganizationName(C.APP_ORG)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    app = QApplication(args)
    apply_theme(app)
    _apply_window_icon(app)

    guard = SingleInstance()
    if not guard.acquire():
        log.info("second instance refused")
        QMessageBox.information(None, C.APP_NAME, tr("error.already_running"))
        return 0

    if not fts5_available():
        log.error("FTS5 unavailable in the bundled SQLite build")
        QMessageBox.critical(None, C.APP_NAME, tr("error.db_corrupt"))
        guard.release()
        return 2

    try:
        db, migration = open_index()
    except IncompatibleIndexError as exc:
        log.error("index schema is newer than this build | %s", exc)
        QMessageBox.critical(None, C.APP_NAME, tr("error.db_corrupt"))
        guard.release()
        return 3
    except DatabaseError as exc:
        log.error("could not open index | %s", exc)
        QMessageBox.critical(None, C.APP_NAME, tr("error.db_corrupt"))
        guard.release()
        return 4

    log.info(
        "index ready | schema=%d | created=%s | path_bytes=%d",
        migration.to_version,
        migration.created,
        db.file_size_bytes(),
    )

    try:
        # A run left in 'running' state means the previous session was killed
        # mid-index; mark it failed so the UI reports honestly.
        Repositories.create(db).runs.abandon_running()
    except DatabaseError as exc:
        log.warning("could not reconcile interrupted runs | %s", exc)

    window = MainWindow(db, settings)
    window.show()

    exit_code = 1
    try:
        exit_code = app.exec()
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            pass
        guard.release()
        log.info("exiting | code=%s", exit_code)
    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
