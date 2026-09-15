"""Privacy and offline acceptance tests (handoff §2.8, §20.4).

These are release blockers.  They assert, mechanically:

* no module in the application imports a networking library;
* no outbound socket can be opened, even under an injected failure;
* document content and search queries never reach the log;
* temporary files are not used for extracted text and are swept on launch;
* SQL injection and FTS metacharacters cannot alter the database;
* document text is never rendered as markup.
"""

from __future__ import annotations

import ast
import inspect
import re
import socket
import sys
from pathlib import Path

import pytest

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.models import SearchRequest, SearchScope
from advance_file_search.logging_setup import (
    SizeRotatingFileHandler,
    clear_logs,
    configure_logging,
    get_logger,
    safe_path_field,
    set_log_paths_enabled,
)

pytestmark = pytest.mark.security

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "advance_file_search"

#: Modules that would give the application network reach.  Importing any of
#: them is a release blocker, whether or not it is called.
FORBIDDEN_IMPORTS = {
    "socket",
    "ssl",
    "http",
    "http.client",
    "http.server",
    "httplib",
    "urllib",
    "urllib.request",
    "urllib2",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "telnetlib",
    "xmlrpc",
    "xmlrpc.client",
    "asyncio",
    "socketserver",
    "webbrowser",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "paramiko",
    "boto3",
    "google",
    "openai",
    "anthropic",
    "transformers",
    "torch",
    "sentry_sdk",
    "posthog",
    "analytics",
    "mixpanel",
    "segment",
}

#: Unsafe builtins that must not appear anywhere in the application source.
#: Matched with a word boundary so Qt's ``app.exec()`` / ``dialog.exec()`` --
#: which are event loops, not dynamic evaluation -- are not false positives.
FORBIDDEN_CALL_RE = re.compile(
    r"(?<![\w.])(?:eval|exec|compile)\s*\(|"
    r"(?:pickle|marshal|shelve|dill)\s*\.\s*loads?\s*\(|"
    r"os\s*\.\s*(?:system|popen|spawn\w*)\s*\("
)


def _python_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _imports_of(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # pragma: no cover
        pytest.fail(f"{path.name} does not parse: {exc}")
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module)
                names.add(node.module.split(".")[0])
    return names


# ---------------------------------------------------------------------------
# 1. No network-capable code
# ---------------------------------------------------------------------------
def test_no_module_imports_a_networking_library():
    offenders: list[str] = []
    for path in _python_files():
        for name in _imports_of(path) & FORBIDDEN_IMPORTS:
            offenders.append(f"{path.relative_to(PACKAGE_ROOT)} imports {name}")
    assert not offenders, "networking imports found: " + "; ".join(offenders)


def test_no_dangerous_dynamic_evaluation():
    """No eval/exec/compile, no unsafe deserialization, no shell spawning."""
    offenders: list[str] = []
    for path in _python_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith(("#", "*")):
                continue
            match = FORBIDDEN_CALL_RE.search(stripped)
            if match:
                offenders.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{number} {match.group(0)!r}"
                )
    assert not offenders, "unsafe constructs: " + "; ".join(offenders)


def test_no_shell_true_anywhere():
    offenders = [
        str(path.relative_to(PACKAGE_ROOT))
        for path in _python_files()
        if "shell=True" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"shell=True found in {offenders}"


def test_no_http_urls_are_fetched():
    """A URL in a comment is fine; one passed to a fetch call is not."""
    offenders: list[str] = []
    for path in _python_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            lowered = line.lower()
            if "http://" in lowered or "https://" in lowered:
                if any(
                    token in lowered
                    for token in ("urlopen", "get(", "post(", "request(", "fetch(")
                ):
                    offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{number}")
    assert not offenders, f"possible network fetch at {offenders}"


def test_full_workflow_with_sockets_disabled(monkeypatch, repos, corpus, settings):
    """Index and search with any socket creation raising.

    This is the automated form of the offline acceptance test: if any code path
    tried to reach the network, it would fail loudly here.
    """
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
    from advance_file_search.search.search_service import SearchService

    def blocked(*args, **kwargs):
        raise AssertionError("the application attempted to open a socket")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "gethostbyname", blocked, raising=False)

    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    assert summary.indexed > 0

    root = repos.roots.find_by_path(str(corpus))
    service = SearchService(repos)
    for query in ("needle", "งบประมาณ", "budget", "ครุภัณฑ์"):
        assert service.search(SearchRequest(query=query, root_id=root.id)) is not None
    # And again after a restart-equivalent update.
    assert (
        IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus)).status
        is not None
    )


