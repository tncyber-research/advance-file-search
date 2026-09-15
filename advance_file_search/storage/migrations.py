"""Explicit, versioned schema migrations.

Rules (section 13.2 of the handoff):

* Schema versions are explicit integers stored in ``PRAGMA user_version``.
* The database is backed up before any destructive migration.
* A user's index is never silently deleted; an incompatible index is reported
  so the UI can offer an explicit Rebuild Index action.
* Interrupted migrations are safe: each step runs in a single transaction and
  the version bump is part of that transaction.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.logging_setup import get_logger
from advance_file_search.storage.database import (
    Database,
    DatabaseCorruptError,
    DatabaseError,
    classify_sqlite_error,
    fts5_available,
    read_schema_sql,
    utc_now,
)

log = get_logger("storage.migrations")


class MigrationError(DatabaseError):
    """A migration could not be applied."""


class IncompatibleIndexError(DatabaseError):
    """The index was written by a newer application version."""

    def __init__(self, found: int, expected: int) -> None:
        super().__init__(
            f"Index schema version {found} is newer than supported version {expected}"
        )
        self.found = found
        self.expected = expected


@dataclass(frozen=True)
class MigrationResult:
    from_version: int
    to_version: int
    created: bool
    backup_path: Path | None = None

    @property
    def migrated(self) -> bool:
        return self.from_version != self.to_version and not self.created


def get_user_version(db: Database) -> int:
    row = db.query_one("PRAGMA user_version")
    return int(row[0]) if row else 0


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    # PRAGMA cannot be parameterized; the value is a validated internal int.
    if not isinstance(version, int) or not 0 <= version <= 100_000:
        raise MigrationError("Invalid schema version")
    conn.execute(f"PRAGMA user_version = {version:d}")


def _create_schema(db: Database) -> None:
    """Apply the base DDL, then stamp the version.

    ``executescript`` implicitly commits, so the DDL cannot share a
    transaction with the version bump.  Every statement in ``schema.sql`` is
    ``IF NOT EXISTS``, so the script is idempotent: an interrupted create
    leaves ``user_version`` at 0 and the next launch simply re-runs it.
    """
    conn = db.connection()
    script = read_schema_sql()
    try:
        conn.executescript(script)
    except sqlite3.Error as exc:
        raise classify_sqlite_error(exc) from exc
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_user_version(conn, C.SCHEMA_VERSION)
        for key, value in (
            ("created_at", utc_now()),
            ("created_by_version", C.APP_VERSION),
        ):
            conn.execute(
                "INSERT INTO app_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO NOTHING",
                (key, value),
            )
        conn.execute(
            "INSERT INTO app_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("last_opened_by_version", C.APP_VERSION),
        )
        conn.execute("COMMIT")
    except sqlite3.Error as exc:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise classify_sqlite_error(exc) from exc


def _database_is_empty(db: Database) -> bool:
    row = db.query_one(
        "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'roots'"
    )
    return not (row and int(row[0]) > 0)


def backup_database(db: Database, *, tag: str = "premigration") -> Path | None:
    """Snapshot the index before a risky operation."""
    if str(db.path) == ":memory:":
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = pathutil.backups_dir() / f"{db.path.stem}-{tag}-{stamp}{db.path.suffix}"
    if db.backup_to(target):
        _prune_backups(target.parent, keep=5)
        return target
    return None


def _prune_backups(directory: Path, *, keep: int) -> None:
    """Keep only the newest ``keep`` pre-migration backups."""
    try:
        entries = sorted(
            (p for p in directory.glob("*-premigration-*.sqlite3") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for stale in entries[keep:]:
        try:
            stale.unlink()
        except OSError:
            continue


# ---------------------------------------------------------------------------
# Migration steps
# ---------------------------------------------------------------------------
#: Maps a starting version to the callable that upgrades it by one step.
#: Version 1 is the initial schema, so there are no steps yet.  Future steps
#: are registered here and must be idempotent within their transaction.
MIGRATION_STEPS: dict[int, Callable[[sqlite3.Connection], None]] = {}


def migrate(db: Database) -> MigrationResult:
    """Bring the database up to :data:`constants.SCHEMA_VERSION`.

    Raises :class:`IncompatibleIndexError` if the file was written by a newer
    application, and :class:`DatabaseCorruptError` if FTS5 is unavailable or
    the required tables are missing and cannot be created.
    """
    if not fts5_available(db.connection()):
        raise DatabaseCorruptError(
            "The bundled SQLite build does not support FTS5, which is required."
        )

    version = get_user_version(db)
    empty = _database_is_empty(db)

    if empty:
        _create_schema(db)
        log.info("created index schema | version=%d", C.SCHEMA_VERSION)
        return MigrationResult(from_version=0, to_version=C.SCHEMA_VERSION, created=True)

    if version == 0:
        # Tables exist but the version marker is missing: an older build or an
        # interrupted create.  Re-run the idempotent DDL and stamp the version.
        _create_schema(db)
        version = C.SCHEMA_VERSION
        log.info("stamped existing index | version=%d", version)
        return MigrationResult(from_version=0, to_version=version, created=False)

    if version > C.SCHEMA_VERSION:
        raise IncompatibleIndexError(version, C.SCHEMA_VERSION)

    if version == C.SCHEMA_VERSION:
        return MigrationResult(from_version=version, to_version=version, created=False)

    backup = backup_database(db)
    start = version
    conn = db.connection()
    while version < C.SCHEMA_VERSION:
        step = MIGRATION_STEPS.get(version)
        if step is None:
            raise MigrationError(f"No migration registered from version {version}")
        try:
            conn.execute("BEGIN IMMEDIATE")
            step(conn)
            _set_user_version(conn, version + 1)
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise MigrationError(
                f"Migration from version {version} failed: {exc}"
            ) from exc
        version += 1
        log.info("applied migration | to_version=%d", version)

    return MigrationResult(
        from_version=start, to_version=version, created=False, backup_path=backup
    )


def open_index(path: Path | str | None = None) -> tuple[Database, MigrationResult]:
    """Open (creating if needed) the index database and migrate it.

    If the file is damaged it is quarantined under ``backups\\`` and a fresh
    index is created, so the application always starts.
    """
    from advance_file_search.storage.database import quarantine_corrupt_database

    db = Database(path)
    try:
        result = migrate(db)
        return db, result
    except DatabaseCorruptError:
        db.close()
        target = Path(path) if path is not None else pathutil.database_path()
        if str(target) != ":memory:":
            quarantine_corrupt_database(target)
        db = Database(path)
        result = migrate(db)
        return db, result
