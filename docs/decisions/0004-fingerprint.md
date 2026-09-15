# ADR 0004 — Incremental-update fingerprint

**Status:** Accepted · **Date:** 2026-09-11

## Decision

The stored fingerprint is `size:mtime_milliseconds:parser_version`, compared
against a fresh `stat` of the file.

## Why not hash every file

Hashing is the obviously-correct answer and the wrong engineering trade-off
here: it reads every byte of every document on every update, which is precisely
the cost an incremental update exists to avoid. A no-op update over 1,000 files
measures at **0.21 s** using `stat` alone; hashing would make it proportional
to the size of the whole corpus.

`size + mtime` misses only a change that preserves both, which requires either
a deliberate timestamp restore or a same-size edit inside the comparison
tolerance. Both are recoverable through **Rebuild Index**, which the UI offers.

`fingerprint.fast_content_hash()` (head + tail + size) and
`fingerprint.sha256_hash()` are implemented and tested for ambiguous cases and
for a future verification mode, but are not on the default path.

## Tolerance

`MTIME_EPSILON = 1.0` second. FAT32 stores modification times with 2-second
granularity, and files copied between filesystems commonly land a fraction of a
second from their source. A stricter comparison reports unchanged files as
modified on every run, which silently turns every update into a full rebuild.

Milliseconds are stored as an integer, not a float: a float round-trip through
SQLite loses precision inconsistently, while integer milliseconds compare
exactly.

## Parser version

`PARSER_VERSION` is part of the fingerprint. Shipping an improved parser and
bumping that constant automatically re-extracts every affected document on the
next update — no user action, no separate migration, no stale extraction
lingering from an older build.

## What counts as a change

| Situation | Behaviour |
|---|---|
| New file | extracted and inserted |
| Changed size or mtime | old units deleted, re-extracted, replaced atomically |
| Unchanged | parsing skipped entirely; only `last_seen_run_id` is touched |
| Deleted | removed after a **complete** scan |
| Renamed / moved | delete plus add (MVP) |
| Parse failed | previous valid entry is kept until a replacement succeeds |

Deleted-file cleanup runs only after a scan that ran to completion. A cancelled
run never removes anything, so cancelling can never silently shrink the index.