# ---------------------------------------------------------------------------
# 2. Logs contain no document content or queries
# ---------------------------------------------------------------------------
@pytest.fixture
def log_file(tmp_path):
    configure_logging(
        level="DEBUG",
        log_paths=True,
        directory=tmp_path,
        console=False,
        replace=True,
    )
    yield tmp_path / C.LOG_FILE_NAME
    for handler in list(get_logger().handlers):
        handler.flush()


def _read_log(path: Path) -> str:
    for handler in get_logger().handlers:
        handler.flush()
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def test_indexing_does_not_log_document_content(tmp_path, repos, settings, log_file):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    secret = "TOPSECRETPAYLOAD9137"
    root = tmp_path / "docs"
    root.mkdir()
    (root / "notes.txt").write_text(f"line with {secret} inside", encoding="utf-8")

    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(root))
    assert secret not in _read_log(log_file)


def test_searching_does_not_log_the_query_or_snippets(tmp_path, repos, settings, log_file):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
    from advance_file_search.search.search_service import SearchService

    secret = "SENSITIVEQUERYTOKEN4242"
    root = tmp_path / "docs"
    root.mkdir()
    (root / "notes.txt").write_text(f"a document containing {secret}", encoding="utf-8")
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(root))
    record = repos.roots.find_by_path(str(root))

    service = SearchService(repos)
    response = service.search(SearchRequest(query=secret, root_id=record.id))
    assert response.total_matched_files == 1

    contents = _read_log(log_file)
    assert secret not in contents


def test_parser_failures_do_not_log_document_text(tmp_path, repos, settings, log_file):
    """A parser traceback can embed the bytes that broke it."""
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    secret = "CORRUPTFILESECRET5150"
    root = tmp_path / "docs"
    root.mkdir()
    (root / "broken.docx").write_bytes(
        b"PK\x03\x04" + secret.encode() + b"\x00" * 200
    )
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(root))
    assert secret not in _read_log(log_file)


def test_tracebacks_are_never_written(log_file):
    log = get_logger("probe")
    try:
        raise ValueError("boom with DOCUMENTSECRET inside")
    except ValueError:
        log.error("operation failed", exc_info=True)
    contents = _read_log(log_file)
    assert "Traceback" not in contents
    assert "ValueError" in contents


def test_log_records_are_single_line(log_file):
    log = get_logger("probe")
    log.info("first\nsecond\rthird")
    contents = _read_log(log_file).strip()
    assert len([line for line in contents.splitlines() if line.strip()]) == 1


def test_sensitive_records_are_dropped(log_file):
    log = get_logger("probe")
    log.info("this must not appear", extra={"sensitive": True})
    assert "this must not appear" not in _read_log(log_file)


def test_path_logging_can_be_disabled():
    set_log_paths_enabled(False)
    try:
        assert safe_path_field("D:\\secret\\file.txt") == "path=<redacted>"
    finally:
        set_log_paths_enabled(True)
    assert "file.txt" in safe_path_field("D:\\secret\\file.txt")


def test_log_rotation_is_configured(log_file):
    handlers = [
        handler
        for handler in get_logger().handlers
        if isinstance(handler, SizeRotatingFileHandler)
    ]
    assert handlers, "a rotating handler must be installed"
    assert handlers[0].max_bytes == C.LOG_MAX_BYTES
    assert handlers[0].backup_count == C.LOG_BACKUP_COUNT


def test_log_rotation_actually_rotates(tmp_path):
    """Rotation caps growth and keeps exactly backup_count old files."""
    configure_logging(
        level="INFO", log_paths=True, directory=tmp_path, console=False, replace=True
    )
    handler = next(
        h for h in get_logger().handlers if isinstance(h, SizeRotatingFileHandler)
    )
    handler.max_bytes = 2_000
    handler.backup_count = 3

    log = get_logger("probe")
    for index in range(400):
        log.info("padding line %04d %s", index, "x" * 80)
    for h in get_logger().handlers:
        h.flush()

    active = tmp_path / C.LOG_FILE_NAME
    assert active.is_file()
    assert active.stat().st_size <= 2_500, "the active log outgrew its limit"
    backups = sorted(tmp_path.glob(C.LOG_FILE_NAME + ".*"))
    assert 1 <= len(backups) <= 3, f"unexpected backups: {[b.name for b in backups]}"
    assert not (tmp_path / f"{C.LOG_FILE_NAME}.4").exists()


