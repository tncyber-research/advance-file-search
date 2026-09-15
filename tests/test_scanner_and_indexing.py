"""Scanner exclusions, fingerprinting and the incremental index lifecycle."""

from __future__ import annotations

import os
import threading
import time

import pytest

from advance_file_search.core import constants as C
from advance_file_search.core.models import RunStatus, SkipReason
from advance_file_search.indexing import fingerprint as fp
from advance_file_search.indexing.coordinator import (
    IndexCoordinator,
    IndexOptions,
    delete_index_for_root,
)
from advance_file_search.indexing.scanner import FileScanner, ScanOptions


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------
def test_fingerprint_round_trip():
    value = fp.make_fingerprint(1234, 1700000000.5)
    size, mtime, parser = fp.parse_fingerprint(value)
    assert size == 1234
    assert abs(mtime - 1700000000.5) < 0.002
    assert parser == C.PARSER_VERSION


def test_parse_fingerprint_rejects_garbage():
    assert fp.parse_fingerprint("") is None
    assert fp.parse_fingerprint("nonsense") is None
    assert fp.parse_fingerprint("a:b:c") is None
    assert fp.parse_fingerprint("1:2") is None


def test_unchanged_detection():
    value = fp.make_fingerprint(100, 1000.0)
    assert fp.is_unchanged(value, 100, 1000.0)
    # Filesystem timestamp granularity must not report a false change.
    assert fp.is_unchanged(value, 100, 1000.0 + fp.MTIME_EPSILON / 2)


def test_changed_size_or_time_is_detected():
    value = fp.make_fingerprint(100, 1000.0)
    assert not fp.is_unchanged(value, 101, 1000.0)
    assert not fp.is_unchanged(value, 100, 2000.0)


def test_parser_version_bump_forces_reextraction():
    """Shipping a better parser must re-read affected documents."""
    value = fp.make_fingerprint(100, 1000.0, parser_version=1)
    assert fp.is_unchanged(value, 100, 1000.0, parser_version=1)
    assert not fp.is_unchanged(value, 100, 1000.0, parser_version=2)


def test_content_hashes(tmp_path):
    target = tmp_path / "a.bin"
    target.write_bytes(b"x" * 5000)
    fast = fp.fast_content_hash(target)
    strong = fp.sha256_hash(target)
    assert fast.startswith("fast:")
    assert strong.startswith("sha256:")
    assert fp.fast_content_hash(target) == fast

    target.write_bytes(b"y" * 5000)
    assert fp.fast_content_hash(target) != fast
    assert fp.sha256_hash(target) != strong


def test_hash_of_a_missing_file_is_empty(tmp_path):
    assert fp.fast_content_hash(tmp_path / "nope") == ""
    assert fp.sha256_hash(tmp_path / "nope") == ""


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------
def test_scanner_finds_supported_files_recursively(tmp_path):
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub" / "deep" / "c.txt").write_text("x", encoding="utf-8")

    found = list(FileScanner(ScanOptions()).scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"a.txt", "b.txt", "c.txt"}
    assert {f.relative_path for f in found} == {
        "a.txt",
        "sub\\b.txt",
        "sub\\deep\\c.txt",
    }


def test_scanner_skips_unsupported_and_executable_files(tmp_path):
    for name in ("keep.txt", "skip.zip", "danger.exe", "run.bat", "macro.docm"):
        (tmp_path / name).write_bytes(b"data")
    scanner = FileScanner(ScanOptions())
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"keep.txt"}
    assert scanner.stats.skips[SkipReason.EXECUTABLE.value] == 3


def test_scanner_skips_office_lock_files(tmp_path):
    (tmp_path / "report.docx").write_bytes(b"data")
    (tmp_path / "~$report.docx").write_bytes(b"data")
    scanner = FileScanner(ScanOptions())
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"report.docx"}
    assert scanner.stats.skips[SkipReason.TEMP_FILE.value] == 1


