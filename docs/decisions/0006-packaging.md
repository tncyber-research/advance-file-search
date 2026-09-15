# ADR 0006 — Packaging, Windows integration and long paths

**Status:** Accepted · **Date:** 2026-09-11

## PyInstaller `onedir`, not `onefile`

`onefile` unpacks the entire application into the user's temp directory on
every launch. For a privacy-focused tool that is the wrong default twice over:
it writes the whole program — including its SQLite library — somewhere the user
is not expecting, and it slows startup. `onedir` keeps everything in the
install folder and starts immediately.

Distribution layout:

```
Advance File Search\
├── AdvanceFileSearch.exe
├── _internal\
├── LICENSES\
└── README.txt
```

The user double-clicks the `.exe`. There is no `.bat`, no `.cmd`, no server and
no browser.

## Windowed release, console debug variant

The release build sets `console=False`, so no console window appears.
Setting `AFS_DEBUG_BUILD=1` before building produces an otherwise identical
console build for diagnosis. A privacy test asserts the spec keeps this
distinction.

## Qt modules are excluded, not merely unused

`PySide6.QtNetwork`, `QtWebEngine*`, `QtWebSockets`, `QtHttpServer`,
`QtNetworkAuth`, `QtWebView` and friends are in the spec's `excludes` list.
Not importing them is a code convention; excluding them from the bundle is a
property of the artefact — a stray import in a future change fails at build
time rather than shipping network reach.

`numpy`, `torch`, `onnxruntime`, `PIL` and `cv2` are excluded too. They are
present in the developer's global environment and none of them belong in this
application; excluding them keeps the bundle honest as well as smaller.

## Hidden imports

Parser backends are imported lazily inside each parser (so a missing backend
degrades to a clear message instead of a startup crash), which defeats
PyInstaller's static analysis. They are listed explicitly in `hiddenimports`,
together with the codecs the TXT parser selects at runtime — `cp874`,
`tis_620`, `utf_16`, `utf_32`, `cp1252`. Without those, Thai text files would
fail to decode in the packaged build while working perfectly from source.

## No UPX

`upx=False`. UPX-packed binaries trip antivirus heuristics, which for a tool
that indexes a user's whole documents folder is a support problem with no
compensating benefit.

## Application data location

Mutable data goes to `%LOCALAPPDATA%\Advance File Search\`, never beside the
executable: the program may be installed under `C:\Program Files`, where a
normal user cannot write. `ADVANCE_FILE_SEARCH_DATA_DIR` overrides it, which is
what the test suite uses to stay out of the developer's real index.

## Long paths

Windows paths beyond 260 characters need the `\\?\` extended-length prefix.
`paths.safe_path()` applies it only when needed and only for absolute paths,
and it is used by the scanner, the parsers and the shell helpers. This was
found by a test: without it, a document twelve Thai-named directories deep was
silently reported as *missing* rather than indexed.

Explorer does not understand the `\\?\` form, so **Reveal in Explorer** passes
the plain path and falls back to opening the containing folder when Explorer
declines.

## Windows shell integration

`explorer.exe` is resolved from `%SystemRoot%`, never from `PATH`, and invoked
with an argument **list** through `subprocess.Popen` — never a command string.
A file name containing `" & calc.exe & "` therefore travels as one argument
that no shell ever parses. `shell=True` appears nowhere in the codebase, and a
test asserts that.

Files are opened with `os.startfile`, which takes a path rather than a command
line. Executables and scripts are refused even if one somehow reaches the UI.

## Single instance

Two SQLite writers must never share the index. The guard is an exclusive OS
lock on byte 0 of `instance.lock`, not a PID file: a PID file goes stale after
a crash and leaves the application unstartable, while an OS lock is released by
the kernel when the process dies.

The lock is taken at offset 0 explicitly. An earlier version locked at the
current file position, then wrote the PID — which moved the position, so the
second instance locked a *different* byte and both believed they were alone.
The test for this spawns a real subprocess, because a Windows lock is owned by
the process and a same-process check always succeeds.