def test_logging_does_not_import_socket():
    """The rotating handler exists so the build can ship without _socket.

    ``logging.handlers`` imports ``socket`` and ``pickle`` at module level to
    define SocketHandler/SysLogHandler.  Importing it here would force those
    binaries into the bundle.
    """
    imports = _imports_of(PACKAGE_ROOT / "logging_setup.py")
    assert "logging.handlers" not in imports
    assert "socket" not in imports
    assert "pickle" not in imports


def test_clear_logs_removes_files(tmp_path):
    configure_logging(
        level="INFO", log_paths=True, directory=tmp_path, console=False, replace=True
    )
    get_logger("probe").info("something")
    for handler in get_logger().handlers:
        handler.flush()
    assert clear_logs(tmp_path) >= 0
    assert not list(tmp_path.glob(C.LOG_FILE_NAME))


# ---------------------------------------------------------------------------
# 3. Temporary files
# ---------------------------------------------------------------------------
def test_indexing_writes_no_temporary_plaintext(repos, corpus, settings):
    """Extraction is in-memory: nothing lands in the temp directory."""
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    temp = pathutil.temp_dir()
    before = set(temp.iterdir()) if temp.exists() else set()
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    after = set(temp.iterdir()) if temp.exists() else set()
    assert after == before


def test_temp_directory_is_swept_on_launch():
    from advance_file_search.app import _cleanup_temp_dir

    temp = pathutil.temp_dir()
    temp.mkdir(parents=True, exist_ok=True)
    leftover = temp / "crash-leftover.tmp"
    leftover.write_text("stale extracted text", encoding="utf-8")
    nested = temp / "stale-dir"
    nested.mkdir(exist_ok=True)
    (nested / "inner.tmp").write_text("more", encoding="utf-8")

    _cleanup_temp_dir()
    assert not leftover.exists()
    assert not nested.exists()


def test_application_data_stays_under_local_appdata():
    """Mutable data must never be written beside the executable."""
    root = str(pathutil.app_data_dir()).casefold()
    for directory in (
        pathutil.index_dir(),
        pathutil.logs_dir(),
        pathutil.settings_dir(),
        pathutil.temp_dir(),
        pathutil.backups_dir(),
    ):
        assert str(directory).casefold().startswith(root)


# ---------------------------------------------------------------------------
# 4. SQL injection and FTS metacharacters
# ---------------------------------------------------------------------------
INJECTION_QUERIES = [
    "'; DROP TABLE files; --",
    '" OR 1=1 --',
    "' UNION SELECT * FROM sqlite_master --",
    "'; DELETE FROM content_units; --",
    "'; UPDATE files SET display_path='x'; --",
    "\\'; DROP TABLE roots; --",
    "1' OR '1'='1",
    "admin'--",
    "'; ATTACH DATABASE 'evil.db' AS evil; --",
    "'; PRAGMA writable_schema=1; --",
]

FTS_METACHARACTER_QUERIES = [
    "NEAR(a b)",
    "NEAR(a b, 5)",
    "a OR b",
    "a AND b NOT c",
    "((((",
    "))))",
    '"""""',
    "*",
    "^",
    "column:value",
    "a*b*c*d*e*f*g*h",
    "-term",
    "{a b}",
    "%",
    "_",
    "\\",
    "[]",
]


@pytest.mark.parametrize("query", INJECTION_QUERIES)
def test_sql_injection_cannot_alter_the_database(svc_state, query):
    service, root, before = svc_state
    response = service.search(SearchRequest(query=query, root_id=root.id))
    assert response is not None
    assert _table_state(service.db) == before


