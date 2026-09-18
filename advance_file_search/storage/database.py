"""SQLite connection management.

Design notes
------------
* One database file holds every indexed root (see
  ``docs/decisions/0002-database-design.md``).
* Each thread gets its own connection; SQLite objects are not shared.
* WAL journaling lets the UI keep searching while the indexer writes.
* ``PRAGMA foreign_keys = ON`` so deleting a root cascades to its files and
  content units.
* Every query in the codebase is parameterized; this module offers no way to
  run a string-built statement.
"""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from advance_file_search.core import paths as pathutil
from advance_file_search.logging_setup import get_logger

log = get_logger("storage.database")

_SCHEMA_FILE = Path(__file__).with_name("schema.sql")

#: How long SQLite waits for a competing writer before raising "locked".
BUSY_TIMEOUT_MS = 15_000


class DatabaseError(RuntimeError):
    """Raised for unrecoverable database problems."""


class DatabaseTransientError(DatabaseError):
    """A failure that is expected to succeed on a retry.

    These arise from concurrency rather than from anything being wrong: the
    writer holds a lock for a moment, or SQLite has to re-prepare a statement
    because the schema cookie moved while an FTS5 optimize ran.  Searching now
    overlaps indexing by design, so these have to be handled rather than
    surfaced to the user as an error.
    """


class DatabaseLockedError(DatabaseTransientError):
    """The database is held by another writer."""


class DatabaseCorruptError(DatabaseError):
    """The database file failed to open or failed an integrity check."""


class DiskFullError(DatabaseError):
    """The volume holding the index is out of space."""


def utc_now() -> str:
    """Timestamps are stored as unambiguous ISO-8601 UTC strings."""
    return datetime.now(UTC).isoformat(timespec="seconds")


#: Message fragments that mark a failure as worth retrying.
_TRANSIENT_FRAGMENTS = (
    "locked",
    "busy",
    # Raised when SQLite re-prepares a statement against an FTS5 table whose
    # schema cookie moved — for example while the indexer runs an optimize.
    "vtable constructor failed",
    "database schema has changed",
)


def classify_sqlite_error(exc: sqlite3.Error) -> DatabaseError:
    """Map a raw sqlite3 error onto an actionable application error."""
    text = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError):
        if "locked" in text or "busy" in text:
            return DatabaseLockedError(str(exc))
        if "disk" in text and "full" in text:
            return DiskFullError(str(exc))
        if any(fragment in text for fragment in _TRANSIENT_FRAGMENTS):
            return DatabaseTransientError(str(exc))
        if "readonly" in text or "attempt to write" in text:
            return DatabaseError(str(exc))
    if isinstance(exc, sqlite3.DatabaseError) and (
        "malformed" in text or "not a database" in text or "corrupt" in text
    ):
        return DatabaseCorruptError(str(exc))
    if "full" in text and "disk" in text:
        return DiskFullError(str(exc))
    return DatabaseError(str(exc))


def fts5_available(connection: sqlite3.Connection | None = None) -> bool:
    """Verify that the bundled SQLite build has FTS5 compiled in."""
    own = connection is None
    conn = connection or sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts5_probe")
        return True
    except sqlite3.Error:
        return False
    finally:
        if own:
            conn.close()


