"""Search behaviour: Thai and English, options, filters, ranking, snippets."""

from __future__ import annotations

import threading
import time

import pytest

from advance_file_search.core import constants as C
from advance_file_search.core.models import (
    MatchSource,
    SearchFilters,
    SearchRequest,
    SearchScope,
    SortField,
)
from advance_file_search.search import ranking
from advance_file_search.search.snippets import (
    build_snippet,
    merge_highlights,
    normalize_for_display,
    row_context,
)
from advance_file_search.search.wildcard import compile_pattern


@pytest.fixture
def svc(search_service, indexed_corpus):
    root, _summary = indexed_corpus
    return search_service, root


def run(svc, query, **kwargs):
    service, root = svc
    return service.search(SearchRequest(query=query, root_id=root.id, **kwargs))


def names(response) -> set[str]:
    return {result.file_name for result in response.results}


# ---------------------------------------------------------------------------
# Thai search — the headline requirement
# ---------------------------------------------------------------------------
def test_thai_word_inside_an_unspaced_run(svc):
    """The reason the index uses a trigram tokenizer.

    "งบประมาณครุภัณฑ์" has no space in it.  A word-boundary tokenizer treats
    the whole run as one token and finds nothing for "งบประมาณ".
    """
    response = run(svc, "งบประมาณ")
    assert response.total_matched_files >= 4
    assert "utf8_thai.txt" in names(response)
    assert "report_thai.docx" in names(response)
    assert "thai.pdf" in names(response)


def test_thai_word_in_the_middle_of_a_run(svc):
    response = run(svc, "ครุภัณฑ์")
    assert response.total_matched_files >= 4
    assert "budget.xlsx" in names(response)


def test_thai_full_phrase(svc):
    response = run(svc, "งบประมาณครุภัณฑ์")
    assert response.total_matched_files >= 3


def test_thai_numerals(svc):
    assert run(svc, "๒๕๖๘").total_matched_files >= 3


def test_arabic_numerals(svc):
    assert run(svc, "2568").total_matched_files >= 3


def test_thai_in_a_worksheet_name_is_reported(svc):
    response = run(svc, "ครุภัณฑ์สำนักงาน")
    xlsx = next(r for r in response.results if r.file_name == "budget.xlsx")
    location = xlsx.best_location
    assert location.location_data["sheet"] == "งบประมาณ 2568"
    assert location.location_data["cell"] == "A2"


def test_thai_file_name_search(repos, search_service, corpus, settings):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    (corpus / "เอกสาร" / "รายงานงบประมาณ.txt").write_text("x content", encoding="utf-8")
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    root = repos.roots.find_by_path(str(corpus))
    response = search_service.search(
        SearchRequest(query="รายงาน", root_id=root.id, scope=SearchScope.NAME_ONLY)
    )
    assert "รายงานงบประมาณ.txt" in {r.file_name for r in response.results}


def test_mixed_thai_and_english(svc):
    response = run(svc, "Budget งบประมาณ")
    assert response.total_matched_files >= 1


def test_number_with_separators(svc):
    assert run(svc, "1,250,000").total_matched_files == 1


# ---------------------------------------------------------------------------
# English search and options
# ---------------------------------------------------------------------------
def test_single_term(svc):
    response = run(svc, "needle")
    assert response.total_matched_files >= 6
    assert all(result.locations for result in response.results)


def test_multiple_terms_require_all(svc):
    both = run(svc, "equipment budget").total_matched_files
    assert both >= 1
    assert run(svc, "equipment nonexistentword").total_matched_files == 0


def test_quoted_phrase_scores_higher_than_loose_terms(svc):
    phrase = run(svc, '"Annual equipment"')
    assert phrase.total_matched_files >= 3
    assert all(r.score >= ranking.SCORE_CONTENT_PHRASE for r in phrase.results)


def test_exact_phrase_option(svc):
    response = run(svc, "annual equipment budget report", exact_phrase=True)
    assert response.total_matched_files >= 3


def test_exact_phrase_rejects_reordered_words(svc):
    assert run(svc, "budget equipment annual", exact_phrase=True).total_matched_files == 0


