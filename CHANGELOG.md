# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The application version has stayed at `1.0.0` throughout development: the
entries below are rounds of work completed before any release, not published
versions. Only changes with evidence in the repository are listed.

## [Unreleased]

### Added
- Per-row **Open file** button beside the existing Open-folder button, with a
  fallback to the Windows "Open with" chooser when no program is registered
  for the file type.
- Neighbouring content units are folded into a match preview when the matching
  unit is shorter than 150 characters, so a one-line hit still reads as
  context. Preview grew to four lines; snippet context 90 → 130 characters.
- Illustrated user manual (`Manual/index.html`) and project report
  (`Manual/report.html`), both generated from the running application and
  shipped with the build.
- Repository documentation: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  this changelog, `docs/HANDOFF.md`, `docs/ROADMAP.md`,
  `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `.gitignore`.

### Changed
- Revealing a file in Explorer now calls `SHOpenFolderAndSelectItems` directly
  instead of launching `explorer.exe /select,<path>`.
- Open-folder button reduced to a fixed 30 × 24 px icon; the column no longer
  grows the button with it.
- The toolbar's About button became **User Manual**; About moved into the
  index menu, where it still carries the privacy statement and licence
  notices.
- Manual typography raised to a 16 px floor after 14 px proved too small to
  read comfortably.
- Ruff configuration gained per-file ignores for the pytest fixture-import
  idiom and for scripts whose purpose is to launch a subprocess.

### Fixed
- **Reveal-in-Explorer opened the wrong folder whenever the path contained a
  space.** `subprocess` quoted the whole `/select,<path>` argument, so Explorer
  no longer recognised its own switch. It looked like a Thai-text problem
  because Thai folder names usually contain spaces; an English path with a
  space failed identically.
- **A search running while the index refreshed in the background could fail**
  with `vtable constructor failed: content_fts` and return an empty result
  list. Transient SQLite errors are now classified and retried once.
- The About dialog's Close button showed Qt's English label in the Thai
  interface.
- A settings checkbox labelled "advanced filters" actually controlled whether
  the filters are remembered between sessions; it now says so.
- The details panel clipped long paths, dropping whole folder components.
- The Match column collapsed to a few characters once the base font and the
  details panel grew.
- 49 lint findings fixed automatically by `ruff check --fix`; the four
  security-rule false positives (error-code constants named `…PASSWORD…`, and
  SQL placeholder counting) are now annotated with the reason.

### Security
- Revealing a file builds no command line at all, removing a whole class of
  quoting question; a test asserts that `reveal_in_explorer` calls no
  `subprocess` function.
