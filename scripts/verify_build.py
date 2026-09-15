"""Verify a packaged build before it is released.

    .venv\\Scripts\\python.exe scripts\\verify_build.py "dist\\Advance File Search"

Checks, in order of importance:

1. no Qt networking or web-view library was bundled;
2. no known telemetry or HTTP client library was bundled;
3. the executable exists and is a windowed (no-console) binary;
4. the third-party licence notices and README shipped;
5. the SQL schema the application needs at runtime is present;
6. nothing is missing that would force a runtime download.

Exit code 0 means the build passed every check.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Substrings that must not appear in any bundled file name.
FORBIDDEN_BINARIES = (
    "qtnetwork",
    "qtwebengine",
    "qtwebview",
    "qtwebsockets",
    "qtwebchannel",
    "qthttpserver",
    "qtnetworkauth",
    "qtremoteobjects",
    "qtbluetooth",
    "qtnfc",
    "qtpositioning",
    "qtlocation",
)

FORBIDDEN_PACKAGES = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "sentry_sdk",
    "posthog",
    "paramiko",
)

REQUIRED_FILES = (
    "AdvanceFileSearch.exe",
    "LICENSES/INDEX.txt",
    "Manual/index.html",
    "Manual/report.html",
    "README.txt",
    "_internal/advance_file_search/storage/schema.sql",
)

#: PE subsystem value 2 is GUI (no console); 3 is console.
_SUBSYSTEM_GUI = 2


def _read_pe_subsystem(exe: Path) -> int | None:
    """Read the PE optional header's Subsystem field without any dependency."""
    try:
        data = exe.read_bytes()
    except OSError:
        return None
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if pe_offset + 0x60 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        return None
    # COFF header is 20 bytes; Subsystem sits 68 bytes into the optional header.
    subsystem_offset = pe_offset + 4 + 20 + 68
    if subsystem_offset + 2 > len(data):
        return None
    return int.from_bytes(data[subsystem_offset : subsystem_offset + 2], "little")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = Path(argv[1]).resolve()
    if not root.is_dir():
        print(f"FAIL  not a directory: {root}")
        return 2

    failures: list[str] = []
    warnings: list[str] = []
    print(f"Verifying {root}\n")

    # --- bundled files -----------------------------------------------------
    all_files = [p for p in root.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in all_files)
    print(f"  files bundled : {len(all_files):,}")
    print(f"  total size    : {total_bytes / 1024 / 1024:,.1f} MB")

    # --- 1. no network-capable Qt libraries --------------------------------
    offenders = [
        str(p.relative_to(root))
        for p in all_files
        if any(token in p.name.casefold() for token in FORBIDDEN_BINARIES)
    ]
    if offenders:
        failures.append(f"network-capable Qt libraries bundled: {offenders}")
    print(f"  [{'FAIL' if offenders else 'PASS'}] no Qt network/web modules")

    # --- 2. no HTTP or telemetry packages ----------------------------------
    package_offenders = sorted(
        {
            part
            for p in all_files
            for part in p.relative_to(root).parts
            if part.casefold() in FORBIDDEN_PACKAGES
        }
    )
    if package_offenders:
        failures.append(f"network/telemetry packages bundled: {package_offenders}")
    print(f"  [{'FAIL' if package_offenders else 'PASS'}] no HTTP/telemetry packages")

    # --- 3. executable is windowed -----------------------------------------
    exe = root / "AdvanceFileSearch.exe"
    if not exe.is_file():
        failures.append("AdvanceFileSearch.exe is missing")
        print("  [FAIL] executable present")
    else:
        subsystem = _read_pe_subsystem(exe)
        if subsystem is None:
            warnings.append("could not read the PE subsystem field")
            print("  [WARN] windowed build (subsystem unreadable)")
        elif subsystem != _SUBSYSTEM_GUI:
            failures.append(
                f"release build must be windowed; PE subsystem is {subsystem} "
                "(3 = console)"
            )
            print("  [FAIL] windowed build (no console)")
        else:
            print("  [PASS] windowed build (no console)")

    # --- 4 & 5. required files ---------------------------------------------
    for relative in REQUIRED_FILES:
        target = root / relative
        ok = target.is_file()
        if not ok:
            failures.append(f"missing required file: {relative}")
        print(f"  [{'PASS' if ok else 'FAIL'}] {relative}")

    # --- 6. parser backends are present ------------------------------------
    for token, label in (
        ("pymupdf", "PDF support"),
        ("docx", "DOCX support"),
        ("openpyxl", "XLSX support"),
    ):
        present = any(token in str(p).casefold() for p in all_files)
        if not present:
            failures.append(f"{label} was not bundled ({token})")
        print(f"  [{'PASS' if present else 'FAIL'}] {label} bundled")

    # --- Thai codecs --------------------------------------------------------
    # These are selected at run time by the TXT parser, so a static analyser
    # cannot see them; without them Thai text files fail to decode.
    encodings_present = any(
        "encodings" in str(p).casefold() or p.name.casefold().startswith("base_library")
        for p in all_files
    )
    if not encodings_present:
        warnings.append("could not confirm the encodings package was bundled")
    print(f"  [{'PASS' if encodings_present else 'WARN'}] text codecs bundled")

    print()
    for warning in warnings:
        print(f"  WARNING: {warning}")
    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All build checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