def test_match_case(svc):
    assert run(svc, "BUDGET", match_case=True).total_matched_files == 0
    assert run(svc, "budget", match_case=True).total_matched_files >= 3
    capitalised = run(svc, "Budget", match_case=True)
    assert capitalised.total_matched_files >= 1
    assert "utf8_thai.txt" in names(capitalised)


def test_match_case_off_is_insensitive(svc):
    assert run(svc, "BUDGET").total_matched_files >= 3


def test_whole_word(svc):
    assert run(svc, "budget", whole_word=True).total_matched_files >= 3
    assert run(svc, "udge", whole_word=True).total_matched_files == 0


def test_wildcard_star(svc):
    assert run(svc, "bud*et").total_matched_files >= 3
    assert run(svc, "*ครุภัณฑ์*").total_matched_files >= 4


def test_wildcard_question(svc):
    assert run(svc, "need?e").total_matched_files >= 6
    assert run(svc, "need??e").total_matched_files == 0


def test_wildcard_on_file_names(svc):
    response = run(svc, "utf8_*", scope=SearchScope.NAME_ONLY)
    assert names(response) == {"utf8_thai.txt", "utf8_bom.txt"}


def test_short_term_uses_the_scan_fallback(svc):
    response = run(svc, "งบ")
    assert "short_term_scan" in response.query_warnings
    assert response.total_matched_files >= 4


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------
def test_name_only_scope(svc):
    response = run(svc, "thai", scope=SearchScope.NAME_ONLY)
    assert response.total_matched_files >= 3
    assert all(r.match_source is MatchSource.NAME for r in response.results)
    assert all(not r.locations for r in response.results)


def test_content_only_scope(svc):
    response = run(svc, "thai", scope=SearchScope.CONTENT_ONLY)
    # No fixture contains the word "thai" in its text, only in file names.
    assert response.total_matched_files == 0


def test_both_scope_marks_dual_matches(svc):
    response = run(svc, "budget")
    dual = [r for r in response.results if r.match_source is MatchSource.BOTH]
    assert dual, "budget.xlsx matches by name and by content"
    assert dual[0].file_name == "budget.xlsx"


def test_both_source_outranks_content_only(svc):
    response = run(svc, "budget")
    assert response.results[0].match_source is MatchSource.BOTH


# ---------------------------------------------------------------------------
# Locations and snippets
# ---------------------------------------------------------------------------
def test_pdf_reports_a_page(svc):
    response = run(svc, "pdf needle")
    result = next(r for r in response.results if r.file_name == "english.pdf")
    assert result.best_location.location_type == C.LOC_PAGE
    assert result.best_location.location_data["page"] == 2


def test_docx_reports_a_table_cell(svc):
    response = run(svc, "table needle")
    result = next(r for r in response.results if r.file_name == "report_thai.docx")
    cell = next(
        loc for loc in result.locations if loc.location_type == C.LOC_TABLE_CELL
    )
    assert cell.location_data == {"table": 1, "row": 2, "column": 3}


def test_xlsx_reports_a_cell_with_row_context(svc):
    response = run(svc, "ครุภัณฑ์สำนักงาน")
    result = next(r for r in response.results if r.file_name == "budget.xlsx")
    location = result.best_location
    assert location.location_data["cell"] == "A2"
    # A bare cell is meaningless, so its row neighbours are shown.
    assert "45000" in location.snippet


def test_txt_reports_a_line(svc):
    response = run(svc, "metacharacter")
    result = response.results[0]
    assert result.best_location.location_type == C.LOC_LINE
    assert result.best_location.location_data["line"] == 1


def test_snippet_includes_context_around_the_match(svc):
    response = run(svc, "budget")
    result = next(r for r in response.results if r.file_name == "english.pdf")
    snippet = result.best_location.snippet
    assert "budget" in snippet.lower()
    assert len(snippet) > len("budget")
    assert len(snippet) <= C.MAX_SNIPPET_LENGTH + 4


def test_highlights_point_at_the_match(svc):
    response = run(svc, "needle")
    for result in response.results:
        location = result.best_location
        assert location.highlights
        for highlight in location.highlights:
            assert 0 <= highlight.start < highlight.end <= len(location.snippet)
            fragment = location.snippet[highlight.start : highlight.end]
            assert fragment.casefold() == "needle"


