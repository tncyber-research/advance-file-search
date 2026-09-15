"""Background workers.

Indexing and searching both run off the UI thread (handoff §5.1, §11.4):

* each worker owns its own SQLite connection, created on the worker thread,
  because a connection may not cross threads;
* progress and results travel back as Qt signals, which Qt queues onto the UI
  thread, so no widget is ever touched from a worker;
* cancellation is a ``threading.Event`` checked at safe points, never a thread
  kill.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal

from advance_file_search.core.models import (
    IndexProgress,
    SearchRequest,
)
from advance_file_search.core.settings import AppSettings
from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
from advance_file_search.logging_setup import get_logger
from advance_file_search.search.search_service import SearchService
from advance_file_search.storage.database import Database, DatabaseError
from advance_file_search.storage.migrations import open_index
from advance_file_search.storage.repositories import Repositories

log = get_logger("ui.workers")


class IndexWorker(QObject):
    """Runs one indexing pass on its own thread."""

    progress = Signal(object)  # IndexProgress
    finished = Signal(object)  # IndexSummary
    failed = Signal(str)

    def __init__(
        self,
        db_path: str,
        root_display: str,
        settings: AppSettings,
        *,
        rebuild: bool = False,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._root = root_display
        self._settings = settings
        self._rebuild = rebuild
        self._cancel = threading.Event()
        self._coordinator: IndexCoordinator | None = None

    def cancel(self) -> None:
        """Request a safe stop.  Callable from the UI thread."""
        self._cancel.set()
        coordinator = self._coordinator
        if coordinator is not None:
            coordinator.cancel()

    def run(self) -> None:
        """Entry point connected to ``QThread.started``."""
        db: Database | None = None
        try:
            # open_index rather than Database: it is idempotent and cheap on an
            # already-migrated file, and it means the writer still works if the
            # index file was removed or replaced since the window opened.
            db, _migration = open_index(self._db_path)
            repos = Repositories.create(db)
            options = IndexOptions(rebuild=self._rebuild, settings=self._settings)
            self._coordinator = IndexCoordinator(
                repos,
                options,
                cancel_event=self._cancel,
                on_progress=self._emit_progress,
            )
            summary = self._coordinator.run(self._root)
            self.finished.emit(summary)
        except DatabaseError as exc:
            log.error("index worker database error | %s", exc)
            self.failed.emit("error.db_locked")
        except Exception as exc:  # noqa: BLE001 - a worker must not crash the app
            log.error("index worker failed | %s: %s", type(exc).__name__, exc)
            self.failed.emit("error.unexpected")
        finally:
            if db is not None:
                try:
                    db.close_thread_connection()
                    db.close()
                except Exception:  # noqa: BLE001
                    pass

    def _emit_progress(self, progress: IndexProgress) -> None:
        self.progress.emit(progress)


class SearchWorker(QObject):
    """Runs one search on its own thread."""

    finished = Signal(object)  # SearchResponse
    failed = Signal(str)

    def __init__(self, db_path: str, request: SearchRequest) -> None:
        super().__init__()
        self._db_path = db_path
        self._request = request
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        db: Database | None = None
        try:
            db = Database(self._db_path)
            repos = Repositories.create(db)
            service = SearchService(repos)
            response = service.search(self._request, cancel=self._cancel)
            if not self._cancel.is_set():
                self.finished.emit(response)
        except DatabaseError as exc:
            log.warning("search worker database error | %s", exc)
            if not self._cancel.is_set():
                self.failed.emit("error.db_locked")
        except Exception as exc:  # noqa: BLE001
            log.error("search worker failed | %s: %s", type(exc).__name__, exc)
            if not self._cancel.is_set():
                self.failed.emit("error.unexpected")
        finally:
            if db is not None:
                try:
                    db.close_thread_connection()
                    db.close()
                except Exception:  # noqa: BLE001
                    pass


class WorkerHandle:
    """Owns a ``QThread`` plus its worker and tears both down cleanly.

    Qt requires the thread to finish before the ``QThread`` is destroyed;
    letting either object be garbage collected early is a common crash source,
    so the handle keeps strong references until ``wait`` returns.
    """

    def __init__(self, worker: QObject) -> None:
        self.worker = worker
        self.thread = QThread()
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)  # type: ignore[attr-defined]

    def start(self) -> None:
        self.thread.start()

    def cancel(self) -> None:
        cancel = getattr(self.worker, "cancel", None)
        if callable(cancel):
            cancel()

    def stop(self, *, wait_ms: int = 8000) -> None:
        """Cancel, quit the event loop and wait for the thread to exit."""
        self.cancel()
        self.thread.quit()
        if not self.thread.wait(wait_ms):
            log.warning("worker thread did not stop within %d ms", wait_ms)

    @property
    def running(self) -> bool:
        return self.thread.isRunning()