class Database:
    """Thread-aware SQLite wrapper for the search index.

    A single instance is shared by the whole application; it hands out one
    connection per thread via :meth:`connection`.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else pathutil.database_path()
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._connections: list[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()
        self._closed = False

    # -- lifecycle --------------------------------------------------------
    def connection(self) -> sqlite3.Connection:
        """Return this thread's connection, creating it on first use."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        if self._closed:
            raise DatabaseError("Database has been closed")
        if str(self.path) != ":memory:":
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DatabaseError(f"Cannot create index directory: {exc}") from exc
        try:
            conn = sqlite3.connect(
                str(self.path),
                timeout=BUSY_TIMEOUT_MS / 1000,
                isolation_level=None,  # explicit transaction control
                check_same_thread=True,
            )
        except sqlite3.Error as exc:
            raise classify_sqlite_error(exc) from exc
        conn.row_factory = sqlite3.Row
        try:
            self._apply_pragmas(conn)
        except BaseException:
            # A damaged file fails here (the first PRAGMA touches the header).
            # The connection is not registered yet, so close it explicitly or
            # it keeps an OS handle on the file and the caller cannot move the
            # damaged index aside.
            with suppress(sqlite3.Error):
                conn.close()
            raise
        self._local.conn = conn
        with self._connections_lock:
            self._connections.append(conn)
        return conn

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys = ON")
            if str(self.path) != ":memory:":
                cursor.execute("PRAGMA journal_mode = WAL")
            # NORMAL is the right trade-off under WAL: a power loss can lose
            # the most recent commits but cannot corrupt the database, and the
            # index is always rebuildable from the user's documents.
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA temp_store = MEMORY")
            cursor.execute("PRAGMA cache_size = -20000")  # ~20 MB
            cursor.execute("PRAGMA secure_delete = ON")
            # Untrusted-input hardening: we never load extensions or run
            # arbitrary SQL, and triggers/views from the file are our own.
            with suppress(AttributeError, sqlite3.Error):
                conn.enable_load_extension(False)
        except sqlite3.Error as exc:
            raise classify_sqlite_error(exc) from exc
        finally:
            cursor.close()

    def close_thread_connection(self) -> None:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            return
        with suppress(sqlite3.Error):
            conn.close()
        with self._connections_lock:
            if conn in self._connections:
                self._connections.remove(conn)
        self._local.conn = None

    def close(self) -> None:
        """Close every connection handed out by this instance."""
        self._closed = True
        with self._connections_lock:
            conns = list(self._connections)
            self._connections.clear()
        for conn in conns:
            with suppress(sqlite3.Error):
                conn.close()
        self._local = threading.local()

    # -- statement helpers ------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        """Run one parameterized statement."""
        try:
            return self.connection().execute(sql, params)
        except sqlite3.Error as exc:
            raise classify_sqlite_error(exc) from exc

    def executemany(
        self, sql: str, seq_params: Sequence[Sequence[Any]]
    ) -> sqlite3.Cursor:
        try:
            return self.connection().executemany(sql, seq_params)
        except sqlite3.Error as exc:
            raise classify_sqlite_error(exc) from exc

    def query_all(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> list[sqlite3.Row]:
        cursor = self.execute(sql, params)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def query_one(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Row | None:
        cursor = self.execute(sql, params)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def query_value(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = (), default: Any = None
    ) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    # -- transactions -----------------------------------------------------
    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        """Run a block inside one transaction, rolling back on any error.

        Writers use ``BEGIN IMMEDIATE`` so that lock contention surfaces at the
        start of the transaction rather than halfway through a batch.
        """
        conn = self.connection()
        with self._write_lock:
            try:
                conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            except sqlite3.Error as exc:
                raise classify_sqlite_error(exc) from exc
            try:
                yield conn
            except BaseException:
                with suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
                raise
            else:
                try:
                    conn.execute("COMMIT")
                except sqlite3.Error as exc:
                    with suppress(sqlite3.Error):
                        conn.execute("ROLLBACK")
                    raise classify_sqlite_error(exc) from exc

    @contextmanager
    def savepoint(self, name: str = "sp") -> Iterator[sqlite3.Connection]:
        """Nested, per-file atomic unit inside an outer transaction.

        ``name`` is generated by the caller from a counter, never from user
        input; it is additionally validated because SQLite cannot parameterize
        a savepoint identifier.
        """
        if not name.replace("_", "").isalnum():
            raise ValueError("Invalid savepoint name")
        conn = self.connection()
        conn.execute(f"SAVEPOINT {name}")
        try:
            yield conn
        except BaseException:
            try:
                conn.execute(f"ROLLBACK TO {name}")
                conn.execute(f"RELEASE {name}")
            except sqlite3.Error:
                pass
            raise
        else:
            try:
                conn.execute(f"RELEASE {name}")
            except sqlite3.Error as exc:
                raise classify_sqlite_error(exc) from exc

    # -- maintenance ------------------------------------------------------
    def integrity_check(self) -> bool:
        try:
            row = self.query_one("PRAGMA integrity_check")
        except DatabaseError:
            return False
        return bool(row) and str(row[0]).lower() == "ok"

    def optimize(self) -> None:
        """Cheap post-indexing housekeeping.  Failures are non-fatal."""
        for statement in (
            "INSERT INTO content_fts(content_fts) VALUES('optimize')",
            "INSERT INTO name_fts(name_fts) VALUES('optimize')",
            "PRAGMA optimize",
            "PRAGMA wal_checkpoint(TRUNCATE)",
        ):
            try:
                self.execute(statement)
            except DatabaseError as exc:
                log.debug("optimize step failed | %s", exc)

    def vacuum(self) -> None:
        try:
            self.execute("VACUUM")
        except DatabaseError as exc:
            log.warning("VACUUM failed | %s", exc)

    def backup_to(self, destination: Path) -> bool:
        """Copy the database using SQLite's online backup API."""
        if str(self.path) == ":memory:":
            return False
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            target = sqlite3.connect(str(destination))
            try:
                self.connection().backup(target)
            finally:
                target.close()
            return True
        except (sqlite3.Error, OSError) as exc:
            log.warning("index backup failed | %s", exc)
            return False

    def file_size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def free_space_bytes(self) -> int:
        try:
            return shutil.disk_usage(self.path.parent).free
        except OSError:
            return 0

    # -- app metadata -----------------------------------------------------
    def get_meta(self, key: str, default: str = "") -> str:
        try:
            row = self.query_one("SELECT value FROM app_meta WHERE key = ?", (key,))
        except DatabaseError:
            return default
        return str(row[0]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO app_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def read_schema_sql() -> str:
    return _SCHEMA_FILE.read_text(encoding="utf-8")


def quarantine_corrupt_database(path: Path) -> Path | None:
    """Move a damaged index aside so a fresh one can be created.

    The user's documents are untouched and the index is rebuildable, but we
    still never silently delete their data.
    """
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = pathutil.backups_dir() / f"{path.stem}-corrupt-{stamp}{path.suffix}"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        for suffix in ("-wal", "-shm"):
            side = Path(str(path) + suffix)
            if side.exists():
                with suppress(OSError):
                    side.unlink()
        log.warning("quarantined damaged index | file=%s", target.name)
        return target
    except OSError as exc:
        log.error("could not quarantine damaged index | %s", exc)
        return None


__all__ = [
    "BUSY_TIMEOUT_MS",
    "Database",
    "DatabaseCorruptError",
    "DatabaseError",
    "DatabaseLockedError",
    "DiskFullError",
    "classify_sqlite_error",
    "fts5_available",
    "quarantine_corrupt_database",
    "read_schema_sql",
    "utc_now",
]
