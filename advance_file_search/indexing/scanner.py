"""Recursive file-system scanner with security-driven exclusions.

The scanner never opens a file and never follows a link.  It walks directories
with ``os.scandir`` (one syscall per entry for both the name and the stat
data), applies the exclusion rules, and yields candidates for extraction.

Exclusion policy (handoff §15):

* directory symlinks, junctions and mount-point reparse points are skipped,
  which prevents recursion loops and stops the scan escaping the chosen root;
* cloud placeholder files are skipped, because reading one would trigger a
  network download;
* the application's own data directory (and the index database) is skipped;
* on a whole-drive scan, Windows system directories are skipped;
* executables and scripts are never candidates, even if the user enabled extra
  formats;
* every candidate is re-checked for containment inside the selected root.
"""

from __future__ import annotations

import os
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import PureWindowsPath

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.models import ScannedFile, ScanSkip, SkipReason
from advance_file_search.core.security import (
    FILE_ATTRIBUTE_HIDDEN,
    FILE_ATTRIBUTE_SYSTEM,
    FILE_ATTRIBUTE_TEMPORARY,
    has_attribute,
    is_cloud_placeholder,
    is_reparse_point,
)
from advance_file_search.logging_setup import get_logger, safe_path_field

log = get_logger("indexing.scanner")


@dataclass
class ScanOptions:
    """Everything the scanner needs to decide what to include."""

    extensions: frozenset[str] = C.CORE_EXTENSIONS
    max_file_size_bytes: int = C.DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024
    include_hidden_files: bool = False
    #: Extra normalized directory paths to skip (the app data dir is added
    #: automatically).
    extra_excluded_dirs: frozenset[str] = frozenset()


@dataclass
class ScanStats:
    """Counters collected during one walk."""

    directories_visited: int = 0
    entries_seen: int = 0
    candidates: int = 0
    skips: Counter[str] = field(default_factory=Counter)
    permission_errors: int = 0
    reparse_points_skipped: int = 0
    vanished: int = 0

    def note_skip(self, reason: SkipReason) -> None:
        self.skips[reason.value] += 1
        if reason is SkipReason.REPARSE_POINT:
            self.reparse_points_skipped += 1
        elif reason is SkipReason.ACCESS_DENIED:
            self.permission_errors += 1
        elif reason is SkipReason.VANISHED:
            self.vanished += 1


