"""Database, migrations and repository behaviour."""

from __future__ import annotations

import sqlite3

import pytest

from advance_file_search.core import constants as C
from advance_file_search.core.models import ContentUnit, IndexSummary, RunStatus
from advance_file_search.storage import database as dbmod
from advance_file_search.storage.database import (
    Database,
    DatabaseCorruptError,
    DatabaseLockedError,
    DiskFullError,
    fts5_available,
)
from advance_file_search.storage.migrations import (
    IncompatibleIndexError,
    get_user_version,
    migrate,
    open_index,
)
from advance_file_search.storage.repositories import FileWrite


# ---------------------------------------------------------------------------
# FTS5 availability
# ---------------------------------------------------------------------------
def test_fts5_is_available():
    """A release blocker if it fails: the whole index depends on FTS5."""
    assert fts5_available()


def test_trigram_tokenizer_is_available(db):
    """Thai search depends on the trigram tokenizer specifically."""
    db.execute("CREATE VIRTUAL TABLE _probe USING fts5(x, tokenize='trigram')")
    db.execute("DROP TABLE _probe")


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
def test_open_index_creates_schema(tmp_path):
    database, result = open_index(tmp_path / "new.sqlite3")
    try:
        assert result.created
        assert result.to_version == C.SCHEMA_VERSION
        assert get_user_version(database) == C.SCHEMA_VERSION
        tables = {
            row[0]
            for row in database.query_all(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
        }
        for expected in (
            "roots",
            "files",
            "content_units",
            "content_fts",
            "name_fts",
            "index_runs",
            "app_meta",
        ):
            assert expected in tables
    finally:
        database.close()


def test_migrate_is_idempotent(db):
    first = migrate(db)
    second = migrate(db)
    assert second.to_version == first.to_version
    assert not second.migrated


def test_newer_schema_is_reported_not_destroyed(tmp_path):
    path = tmp_path / "future.sqlite3"
    database, _ = open_index(path)
    database.connection().execute(f"PRAGMA user_version = {C.SCHEMA_VERSION + 5}")
    database.close()

    database = Database(path)
    try:
        with pytest.raises(IncompatibleIndexError) as excinfo:
            migrate(database)
        assert excinfo.value.found == C.SCHEMA_VERSION + 5
        # The user's data is still there: nothing was deleted.
        assert database.query_one("SELECT count(*) FROM roots") is not None
    finally:
        database.close()


def test_corrupt_database_is_quarantined_not_deleted(tmp_path):
    from advance_file_search.core import paths as pathutil

    path = tmp_path / "broken.sqlite3"
    path.write_bytes(b"this is definitely not a sqlite database" * 40)

    database, result = open_index(path)
    try:
        assert result.created
        assert database.integrity_check()
    finally:
        database.close()

    quarantined = list(pathutil.backups_dir().glob("*corrupt*"))
    assert quarantined, "the damaged file must be preserved, not discarded"


def test_stamping_an_unversioned_database(tmp_path):
    path = tmp_path / "unversioned.sqlite3"
    database, _ = open_index(path)
    database.connection().execute("PRAGMA user_version = 0")
    database.close()

    database = Database(path)
    try:
        result = migrate(database)
        assert result.to_version == C.SCHEMA_VERSION
        assert not result.created
    finally:
        database.close()


# ---------------------------------------------------------------------------
# Pragmas and error classification
# ---------------------------------------------------------------------------
def test_pragmas_are_applied(db):
    assert str(db.query_value("PRAGMA journal_mode")).lower() == "wal"
    assert int(db.query_value("PRAGMA foreign_keys")) == 1
    assert int(db.query_value("PRAGMA secure_delete")) == 1


def test_foreign_keys_cascade_from_roots_to_units(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "a.txt"))
        repos.content.insert_units(file_id, [_unit("hello world")])
    assert repos.content.total_units() == 1
    repos.roots.delete(root.id)
    assert repos.content.total_units() == 0
    assert repos.files.count_for_root(root.id) == 0


def test_error_classification():
    assert isinstance(
        dbmod.classify_sqlite_error(sqlite3.OperationalError("database is locked")),
        DatabaseLockedError,
    )
    assert isinstance(
        dbmod.classify_sqlite_error(sqlite3.DatabaseError("database disk image is malformed")),
        DatabaseCorruptError,
    )
    assert isinstance(
        dbmod.classify_sqlite_error(sqlite3.OperationalError("disk is full")),
        DiskFullError,
    )


def test_load_extension_is_disabled(db):
    conn = db.connection()
    with pytest.raises((sqlite3.OperationalError, AttributeError, sqlite3.DatabaseError)):
        conn.load_extension("anything")


