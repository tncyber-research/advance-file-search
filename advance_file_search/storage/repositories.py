"""Data-access objects for roots, files, content units and index runs.

Every statement is parameterized.  Where an identifier must be interpolated
(ORDER BY direction, savepoint names) the value comes from a closed internal
enum, never from user input.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.models import (
    ContentUnit,
    IndexSummary,
    Root,
    RunStatus,
)
from advance_file_search.logging_setup import get_logger
from advance_file_search.storage.database import Database, utc_now

log = get_logger("storage.repositories")


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------
class RootRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_or_create(self, display_path: str) -> Root:
        shown = pathutil.display_path(display_path)
        normalized = pathutil.normalized_path(shown)
        if not normalized:
            raise ValueError("Empty root path")
        existing = self.find_by_path(shown)
        if existing is not None:
            if existing.display_path != shown:
                self.db.execute(
                    "UPDATE roots SET display_path = ? WHERE id = ?",
                    (shown, existing.id),
                )
                existing.display_path = shown
            return existing
        self.db.execute(
            "INSERT INTO roots(display_path, normalized_path, created_at, schema_version) "
            "VALUES(?, ?, ?, ?)",
            (shown, normalized, utc_now(), C.SCHEMA_VERSION),
        )
        created = self.find_by_path(shown)
        if created is None:  # pragma: no cover - defensive
            raise RuntimeError("Root insert did not persist")
        return created

    def find_by_path(self, display_path: str) -> Root | None:
        normalized = pathutil.normalized_path(display_path)
        if not normalized:
            return None
        row = self.db.query_one(
            "SELECT * FROM roots WHERE normalized_path = ?", (normalized,)
        )
        return _row_to_root(row) if row else None

    def get(self, root_id: int) -> Root | None:
        row = self.db.query_one("SELECT * FROM roots WHERE id = ?", (int(root_id),))
        return _row_to_root(row) if row else None

    def list_all(self) -> list[Root]:
        rows = self.db.query_all("SELECT * FROM roots ORDER BY display_path COLLATE NOCASE")
        return [_row_to_root(row) for row in rows]

    def mark_run_started(self, root_id: int) -> None:
        self.db.execute(
            "UPDATE roots SET last_index_started_at = ?, last_index_status = ? WHERE id = ?",
            (utc_now(), RunStatus.RUNNING.value, int(root_id)),
        )

    def mark_run_finished(self, root_id: int, status: RunStatus, file_count: int) -> None:
        completed = utc_now() if status is RunStatus.COMPLETED else None
        if completed is None:
            self.db.execute(
                "UPDATE roots SET last_index_status = ?, file_count = ? WHERE id = ?",
                (status.value, int(file_count), int(root_id)),
            )
        else:
            self.db.execute(
                "UPDATE roots SET last_index_status = ?, last_index_completed_at = ?, "
                "file_count = ? WHERE id = ?",
                (status.value, completed, int(file_count), int(root_id)),
            )

    def refresh_file_count(self, root_id: int) -> int:
        count = int(
            self.db.query_value(
                "SELECT count(*) FROM files WHERE root_id = ?", (int(root_id),), default=0
            )
        )
        self.db.execute(
            "UPDATE roots SET file_count = ? WHERE id = ?", (count, int(root_id))
        )
        return count

    def delete(self, root_id: int) -> None:
        """Remove a root and everything indexed under it (FK cascade)."""
        with self.db.transaction():
            self.db.execute("DELETE FROM roots WHERE id = ?", (int(root_id),))

    def clear_content(self, root_id: int) -> None:
        """Drop every file/unit for a root, keeping the root record itself."""
        with self.db.transaction():
            self.db.execute("DELETE FROM files WHERE root_id = ?", (int(root_id),))
            self.db.execute(
                "UPDATE roots SET file_count = 0, last_index_completed_at = NULL, "
                "last_index_status = NULL WHERE id = ?",
                (int(root_id),),
            )


def _row_to_root(row: sqlite3.Row) -> Root:
    return Root(
        id=int(row["id"]),
        display_path=str(row["display_path"]),
        normalized_path=str(row["normalized_path"]),
        created_at=str(row["created_at"]),
        last_index_started_at=row["last_index_started_at"],
        last_index_completed_at=row["last_index_completed_at"],
        last_index_status=row["last_index_status"],
        file_count=int(row["file_count"] or 0),
    )


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FileRecord:
    """A stored file row, used for incremental-update decisions."""

    id: int
    root_id: int
    display_path: str
    normalized_path: str
    relative_path: str
    file_name: str
    extension: str
    size_bytes: int
    created_time: float | None
    modified_time: float | None
    fingerprint: str
    content_status: str
    parser_version: int
    unit_count: int
    char_count: int
    error_code: str = ""


@dataclass(slots=True)
class FileWrite:
    """Everything needed to insert or replace one file's index entry."""

    root_id: int
    display_path: str
    normalized_path: str
    relative_path: str
    file_name: str
    extension: str
    size_bytes: int
    created_time: float | None
    modified_time: float | None
    fingerprint: str
    content_status: str
    unit_count: int = 0
    char_count: int = 0
    error_code: str = ""
    error_message: str = ""
    run_id: int | None = None


class FileRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- reads ------------------------------------------------------------
    def fingerprints_for_root(self, root_id: int) -> dict[str, FileRecord]:
        """Load the whole root's index state keyed by normalized path.

        Only metadata is loaded (no document text), which keeps this cheap for
        the target workload of a few thousand files.
        """
        rows = self.db.query_all(
            "SELECT id, root_id, display_path, normalized_path, relative_path, "
            "file_name, extension, size_bytes, created_time, modified_time, "
            "fingerprint, content_status, parser_version, unit_count, char_count, "
            "error_code FROM files WHERE root_id = ?",
            (int(root_id),),
        )
        return {str(row["normalized_path"]): _row_to_file_record(row) for row in rows}

    def get(self, file_id: int) -> FileRecord | None:
        row = self.db.query_one(
            "SELECT id, root_id, display_path, normalized_path, relative_path, "
            "file_name, extension, size_bytes, created_time, modified_time, "
            "fingerprint, content_status, parser_version, unit_count, char_count, "
            "error_code FROM files WHERE id = ?",
            (int(file_id),),
        )
        return _row_to_file_record(row) if row else None

    def count_for_root(self, root_id: int) -> int:
        return int(
            self.db.query_value(
                "SELECT count(*) FROM files WHERE root_id = ?", (int(root_id),), default=0
            )
        )

    def status_counts(self, root_id: int) -> dict[str, int]:
        rows = self.db.query_all(
            "SELECT content_status, count(*) AS n FROM files WHERE root_id = ? "
            "GROUP BY content_status",
            (int(root_id),),
        )
        return {str(row["content_status"]): int(row["n"]) for row in rows}

    def extensions_for_root(self, root_id: int) -> list[tuple[str, int]]:
        rows = self.db.query_all(
            "SELECT extension, count(*) AS n FROM files WHERE root_id = ? "
            "GROUP BY extension ORDER BY n DESC",
            (int(root_id),),
        )
        return [(str(row["extension"]), int(row["n"])) for row in rows]

    def stale_paths(self, root_id: int, run_id: int) -> list[tuple[int, str]]:
        """Files not seen by ``run_id`` — i.e. deleted or moved since."""
        rows = self.db.query_all(
            "SELECT id, relative_path FROM files "
            "WHERE root_id = ? AND (last_seen_run_id IS NULL OR last_seen_run_id < ?)",
            (int(root_id), int(run_id)),
        )
        return [(int(row["id"]), str(row["relative_path"])) for row in rows]

    # -- writes -----------------------------------------------------------
    def touch_seen(self, file_id: int, run_id: int) -> None:
        self.db.execute(
            "UPDATE files SET last_seen_run_id = ? WHERE id = ?",
            (int(run_id), int(file_id)),
        )

    def touch_seen_many(self, file_ids: Sequence[int], run_id: int) -> None:
        if not file_ids:
            return
        self.db.executemany(
            "UPDATE files SET last_seen_run_id = ? WHERE id = ?",
            [(int(run_id), int(fid)) for fid in file_ids],
        )

    def upsert(self, write: FileWrite) -> int:
        """Insert or update a file row and return its id."""
        now = utc_now()
        self.db.execute(
            """
            INSERT INTO files(
                root_id, display_path, normalized_path, relative_path, file_name,
                file_name_folded, extension, mime_category, size_bytes, created_time,
                modified_time, fingerprint, content_status, parser_version,
                unit_count, char_count, indexed_at, last_seen_run_id,
                error_code, error_message_sanitized
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(root_id, normalized_path) DO UPDATE SET
                display_path            = excluded.display_path,
                relative_path           = excluded.relative_path,
                file_name               = excluded.file_name,
                file_name_folded        = excluded.file_name_folded,
                extension               = excluded.extension,
                mime_category           = excluded.mime_category,
                size_bytes              = excluded.size_bytes,
                created_time            = excluded.created_time,
                modified_time           = excluded.modified_time,
                fingerprint             = excluded.fingerprint,
                content_status          = excluded.content_status,
                parser_version          = excluded.parser_version,
                unit_count              = excluded.unit_count,
                char_count              = excluded.char_count,
                indexed_at              = excluded.indexed_at,
                last_seen_run_id        = excluded.last_seen_run_id,
                error_code              = excluded.error_code,
                error_message_sanitized = excluded.error_message_sanitized
            """,
            (
                int(write.root_id),
                write.display_path,
                write.normalized_path,
                write.relative_path,
                write.file_name,
                write.file_name.casefold(),
                write.extension,
                _mime_category(write.extension),
                int(write.size_bytes),
                write.created_time,
                write.modified_time,
                write.fingerprint,
                write.content_status,
                C.PARSER_VERSION,
                int(write.unit_count),
                int(write.char_count),
                now,
                write.run_id,
                write.error_code,
                write.error_message,
            ),
        )
        file_id = self.db.query_value(
            "SELECT id FROM files WHERE root_id = ? AND normalized_path = ?",
            (int(write.root_id), write.normalized_path),
            default=0,
        )
        return int(file_id)

    def delete_units(self, file_id: int) -> None:
        """Remove a file's content units; FTS rows follow via triggers."""
        self.db.execute("DELETE FROM content_units WHERE file_id = ?", (int(file_id),))

    def delete_file(self, file_id: int) -> None:
        self.db.execute("DELETE FROM files WHERE id = ?", (int(file_id),))

    def delete_files(self, file_ids: Sequence[int]) -> int:
        if not file_ids:
            return 0
        self.db.executemany(
            "DELETE FROM files WHERE id = ?", [(int(fid),) for fid in file_ids]
        )
        return len(file_ids)

    def mark_status(
        self, file_id: int, status: str, error_code: str = "", error_message: str = ""
    ) -> None:
        self.db.execute(
            "UPDATE files SET content_status = ?, error_code = ?, "
            "error_message_sanitized = ? WHERE id = ?",
            (status, error_code, error_message[: C.MAX_LOGGED_MESSAGE_LENGTH], int(file_id)),
        )


