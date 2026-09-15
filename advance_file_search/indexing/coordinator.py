"""Indexing coordinator: scan, decide, extract, commit.

Data-safety guarantees:

* **Per-file atomicity.**  Each file's delete-then-reinsert happens inside a
  SQLite ``SAVEPOINT``.  If extraction or insertion fails, that savepoint rolls
  back and the previous valid entry for the file survives.
* **Batched durability.**  Savepoints are grouped into outer transactions of
  :data:`constants.INDEX_COMMIT_BATCH_SIZE` files, so a crash loses at most one
  batch, never the whole run.
* **Safe cancellation.**  Cancellation is checked between files and inside the
  extraction loop.  Completed batches stay committed, the in-flight file rolls
  back, the run is marked ``cancelled``, and previously indexed data remains
  searchable.
* **No orphan deletions.**  Deleted-file cleanup runs only after a *complete*
  scan; a cancelled run never removes entries, so cancelling cannot silently
  shrink the index.

Nothing in this module writes document text anywhere except SQLite, and no
extracted text is ever logged.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.models import (
    IndexError as IndexErrorRecord,
)
from advance_file_search.core.models import (
    IndexPhase,
    IndexProgress,
    IndexSummary,
    ParseOutcome,
    ParseResult,
    RunStatus,
    ScannedFile,
    SkipReason,
)
from advance_file_search.core.security import validate_root
from advance_file_search.core.settings import AppSettings
from advance_file_search.indexing.fingerprint import is_unchanged, make_fingerprint
from advance_file_search.indexing.parsers.base import (
    ParseOptions,
    ParserRegistry,
    build_registry,
)
from advance_file_search.indexing.scanner import FileScanner, ScanOptions
from advance_file_search.logging_setup import get_logger, safe_path_field
from advance_file_search.storage.database import (
    DatabaseError,
    DatabaseLockedError,
    DiskFullError,
)
from advance_file_search.storage.repositories import FileWrite, Repositories

log = get_logger("indexing.coordinator")

#: Free space below which an index update refuses to start.
MIN_FREE_BYTES = 256 * 1024 * 1024

#: Maximum per-file errors retained for the UI summary.
MAX_REPORTED_ERRORS = 500


class IndexCancelled(Exception):
    """Raised internally to unwind to the run boundary on cancellation."""


@dataclass
class IndexOptions:
    """Per-run behaviour derived from settings and the user's button choice."""

    rebuild: bool = False
    settings: AppSettings = field(default_factory=AppSettings)

    def scan_options(self) -> ScanOptions:
        return ScanOptions(
            extensions=self.settings.active_extensions,
            max_file_size_bytes=self.settings.max_file_size_bytes,
            include_hidden_files=self.settings.include_hidden_files,
        )

    def parse_options(self) -> ParseOptions:
        return ParseOptions(
            max_file_size_bytes=self.settings.max_file_size_bytes,
            include_docx_headers=self.settings.index_docx_headers,
        )


ProgressCallback = Callable[[IndexProgress], None]


