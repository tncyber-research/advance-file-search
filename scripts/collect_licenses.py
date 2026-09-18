"""Collect third-party license notices into the LICENSES directory.

Run from the project root with the build virtual environment:

    .venv\\Scripts\\python.exe scripts\\collect_licenses.py

The notices are read from the installed distributions' own metadata; nothing
is downloaded.  The resulting directory is bundled next to the executable and
shown in the About dialog.
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "LICENSES"

#: Distributions shipped inside the application.
BUNDLED = [
    "PySide6",
    "PySide6-Essentials",
    "PySide6-Addons",
    "shiboken6",
    "PyMuPDF",
    "python-docx",
    "openpyxl",
    "et-xmlfile",
    "lxml",
    "typing_extensions",
]

#: Filenames inside a distribution that hold the licence text.
LICENSE_FILE_HINTS = (
    "LICENSE",
    "LICENCE",
    "COPYING",
    "NOTICE",
    "AUTHORS",
)


#: dist-info bookkeeping files that are never licence text.
_METADATA_FILES = {"METADATA", "RECORD", "WHEEL", "INSTALLER", "REQUESTED", "TOP_LEVEL.TXT"}


def _license_texts(distribution: metadata.Distribution) -> list[tuple[str, str]]:
    """Read every licence document the distribution ships.

    ``PackagePath.read_text`` is used rather than ``Distribution.read_text``:
    the latter resolves names relative to the dist-info directory, so passing
    an already-relative path finds nothing.
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in distribution.files or []:
        name = Path(str(entry)).name
        upper = name.upper()
        if upper in _METADATA_FILES or upper in seen:
            continue
        if not any(upper.startswith(hint) for hint in LICENSE_FILE_HINTS):
            continue
        if upper.endswith((".PY", ".PYC", ".SO", ".PYD", ".DLL")):
            continue
        try:
            text = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, TypeError):
            try:
                text = entry.read_text()
            except Exception:  # noqa: BLE001, S112 - one unreadable distribution must not stop the collection
                continue
        if text and text.strip():
            seen.add(upper)
            found.append((name, text))
    return found


def _summary(distribution: metadata.Distribution) -> str:
    meta = distribution.metadata
    lines = [
        f"Package: {meta.get('Name', '?')}",
        f"Version: {distribution.version}",
        f"License: {meta.get('License') or _classifier_license(meta) or 'see below'}",
        f"Home-page: {meta.get('Home-page') or meta.get('Project-URL') or '-'}",
    ]
    return "\n".join(lines)


def _classifier_license(meta) -> str:
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.split("::")[-1].strip()
    return ""


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT.glob("*.txt"):
        stale.unlink()

    written = 0
    missing: list[str] = []
    index_lines = [
        "Third-party components bundled with Advance File Search",
        "=" * 60,
        "",
        "Advance File Search itself performs no network access.  None of the",
        "components below are downloaded at runtime; every one is packaged",
        "inside the application directory.",
        "",
    ]

    for name in BUNDLED:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
            continue

        parts = [_summary(distribution), ""]
        texts = _license_texts(distribution)
        if texts:
            for filename, text in texts:
                parts.append(f"--- {filename} ---")
                parts.append(text.strip())
                parts.append("")
        else:
            parts.append(
                "The distribution does not ship a licence file in its metadata; "
                "the licence named above applies."
            )
            parts.append("")

        target = OUTPUT / f"{distribution.metadata.get('Name', name)}.txt"
        target.write_text("\n".join(parts), encoding="utf-8")
        written += 1
        index_lines.append(
            f"  {distribution.metadata.get('Name', name)} "
            f"{distribution.version} - {target.name}"
        )

    index_lines.extend(
        [
            "",
            "Python itself is distributed under the PSF License Agreement.",
            "SQLite (including the FTS5 extension) is in the public domain.",
            "",
            "Qt / PySide6 notice",
            "-------------------",
            "PySide6 and the Qt libraries it wraps are used here under the GNU",
            "Lesser General Public License v3.  Qt is dynamically linked and its",
            "unmodified shared libraries are shipped in the application folder,",
            "so they can be replaced by the recipient.  The full LGPLv3 text is",
            "available from the Qt Project and the Free Software Foundation.",
            "PySide6's own wheel ships only the commercial-licence reference file,",
            "which is reproduced for completeness and does not apply here.",
            "",
            "PyMuPDF notice - READ BEFORE DISTRIBUTING",
            "----------------------------------------",
            "PyMuPDF is dual licensed: GNU AFFERO GPL v3, or a commercial licence",
            "from Artifex.  The AGPL is strongly copyleft.  If this application is",
            "distributed outside the organisation that built it, either the whole",
            "application must be released under the AGPL with source available, or",
            "a commercial PyMuPDF licence must be obtained.",
            "",
            "If neither is acceptable, the PDF parser is the only module that uses",
            "PyMuPDF (advance_file_search/indexing/parsers/pdf_parser.py) and can",
            "be reimplemented on a permissively licensed library such as pypdf",
            "(BSD-3-Clause) or pdfminer.six (MIT).  See",
            "docs/decisions/0007-pdf-library-licensing.md.",
        ]
    )
    (OUTPUT / "INDEX.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    print(f"wrote {written} notices to {OUTPUT}")
    if missing:
        print(f"not installed (skipped): {', '.join(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