def _row_to_file_record(row: sqlite3.Row) -> FileRecord:
    return FileRecord(
        id=int(row["id"]),
        root_id=int(row["root_id"]),
        display_path=str(row["display_path"]),
        normalized_path=str(row["normalized_path"]),
        relative_path=str(row["relative_path"]),
        file_name=str(row["file_name"]),
        extension=str(row["extension"]),
        size_bytes=int(row["size_bytes"] or 0),
        created_time=row["created_time"],
        modified_time=row["modified_time"],
        fingerprint=str(row["fingerprint"] or ""),
        content_status=str(row["content_status"] or ""),
        parser_version=int(row["parser_version"] or 0),
        unit_count=int(row["unit_count"] or 0),
        char_count=int(row["char_count"] or 0),
        error_code=str(row["error_code"] or ""),
    )


_MIME_CATEGORIES = {
    ".pdf": "pdf",
    ".docx": "word",
    ".xlsx": "excel",
    ".txt": "text",
    ".md": "text",
    ".csv": "text",
    ".log": "text",
}


def _mime_category(extension: str) -> str:
    return _MIME_CATEGORIES.get(extension.casefold(), "other")


# ---------------------------------------------------------------------------
# Content units
# ---------------------------------------------------------------------------
class ContentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_units(self, file_id: int, units: Iterable[ContentUnit]) -> tuple[int, int]:
        """Insert content units in bounded chunks.

        Returns ``(unit_count, char_count)``.  The caller owns the enclosing
        transaction/savepoint so that a failure leaves no partial entry.
        """
        buffer: list[tuple[Any, ...]] = []
        total_units = 0
        total_chars = 0
        for unit in units:
            text = unit.text
            if not text or not text.strip():
                continue
            if len(text) > C.MAX_UNIT_TEXT_LENGTH:
                text = text[: C.MAX_UNIT_TEXT_LENGTH]
            buffer.append(
                (
                    int(file_id),
                    int(unit.sequence),
                    unit.location_type,
                    unit.location_label[:200],
                    json.dumps(unit.location_data, ensure_ascii=False, separators=(",", ":")),
                    text,
                )
            )
            total_units += 1
            total_chars += len(text)
            if len(buffer) >= C.UNIT_INSERT_CHUNK:
                self._flush(buffer)
                buffer.clear()
        if buffer:
            self._flush(buffer)
        return total_units, total_chars

    def _flush(self, rows: Sequence[tuple[Any, ...]]) -> None:
        self.db.executemany(
            "INSERT INTO content_units("
            "file_id, sequence, location_type, location_label, location_json, text"
            ") VALUES(?, ?, ?, ?, ?, ?)",
            rows,
        )

    def units_for_file(self, file_id: int, limit: int = 0) -> list[ContentUnit]:
        sql = (
            "SELECT sequence, location_type, location_label, location_json, text "
            "FROM content_units WHERE file_id = ? ORDER BY sequence"
        )
        params: list[Any] = [int(file_id)]
        if limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = self.db.query_all(sql, params)
        return [_row_to_unit(row) for row in rows]

    def iter_units_for_file(self, file_id: int) -> Iterator[ContentUnit]:
        cursor = self.db.execute(
            "SELECT sequence, location_type, location_label, location_json, text "
            "FROM content_units WHERE file_id = ? ORDER BY sequence",
            (int(file_id),),
        )
        try:
            for row in cursor:
                yield _row_to_unit(row)
        finally:
            cursor.close()

    def total_units(self) -> int:
        return int(self.db.query_value("SELECT count(*) FROM content_units", default=0))