def test_scanner_skips_empty_files(tmp_path):
    (tmp_path / "empty.txt").write_bytes(b"")
    scanner = FileScanner(ScanOptions())
    assert not list(scanner.scan(str(tmp_path)))
    assert scanner.stats.skips[SkipReason.EMPTY.value] == 1


def test_scanner_respects_the_size_limit(tmp_path):
    (tmp_path / "big.txt").write_bytes(b"x" * 5000)
    (tmp_path / "small.txt").write_bytes(b"x" * 10)
    scanner = FileScanner(ScanOptions(max_file_size_bytes=1000))
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"small.txt"}
    assert scanner.stats.skips[SkipReason.TOO_LARGE.value] == 1


def test_scanner_skips_excluded_directory_names(tmp_path):
    for name in ("$RECYCLE.BIN", "System Volume Information", "node_modules"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "hidden.txt").write_text("x", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    scanner = FileScanner(ScanOptions())
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"ok.txt"}
    assert scanner.stats.skips[SkipReason.EXCLUDED_DIR.value] == 3


def test_scanner_skips_the_application_data_directory(tmp_path, monkeypatch):
    from advance_file_search.core import paths as pathutil

    data_dir = tmp_path / "AppData"
    (data_dir / "index").mkdir(parents=True)
    (data_dir / "index" / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(pathutil, "app_data_dir", lambda: data_dir)

    scanner = FileScanner(ScanOptions())
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"ok.txt"}
    assert scanner.stats.skips[SkipReason.APP_DATA.value] >= 1


def test_scanner_extra_exclusions(tmp_path):
    from advance_file_search.core import paths as pathutil

    excluded = tmp_path / "private"
    excluded.mkdir()
    (excluded / "secret.txt").write_text("x", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    scanner = FileScanner(
        ScanOptions(
            extra_excluded_dirs=frozenset({pathutil.normalized_path(str(excluded))})
        )
    )
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"ok.txt"}


@pytest.mark.skipif(os.name != "nt", reason="Windows attributes")
def test_scanner_skips_hidden_files_by_default(tmp_path):
    import ctypes

    hidden = tmp_path / "hidden.txt"
    hidden.write_text("x", encoding="utf-8")
    visible = tmp_path / "visible.txt"
    visible.write_text("x", encoding="utf-8")
    if not ctypes.windll.kernel32.SetFileAttributesW(str(hidden), 0x2):
        pytest.skip("could not set the hidden attribute")

    assert {f.file_name for f in FileScanner(ScanOptions()).scan(str(tmp_path))} == {
        "visible.txt"
    }
    both = FileScanner(ScanOptions(include_hidden_files=True)).scan(str(tmp_path))
    assert {f.file_name for f in both} == {"hidden.txt", "visible.txt"}


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions")
def test_scanner_does_not_follow_a_directory_junction(tmp_path):
    """A junction loop must not make the scan recurse forever."""
    import subprocess

    real = tmp_path / "real"
    real.mkdir()
    (real / "inside.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "loop"
    try:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(tmp_path)],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        pytest.skip("mklink is unavailable")

    scanner = FileScanner(ScanOptions())
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"inside.txt"}
    assert scanner.stats.reparse_points_skipped >= 1


def test_scanner_cancellation_stops_the_walk(tmp_path):
    for index in range(300):
        (tmp_path / f"f{index}.txt").write_text("x", encoding="utf-8")
    cancel = threading.Event()
    scanner = FileScanner(ScanOptions())
    collected = []
    for candidate in scanner.scan(str(tmp_path), cancel=cancel):
        collected.append(candidate)
        if len(collected) == 5:
            cancel.set()
    assert len(collected) <= 20  # stops promptly, not after all 300


def test_scanner_handles_a_missing_root(tmp_path):
    assert not list(FileScanner(ScanOptions()).scan(str(tmp_path / "nope")))