def test_name_highlights_point_at_the_match(svc):
    response = run(svc, "thai", scope=SearchScope.NAME_ONLY)
    for result in response.results:
        assert result.name_highlights
        for highlight in result.name_highlights:
            fragment = result.file_name[highlight.start : highlight.end]
            assert fragment.casefold() == "thai"


def test_locations_are_capped_per_file(svc):
    response = run(svc, "row")
    for result in response.results:
        assert len(result.locations) <= C.MAX_SNIPPETS_PER_FILE


def test_match_count_reflects_multiple_locations(svc):
    response = run(svc, "needle")
    docx = next(r for r in response.results if r.file_name == "report_thai.docx")
    assert docx.match_count >= 2
    assert len(docx.locations) >= 2


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def test_extension_filter(svc):
    response = run(svc, "needle", filters=SearchFilters(extensions=frozenset({".xlsx"})))
    assert response.total_matched_files >= 1
    assert all(r.extension == ".xlsx" for r in response.results)


def test_multiple_extension_filter(svc):
    response = run(
        svc, "needle", filters=SearchFilters(extensions=frozenset({".txt", ".docx"}))
    )
    assert {r.extension for r in response.results} <= {".txt", ".docx"}


def test_size_filters(svc):
    baseline = run(svc, "needle").total_matched_files
    large = run(svc, "needle", filters=SearchFilters(min_size_bytes=30_000))
    assert 0 < large.total_matched_files < baseline
    assert all(r.size_bytes >= 30_000 for r in large.results)

    small = run(svc, "needle", filters=SearchFilters(max_size_bytes=1000))
    assert all(r.size_bytes <= 1000 for r in small.results)


def test_date_filters(svc):
    future = time.time() + 86_400
    assert run(svc, "needle", filters=SearchFilters(modified_after=future)).total_matched_files == 0
    past = time.time() - 86_400
    assert run(svc, "needle", filters=SearchFilters(modified_after=past)).total_matched_files > 0
    assert run(svc, "needle", filters=SearchFilters(modified_before=past)).total_matched_files == 0


def test_subfolder_filter(svc, corpus):
    response = run(
        svc,
        "needle",
        filters=SearchFilters(subfolder=str(corpus / "เอกสาร" / "xlsx")),
    )
    assert response.total_matched_files >= 1
    assert all(r.extension == ".xlsx" for r in response.results)


def test_subfolder_filter_escapes_like_metacharacters(svc, corpus):
    """A folder name containing % must not widen the filter."""
    response = run(svc, "needle", filters=SearchFilters(subfolder=str(corpus / "%")))
    assert response.total_matched_files == 0


def test_combined_filters(svc, corpus):
    response = run(
        svc,
        "needle",
        filters=SearchFilters(
            extensions=frozenset({".xlsx"}),
            min_size_bytes=1,
            modified_after=time.time() - 86_400,
            subfolder=str(corpus / "เอกสาร"),
        ),
    )
    assert response.total_matched_files >= 1


# ---------------------------------------------------------------------------
# Sorting, paging and ranking
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "field",
    [
        SortField.RELEVANCE,
        SortField.NAME,
        SortField.TYPE,
        SortField.SIZE,
        SortField.MODIFIED,
        SortField.PATH,
    ],
)
def test_every_sort_field_works(svc, field):
    response = run(svc, "needle", sort_field=field, sort_descending=False)
    assert response.total_matched_files > 0
    assert len(response.results) == response.total_matched_files


def test_sort_by_name_is_ordered(svc):
    response = run(svc, "needle", sort_field=SortField.NAME, sort_descending=False)
    values = [r.file_name.casefold() for r in response.results]
    assert values == sorted(values)


def test_sort_by_size_is_ordered(svc):
    response = run(svc, "needle", sort_field=SortField.SIZE, sort_descending=True)
    values = [r.size_bytes for r in response.results]
    assert values == sorted(values, reverse=True)


def test_paging(svc):
    first = run(svc, "needle", limit=2, offset=0)
    assert len(first.results) == 2
    assert first.truncated
    second = run(svc, "needle", limit=2, offset=2)
    assert not {r.file_id for r in first.results} & {
        r.file_id for r in second.results
    }


def test_result_limit_is_clamped(svc):
    response = run(svc, "needle", limit=C.MAX_RESULT_LIMIT * 10)
    assert len(response.results) <= C.MAX_RESULT_LIMIT


