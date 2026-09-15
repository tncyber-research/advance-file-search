# ADR 0008 — Network-path detection and reparse-point policy

**Status:** Accepted · **Date:** 2026-09-11

## Local paths only

Handoff §2.2 requires version 1 to accept only local Windows file-system paths.
`core/security.py` is the single place that decides, and `validate_root()` is
the only entry point. Everything else — the scanner, the coordinator, the shell
helpers, the UI — asks it rather than making its own judgement.

## Check order matters

```
1. URL-ish scheme      →  rejected
2. device namespace    →  rejected   (\\.\PhysicalDrive0, \\?\GLOBALROOT…)
3. UNC form            →  rejected   (\\server\share, \\?\UNC\…)
4. drive letter        →  required
5. GetDriveTypeW       →  must be FIXED, REMOVABLE or RAMDISK
6. exists / is a dir   →  filesystem is touched only now
```

Steps 1–3 run **before the filesystem is touched at all**. That ordering is the
whole point: calling `os.stat()` on `\\evil-server\share` makes Windows attempt
an SMB connection, which is an outbound network connection made by an
application that claims to make none. A test (`test_url_check_happens_before_
filesystem_access`) monkey-patches `os.stat` and `os.path.exists` to raise, then
asserts the hostile paths are still rejected.

## Remote drive detection

Mapped network drives are detected with `GetDriveTypeW`, which reads the local
mount table and does not contact the server. `DRIVE_REMOTE` is refused with a
message naming the drive. `WNetGetConnectionW` is used *only* to show the user
which UNC path the drive points at, for a clearer explanation — the application
never connects to it.

Optical drives (`DRIVE_CDROM`) are refused too: indexing a disc that will be
ejected produces an index full of permanently missing files.

On a non-Windows platform `get_drive_type()` returns `DRIVE_UNKNOWN` rather
than pretending a path is local, so the test suite runs anywhere without the
security checks silently passing.

## Symlinks, junctions and mount points

Directory traversal uses `os.scandir` with `follow_symlinks=False` on every
`stat`, and any entry with `FILE_ATTRIBUTE_REPARSE_POINT` is skipped and
counted.

This one rule covers three separate problems at once:

* **Recursion loops.** A junction pointing at its own ancestor makes a naive
  walk run until the path length limit. A test creates exactly that with
  `mklink /J` and asserts the scan terminates with the right file count.
* **Escaping the selected root.** A link inside the chosen folder can point
  anywhere on the machine. Skipping links means the index cannot contain
  anything outside what the user picked — and every candidate is re-checked
  with `is_within_root()` before insertion regardless.
* **Reaching the network.** A junction can point at a mapped drive, which would
  route around the local-only check entirely.

Windows shortcut files (`.lnk`) are refused by extension as well, so following
one is not possible even in principle.

## Cloud placeholders

Files carrying `FILE_ATTRIBUTE_RECALL_ON_OPEN` or
`FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` — OneDrive-style "online only" files —
are skipped and reported under their own skip reason. Reading one triggers a
download: an outbound network request, initiated by the user's sync client but
caused by us. Skipping them keeps the offline guarantee true in the one case
where the file system would otherwise break it silently.

## Whole-drive scans

Selecting a drive root prompts for confirmation and excludes `Windows`,
`Program Files`, `Program Files (x86)`, `ProgramData`, `PerfLogs`, `MSOCache`,
`$RECYCLE.BIN` and `System Volume Information`. These are defaults, listed in
`core/constants.py` for review rather than buried in the scanner.

The application's own data directory is always excluded, so the index never
indexes itself.
