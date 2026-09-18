# Contributing

## Development environment

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
set PYTHONPATH=%CD%
.venv\Scripts\python.exe -m advance_file_search.app --debug
```

Python 3.12 is required: `requirements.txt` pins PySide6 6.11.2, which is
built against a specific CPython ABI. `requirements-dev.txt` also pins `ruff`,
so your results match CI's.

Windows is required for the GUI tests and for anything under `winplat/`.

## Branch and commit workflow

- `main` is the default branch and is expected to build and pass tests.
- Work on a topic branch (`fix/…`, `feat/…`, `docs/…`) and open a pull
  request when the change is not trivially safe.
- Write commit subjects in the imperative, prefixed by type:
  `fix:`, `feat:`, `docs:`, `test:`, `chore:`, `refactor:`.
- Keep a commit to one concern. The reason for a change belongs in the
  message; the mechanics are visible in the diff.
- Do not rewrite published history. No force pushes to `main`.

## Coding conventions

These are the conventions the existing code follows; match them rather than
introducing a second style.

- `from __future__ import annotations` at the top of every module.
- Type hints on public functions; `dataclass` for value objects.
- Line length 100 (`ruff` setting), four-space indentation.
- Module docstrings explain *why* the module exists, and comments explain
  decisions rather than restating the code.
- Never build SQL by concatenating values. Only the number of `?`
  placeholders may be interpolated; every value is bound.
- No new dependency without a reason recorded in an ADR — the offline
  guarantee and the licence position both depend on the dependency list
  staying small.
- User-visible strings go through `advance_file_search.core.i18n.tr()` and
  must exist in **both** the Thai and English tables; a test asserts the two
  tables have identical keys.
- Anything Windows-specific belongs in `winplat/`, so the rest of the code
  stays testable without it.

## Non-negotiables

The project's premise is that documents never leave the machine. A change is
not acceptable if it:

- imports a networking library, or adds one to the distribution;
- writes document text, search terms or snippets into the log;
- accepts a UNC path, mapped network drive or URL as a search root;
- follows a shortcut, junction or symlink while scanning;
- renders document content as markup or HTML;
- executes, modifies, moves or deletes a user's document.

`pytest -m security` exists to catch exactly these.

## Before submitting a change

```bat
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest
```

If the change touches the UI, also regenerate the manual's screenshots and
re-run its tests, since the manual is captured from the running application:

```bat
.venv\Scripts\python.exe scripts\make_manual_screenshots.py
.venv\Scripts\python.exe -m pytest tests\test_manual.py tests\test_report.py
```

If the change touches packaging or anything that ships, rebuild and verify:

```bat
.venv\Scripts\python.exe -m PyInstaller build\AdvanceFileSearch.spec --noconfirm
.venv\Scripts\python.exe scripts\postbuild.py "dist\Advance File Search"
.venv\Scripts\python.exe scripts\verify_build.py "dist\Advance File Search"
python scripts\test_packaged_build.py "dist\Advance File Search"
```

CI runs `ruff check .` and the whole test suite on Windows for every push and
pull request, split into a non-GUI job and a Qt widget job. Both must pass.

State test results honestly in the pull request: what you ran, what passed,
and what you did not run. "Tests pass" without having run them is worse than
saying you skipped them.

## Pull requests

Include:

- what changed and why;
- the user-visible effect, if any;
- the commands you ran and their results;
- anything you deliberately left undone, and why.

Update `CHANGELOG.md` under `Unreleased`, and add an ADR under
`docs/decisions/` when the change involves a trade-off a future maintainer
would otherwise have to re-derive.