def test_exact_name_match_outranks_content(repos, search_service, corpus, settings):
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    (corpus / "เอกสาร" / "uniqueword.txt").write_text("unrelated body", encoding="utf-8")
    (corpus / "เอกสาร" / "other.txt").write_text("uniqueword in body", encoding="utf-8")
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    root = repos.roots.find_by_path(str(corpus))
    response = search_service.search(SearchRequest(query="uniqueword", root_id=root.id))
    assert response.results[0].file_name == "uniqueword.txt"


def test_ranking_bands():
    assert ranking.name_score("budget.xlsx", ["budget.xlsx"]) == ranking.SCORE_NAME_EXACT
    assert ranking.name_score("budget.xlsx", ["budget"]) == ranking.SCORE_NAME_EXACT_STEM
    assert ranking.name_score("budget_2568.xlsx", ["budget"]) == ranking.SCORE_NAME_PREFIX
    assert ranking.name_score("annual_budget.xlsx", ["budget"]) == ranking.SCORE_NAME_WORD
    assert ranking.name_score("xxbudgetxx.xlsx", ["budget"]) == ranking.SCORE_NAME_SUBSTRING
    assert ranking.name_score("nothing.xlsx", ["budget"]) == 0.0


def test_recency_is_only_a_tie_breaker():
    now = time.time()
    old = now - 365 * 86_400
    assert ranking.recency_bonus(now, now) <= ranking.MAX_RECENCY_BONUS
    assert ranking.recency_bonus(old, now) < ranking.recency_bonus(now, now)
    # A recency bonus can never bridge two score bands.
    assert ranking.MAX_RECENCY_BONUS < (
        ranking.SCORE_CONTENT_PHRASE - ranking.SCORE_CONTENT_TERM
    )


def test_content_score_rewards_more_matches():
    one = ranking.content_score(phrase_match=False, match_count=1)
    many = ranking.content_score(phrase_match=False, match_count=10)
    assert many > one
    assert many - one <= ranking.MAX_MATCH_BONUS


# ---------------------------------------------------------------------------
# Missing files, empty results, cancellation
# ---------------------------------------------------------------------------
def test_missing_file_is_flagged_and_does_not_crash(svc, corpus):
    service, root = svc
    target = corpus / "เอกสาร" / "hostile" / "injection_content.txt"
    target.unlink()
    response = service.search(SearchRequest(query="injection needle", root_id=root.id))
    stale = [r for r in response.results if r.file_name == "injection_content.txt"]
    assert stale and not stale[0].exists


def test_existing_files_are_marked_present(svc):
    response = run(svc, "needle")
    assert all(r.exists for r in response.results)


def test_no_results_for_an_absent_term(svc):
    response = run(svc, "zzzznotpresentzzzz")
    assert response.total_matched_files == 0
    assert not response.results


def test_search_in_an_unknown_root(search_service):
    response = search_service.search(SearchRequest(query="anything", root_id=99999))
    assert response.total_matched_files == 0


def test_cancellation_returns_promptly(svc):
    service, root = svc
    cancel = threading.Event()
    cancel.set()
    response = service.search(
        SearchRequest(query="needle", root_id=root.id), cancel=cancel
    )
    assert response.cancelled
    assert not response.results


def test_search_reports_timing(svc):
    response = run(svc, "needle")
    assert response.elapsed_ms >= 0


def test_search_is_fast_enough(svc):
    """Common queries should return well inside a second."""
    for query in ("needle", "งบประมาณ", "budget report", "ครุภัณฑ์"):
        start = time.perf_counter()
        run(svc, query)
        assert time.perf_counter() - start < 1.0


# ---------------------------------------------------------------------------
# Snippet helpers
# ---------------------------------------------------------------------------
def test_normalize_for_display_collapses_whitespace_only():
    assert normalize_for_display("a \n\t b") == "a b"
    thai = "ที่นี่มีครุภัณฑ์"
    assert normalize_for_display(thai) == thai


def test_build_snippet_windows_around_the_match():
    text = "prefix " * 40 + "NEEDLE" + " suffix" * 40
    snippet = build_snippet(text, [compile_pattern("needle")])
    assert snippet is not None
    assert "NEEDLE" in snippet.text
    assert snippet.leading_ellipsis
    assert snippet.trailing_ellipsis
    assert len(snippet.text) <= C.MAX_SNIPPET_LENGTH


