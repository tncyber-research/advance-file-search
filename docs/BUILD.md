# Building Advance File Search

## Prerequisites

* Windows 10/11 64-bit
* Python 3.12 (3.12.10 was used for this build)
* No network access is needed to *run* the application; it is needed once, at
  set-up time, to install the pinned dependencies.

## Set up

```bat
cd D:\PROJECT\Advance_FileSearch
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements.txt` pins every runtime dependency to an exact version.
`requirements-dev.txt` adds pytest and PyInstaller.

## Run from source

```bat
set PYTHONPATH=D:\PROJECT\Advance_FileSearch
.venv\Scripts\python.exe -m advance_file_search.app
```

Add `--debug` for console logging and DEBUG level. Set
`ADVANCE_FILE_SEARCH_DATA_DIR` to use a scratch data directory instead of
`%LOCALAPPDATA%`.

## Tests

```bat
.venv\Scripts\python.exe -m pytest              # everything
.venv\Scripts\python.exe -m pytest -m security  # privacy/security only
.venv\Scripts\python.exe -m pytest -m gui       # Qt widget tests
```

The GUI tests create real windows. They run on a normal desktop session; a
headless agent needs a Windows session with a desktop.

Test documents are generated at run time by `tests/make_fixtures.py`. No real
or confidential document is in this repository. To inspect them:

```bat
.venv\Scripts\python.exe -m tests.make_fixtures tests\fixtures\generated
```

## Third-party licence notices

```bat
.venv\Scripts\python.exe scripts\collect_licenses.py
```

Reads the installed distributions' own metadata and writes `LICENSES\`.
Re-run whenever a dependency version changes. Read `LICENSES\INDEX.txt`
afterwards — it carries the PyMuPDF AGPL notice.

## Regenerate the user manual

The manual ships with the application and is opened from its toolbar. Its
screenshots are captured from the real UI, so regenerate them whenever the
interface changes:

```bat
.venv\Scripts\python.exe scripts\make_manual_graphics.py
.venv\Scripts\python.exe scripts\make_manual_screenshots.py
```

The first writes the SVG infographics; the second drives the application over
a synthetic corpus, captures each screen, and stamps the numbered callout
badges. Badge positions come from live widget geometry, so they follow the
controls rather than needing to be nudged by hand.

The manual explains the main screen a region at a time, so the capture script
also crops bands of the window (`20_area_top` … `23_area_actions`). Those
crops are pasted onto a canvas with a margin, and their badges are built with
`clamp=False` so they sit in that margin instead of on top of a control's own
label.

Output lands in `Manual\images\`. The prose lives in `Manual\index.html`
and is edited directly.

`pytest tests/test_manual.py` checks that every referenced image exists, that
the page pulls nothing from a network, and that each required section is
present.

## Regenerate the project report

`Manual\report.html` is the project report: architecture, tech stack, database
design, test results and revision history. It ships with the build but is
deliberately **not** linked from the application's interface.

Its diagrams are drawn by their own script:

```bat
.venv\Scripts\python.exe scripts\make_report_graphics.py
```

That writes `Manual\images\dia_*.svg`. The script imports its palette and
drawing helpers from `make_manual_graphics.py`, so both documents stay
visually identical; change a colour in one place and everything follows.

The report's screenshots come from the same capture script as the manual's.
The prose lives in `Manual\report.html` and is edited directly, exactly like
the manual.

`pytest tests/test_report.py` checks the same offline rules as the manual,
that every diagram the brief asked for exists and is actually used, and that
the report stays out of the application's UI.

## Build the executable

```bat
.venv\Scripts\python.exe -m PyInstaller build\AdvanceFileSearch.spec --noconfirm
```

Output: `dist\Advance File Search\AdvanceFileSearch.exe`

For a console-enabled debug build:

```bat
set AFS_DEBUG_BUILD=1
.venv\Scripts\python.exe -m PyInstaller build\AdvanceFileSearch.spec --noconfirm
set AFS_DEBUG_BUILD=
```

`onedir` is used deliberately; see
[ADR 0006](decisions/0006-packaging.md). Do not switch to `onefile`.

## Optional: icon and version resource

* `assets\app.ico` — picked up automatically if present.
* `build\version_info.txt` — a PyInstaller version resource, picked up
  automatically if present.

Both are optional; the build works without them.

## Verify the build

```bat
.venv\Scripts\python.exe scripts\verify_build.py "dist\Advance File Search"
```

Checks that the executable exists, that no Qt network or WebEngine DLL was
bundled, that the licence notices shipped, and that the schema file is present.

Then run the manual acceptance pass in
[SECURITY.md § 11](SECURITY.md#11-release-checklist).

## Clean-machine test

Copy `dist\Advance File Search\` to a Windows 10/11 machine **without Python
installed**, then:

1. double-click `AdvanceFileSearch.exe` — it must start with no console window;
2. select a local folder, create the index;
3. search Thai and English text;
4. open a result and reveal it in Explorer;
5. close and restart, confirm the index is still there;
6. update the index;
7. confirm no network connection was attempted;
8. delete the program folder and confirm the index under
   `%LOCALAPPDATA%\Advance File Search\` remains (it is user data and is not
   removed by deleting the program).