# ---------------------------------------------------------------------------
# Transactions and savepoints
# ---------------------------------------------------------------------------
def test_transaction_rolls_back_on_error(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with pytest.raises(RuntimeError), db.transaction():
        repos.files.upsert(_write(root.id, "a.txt"))
        raise RuntimeError("boom")
    assert repos.files.count_for_root(root.id) == 0


def test_savepoint_isolates_one_file(db, repos):
    """A failure while indexing one file must not lose the others."""
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        repos.files.upsert(_write(root.id, "good1.txt"))
        try:
            with db.savepoint("f1"):
                repos.files.upsert(_write(root.id, "bad.txt"))
                raise ValueError("parser exploded")
        except ValueError:
            pass
        repos.files.upsert(_write(root.id, "good2.txt"))

    names = {
        row[0]
        for row in db.query_all("SELECT file_name FROM files WHERE root_id = ?", (root.id,))
    }
    assert names == {"good1.txt", "good2.txt"}


def test_savepoint_rejects_an_unsafe_name(db):
    with pytest.raises(ValueError), db.savepoint("bad; DROP TABLE files"):
        pass


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------
def test_root_is_deduplicated_case_insensitively(repos):
    first = repos.roots.get_or_create("D:\\Docs")
    second = repos.roots.get_or_create("d:\\docs\\")
    assert first.id == second.id


def test_root_display_path_is_refreshed(repos):
    repos.roots.get_or_create("D:\\Docs")
    updated = repos.roots.get_or_create("D:\\DOCS")
    assert updated.display_path == "D:\\DOCS"


def test_root_run_status_lifecycle(repos):
    root = repos.roots.get_or_create("D:\\Docs")
    repos.roots.mark_run_started(root.id)
    assert repos.roots.get(root.id).last_index_status == RunStatus.RUNNING.value
    repos.roots.mark_run_finished(root.id, RunStatus.COMPLETED, 12)
    reloaded = repos.roots.get(root.id)
    assert reloaded.last_index_status == RunStatus.COMPLETED.value
    assert reloaded.file_count == 12
    assert reloaded.last_index_completed_at


def test_cancelled_run_does_not_set_a_completion_time(repos):
    root = repos.roots.get_or_create("D:\\Docs")
    repos.roots.mark_run_finished(root.id, RunStatus.CANCELLED, 3)
    assert repos.roots.get(root.id).last_index_completed_at is None


def test_clear_content_keeps_the_root_record(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        repos.files.upsert(_write(root.id, "a.txt"))
    repos.roots.clear_content(root.id)
    assert repos.roots.get(root.id) is not None
    assert repos.files.count_for_root(root.id) == 0


def test_empty_root_path_is_refused(repos):
    with pytest.raises(ValueError):
        repos.roots.get_or_create("   ")


# ---------------------------------------------------------------------------
# Files and content
# ---------------------------------------------------------------------------
def test_upsert_replaces_rather_than_duplicating(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        first = repos.files.upsert(_write(root.id, "a.txt", size=10))
    with db.transaction():
        second = repos.files.upsert(_write(root.id, "a.txt", size=20))
    assert first == second
    assert repos.files.count_for_root(root.id) == 1
    assert repos.files.get(first).size_bytes == 20


def test_insert_units_skips_blank_text(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "a.txt"))
        count, chars = repos.content.insert_units(
            file_id, [_unit("real"), _unit("   "), _unit("")]
        )
    assert count == 1
    assert chars == 4


def test_insert_units_caps_text_length(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "a.txt"))
        repos.content.insert_units(
            file_id, [_unit("z" * (C.MAX_UNIT_TEXT_LENGTH + 5000))]
        )
    stored = repos.content.units_for_file(file_id)[0]
    assert len(stored.text) == C.MAX_UNIT_TEXT_LENGTH


def test_units_round_trip_location_data(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    data = {"sheet": "งบประมาณ 2568", "cell": "F12", "row": 12, "column": 6}
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "a.xlsx"))
        repos.content.insert_units(
            file_id,
            [
                ContentUnit(
                    sequence=1,
                    location_type=C.LOC_SHEET_CELL,
                    location_label="Sheet: งบประมาณ 2568, Cell: F12",
                    location_data=data,
                    text="ครุภัณฑ์",
                )
            ],
        )
    stored = repos.content.units_for_file(file_id)[0]
    assert stored.location_data == data


def test_malformed_location_json_degrades_to_empty(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "a.txt"))
        repos.content.insert_units(file_id, [_unit("text")])
    db.execute("UPDATE content_units SET location_json = 'not json' WHERE file_id = ?", (file_id,))
    assert repos.content.units_for_file(file_id)[0].location_data == {}


def test_delete_units_removes_fts_rows(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "a.txt"))
        repos.content.insert_units(file_id, [_unit("findable content")])
    assert _fts_count(db, "findable") == 1
    repos.files.delete_units(file_id)
    assert _fts_count(db, "findable") == 0


def test_delete_file_removes_fts_name_rows(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "uniquename.txt"))
    assert _name_fts_count(db, "uniquename") == 1
    repos.files.delete_file(file_id)
    assert _name_fts_count(db, "uniquename") == 0