def test_build_snippet_returns_none_when_nothing_matches():
    assert build_snippet("some text", [compile_pattern("absent")]) is None
    assert build_snippet("", [compile_pattern("x")]) is None


def test_build_snippet_preserves_thai_exactly():
    text = "งบประมาณครุภัณฑ์ประจำปี ๒๕๖๘ ของสำนักงานอธิการบดี"
    snippet = build_snippet(text, [compile_pattern("ครุภัณฑ์")])
    assert snippet is not None
    assert "ครุภัณฑ์" in snippet.text
    # Thai combining marks must not be split or reordered.
    fragment = snippet.text[snippet.highlights[0].start : snippet.highlights[0].end]
    assert fragment == "ครุภัณฑ์"


def test_display_highlights_account_for_the_leading_ellipsis():
    text = "x" * 300 + "needle" + "y" * 300
    snippet = build_snippet(text, [compile_pattern("needle")])
    assert snippet is not None
    assert snippet.leading_ellipsis
    display = snippet.display
    for highlight in snippet.display_highlights():
        assert display[highlight.start : highlight.end].casefold() == "needle"


def test_merge_highlights_coalesces_overlaps():
    merged = merge_highlights([(0, 5), (3, 8), (10, 12)])
    assert [(h.start, h.end) for h in merged] == [(0, 8), (10, 12)]
    assert merge_highlights([]) == ()


def test_row_context_joins_and_caps():
    text = row_context("value", ["a", "b", "c"])
    assert text.startswith("value")
    assert "a" in text and "c" in text
    long_text = row_context("x" * 2000, ["y" * 2000])
    assert len(long_text) <= C.MAX_SNIPPET_LENGTH + 1


# ---------------------------------------------------------------------------
# Concurrency with the background indexer
# ---------------------------------------------------------------------------
def test_transient_database_error_is_retried(svc, monkeypatch):
    """Searching overlaps indexing by design, so a momentary SQLite failure
    must not surface as an empty result list."""
    import sqlite3

    from advance_file_search.storage.database import DatabaseTransientError

    service, root = svc
    attempts = {"n": 0}
    original = service._execute

    def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise DatabaseTransientError("vtable constructor failed: content_fts")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_execute", flaky)
    response = service.search(SearchRequest(query="needle", root_id=root.id))
    assert attempts["n"] == 2, "the search should have been retried exactly once"
    assert response.total_matched_files > 0
    assert "db_error" not in response.query_warnings
    del sqlite3


def test_a_persistent_database_error_is_reported(svc, monkeypatch):
    from advance_file_search.storage.database import DatabaseTransientError

    service, root = svc
    attempts = {"n": 0}

    def always_failing(*args, **kwargs):
        attempts["n"] += 1
        raise DatabaseTransientError("database is locked")

    monkeypatch.setattr(service, "_execute", always_failing)
    response = service.search(SearchRequest(query="needle", root_id=root.id))
    assert attempts["n"] == 2, "it should give up after one retry"
    assert "db_error" in response.query_warnings
    assert not response.results


def test_transient_errors_are_classified_as_retryable():
    import sqlite3

    from advance_file_search.storage.database import (
        DatabaseTransientError,
        classify_sqlite_error,
    )

    for message in (
        "database is locked",
        "database table is busy",
        "vtable constructor failed: content_fts",
        "database schema has changed",
    ):
        classified = classify_sqlite_error(sqlite3.OperationalError(message))
        assert isinstance(classified, DatabaseTransientError), message


