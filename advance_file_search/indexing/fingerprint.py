"""Change detection for incremental index updates.

Strategy (see ``docs/decisions/0004-fingerprint.md``):

* The cheap fingerprint is ``size:mtime_ns:parser_version``.  Together with the
  normalized path this catches essentially every real edit, costs one ``stat``
  per file, and lets an update skip parsing for unchanged files.
* ``parser_version`` is part of the fingerprint so that shipping an improved
  parser automatically re-extracts affected documents.
* A content hash is computed only on request (ambiguous cases and the optional
  verification mode), because hashing every file would read the whole corpus
  on every update and defeat the point of an incremental run.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from advance_file_search.core import constants as C
from advance_file_search.core.paths import safe_path

#: Modification times are compared with this tolerance, in seconds.  FAT32 and
#: some network-copied files quantize mtime to 2 s; a smaller epsilon would
#: report unchanged files as modified forever.
MTIME_EPSILON = 1.0

#: Bytes read per chunk when hashing.
_HASH_CHUNK = 1024 * 1024

#: Bytes sampled from the head and tail for the fast hash.
_FAST_SAMPLE = 256 * 1024


def make_fingerprint(
    size_bytes: int, modified_time: float, *, parser_version: int = C.PARSER_VERSION
) -> str:
    """Build the cheap fingerprint string stored in ``files.fingerprint``."""
    # Whole milliseconds keep the value stable across filesystem round-trips
    # that lose sub-millisecond precision.
    millis = int(round(float(modified_time) * 1000))
    return f"{int(size_bytes)}:{millis}:{int(parser_version)}"


def parse_fingerprint(value: str) -> tuple[int, float, int] | None:
    """Decode a stored fingerprint, or ``None`` if it is unreadable."""
    parts = str(value or "").split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]) / 1000.0, int(parts[2])
    except (TypeError, ValueError):
        return None


def is_unchanged(
    stored_fingerprint: str,
    size_bytes: int,
    modified_time: float,
    *,
    parser_version: int = C.PARSER_VERSION,
) -> bool:
    """True when the stored entry can be reused without re-parsing."""
    stored = parse_fingerprint(stored_fingerprint)
    if stored is None:
        return False
    stored_size, stored_mtime, stored_parser = stored
    if stored_parser != int(parser_version):
        return False
    if stored_size != int(size_bytes):
        return False
    return abs(stored_mtime - float(modified_time)) <= MTIME_EPSILON


def fast_content_hash(path: str | Path) -> str:
    """Hash the head, tail and size of a file.

    Used only to disambiguate a suspicious same-size/same-mtime pair.  It is
    not a security primitive and is never presented as proof of integrity.
    """
    target = safe_path(path)
    digest = hashlib.blake2b(digest_size=16)
    try:
        size = os.path.getsize(target)
        digest.update(str(size).encode("ascii"))
        with open(target, "rb") as handle:
            digest.update(handle.read(_FAST_SAMPLE))
            if size > _FAST_SAMPLE * 2:
                handle.seek(-_FAST_SAMPLE, os.SEEK_END)
                digest.update(handle.read(_FAST_SAMPLE))
    except OSError:
        return ""
    return "fast:" + digest.hexdigest()


def sha256_hash(path: str | Path) -> str:
    """Full SHA-256 of a file, streamed so memory use stays flat."""
    target = safe_path(path)
    digest = hashlib.sha256()
    try:
        with open(target, "rb") as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return ""
    return "sha256:" + digest.hexdigest()