class IndexCoordinator:
    """Runs one indexing pass over one root.

    Instances are single-use and must be driven from a worker thread: the
    database connection is created on whichever thread calls :meth:`run`.
    """

    def __init__(
        self,
        repos: Repositories,
        options: IndexOptions | None = None,
        *,
        registry: ParserRegistry | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.repos = repos
        self.options = options or IndexOptions()
        self.registry = registry or build_registry(self.options.parse_options())
        self.cancel_event = cancel_event or threading.Event()
        self.on_progress = on_progress

        self.progress = IndexProgress()
        self.errors: list[IndexErrorRecord] = []
        self.skip_counts: dict[str, int] = {}
        self._started = 0.0
        self._last_emit = 0.0
        self._savepoint_counter = 0

    # -- cancellation -----------------------------------------------------
    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise IndexCancelled

    # -- progress ---------------------------------------------------------
    def _emit(self, *, force: bool = False) -> None:
        now = time.monotonic()
        self.progress.elapsed_seconds = max(0.0, now - self._started)
        if self.on_progress is None:
            return
        if not force and (now - self._last_emit) * 1000 < C.PROGRESS_EMIT_INTERVAL_MS:
            return
        self._last_emit = now
        # A copy is handed out so the UI thread never reads a mutating object.
        self.on_progress(
            IndexProgress(
                phase=self.progress.phase,
                current_item=self.progress.current_item,
                discovered=self.progress.discovered,
                processed=self.progress.processed,
                indexed=self.progress.indexed,
                skipped=self.progress.skipped,
                failed=self.progress.failed,
                no_text=self.progress.no_text,
                deleted=self.progress.deleted,
                unchanged=self.progress.unchanged,
                warnings=self.progress.warnings,
                elapsed_seconds=self.progress.elapsed_seconds,
            )
        )

    def _set_phase(self, phase: IndexPhase) -> None:
        self.progress.phase = phase
        self.progress.current_item = ""
        self._emit(force=True)

    # -- main entry point -------------------------------------------------
    def run(self, root_display: str) -> IndexSummary:
        """Index ``root_display`` and return a summary.

        Never raises for document-level problems.  Infrastructure failures
        (locked or full database) are reported through the summary status and
        logged; the previous index is left intact.
        """
        self._started = time.monotonic()
        self._set_phase(IndexPhase.PREPARING)

        check = validate_root(root_display)
        if not check.ok:
            log.warning(
                "index refused | verdict=%s | %s",
                check.verdict.value,
                safe_path_field(check.display),
            )
            return self._failed_summary(0, 0, check.verdict.value)

        free = self.repos.db.free_space_bytes()
        if free and free < MIN_FREE_BYTES:
            log.error("index refused | reason=disk_space | free_mb=%d", free // 1024 // 1024)
            return self._failed_summary(0, 0, C.ERR_DISK_FULL)

        try:
            root = self.repos.roots.get_or_create(check.display)
        except (DatabaseError, ValueError) as exc:
            log.error("index refused | reason=root_record | %s", exc)
            return self._failed_summary(0, 0, C.ERR_UNKNOWN)

        run_id = 0
        status = RunStatus.FAILED
        scan_complete = False
        try:
            if self.options.rebuild:
                self.repos.roots.clear_content(root.id)
                log.info("rebuild requested | root_id=%d", root.id)

            run_id = self.repos.runs.start(
                root.id, "rebuild" if self.options.rebuild else "update"
            )
            self.repos.roots.mark_run_started(root.id)

            existing = self.repos.files.fingerprints_for_root(root.id)
            scan_complete = self._index_files(root.id, check.display, run_id, existing)
            self._check_cancel()

            if scan_complete:
                self._set_phase(IndexPhase.REMOVING_DELETED)
                self._remove_deleted(root.id, run_id)

            self._set_phase(IndexPhase.FINALIZING)
            count = self.repos.roots.refresh_file_count(root.id)
            self.repos.db.optimize()
            status = RunStatus.COMPLETED
            self.repos.roots.mark_run_finished(root.id, status, count)
            self._set_phase(IndexPhase.DONE)

        except IndexCancelled:
            status = RunStatus.CANCELLED
            count = self._safe_refresh_count(root.id)
            self.repos.roots.mark_run_finished(root.id, status, count)
            self._set_phase(IndexPhase.CANCELLED)
            log.info(
                "index cancelled | root_id=%d | processed=%d | indexed=%d",
                root.id,
                self.progress.processed,
                self.progress.indexed,
            )
        except DiskFullError as exc:
            status = RunStatus.FAILED
            self._record_error("", C.ERR_DISK_FULL, "out of disk space")
            log.error("index failed | reason=disk_full | %s", exc)
            self._finish_failed(root.id)
        except DatabaseLockedError as exc:
            status = RunStatus.FAILED
            self._record_error("", C.ERR_UNKNOWN, "index database is busy")
            log.error("index failed | reason=locked | %s", exc)
            self._finish_failed(root.id)
        except DatabaseError as exc:
            status = RunStatus.FAILED
            self._record_error("", C.ERR_UNKNOWN, "index database error")
            log.error("index failed | reason=database | %s", exc)
            self._finish_failed(root.id)
        except Exception as exc:  # noqa: BLE001 - a run must never crash the app
            status = RunStatus.FAILED
            self._record_error("", C.ERR_UNKNOWN, type(exc).__name__)
            log.error("index failed | reason=unexpected | %s: %s", type(exc).__name__, exc)
            self._finish_failed(root.id)

        summary = IndexSummary(
            run_id=run_id,
            root_id=root.id,
            status=status,
            discovered=self.progress.discovered,
            processed=self.progress.processed,
            indexed=self.progress.indexed,
            skipped=self.progress.skipped,
            failed=self.progress.failed,
            no_text=self.progress.no_text,
            deleted=self.progress.deleted,
            unchanged=self.progress.unchanged,
            elapsed_seconds=max(0.0, time.monotonic() - self._started),
            errors=list(self.errors),
            skip_counts=dict(self.skip_counts),
        )
        if run_id:
            try:
                self.repos.runs.finish(run_id, summary)
            except DatabaseError as exc:
                log.warning("could not record run summary | %s", exc)

        log.info(
            "index run finished | root_id=%d | status=%s | discovered=%d indexed=%d "
            "unchanged=%d skipped=%d failed=%d no_text=%d deleted=%d | %.2fs",
            root.id,
            status.value,
            summary.discovered,
            summary.indexed,
            summary.unchanged,
            summary.skipped,
            summary.failed,
            summary.no_text,
            summary.deleted,
            summary.elapsed_seconds,
        )
        return summary

    # -- phases -----------------------------------------------------------
    def _index_files(
        self,
        root_id: int,
        root_display: str,
        run_id: int,
        existing: dict[str, object],
    ) -> bool:
        """Scan and extract.  Returns True when the scan ran to completion."""
        scanner = FileScanner(self.options.scan_options())
        self._set_phase(IndexPhase.SCANNING)

        # The scan is consumed lazily so that extraction overlaps discovery and
        # the whole file list is never held in memory twice.
        batch: list[ScannedFile] = []
        self._set_phase(IndexPhase.EXTRACTING)

        for candidate in scanner.scan(root_display, cancel=self.cancel_event):
            self._check_cancel()
            self.progress.discovered += 1
            batch.append(candidate)
            if len(batch) >= C.INDEX_COMMIT_BATCH_SIZE:
                self._process_batch(root_id, run_id, batch, existing)
                batch.clear()

        if batch:
            self._process_batch(root_id, run_id, batch, existing)
            batch.clear()

        # Scan-level skips are reported per reason.  "not_supported" is
        # excluded from the headline skip count because every unrelated file on
        # the disk would otherwise dominate it and mean nothing to the user.
        for reason, count in scanner.stats.skips.items():
            self.skip_counts[reason] = self.skip_counts.get(reason, 0) + count
            if reason != SkipReason.NOT_SUPPORTED.value:
                self.progress.skipped += count
        self.progress.warnings += scanner.stats.reparse_points_skipped
        self._emit(force=True)

        # The scan completed only if we were not cancelled mid-walk.
        return not self.cancel_event.is_set()

    def _process_batch(
        self,
        root_id: int,
        run_id: int,
        batch: Iterable[ScannedFile],
        existing: dict[str, object],
    ) -> None:
        """Handle one commit batch inside a single outer transaction."""
        with self.repos.db.transaction():
            for candidate in batch:
                self._check_cancel()
                self.progress.current_item = candidate.relative_path
                record = existing.get(candidate.normalized_path)

                if record is not None and is_unchanged(
                    getattr(record, "fingerprint", ""),
                    candidate.size_bytes,
                    candidate.modified_time,
                ):
                    self.repos.files.touch_seen(record.id, run_id)
                    self.progress.unchanged += 1
                    self.progress.processed += 1
                    self._emit()
                    continue

                self._savepoint_counter += 1
                name = f"f{self._savepoint_counter}"
                try:
                    with self.repos.db.savepoint(name):
                        self._index_one(root_id, candidate, run_id, record)
                except IndexCancelled:
                    raise
                except (DiskFullError, DatabaseLockedError):
                    raise
                except DatabaseError as exc:
                    # Per-file database failure: the savepoint rolled back, so
                    # the previous entry for this file is still valid.
                    self.progress.failed += 1
                    self._record_error(
                        candidate.relative_path, C.ERR_UNKNOWN, "database error"
                    )
                    log.warning(
                        "file not indexed | %s | %s",
                        safe_path_field(candidate.display_path),
                        exc,
                    )
                self.progress.processed += 1
                self._emit()

    def _index_one(
        self,
        root_id: int,
        candidate: ScannedFile,
        run_id: int,
        previous: object | None,
    ) -> None:
        """Extract and store one file inside the caller's savepoint."""
        parser = self.registry.get(candidate.extension)
        if parser is None:
            self.progress.skipped += 1
            return

        result: ParseResult = parser.parse(candidate.display_path)

        status = C.STATUS_INDEXED
        error_code = ""
        error_message = ""

        if result.outcome is ParseOutcome.OK:
            pass
        elif result.outcome is ParseOutcome.NO_TEXT:
            status = C.STATUS_NO_TEXT
            error_code = result.error_code or C.ERR_NO_TEXT
            error_message = result.error_message
            self.progress.no_text += 1
        elif result.outcome in (ParseOutcome.MISSING,):
            # The file vanished between the scan and extraction.  Drop the old
            # entry so search does not offer a file that is gone.
            if previous is not None:
                self.repos.files.delete_file(previous.id)
                self.progress.deleted += 1
            self.progress.skipped += 1
            return
        else:
            status = C.STATUS_FAILED
            error_code = result.error_code or C.ERR_UNKNOWN
            error_message = result.error_message
            self.progress.failed += 1
            self._record_error(candidate.relative_path, error_code, error_message)

        write = FileWrite(
            root_id=root_id,
            display_path=candidate.display_path,
            normalized_path=candidate.normalized_path,
            relative_path=candidate.relative_path,
            file_name=candidate.file_name,
            extension=candidate.extension,
            size_bytes=candidate.size_bytes,
            created_time=candidate.created_time,
            modified_time=candidate.modified_time,
            fingerprint=make_fingerprint(candidate.size_bytes, candidate.modified_time),
            content_status=status,
            error_code=error_code,
            error_message=error_message,
            run_id=run_id,
        )
        file_id = self.repos.files.upsert(write)
        if not file_id:  # pragma: no cover - defensive
            raise DatabaseError("file row did not persist")

        # Replace content atomically: old units are removed and new ones
        # inserted inside the same savepoint as the metadata update.
        self.repos.files.delete_units(file_id)

        if result.document is not None and result.document.units:
            unit_count, char_count = self.repos.content.insert_units(
                file_id, result.document.units
            )
            if unit_count != write.unit_count or char_count != write.char_count:
                self.repos.db.execute(
                    "UPDATE files SET unit_count = ?, char_count = ? WHERE id = ?",
                    (unit_count, char_count, file_id),
                )
            if status == C.STATUS_INDEXED:
                self.progress.indexed += 1
        elif status == C.STATUS_INDEXED:
            # OK outcome with no units should not happen, but treat it as
            # no_text rather than claiming a successful index.
            self.repos.files.mark_status(file_id, C.STATUS_NO_TEXT, C.ERR_NO_TEXT, "")
            self.progress.no_text += 1

        if result.warnings:
            self.progress.warnings += len(result.warnings)

    def _remove_deleted(self, root_id: int, run_id: int) -> None:
        """Drop index entries for files no longer present under the root."""
        stale = self.repos.files.stale_paths(root_id, run_id)
        if not stale:
            return
        self._check_cancel()
        ids = [file_id for file_id, _ in stale]
        with self.repos.db.transaction():
            removed = self.repos.files.delete_files(ids)
        self.progress.deleted += removed
        self._emit(force=True)
        log.info("removed deleted files from index | root_id=%d | count=%d", root_id, removed)

    # -- bookkeeping ------------------------------------------------------
    def _record_error(self, relative_path: str, code: str, message: str) -> None:
        if len(self.errors) >= MAX_REPORTED_ERRORS:
            return
        self.errors.append(
            IndexErrorRecord(
                relative_path=relative_path,
                error_code=code,
                message=message[: C.MAX_LOGGED_MESSAGE_LENGTH],
            )
        )

    def _safe_refresh_count(self, root_id: int) -> int:
        try:
            return self.repos.roots.refresh_file_count(root_id)
        except DatabaseError:
            return 0

    def _finish_failed(self, root_id: int) -> None:
        self._set_phase(IndexPhase.FAILED)
        try:
            count = self.repos.files.count_for_root(root_id)
            self.repos.roots.mark_run_finished(root_id, RunStatus.FAILED, count)
        except DatabaseError:
            pass

    def _failed_summary(self, run_id: int, root_id: int, code: str) -> IndexSummary:
        self._set_phase(IndexPhase.FAILED)
        self._record_error("", code, code)
        return IndexSummary(
            run_id=run_id,
            root_id=root_id,
            status=RunStatus.FAILED,
            elapsed_seconds=max(0.0, time.monotonic() - self._started),
            errors=list(self.errors),
        )


def delete_index_for_root(repos: Repositories, root_display: str) -> bool:
    """Remove a root and all of its indexed data.  Returns True if removed."""
    root = repos.roots.find_by_path(pathutil.display_path(root_display))
    if root is None:
        return False
    repos.roots.delete(root.id)
    # secure_delete=ON means the freed pages are zeroed; VACUUM then returns
    # the space to the filesystem so the removed text is not recoverable from
    # the index file.
    repos.db.vacuum()
    log.info("deleted index for root | root_id=%d", root.id)
    return True