def test_searching_while_indexing_returns_results(repos, corpus, settings, tmp_path):
    """Run a real indexer against the same database while searching."""
    import threading

    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions
    from advance_file_search.search.search_service import SearchService
    from advance_file_search.storage.database import Database
    from advance_file_search.storage.migrations import open_index
    from advance_file_search.storage.repositories import Repositories

    db_path = tmp_path / "concurrent.sqlite3"
    writer_db, _ = open_index(db_path)
    writer_repos = Repositories.create(writer_db)
    IndexCoordinator(writer_repos, IndexOptions(settings=settings)).run(str(corpus))
    root = writer_repos.roots.find_by_path(str(corpus))

    failures: list[str] = []
    counts: list[int] = []
    stop = threading.Event()

    def reader() -> None:
        reader_db = Database(db_path)
        try:
            service = SearchService(Repositories.create(reader_db))
            while not stop.is_set():
                response = service.search(
                    SearchRequest(query="needle", root_id=root.id)
                )
                if response.query_warnings and "db_error" in response.query_warnings:
                    failures.append("db_error")
                counts.append(response.total_matched_files)
        finally:
            reader_db.close_thread_connection()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for round_number in range(4):
            (corpus / "เอกสาร" / "txt" / f"concurrent{round_number}.txt").write_text(
                f"round {round_number} needle", encoding="utf-8"
            )
            IndexCoordinator(writer_repos, IndexOptions(settings=settings)).run(str(corpus))
    finally:
        stop.set()
        thread.join(timeout=20)

    writer_db.close()
    assert counts, "the reader never completed a search"
    assert not failures, "a search failed while the index was being written"
    assert max(counts) > 0


# ---------------------------------------------------------------------------
# Preview context — a one-line unit is not enough to judge a result by
# ---------------------------------------------------------------------------
@pytest.fixture
def short_lines_corpus(repos, tmp_path, settings):
    """A text file whose lines are each far too short to read on their own."""
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    root_dir = tmp_path / "บันทึก ราชการ"
    root_dir.mkdir()
    (root_dir / "รายงาน การประชุม.txt").write_text(
        "\n".join(
            [
                "ระเบียบวาระที่ ๑ เรื่องที่ประธานแจ้งให้ที่ประชุมทราบ",
                "ที่ประชุมรับทราบการโอนงบประมาณระหว่างหมวดรายจ่าย",
                "งบประมาณ 1,250,000 บาท",
                "มติที่ประชุมเห็นชอบตามที่ฝ่ายเลขานุการเสนอทุกประการ",
                "ปิดประชุมเวลา 16.30 นาฬิกา",
            ]
        ),
        encoding="utf-8",
    )
    IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(root_dir))
    root = repos.roots.find_by_path(str(root_dir))
    assert root is not None
    return root


def _first_location(service, root, query):
    response = service.search(SearchRequest(query=query, root_id=root.id))
    assert response.results, f"nothing matched {query!r}"
    locations = response.results[0].locations
    assert locations, "the match has no location"
    return locations[0]


def test_short_line_match_borrows_its_neighbours(search_service, short_lines_corpus):
    """The matching line is 22 characters; on its own it tells the user nothing."""
    location = _first_location(search_service, short_lines_corpus, "1,250,000")

    assert "1,250,000" in location.snippet
    # Text from the lines above and below is included.
    assert "หมวดรายจ่าย" in location.snippet or "มติที่ประชุม" in location.snippet
    assert len(location.snippet) > 60


def test_borrowed_context_keeps_the_highlight_on_the_match(
    search_service, short_lines_corpus
):
    """Widening must not leave the highlight pointing at the old offsets."""
    location = _first_location(search_service, short_lines_corpus, "1,250,000")

    assert location.highlights, "the match must still be highlighted"
    for highlight in location.highlights:
        assert 0 <= highlight.start < highlight.end <= len(location.snippet)
        assert location.snippet[highlight.start : highlight.end] == "1,250,000"


def test_context_does_not_cross_into_another_file(search_service, short_lines_corpus):
    """Neighbours are read by file, so no other document can leak into a preview."""
    location = _first_location(search_service, short_lines_corpus, "1,250,000")
    assert "ปิดประชุม" in location.snippet or "ระเบียบวาระ" in location.snippet
    assert "needle" not in location.snippet


def test_a_long_unit_is_left_alone(svc):
    """A PDF page already carries plenty of context; nothing is borrowed."""
    service, root = svc
    response = service.search(SearchRequest(query="งบประมาณ", root_id=root.id))
    pages = [
        location
        for result in response.results
        for location in result.locations
        if location.location_type == C.LOC_PAGE
    ]
    if not pages:
        pytest.skip("no PDF page match in this corpus")
    assert all(len(page.snippet) <= C.MAX_SNIPPET_LENGTH for page in pages)
