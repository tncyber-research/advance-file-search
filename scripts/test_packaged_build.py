"""Acceptance test for a packaged build.

    python scripts\\test_packaged_build.py "dist\\Advance File Search"

Run this with the **system** Python, not the build virtual environment: the
packaged application must not need anything from the build environment, and
running it from outside proves that.

Covers handoff §20.5 (packaging tests) and the automatable parts of §2.8
(offline acceptance).  The remaining manual steps — watching the process with
a network monitor, and clicking through the UI on a clean machine — are listed
in docs/SECURITY.md § 11.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FAILURES: list[str] = []

# The self-test echoes Thai file names and locations.  A Windows console on a
# Thai system is cp874, which cannot encode every character that comes back, so
# printing one would abort the run.  Replace the unencodable characters instead:
# the checks are what matter here, not the glyphs.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - redirected output
        pass


def check(label: str, ok: bool, extra: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} {extra}".rstrip())
    if not ok:
        FAILURES.append(label)
    return ok


def build_corpus(root: Path) -> None:
    """Synthetic Thai and English documents, written fresh for this run."""
    root.mkdir(parents=True, exist_ok=True)
    docs = root / "เอกสาร"
    docs.mkdir(exist_ok=True)
    (docs / "thai_budget.txt").write_text(
        "งบประมาณครุภัณฑ์ประจำปี ๒๕๖๘ ของสำนักงานอธิการบดี\n"
        "Annual equipment budget report for fiscal year 2568.\n"
        "packaged_needle marker line\n",
        encoding="utf-8",
    )
    (docs / "cp874_thai.txt").write_bytes(
        "ทดสอบภาษาไทย รหัส cp874 packaged_needle".encode("cp874")
    )
    (docs / "utf16.txt").write_text(
        "UTF-16 รายงานผลการดำเนินงาน packaged_needle", encoding="utf-16"
    )
    # Files that must be refused rather than indexed.
    (docs / "payload.exe").write_bytes(b"MZ" + b"\x00" * 64)
    (docs / "~$lock.docx").write_bytes(b"\x00" * 32)


def run_exe(exe: Path, args: list[str], data_dir: Path, timeout: int = 300):
    env = dict(os.environ)
    env["ADVANCE_FILE_SEARCH_DATA_DIR"] = str(data_dir)
    for leak in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(leak, None)
    # Ask the child for UTF-8 so its Thai output survives the pipe intact.
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [str(exe), *args],
        env=env,
        cwd=str(exe.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    dist = Path(argv[1]).resolve()
    exe = dist / "AdvanceFileSearch.exe"

    print(f"Packaged build acceptance test\n  {dist}\n")
    if not check("executable exists", exe.is_file(), str(exe)):
        return 1

    scratch = Path(tempfile.mkdtemp(prefix="afs-pkg-"))
    corpus = scratch / "corpus"
    data = scratch / "appdata"
    try:
        build_corpus(corpus)

        # -- 1. no Python needed ------------------------------------------
        print("\n1. Runs without the build environment")
        result = run_exe(exe, ["--selftest", str(corpus)], data)
        print("   --- self-test output ---")
        for line in (result.stdout or "").splitlines():
            print("   " + line)
        if result.stderr.strip():
            print("   --- stderr ---")
            for line in result.stderr.splitlines()[:15]:
                print("   " + line)
        check("self-test exits 0", result.returncode == 0, f"rc={result.returncode}")
        check("reports a frozen build", "frozen : True" in result.stdout)
        check("self-test passed", "SELF-TEST PASSED" in result.stdout)

        # -- 2. formats and Thai ------------------------------------------
        print("\n2. Formats and Thai text")
        check("SQLite FTS5 available", "[PASS] SQLite has FTS5" in result.stdout)
        check("trigram tokenizer available", "[PASS] trigram tokenizer" in result.stdout)
        check("files were indexed", "[PASS] at least one file indexed" in result.stdout)
        check("Thai search returned results", "Thai search" in result.stdout)
        check("executables were not indexed", "'.exe'" not in result.stdout)

        # -- 3. GUI start and app data -------------------------------------
        print("\n3. GUI starts and creates its data directory")
        gui_data = scratch / "guidata"
        env = dict(os.environ)
        env["ADVANCE_FILE_SEARCH_DATA_DIR"] = str(gui_data)
        env.pop("PYTHONPATH", None)
        process = subprocess.Popen([str(exe)], env=env, cwd=str(dist))
        log = gui_data / "logs" / "application.log"
        deadline = time.time() + 60
        while time.time() < deadline and not log.exists():
            if process.poll() is not None:
                break
            time.sleep(0.5)
        time.sleep(3)
        check("process is running", process.poll() is None)
        check("application data tree created", (gui_data / "index").is_dir())
        check("log file created", log.is_file())

        log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        check("startup logged", "starting" in log_text)
        check("index opened", "index ready" in log_text)
        check("no traceback in the log", "Traceback" not in log_text)

        # -- 4. single instance --------------------------------------------
        print("\n4. Single-instance guard")
        second = subprocess.Popen([str(exe)], env=env, cwd=str(dist))
        time.sleep(8)
        second_log = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        # A refused instance logs "second instance refused" and never reaches
        # "index ready" again; it then waits on a modal message box, which is
        # correct behaviour for a person and simply has to be closed here.
        check(
            "second instance was refused",
            "second instance refused" in second_log,
        )
        check(
            "second instance did not open the index",
            second_log.count("index ready") == 1,
            f"count={second_log.count('index ready')}",
        )
        second.terminate()
        try:
            second.wait(timeout=15)
        except subprocess.TimeoutExpired:
            second.kill()

        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()

        # -- 5. privacy of the log -----------------------------------------
        print("\n5. Log privacy")
        final_log = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        for secret in ("packaged_needle", "งบประมาณครุภัณฑ์", "อธิการบดี"):
            check(f"log does not contain {secret[:18]!r}", secret not in final_log)
        check("log has no document content", "Annual equipment budget" not in final_log)

        # -- 6. no networking binaries -------------------------------------
        print("\n6. No networking capability is bundled")
        names = {p.name.casefold() for p in dist.rglob("*") if p.is_file()}
        for forbidden in (
            "_socket.pyd",
            "_ssl.pyd",
            "libssl-3.dll",
            "libcrypto-3.dll",
            "qt6network.dll",
            "qt6webenginecore.dll",
            "qt6websockets.dll",
        ):
            check(f"{forbidden} absent", forbidden not in names)

        # -- 7. index integrity --------------------------------------------
        print("\n7. Index written by the packaged application")
        db_file = gui_data / "index" / "search_index.sqlite3"
        if check("index database exists", db_file.is_file()):
            connection = sqlite3.connect(str(db_file))
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                check(
                    "schema present",
                    {"roots", "files", "content_units", "index_runs"} <= tables,
                )
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                check("schema version stamped", version >= 1, f"v{version}")
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                check("integrity check", integrity == "ok", integrity)
            finally:
                connection.close()

        # -- 8. distribution contents --------------------------------------
        print("\n8. Distribution contents")
        for relative in ("README.txt", "PRIVACY.txt", "LICENSES/INDEX.txt"):
            check(f"{relative} ships beside the executable", (dist / relative).is_file())
        licences = list((dist / "LICENSES").glob("*.txt")) if (dist / "LICENSES").is_dir() else []
        check("licence notices present", len(licences) >= 8, f"{len(licences)} files")
        check(
            "no .bat or .cmd launcher",
            not list(dist.glob("*.bat")) and not list(dist.glob("*.cmd")),
        )

    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for failure in FAILURES:
            print(f"  - {failure}")
        print("=" * 62)
        return 1
    print("ALL PACKAGED-BUILD CHECKS PASSED")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