@pytest.mark.parametrize("query", FTS_METACHARACTER_QUERIES)
def test_fts_metacharacters_do_not_crash(svc_state, query):
    service, root, before = svc_state
    for scope in SearchScope:
        response = service.search(
            SearchRequest(query=query, root_id=root.id, scope=scope)
        )
        assert response is not None
        assert not response.query_warnings or all(
            code
            in {"query_too_long", "query_too_complex", "query_empty", "short_term_scan"}
            for code in response.query_warnings
        )
    assert _table_state(service.db) == before


def test_injection_in_a_root_path_is_rejected(repos, settings):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    before = _table_state(repos.db)
    for hostile in (
        "D:\\'; DROP TABLE files; --",
        "D:\\\" OR 1=1 --",
        "'; DELETE FROM roots; --",
    ):
        IndexCoordinator(repos, IndexOptions(settings=settings)).run(hostile)
    assert _table_state(repos.db) == before


def test_injection_in_a_file_name_is_stored_as_data(repos, indexed_corpus, search_service):
    """A hostile file name is indexed as text, not executed as SQL."""
    root, _ = indexed_corpus
    before = _table_state(repos.db)
    response = search_service.search(
        SearchRequest(query="drop table", root_id=root.id, scope=SearchScope.NAME_ONLY)
    )
    assert any("drop table" in r.file_name.casefold() for r in response.results)
    assert _table_state(repos.db) == before


def test_injection_in_file_content_is_stored_as_data(repos, indexed_corpus, search_service):
    root, _ = indexed_corpus
    before = _table_state(repos.db)
    response = search_service.search(
        SearchRequest(query="DROP TABLE files", root_id=root.id)
    )
    assert response.total_matched_files >= 1
    assert _table_state(repos.db) == before


def test_over_long_query_is_refused_not_executed(svc_state):
    service, root, before = svc_state
    response = service.search(
        SearchRequest(query="x" * (C.MAX_QUERY_LENGTH + 500), root_id=root.id)
    )
    assert "query_too_long" in response.query_warnings
    assert not response.results
    assert _table_state(service.db) == before


def test_nul_byte_in_a_query_is_handled(svc_state):
    service, root, before = svc_state
    response = service.search(SearchRequest(query="bud\x00get", root_id=root.id))
    assert "db_error" not in response.query_warnings
    assert _table_state(service.db) == before


def test_database_integrity_after_hostile_queries(svc_state):
    service, root, _before = svc_state
    for query in INJECTION_QUERIES + FTS_METACHARACTER_QUERIES:
        service.search(SearchRequest(query=query, root_id=root.id))
    assert service.db.integrity_check()


@pytest.fixture
def svc_state(search_service, indexed_corpus):
    root, _summary = indexed_corpus
    return search_service, root, _table_state(search_service.db)


def _table_state(db) -> tuple:
    """A fingerprint of the schema and row counts, to prove nothing changed."""
    schema = tuple(
        sorted(
            row[0]
            for row in db.query_all(
                "SELECT name FROM sqlite_master WHERE type IN ('table','trigger','view')"
            )
        )
    )
    counts = tuple(
        int(db.query_value(f"SELECT count(*) FROM {table}", default=0))
        for table in ("roots", "files", "content_units", "index_runs", "app_meta")
    )
    return schema, counts


# ---------------------------------------------------------------------------
# 5. Document content is never rendered as markup
# ---------------------------------------------------------------------------
def test_html_like_content_is_returned_as_plain_text(svc_state):
    service, root, _ = svc_state
    response = service.search(SearchRequest(query="injection needle", root_id=root.id))
    hit = next(r for r in response.results if r.file_name == "html_like.docx")
    snippet = hit.best_location.snippet
    # The snippet is plain text: the tags are still visible as characters, and
    # the delegate paints text rather than parsing markup.
    assert "<script>" in snippet
    assert "<b>bold</b>" in snippet


def test_snippet_highlights_are_offsets_not_markup(svc_state):
    service, root, _ = svc_state
    response = service.search(SearchRequest(query="needle", root_id=root.id))
    for result in response.results:
        for location in result.locations:
            assert "<" not in "".join(
                str(h.start) + str(h.end) for h in location.highlights
            )
            for highlight in location.highlights:
                assert isinstance(highlight.start, int)
                assert isinstance(highlight.end, int)
                assert 0 <= highlight.start < highlight.end <= len(location.snippet)