def test_stale_paths_finds_files_not_seen_in_a_run(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        old = repos.files.upsert(_write(root.id, "old.txt", run_id=1))
        repos.files.upsert(_write(root.id, "new.txt", run_id=2))
    stale = repos.files.stale_paths(root.id, 2)
    assert [file_id for file_id, _ in stale] == [old]


def test_status_and_extension_summaries(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        repos.files.upsert(_write(root.id, "a.txt", status=C.STATUS_INDEXED))
        repos.files.upsert(_write(root.id, "b.pdf", status=C.STATUS_NO_TEXT))
        repos.files.upsert(_write(root.id, "c.pdf", status=C.STATUS_FAILED))
    assert repos.files.status_counts(root.id) == {
        C.STATUS_INDEXED: 1,
        C.STATUS_NO_TEXT: 1,
        C.STATUS_FAILED: 1,
    }
    assert dict(repos.files.extensions_for_root(root.id)) == {".txt": 1, ".pdf": 2}


# ---------------------------------------------------------------------------
# Index runs
# ---------------------------------------------------------------------------
def test_run_lifecycle(repos):
    root = repos.roots.get_or_create("D:\\Docs")
    run_id = repos.runs.start(root.id, "full")
    summary = IndexSummary(
        run_id=run_id,
        root_id=root.id,
        status=RunStatus.COMPLETED,
        discovered=10,
        indexed=8,
        failed=1,
        elapsed_seconds=1.25,
    )
    repos.runs.finish(run_id, summary)
    row = repos.runs.latest_for_root(root.id)
    assert row["status"] == RunStatus.COMPLETED.value
    assert row["files_indexed"] == 8
    assert row["mode"] == "full"
    assert row["application_version"] == C.APP_VERSION


def test_interrupted_runs_are_reported_as_failed(repos):
    """A crash mid-index must not leave the UI claiming it is still running."""
    root = repos.roots.get_or_create("D:\\Docs")
    repos.runs.start(root.id)
    repos.roots.mark_run_started(root.id)
    assert repos.runs.abandon_running() == 1
    assert repos.runs.latest_for_root(root.id)["status"] == RunStatus.FAILED.value
    assert repos.roots.get(root.id).last_index_status == RunStatus.FAILED.value


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
def test_integrity_check_and_optimize(db, repos):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        file_id = repos.files.upsert(_write(root.id, "a.txt"))
        repos.content.insert_units(file_id, [_unit("content")])
    db.optimize()
    assert db.integrity_check()


def test_backup_creates_a_usable_copy(db, repos, tmp_path):
    root = repos.roots.get_or_create("D:\\Docs")
    with db.transaction():
        repos.files.upsert(_write(root.id, "a.txt"))
    target = tmp_path / "backup.sqlite3"
    assert db.backup_to(target)
    copy = Database(target)
    try:
        assert copy.query_value("SELECT count(*) FROM files") == 1
    finally:
        copy.close()


def test_app_meta_round_trip(db):
    db.set_meta("probe", "value")
    assert db.get_meta("probe") == "value"
    db.set_meta("probe", "updated")
    assert db.get_meta("probe") == "updated"
    assert db.get_meta("absent", "fallback") == "fallback"


def test_closed_database_refuses_new_connections(tmp_path):
    database = Database(tmp_path / "x.sqlite3")
    database.connection()
    database.close()
    database._local = type(database._local)()  # simulate a fresh thread
    with pytest.raises(dbmod.DatabaseError):
        database.connection()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _write(root_id: int, name: str, *, size: int = 100, status: str = C.STATUS_INDEXED,
           run_id: int | None = None) -> FileWrite:
    from advance_file_search.core import paths as pathutil

    display = f"D:\\Docs\\{name}"
    return FileWrite(
        root_id=root_id,
        display_path=display,
        normalized_path=pathutil.normalized_path(display),
        relative_path=name,
        file_name=name,
        extension=pathutil.extension_of(name),
        size_bytes=size,
        created_time=1.0,
        modified_time=2.0,
        fingerprint=f"{size}:2000:1",
        content_status=status,
        run_id=run_id,
    )


def _unit(text: str, sequence: int = 1) -> ContentUnit:
    return ContentUnit(
        sequence=sequence,
        location_type=C.LOC_LINE,
        location_label=f"Line {sequence}",
        location_data={"line": sequence},
        text=text,
    )


def _fts_count(db: Database, term: str) -> int:
    return int(
        db.query_value(
            "SELECT count(*) FROM content_fts WHERE content_fts MATCH ?", (f'"{term}"',)
        )
    )


def _name_fts_count(db: Database, term: str) -> int:
    return int(
        db.query_value(
            "SELECT count(*) FROM name_fts WHERE name_fts MATCH ?", (f'"{term}"',)
        )
    )