class FileScanner:
    """Walks a local root and yields indexable files."""

    def __init__(self, options: ScanOptions | None = None) -> None:
        self.options = options or ScanOptions()
        self.stats = ScanStats()
        self._excluded_norm_dirs = self._build_excluded_dirs()

    def _build_excluded_dirs(self) -> frozenset[str]:
        excluded = {
            pathutil.normalized_path(str(pathutil.app_data_dir())),
        }
        excluded.update(self.options.extra_excluded_dirs)
        excluded.discard("")
        return frozenset(excluded)

    # -- public API -------------------------------------------------------
    def scan(
        self,
        root_display: str,
        *,
        cancel: Callable[[], bool] | threading.Event | None = None,
        on_skip: Callable[[ScanSkip], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> Iterator[ScannedFile]:
        """Yield every indexable file under ``root_display``.

        ``cancel`` may be a callable or an :class:`threading.Event`; the walk
        stops at the next entry boundary when it is set.
        """
        self.stats = ScanStats()
        root = pathutil.display_path(root_display)
        if not root:
            return
        is_drive = pathutil.is_drive_root(root)
        should_cancel = _make_cancel(cancel)

        # Explicit stack instead of os.walk: it lets us stat each directory
        # entry exactly once and drop reparse points before descending.
        stack: list[str] = [root]
        while stack:
            if should_cancel():
                return
            current = stack.pop()
            self.stats.directories_visited += 1
            if on_progress is not None:
                on_progress(self.stats.candidates)

            try:
                iterator = os.scandir(pathutil.extended_path(current))
            except PermissionError:
                self.stats.note_skip(SkipReason.ACCESS_DENIED)
                _report(on_skip, current, SkipReason.ACCESS_DENIED)
                continue
            except FileNotFoundError:
                self.stats.note_skip(SkipReason.VANISHED)
                continue
            except OSError as exc:
                log.warning("scan error | %s | %s", safe_path_field(current), exc)
                self.stats.note_skip(SkipReason.ACCESS_DENIED)
                continue

            with iterator:
                while True:
                    if should_cancel():
                        return
                    try:
                        entry = next(iterator)
                    except StopIteration:
                        break
                    except PermissionError:
                        self.stats.note_skip(SkipReason.ACCESS_DENIED)
                        break
                    except OSError:
                        self.stats.note_skip(SkipReason.ACCESS_DENIED)
                        break

                    self.stats.entries_seen += 1
                    try:
                        # follow_symlinks=False: never resolve a link target.
                        st = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        self.stats.note_skip(SkipReason.VANISHED)
                        continue
                    except PermissionError:
                        self.stats.note_skip(SkipReason.ACCESS_DENIED)
                        _report(on_skip, entry.path, SkipReason.ACCESS_DENIED)
                        continue
                    except OSError:
                        self.stats.note_skip(SkipReason.ACCESS_DENIED)
                        continue

                    if is_reparse_point(st):
                        self.stats.note_skip(SkipReason.REPARSE_POINT)
                        _report(on_skip, entry.path, SkipReason.REPARSE_POINT)
                        continue

                    try:
                        entry_is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        self.stats.note_skip(SkipReason.VANISHED)
                        continue

                    if entry_is_dir:
                        reason = self._directory_skip_reason(entry.name, entry.path, st, is_drive)
                        if reason is not None:
                            self.stats.note_skip(reason)
                            _report(on_skip, entry.path, reason)
                            continue
                        stack.append(pathutil.display_path(entry.path))
                        continue

                    candidate = self._make_candidate(entry.name, entry.path, st, root, on_skip)
                    if candidate is not None:
                        self.stats.candidates += 1
                        yield candidate

    # -- decision helpers -------------------------------------------------
    def _directory_skip_reason(
        self, name: str, full_path: str, st: os.stat_result, is_drive_root: bool
    ) -> SkipReason | None:
        folded = name.casefold()
        if folded in C.EXCLUDED_DIR_NAMES:
            return SkipReason.EXCLUDED_DIR
        if is_drive_root and folded in C.EXCLUDED_DRIVE_ROOT_DIRS:
            return SkipReason.EXCLUDED_DIR
        normalized = pathutil.normalized_path(full_path)
        for excluded in self._excluded_norm_dirs:
            if normalized == excluded or normalized.startswith(excluded + pathutil.SEP):
                return SkipReason.APP_DATA
        if has_attribute(st, FILE_ATTRIBUTE_SYSTEM):
            return SkipReason.SYSTEM
        if not self.options.include_hidden_files and has_attribute(
            st, FILE_ATTRIBUTE_HIDDEN
        ):
            return SkipReason.HIDDEN
        return None

    def _make_candidate(
        self,
        name: str,
        full_path: str,
        st: os.stat_result,
        root: str,
        on_skip: Callable[[ScanSkip], None] | None,
    ) -> ScannedFile | None:
        for prefix in C.TEMP_FILE_PREFIXES:
            if name.startswith(prefix):
                self.stats.note_skip(SkipReason.TEMP_FILE)
                return None

        extension = pathutil.extension_of(name)
        if extension in C.EXECUTABLE_EXTENSIONS:
            self.stats.note_skip(SkipReason.EXECUTABLE)
            return None
        if extension not in self.options.extensions:
            self.stats.note_skip(SkipReason.NOT_SUPPORTED)
            return None

        if has_attribute(st, FILE_ATTRIBUTE_SYSTEM):
            self.stats.note_skip(SkipReason.SYSTEM)
            _report(on_skip, full_path, SkipReason.SYSTEM)
            return None
        if not self.options.include_hidden_files and has_attribute(
            st, FILE_ATTRIBUTE_HIDDEN
        ):
            self.stats.note_skip(SkipReason.HIDDEN)
            return None
        if has_attribute(st, FILE_ATTRIBUTE_TEMPORARY):
            self.stats.note_skip(SkipReason.TEMP_FILE)
            return None
        if is_cloud_placeholder(st):
            self.stats.note_skip(SkipReason.CLOUD_PLACEHOLDER)
            _report(on_skip, full_path, SkipReason.CLOUD_PLACEHOLDER)
            return None

        size = int(getattr(st, "st_size", 0) or 0)
        if size == 0:
            self.stats.note_skip(SkipReason.EMPTY)
            return None
        if self.options.max_file_size_bytes and size > self.options.max_file_size_bytes:
            self.stats.note_skip(SkipReason.TOO_LARGE)
            _report(on_skip, full_path, SkipReason.TOO_LARGE)
            return None

        shown = pathutil.display_path(full_path)
        # Defence in depth: even though we never follow links, confirm the
        # candidate really is inside the selected root before indexing it.
        if not pathutil.is_within_root(shown, root):
            self.stats.note_skip(SkipReason.OUTSIDE_ROOT)
            _report(on_skip, full_path, SkipReason.OUTSIDE_ROOT)
            return None

        normalized = pathutil.normalized_path(shown)
        if normalized in self._excluded_norm_dirs:
            self.stats.note_skip(SkipReason.APP_DATA)
            return None

        created = getattr(st, "st_birthtime", None)
        if created is None:
            created = getattr(st, "st_ctime", None)

        return ScannedFile(
            display_path=shown,
            normalized_path=normalized,
            relative_path=pathutil.relative_display_path(shown, root),
            file_name=PureWindowsPath(shown).name,
            extension=extension,
            size_bytes=size,
            created_time=float(created) if created else None,
            modified_time=float(getattr(st, "st_mtime", 0.0) or 0.0),
        )


def _make_cancel(
    cancel: Callable[[], bool] | threading.Event | None,
) -> Callable[[], bool]:
    if cancel is None:
        return lambda: False
    if isinstance(cancel, threading.Event):
        return cancel.is_set
    return cancel


def _report(
    on_skip: Callable[[ScanSkip], None] | None, path: str, reason: SkipReason
) -> None:
    if on_skip is not None:
        on_skip(ScanSkip(display_path=pathutil.display_path(path), reason=reason))