def test_highlight_ranges_never_overlap(svc_state):
    from advance_file_search.ui.delegates import highlight_ranges_valid

    service, root, _ = svc_state
    response = service.search(SearchRequest(query="needle budget", root_id=root.id))
    for result in response.results:
        for location in result.locations:
            assert highlight_ranges_valid(
                list(location.highlights), len(location.snippet)
            )


# ---------------------------------------------------------------------------
# 6. Executable content
# ---------------------------------------------------------------------------
def test_no_indexed_file_is_executable(repos, indexed_corpus):
    root, _ = indexed_corpus
    rows = repos.db.query_all(
        "SELECT extension FROM files WHERE root_id = ?", (root.id,)
    )
    for row in rows:
        assert row[0] not in C.EXECUTABLE_EXTENSIONS


def test_shell_helper_refuses_executables(fixture_tree):
    from advance_file_search.winplat import windows_shell

    result = windows_shell.open_file(str(fixture_tree / "hostile" / "payload.exe"))
    assert not result.ok


def test_shell_helper_refuses_remote_paths():
    from advance_file_search.winplat import windows_shell

    for hostile in (
        "\\\\server\\share\\doc.pdf",
        "http://example.com/doc.pdf",
        "\\\\.\\PhysicalDrive0",
    ):
        result = windows_shell.open_file(hostile)
        assert not result.ok


def test_explorer_arguments_are_a_list_not_a_command_string():
    """Opening a folder must not be built by string concatenation."""
    from advance_file_search.winplat import windows_shell

    hostile = 'C:\\docs\\file" & calc.exe & ".txt'
    args = windows_shell.explorer_folder_args(hostile)
    assert isinstance(args, list)
    assert len(args) == 2
    assert args[0].casefold().endswith("explorer.exe")
    # The executable is an absolute path, not resolved through PATH.
    assert ":" in args[0]
    # The folder travels as one argument; no shell ever parses it.
    assert "&" not in args[0]


def test_revealing_a_file_builds_no_command_line_at_all():
    """Selecting a file goes through the shell API, not Explorer's switches.

    ``explorer.exe /select,<path>`` has to survive command-line quoting, and it
    does not when the path contains a space — which broke revealing files in
    Thai folders, whose names usually do.
    """
    from advance_file_search.winplat import windows_shell

    source = inspect.getsource(windows_shell)
    tree = ast.parse(source)
    reveal = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "reveal_in_explorer"
    )
    called = {
        ast.unparse(node.func) for node in ast.walk(reveal) if isinstance(node, ast.Call)
    }
    assert not any(name.startswith("subprocess") for name in called), (
        f"reveal still launches a process: {sorted(called)}"
    )
    assert "_select_in_explorer" in called
    assert "SHOpenFolderAndSelectItems" in source


def test_release_build_has_no_console_by_default():
    """The packaged release must be windowed; only an explicit flag adds a console."""
    spec = (PACKAGE_ROOT.parent / "build" / "AdvanceFileSearch.spec").read_text(
        encoding="utf-8"
    )
    assert "console=DEBUG_BUILD" in spec or "console=False" in spec
    assert "DEBUG_BUILD = " in spec


def test_no_frozen_module_pulls_in_a_web_view():
    """A WebView could load remote resources; none may be bundled."""
    offenders: list[str] = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for forbidden in (
            "QtWebEngine",
            "QtWebView",
            "QWebEngineView",
            "QtNetwork",
            "QNetworkAccessManager",
        ):
            if forbidden in text:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {forbidden}")
    assert not offenders, f"web/network Qt modules referenced: {offenders}"


def test_no_remote_font_or_asset_references():
    offenders: list[str] = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8").casefold()
        for forbidden in ("fonts.googleapis", "cdn.", "cdnjs", "jsdelivr", "unpkg"):
            if forbidden in text:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {forbidden}")
    assert not offenders, f"remote asset references: {offenders}"


def test_python_process_imports_no_network_module_after_startup():
    """Nothing the application imports drags in an HTTP client."""
    import subprocess

    script = (
        "import sys;"
        "import advance_file_search.app as _;"
        "bad=[m for m in sys.modules if m.split('.')[0] in "
        "{'requests','httpx','aiohttp','urllib3','websockets','sentry_sdk'}];"
        "print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(PACKAGE_ROOT.parent),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