def _row_to_unit(row: sqlite3.Row) -> ContentUnit:
    try:
        data = json.loads(row["location_json"] or "{}")
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, ValueError, TypeError):
        data = {}
    return ContentUnit(
        sequence=int(row["sequence"]),
        location_type=str(row["location_type"]),
        location_label=str(row["location_label"] or ""),
        location_data=data,
        text=str(row["text"] or ""),
    )


# ---------------------------------------------------------------------------
# Index runs
# ---------------------------------------------------------------------------
class IndexRunRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def start(self, root_id: int, mode: str = "update") -> int:
        self.db.execute(
            "INSERT INTO index_runs(root_id, started_at, status, mode, application_version) "
            "VALUES(?, ?, ?, ?, ?)",
            (int(root_id), utc_now(), RunStatus.RUNNING.value, mode, C.APP_VERSION),
        )
        return int(self.db.query_value("SELECT last_insert_rowid()", default=0))

    def finish(self, run_id: int, summary: IndexSummary) -> None:
        self.db.execute(
            """
            UPDATE index_runs SET
                finished_at      = ?,
                status           = ?,
                files_discovered = ?,
                files_processed  = ?,
                files_indexed    = ?,
                files_unchanged  = ?,
                files_skipped    = ?,
                files_failed     = ?,
                files_no_text    = ?,
                files_deleted    = ?,
                elapsed_seconds  = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                summary.status.value,
                summary.discovered,
                summary.processed,
                summary.indexed,
                summary.unchanged,
                summary.skipped,
                summary.failed,
                summary.no_text,
                summary.deleted,
                round(summary.elapsed_seconds, 3),
                int(run_id),
            ),
        )

    def latest_for_root(self, root_id: int) -> sqlite3.Row | None:
        return self.db.query_one(
            "SELECT * FROM index_runs WHERE root_id = ? ORDER BY id DESC LIMIT 1",
            (int(root_id),),
        )

    def abandon_running(self) -> int:
        """Mark runs left 'running' by a crash as failed on next launch."""
        cursor = self.db.execute(
            "UPDATE index_runs SET status = ?, finished_at = ? WHERE status = ?",
            (RunStatus.FAILED.value, utc_now(), RunStatus.RUNNING.value),
        )
        count = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        cursor.close()
        if count:
            self.db.execute(
                "UPDATE roots SET last_index_status = ? WHERE last_index_status = ?",
                (RunStatus.FAILED.value, RunStatus.RUNNING.value),
            )
            log.info("recovered interrupted index runs | count=%d", count)
        return count


@dataclass(slots=True)
class Repositories:
    """Convenience bundle passed around by the indexing and search services."""

    db: Database
    roots: RootRepository
    files: FileRepository
    content: ContentRepository
    runs: IndexRunRepository

    @classmethod
    def create(cls, db: Database) -> Repositories:
        return cls(
            db=db,
            roots=RootRepository(db),
            files=FileRepository(db),
            content=ContentRepository(db),
            runs=IndexRunRepository(db),
        )
