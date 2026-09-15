"""End-to-end integration: full lifecycle, restarts, settings and workers."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.models import (
    RunStatus,
    SearchRequest,
    SearchScope,
)
from advance_file_search.core.settings import AppSettings, load_settings, save_settings
from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
from advance_file_search.search.search_service import SearchService
from advance_file_search.storage.migrations import open_index
from advance_file_search.storage.repositories import Repositories

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _index(repos, root, settings, *, rebuild: bool = False):
    return IndexCoordinator(
        repos, IndexOptions(rebuild=rebuild, settings=settings)
    ).run(str(root))


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------
def test_index_search_restart_update_cycle(tmp_path, corpus, settings):
    """The workflow from handoff §2.8, exercised without a UI."""
    db_path = tmp_path / "index.sqlite3"

    # --- session 1: build the index ---------------------------------------
    db, migration = open_index(db_path)
    repos = Repositories.create(db)
    assert migration.created
    first = _index(repos, corpus, settings)
    assert first.status is RunStatus.COMPLETED
    root_id = repos.roots.find_by_path(str(corpus)).id

    service = SearchService(repos)
    thai_before = service.search(
        SearchRequest(query="งบประมาณ", root_id=root_id)
    ).total_matched_files
    english_before = service.search(
        SearchRequest(query="budget", root_id=root_id)
    ).total_matched_files
    assert thai_before > 0 and english_before > 0
    db.close()

    # --- session 2: reopen and search without reindexing ------------------
    db, migration = open_index(db_path)
    repos = Repositories.create(db)
    assert not migration.created
    service = SearchService(repos)
    root = repos.roots.find_by_path(str(corpus))
    assert root.file_count == first.discovered
    assert (
        service.search(SearchRequest(query="งบประมาณ", root_id=root.id)).total_matched_files
        == thai_before
    )

    # --- session 2 continued: incremental update --------------------------
    (corpus / "เอกสาร" / "txt" / "session2.txt").write_text(
        "added in the second session needle_session2", encoding="utf-8"
    )
    second = _index(repos, corpus, settings)
    assert second.indexed == 1
    assert second.unchanged == first.discovered
    assert (
        service.search(
            SearchRequest(query="needle_session2", root_id=root.id)
        ).total_matched_files
        == 1
    )
    db.close()

    # --- session 3: everything still works --------------------------------
    db, _ = open_index(db_path)
    repos = Repositories.create(db)
    service = SearchService(repos)
    root = repos.roots.find_by_path(str(corpus))
    assert (
        service.search(
            SearchRequest(query="needle_session2", root_id=root.id)
        ).total_matched_files
        == 1
    )
    assert db.integrity_check()
    db.close()


def test_multiple_roots_are_scoped_independently(repos, tmp_path, settings):
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    (alpha / "a.txt").write_text("shared_token alpha_only", encoding="utf-8")
    (beta / "b.txt").write_text("shared_token beta_only", encoding="utf-8")

    _index(repos, alpha, settings)
    _index(repos, beta, settings)
    assert len(repos.roots.list_all()) == 2

    service = SearchService(repos)
    alpha_id = repos.roots.find_by_path(str(alpha)).id
    beta_id = repos.roots.find_by_path(str(beta)).id

    # Both roots contain the shared token, but a search is scoped to one root.
    for root_id, expected, unexpected in (
        (alpha_id, "alpha_only", "beta_only"),
        (beta_id, "beta_only", "alpha_only"),
    ):
        response = service.search(SearchRequest(query="shared_token", root_id=root_id))
        assert response.total_matched_files == 1
        assert (
            service.search(SearchRequest(query=expected, root_id=root_id)).total_matched_files
            == 1
        )
        assert (
            service.search(
                SearchRequest(query=unexpected, root_id=root_id)
            ).total_matched_files
            == 0
        )


def test_deleting_one_root_leaves_the_other(repos, tmp_path, settings):
    from advance_file_search.indexing.coordinator import delete_index_for_root

    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    for directory, token in ((alpha, "alpha_token"), (beta, "beta_token")):
        directory.mkdir()
        (directory / "f.txt").write_text(token, encoding="utf-8")
        _index(repos, directory, settings)

    delete_index_for_root(repos, str(alpha))
    assert repos.roots.find_by_path(str(alpha)) is None
    beta_root = repos.roots.find_by_path(str(beta))
    assert beta_root is not None
    service = SearchService(repos)
    assert (
        service.search(SearchRequest(query="beta_token", root_id=beta_root.id)).total_matched_files
        == 1
    )


def test_rebuild_after_enabling_optional_formats(repos, tmp_path):
    core_only = AppSettings(enable_optional_formats=False).normalize()
    extended = AppSettings(enable_optional_formats=True).normalize()

    root = tmp_path / "docs"
    root.mkdir()
    (root / "notes.md").write_text("markdown needle_md", encoding="utf-8")
    (root / "plain.txt").write_text("plain needle_txt", encoding="utf-8")

    _index(repos, root, core_only)
    record = repos.roots.find_by_path(str(root))
    service = SearchService(repos)
    assert (
        service.search(SearchRequest(query="needle_md", root_id=record.id)).total_matched_files
        == 0
    )

    _index(repos, root, extended)
    assert (
        service.search(SearchRequest(query="needle_md", root_id=record.id)).total_matched_files
        == 1
    )


def test_index_survives_a_missing_root_on_a_later_run(repos, tmp_path, settings):
    """Losing the folder must not wipe the index."""
    import shutil

    root = tmp_path / "removable"
    root.mkdir()
    (root / "a.txt").write_text("content needle", encoding="utf-8")
    _index(repos, root, settings)
    record = repos.roots.find_by_path(str(root))
    before = repos.files.count_for_root(record.id)

    shutil.rmtree(root)
    summary = _index(repos, root, settings)
    assert summary.status is RunStatus.FAILED
    # Previously indexed data is still there and still searchable.
    assert repos.files.count_for_root(record.id) == before
    service = SearchService(repos)
    response = service.search(SearchRequest(query="needle", root_id=record.id))
    assert response.total_matched_files == 1
    assert not response.results[0].exists


def test_a_whole_run_of_corrupt_files_does_not_abort_indexing(repos, tmp_path, settings):
    root = tmp_path / "docs"
    root.mkdir()
    for index in range(20):
        (root / f"broken{index}.docx").write_bytes(b"PK\x03\x04 not a package")
    (root / "good.txt").write_text("the only good file needle", encoding="utf-8")

    summary = _index(repos, root, settings)
    assert summary.status is RunStatus.COMPLETED
    assert summary.failed == 20
    assert summary.indexed == 1
    record = repos.roots.find_by_path(str(root))
    service = SearchService(repos)
    assert (
        service.search(SearchRequest(query="needle", root_id=record.id)).total_matched_files
        == 1
    )


def test_deep_and_long_paths(repos, tmp_path, settings):
    """Long paths and Thai directory names must index and search."""
    deep = tmp_path
    for level in range(12):
        deep = deep / f"ระดับ{level}_directory_with_a_fairly_long_name"
    target = deep / "เอกสารงบประมาณประจำปีงบประมาณ ๒๕๖๘.txt"
    assert len(str(target)) > 260, "the fixture must exceed MAX_PATH to be meaningful"
    try:
        # Plain pathlib cannot create this path.  The application's own
        # extended-path helper is what makes long paths work, so the fixture
        # is built with it too.
        pathutil.safe_path(deep).mkdir(parents=True)
        pathutil.safe_path(target).write_text(
            "deep needle_deep งบประมาณ", encoding="utf-8"
        )
    except OSError as exc:
        pytest.skip(f"the filesystem refused the long path: {exc}")

    summary = _index(repos, tmp_path, settings)
    assert summary.indexed >= 1
    record = repos.roots.find_by_path(str(tmp_path))
    service = SearchService(repos)
    response = service.search(SearchRequest(query="needle_deep", root_id=record.id))
    assert response.total_matched_files == 1
    assert "ระดับ0" in response.results[0].relative_path
    assert (
        service.search(
            SearchRequest(
                query="งบประมาณ", root_id=record.id, scope=SearchScope.NAME_ONLY
            )
        ).total_matched_files
        == 1
    )


def test_many_files_performance(repos, tmp_path):
    """A run at roughly the documented target workload."""
    settings = AppSettings(enable_optional_formats=False).normalize()
    root = tmp_path / "bulk"
    root.mkdir()
    for bucket in range(20):
        directory = root / f"folder{bucket:02d}"
        directory.mkdir()
        for index in range(50):
            (directory / f"doc{index:03d}.txt").write_text(
                f"document {bucket}-{index} งบประมาณ ครุภัณฑ์ budget report "
                f"filler line one\nfiller line two with token{bucket}_{index}\n",
                encoding="utf-8",
            )

    start = time.perf_counter()
    summary = _index(repos, root, settings)
    build_seconds = time.perf_counter() - start
    assert summary.status is RunStatus.COMPLETED
    assert summary.indexed == 1000

    record = repos.roots.find_by_path(str(root))
    service = SearchService(repos)
    for query in ("งบประมาณ", "budget report", "token7_13", "ครุภัณฑ์"):
        query_start = time.perf_counter()
        response = service.search(SearchRequest(query=query, root_id=record.id))
        elapsed = time.perf_counter() - query_start
        assert response.total_matched_files > 0
        assert elapsed < 2.0, f"{query!r} took {elapsed:.2f}s"

    # An update with nothing changed must be far cheaper than the build.
    start = time.perf_counter()
    second = _index(repos, root, settings)
    update_seconds = time.perf_counter() - start
    assert second.unchanged == 1000
    assert second.indexed == 0
    assert update_seconds < build_seconds

    print(
        f"\n  1000 files: build {build_seconds:.2f}s, "
        f"no-op update {update_seconds:.2f}s, "
        f"index {repos.db.file_size_bytes() / 1024 / 1024:.1f} MB"
    )


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------
def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(
        language="en",
        max_file_size_mb=250,
        include_hidden_files=True,
        result_limit=500,
        log_file_paths=False,
    )
    settings.remember_root("D:\\Docs")
    assert save_settings(settings, path)

    loaded = load_settings(path)
    assert loaded.language == "en"
    assert loaded.max_file_size_mb == 250
    assert loaded.include_hidden_files
    assert loaded.result_limit == 500
    assert not loaded.log_file_paths
    assert loaded.last_root == "D:\\Docs"
    assert loaded.recent_roots == ["D:\\Docs"]


def test_settings_defaults_on_a_missing_file(tmp_path):
    loaded = load_settings(tmp_path / "absent.json")
    assert loaded.max_file_size_mb == C.DEFAULT_MAX_FILE_SIZE_MB
    assert loaded.recent_roots == []


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        "[]",
        "null",
        '{"max_file_size_mb": "enormous"}',
        '{"language": "klingon", "result_limit": -5}',
        '{"unknown_field": 1}',
        '{"recent_roots": "not-a-list"}',
    ],
)
def test_malformed_settings_degrade_to_defaults(tmp_path, payload):
    """A broken settings file must never stop the application starting."""
    path = tmp_path / "settings.json"
    path.write_text(payload, encoding="utf-8")
    loaded = load_settings(path)
    assert 1 <= loaded.max_file_size_mb <= C.MAX_FILE_SIZE_LIMIT_MB
    assert 10 <= loaded.result_limit <= C.MAX_RESULT_LIMIT
    assert loaded.language in {"th", "en"}
    assert isinstance(loaded.recent_roots, list)


def test_settings_are_written_atomically(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(AppSettings(), path)
    # No temporary artefact is left behind.
    assert not list(tmp_path.glob(".settings-*"))
    assert path.is_file()


def test_recent_roots_are_deduplicated_and_capped():
    settings = AppSettings()
    for index in range(30):
        settings.remember_root(f"D:\\Root{index}")
    settings.remember_root("d:\\root0")  # same path, different case
    settings.normalize()
    assert len(settings.recent_roots) <= 12
    normalized = [pathutil.normalized_path(root) for root in settings.recent_roots]
    assert len(normalized) == len(set(normalized))
    assert settings.recent_roots[0].casefold() == "d:\\root0"


def test_forget_root_updates_last_root():
    settings = AppSettings()
    settings.remember_root("D:\\A")
    settings.remember_root("D:\\B")
    assert settings.last_root == "D:\\B"
    settings.forget_root("D:\\B")
    assert settings.last_root == "D:\\A"
    settings.forget_root("D:\\A")
    assert settings.last_root == ""


def test_window_state_rejects_non_base64():
    settings = AppSettings(window_geometry="<not base64!>").normalize()
    assert settings.window_geometry == ""
    settings = AppSettings(window_geometry="QUJDRA==").normalize()
    assert settings.window_geometry == "QUJDRA=="


def test_active_extensions_follow_the_optional_flag():
    assert AppSettings(enable_optional_formats=False).active_extensions == C.CORE_EXTENSIONS
    assert AppSettings(enable_optional_formats=True).active_extensions == C.SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------
def _probe_lock_from_subprocess(lock_path) -> bool:
    """Try to acquire the lock in a separate process; True if it succeeded.

    A Windows file lock is owned by the process, so a second attempt from the
    *same* process always succeeds.  Only a real subprocess tests what the
    guard is actually for: preventing two application instances from writing
    to one SQLite index.
    """
    import subprocess
    import sys

    script = (
        "import pathlib, sys;"
        "sys.path.insert(0, sys.argv[2]);"
        "from advance_file_search.winplat.single_instance import SingleInstance;"
        "g = SingleInstance(pathlib.Path(sys.argv[1]));"
        "print('ACQUIRED' if g.acquire() else 'REFUSED');"
        "g.release()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(lock_path), str(PROJECT_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return "ACQUIRED" in result.stdout


def test_single_instance_guard(tmp_path):
    from advance_file_search.winplat.single_instance import SingleInstance

    lock = tmp_path / "instance.lock"
    first = SingleInstance(lock)
    assert first.acquire()
    try:
        assert not _probe_lock_from_subprocess(
            lock
        ), "a second process must be refused while the first holds the lock"
    finally:
        first.release()

    # Once the first instance releases it, another process can start.
    assert _probe_lock_from_subprocess(lock)


def test_single_instance_lock_cannot_go_stale(tmp_path):
    """The lock is an OS handle, so a hard kill cannot leave it held."""
    lock = tmp_path / "instance.lock"
    assert _probe_lock_from_subprocess(lock)
    # The probe process has exited; the lock must already be free again.
    assert _probe_lock_from_subprocess(lock)


def test_single_instance_context_manager(tmp_path):
    from advance_file_search.winplat.single_instance import SingleInstance

    lock = tmp_path / "instance.lock"
    with SingleInstance(lock) as guard:
        assert guard.acquired
        assert not _probe_lock_from_subprocess(lock)
    assert _probe_lock_from_subprocess(lock)


def test_single_instance_does_not_block_startup_if_unavailable(tmp_path):
    """A lock we cannot create must not prevent the application running."""
    from advance_file_search.winplat.single_instance import SingleInstance

    blocked = tmp_path / "afile"
    blocked.write_text("x", encoding="utf-8")
    guard = SingleInstance(blocked / "sub" / "instance.lock")
    assert guard.acquire()
    guard.release()


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
def test_search_while_indexing(tmp_path, corpus, settings):
    """WAL journalling must let a reader work while the writer runs."""
    db_path = tmp_path / "index.sqlite3"
    writer_db, _ = open_index(db_path)
    writer_repos = Repositories.create(writer_db)
    _index(writer_repos, corpus, settings)
    root_id = writer_repos.roots.find_by_path(str(corpus)).id

    errors: list[BaseException] = []
    results: list[int] = []
    stop = threading.Event()

    def reader():
        reader_db = None
        try:
            reader_db = type(writer_db)(db_path)
            service = SearchService(Repositories.create(reader_db))
            while not stop.is_set():
                response = service.search(
                    SearchRequest(query="needle", root_id=root_id)
                )
                results.append(response.total_matched_files)
                time.sleep(0.01)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            if reader_db is not None:
                reader_db.close_thread_connection()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for round_number in range(3):
            (corpus / "เอกสาร" / "txt" / f"live{round_number}.txt").write_text(
                f"live update {round_number} needle", encoding="utf-8"
            )
            _index(writer_repos, corpus, settings)
    finally:
        stop.set()
        thread.join(timeout=15)

    assert not errors, f"the reader failed: {errors[0]!r}"
    assert results, "the reader never completed a search"
    assert writer_db.integrity_check()
    writer_db.close()


def test_workers_run_off_the_calling_thread(qapp, tmp_path, corpus, settings):
    """IndexWorker and SearchWorker must each own their own connection."""
    from PySide6.QtCore import QEventLoop, QTimer

    from advance_file_search.ui.workers import IndexWorker, SearchWorker, WorkerHandle

    db_path = tmp_path / "index.sqlite3"
    db, _ = open_index(db_path)
    db.close()

    main_thread = threading.get_ident()
    worker_threads: list[int] = []
    finished: list[object] = []

    # Spying on the coordinator records the thread the work actually ran on,
    # which is the property that matters: the UI thread must never index.
    original_run = IndexCoordinator.run

    def spy(self, root_display):
        worker_threads.append(threading.get_ident())
        return original_run(self, root_display)

    IndexCoordinator.run = spy  # type: ignore[method-assign]
    worker = IndexWorker(str(db_path), str(corpus), settings)
    handle = WorkerHandle(worker)
    worker.finished.connect(finished.append)

    loop = QEventLoop()
    worker.finished.connect(lambda *_: loop.quit())
    worker.failed.connect(lambda *_: loop.quit())
    QTimer.singleShot(120_000, loop.quit)
    handle.start()
    try:
        loop.exec()
    finally:
        handle.stop()
        IndexCoordinator.run = original_run  # type: ignore[method-assign]

    assert finished, "the index worker never reported back"
    assert worker_threads, "the coordinator never ran"
    assert worker_threads[0] != main_thread, "indexing ran on the calling thread"

    # Now a search worker against the same database file.
    db, _ = open_index(db_path)
    repos = Repositories.create(db)
    root = repos.roots.find_by_path(str(corpus))
    assert root is not None
    db.close()

    search_results: list[object] = []
    search_worker = SearchWorker(
        str(db_path), SearchRequest(query="needle", root_id=root.id)
    )
    search_handle = WorkerHandle(search_worker)
    search_worker.finished.connect(search_results.append)
    loop = QEventLoop()
    search_worker.finished.connect(lambda *_: loop.quit())
    search_worker.failed.connect(lambda *_: loop.quit())
    QTimer.singleShot(30_000, loop.quit)
    search_handle.start()
    loop.exec()
    search_handle.stop()

    assert search_results
    assert search_results[0].total_matched_files > 0


def test_index_worker_cancellation(qapp, tmp_path, corpus, settings):
    from PySide6.QtCore import QEventLoop, QTimer

    from advance_file_search.ui.workers import IndexWorker, WorkerHandle

    db_path = tmp_path / "index.sqlite3"
    worker = IndexWorker(str(db_path), str(corpus), settings)
    handle = WorkerHandle(worker)
    outcome: list[object] = []
    worker.finished.connect(outcome.append)

    loop = QEventLoop()
    worker.finished.connect(lambda *_: loop.quit())
    worker.failed.connect(lambda *_: loop.quit())
    handle.start()
    QTimer.singleShot(60, worker.cancel)
    QTimer.singleShot(60_000, loop.quit)
    loop.exec()
    handle.stop()

    assert outcome
    assert outcome[0].status in (RunStatus.CANCELLED, RunStatus.COMPLETED)

    db, _ = open_index(db_path)
    try:
        assert db.integrity_check()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Disk space guard
# ---------------------------------------------------------------------------
def test_index_refuses_to_start_without_disk_space(repos, corpus, settings, monkeypatch):
    monkeypatch.setattr(type(repos.db), "free_space_bytes", lambda self: 1024)
    summary = _index(repos, corpus, settings)
    assert summary.status is RunStatus.FAILED
    assert any(error.error_code == C.ERR_DISK_FULL for error in summary.errors)