def test_scanner_tolerates_a_file_vanishing_midway(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")

    original = os.DirEntry.stat

    def flaky(self, *, follow_symlinks=True):
        if self.name == "a.txt":
            raise FileNotFoundError(self.path)
        return original(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os.DirEntry, "stat", flaky, raising=False)
    scanner = FileScanner(ScanOptions())
    found = list(scanner.scan(str(tmp_path)))
    assert {f.file_name for f in found} == {"b.txt"}
    assert scanner.stats.vanished >= 1


def test_scanner_thai_names_and_metadata(tmp_path):
    target = tmp_path / "งบประมาณ ๒๕๖๘.txt"
    target.write_text("content", encoding="utf-8")
    found = list(FileScanner(ScanOptions()).scan(str(tmp_path)))
    assert len(found) == 1
    entry = found[0]
    assert entry.file_name == "งบประมาณ ๒๕๖๘.txt"
    assert entry.extension == ".txt"
    assert entry.size_bytes == 7
    assert entry.modified_time > 0
    assert entry.normalized_path == entry.normalized_path.casefold()


def test_scanner_optional_formats_are_opt_in(tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    core = FileScanner(ScanOptions(extensions=C.CORE_EXTENSIONS))
    assert {f.file_name for f in core.scan(str(tmp_path))} == {"b.txt"}
    extended = FileScanner(ScanOptions(extensions=C.SUPPORTED_EXTENSIONS))
    assert {f.file_name for f in extended.scan(str(tmp_path))} == {"a.md", "b.txt"}


# ---------------------------------------------------------------------------
# Coordinator: first run
# ---------------------------------------------------------------------------
def test_first_index_run(repos, corpus, settings):
    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    assert summary.status is RunStatus.COMPLETED
    assert summary.discovered > 0
    assert summary.indexed > 0
    assert summary.unchanged == 0
    # Corrupt and password-protected fixtures are recorded, not fatal.
    assert summary.failed > 0
    assert summary.no_text > 0
    assert summary.errors


def test_index_records_status_per_file(repos, indexed_corpus):
    root, _summary = indexed_corpus
    counts = repos.files.status_counts(root.id)
    assert counts.get(C.STATUS_INDEXED, 0) > 0
    assert counts.get(C.STATUS_NO_TEXT, 0) > 0
    assert counts.get(C.STATUS_FAILED, 0) > 0


def test_index_refuses_a_network_path(repos, settings):
    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(
        "\\\\server\\share"
    )
    assert summary.status is RunStatus.FAILED
    assert not repos.roots.list_all()


def test_index_refuses_a_url(repos, settings):
    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(
        "https://example.com/docs"
    )
    assert summary.status is RunStatus.FAILED


def test_index_refuses_a_missing_root(repos, settings, tmp_path):
    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(
        str(tmp_path / "absent")
    )
    assert summary.status is RunStatus.FAILED


def test_executables_never_enter_the_index(repos, indexed_corpus):
    root, _ = indexed_corpus
    extensions = dict(repos.files.extensions_for_root(root.id))
    for forbidden in (".exe", ".bat", ".docm", ".lnk"):
        assert forbidden not in extensions


def test_lock_files_never_enter_the_index(repos, indexed_corpus, db):
    root, _ = indexed_corpus
    assert (
        db.query_value(
            "SELECT count(*) FROM files WHERE root_id = ? AND file_name LIKE '~$%'",
            (root.id,),
        )
        == 0
    )


# ---------------------------------------------------------------------------
# Coordinator: incremental update
# ---------------------------------------------------------------------------
def test_second_run_skips_unchanged_files(repos, corpus, settings, indexed_corpus):
    _root, first = indexed_corpus
    second = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    assert second.status is RunStatus.COMPLETED
    assert second.unchanged > 0
    assert second.indexed == 0
    assert second.discovered == first.discovered


def test_new_file_is_added(repos, corpus, settings, indexed_corpus, search_service):
    root, _ = indexed_corpus
    (corpus / "เอกสาร" / "txt" / "added.txt").write_text(
        "brand new needle_added ไฟล์ใหม่", encoding="utf-8"
    )
    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    assert summary.indexed == 1
    assert _search_count(search_service, root.id, "needle_added") == 1


def test_modified_file_is_reindexed(repos, corpus, settings, indexed_corpus, search_service):
    root, _ = indexed_corpus
    target = corpus / "เอกสาร" / "txt" / "utf8_thai.txt"
    assert _search_count(search_service, root.id, "งบประมาณ") > 0
    time.sleep(0.01)
    target.write_text("replaced needle_modified", encoding="utf-8")

    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    assert summary.indexed == 1
    assert _search_count(search_service, root.id, "needle_modified") == 1
    # The old content is gone, not merely shadowed.
    response = search_service.search(_request(root.id, "งบประมาณ"))
    assert all(r.file_name != "utf8_thai.txt" for r in response.results)


def test_deleted_file_is_removed(repos, corpus, settings, indexed_corpus, search_service, db):
    root, _ = indexed_corpus
    (corpus / "เอกสาร" / "txt" / "table.csv").unlink()
    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    assert summary.deleted == 1
    assert (
        db.query_value(
            "SELECT count(*) FROM files WHERE root_id = ? AND file_name = 'table.csv'",
            (root.id,),
        )
        == 0
    )


def test_renamed_file_becomes_delete_plus_add(repos, corpus, settings, indexed_corpus, db):
    root, _ = indexed_corpus
    source = corpus / "เอกสาร" / "txt" / "utf8_thai.txt"
    source.rename(source.with_name("renamed_ไฟล์.txt"))
    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    assert summary.indexed == 1
    assert summary.deleted == 1
    names = {
        row[0]
        for row in db.query_all("SELECT file_name FROM files WHERE root_id = ?", (root.id,))
    }
    assert "renamed_ไฟล์.txt" in names
    assert "utf8_thai.txt" not in names


def test_no_orphan_units_after_updates(repos, corpus, settings, indexed_corpus, db):
    root, _ = indexed_corpus
    target = corpus / "เอกสาร" / "txt" / "utf8_thai.txt"
    for round_number in range(3):
        target.write_text(f"round {round_number} content", encoding="utf-8")
        time.sleep(0.01)
        IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    orphans = db.query_value(
        "SELECT count(*) FROM content_units cu "
        "LEFT JOIN files f ON f.id = cu.file_id WHERE f.id IS NULL"
    )
    assert orphans == 0
    # The FTS index must not accumulate stale rows either.
    fts_rows = db.query_value("SELECT count(*) FROM content_fts")
    unit_rows = db.query_value("SELECT count(*) FROM content_units")
    assert fts_rows == unit_rows
    del root


# ---------------------------------------------------------------------------
# Coordinator: cancellation and rebuild
# ---------------------------------------------------------------------------
def test_cancellation_preserves_previously_indexed_data(repos, corpus, settings):
    """Cancelling must never shrink or corrupt the index."""
    first = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    root = repos.roots.find_by_path(str(corpus))
    before = repos.files.count_for_root(root.id)
    assert before > 0

    cancel = threading.Event()
    cancel.set()  # cancelled before it starts
    coordinator = IndexCoordinator(
        repos, IndexOptions(settings=settings), cancel_event=cancel
    )
    summary = coordinator.run(str(corpus))
    assert summary.status is RunStatus.CANCELLED
    assert repos.files.count_for_root(root.id) == before
    assert repos.db.integrity_check()
    del first


def test_cancellation_midway_keeps_the_index_searchable(
    repos, corpus, settings, search_service
):
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    root = repos.roots.find_by_path(str(corpus))
    before = repos.files.count_for_root(root.id)

    cancel = threading.Event()
    coordinator = IndexCoordinator(
        repos, IndexOptions(rebuild=False, settings=settings), cancel_event=cancel
    )
    progressed = {"n": 0}

    def on_progress(progress):
        progressed["n"] = progress.processed
        if progress.processed >= 3:
            cancel.set()

    coordinator.on_progress = on_progress
    summary = coordinator.run(str(corpus))
    assert summary.status is RunStatus.CANCELLED
    # Cancelled runs never delete entries, so nothing was lost.
    assert repos.files.count_for_root(root.id) == before
    assert _search_count(search_service, root.id, "needle") > 0
    assert repos.db.integrity_check()


def test_cancelled_run_does_not_delete_missing_files(repos, corpus, settings):
    """Deleted-file cleanup must only run after a complete scan."""
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    root = repos.roots.find_by_path(str(corpus))
    before = repos.files.count_for_root(root.id)

    # Remove a file, then cancel the update before the scan finishes.
    (corpus / "เอกสาร" / "txt" / "table.csv").unlink()
    cancel = threading.Event()
    coordinator = IndexCoordinator(
        repos, IndexOptions(settings=settings), cancel_event=cancel
    )
    coordinator.on_progress = lambda p: cancel.set() if p.processed >= 2 else None
    summary = coordinator.run(str(corpus))
    assert summary.status is RunStatus.CANCELLED
    assert summary.deleted == 0
    assert repos.files.count_for_root(root.id) == before


def test_rebuild_reextracts_everything(repos, corpus, settings, indexed_corpus):
    _root, first = indexed_corpus
    summary = IndexCoordinator(
        repos, IndexOptions(rebuild=True, settings=settings)
    ).run(str(corpus))
    assert summary.status is RunStatus.COMPLETED
    assert summary.unchanged == 0
    assert summary.indexed == first.indexed


def test_delete_index_for_root(repos, corpus, indexed_corpus, db):
    root, _ = indexed_corpus
    assert delete_index_for_root(repos, str(corpus))
    assert repos.roots.find_by_path(str(corpus)) is None
    assert db.query_value("SELECT count(*) FROM files WHERE root_id = ?", (root.id,)) == 0
    assert not delete_index_for_root(repos, str(corpus))


def test_index_survives_a_file_disappearing_between_scan_and_read(
    repos, tmp_path, settings
):
    doomed = tmp_path / "doomed.txt"
    doomed.write_text("content", encoding="utf-8")
    (tmp_path / "survivor.txt").write_text("kept needle", encoding="utf-8")

    coordinator = IndexCoordinator(repos, IndexOptions(settings=settings))
    registry = coordinator.registry
    original = registry.get(".txt").parse

    def vanishing(path):
        if str(path).endswith("doomed.txt"):
            try:
                os.unlink(path)
            except OSError:
                pass
        return original(path)

    registry.get(".txt").parse = vanishing  # type: ignore[method-assign]
    try:
        summary = coordinator.run(str(tmp_path))
    finally:
        registry.get(".txt").parse = original  # type: ignore[method-assign]

    assert summary.status is RunStatus.COMPLETED
    root = repos.roots.find_by_path(str(tmp_path))
    names = {
        row[0]
        for row in repos.db.query_all(
            "SELECT file_name FROM files WHERE root_id = ?", (root.id,)
        )
    }
    assert "survivor.txt" in names


def test_progress_reports_are_emitted(repos, corpus, settings):
    seen = []
    coordinator = IndexCoordinator(
        repos, IndexOptions(settings=settings), on_progress=seen.append
    )
    coordinator.run(str(corpus))
    assert seen
    phases = {snapshot.phase for snapshot in seen}
    assert len(phases) > 1
    # Progress snapshots must be copies, not a shared mutating object.
    assert len({id(snapshot) for snapshot in seen}) == len(seen)


def test_progress_current_item_is_relative_not_absolute(repos, corpus, settings):
    """Privacy: the progress line must not reveal a full path."""
    items = []

    def collect(progress):
        if progress.current_item:
            items.append(progress.current_item)

    IndexCoordinator(
        repos, IndexOptions(settings=settings), on_progress=collect
    ).run(str(corpus))
    assert items
    assert all(":" not in item for item in items)
    assert all(not item.startswith("\\\\") for item in items)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _request(root_id: int, query: str):
    from advance_file_search.core.models import SearchRequest

    return SearchRequest(query=query, root_id=root_id)


def _search_count(service, root_id: int, query: str) -> int:
    return service.search(_request(root_id, query)).total_matched_files
