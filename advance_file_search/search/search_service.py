"""Search execution: hybrid FTS5 retrieval plus bounded local verification.

Pipeline
--------
1. **Candidate retrieval.**  Each query term contributes literal fragments of
   at least 3 characters; those go to the trigram FTS index, which returns
   matching ``content_units`` rows (or ``files`` rows for name search).  All
   fragments of a term must be present (``AND``), and a file must satisfy every
   term.
2. **Fallback retrieval.**  A term shorter than 3 characters cannot use the
   trigram index, so a bounded ``LIKE`` scan over the root's content is used
   instead.  The scan is row-limited and cancellable.
3. **Local verification.**  Case-sensitive matching, whole-word matching and
   ``?``/``*`` wildcards are checked against the stored unit text.  This is
   what makes Thai search behave correctly without a segmentation library.
4. **Snippets and ranking.**  Snippets are generated locally with exact
   highlight offsets, then results are scored and sorted.

Every SQL statement is parameterized; the only text interpolated into SQL is a
sort direction chosen from a closed enum.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from advance_file_search.core import constants as C
from advance_file_search.core import paths as pathutil
from advance_file_search.core.models import (
    Highlight,
    MatchLocation,
    MatchSource,
    SearchFilters,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchScope,
    SortField,
)
from advance_file_search.logging_setup import get_logger
from advance_file_search.search import ranking
from advance_file_search.search.query_parser import (
    ParsedQuery,
    QueryError,
    QueryTerm,
    build_fts_expression,
    name_pattern_for,
    parse_query,
)
from advance_file_search.search.snippets import (
    Snippet,
    build_snippet,
    highlight_name,
    merge_highlights,
    row_context,
)
from advance_file_search.search.wildcard import CompiledPattern, highlight_spans, matches
from advance_file_search.storage.database import (
    Database,
    DatabaseError,
    DatabaseTransientError,
)
from advance_file_search.storage.repositories import Repositories

log = get_logger("search.service")

#: Hard ceiling on candidate content rows examined for one term.
MAX_CANDIDATE_ROWS = 40_000
#: Hard ceiling on rows examined by the short-term LIKE fallback.
MAX_FALLBACK_ROWS = 60_000
#: Maximum files whose content is verified in detail.
MAX_VERIFY_FILES = 4_000
#: Pause before retrying a search that hit a transient database error.
RETRY_DELAY_SECONDS = 0.12

_SORT_COLUMNS: dict[SortField, str] = {
    SortField.NAME: "file_name_folded",
    SortField.TYPE: "extension",
    SortField.SIZE: "size_bytes",
    SortField.MODIFIED: "modified_time",
    SortField.PATH: "normalized_path",
}


#: A snippet shorter than this is padded with the text of the neighbouring
#: units.  One line of a text file, or a one-line paragraph, carries too little
#: context to tell whether a result is the right document.
NEIGHBOUR_CONTEXT_MIN_CHARS = 150

#: How many units on each side may be borrowed for that context.
NEIGHBOUR_CONTEXT_UNITS = 2

#: Unit kinds that are small enough to need it.  Pages already hold plenty of
#: text, and a spreadsheet cell gets its own row context instead.
NEIGHBOUR_CONTEXT_TYPES = frozenset(
    {C.LOC_LINE, C.LOC_PARAGRAPH, C.LOC_TABLE_CELL, C.LOC_HEADER, C.LOC_FOOTER}
)


class SearchCancelled(Exception):
    """Raised internally when a cancellation token is set mid-search."""


@dataclass
class _FileHit:
    """Accumulator for one file while candidates are being collected."""

    file_id: int
    unit_ids: set[int]
    terms_matched: set[int]


class SearchService:
    """Executes searches against the index.

    Safe to use from a worker thread; it acquires its own connection via
    :class:`Database`.  One instance may serve many sequential searches.
    """

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.db: Database = repos.db

    # -- public API -------------------------------------------------------
    def search(
        self,
        request: SearchRequest,
        *,
        cancel: threading.Event | Callable[[], bool] | None = None,
    ) -> SearchResponse:
        """Run one search.  Never raises for query problems."""
        started = time.perf_counter()
        should_cancel = _make_cancel(cancel)
        response = SearchResponse()

        try:
            parsed = parse_query(
                request.query,
                scope=request.scope,
                match_case=request.match_case,
                exact_phrase=request.exact_phrase,
                whole_word=request.whole_word,
            )
        except QueryError as exc:
            response.query_warnings.append(exc.code)
            response.elapsed_ms = (time.perf_counter() - started) * 1000
            return response

        response.query_warnings.extend(parsed.warnings)

        try:
            results = self._execute_with_retry(request, parsed, should_cancel)
        except SearchCancelled:
            response.cancelled = True
            response.elapsed_ms = (time.perf_counter() - started) * 1000
            return response
        except DatabaseError as exc:
            log.warning("search failed | %s", exc)
            response.query_warnings.append("db_error")
            response.elapsed_ms = (time.perf_counter() - started) * 1000
            return response

        response.total_matched_files = len(results)
        ranking.finalize_scores(results)
        ordered = self._apply_sort(results, request)

        offset = max(0, request.offset)
        limit = max(1, min(request.limit or C.DEFAULT_RESULT_LIMIT, C.MAX_RESULT_LIMIT))
        response.results = ordered[offset : offset + limit]
        response.truncated = len(ordered) > offset + limit
        # Existence is confirmed only for the page actually shown, so a stale
        # index does not cost one stat call per matched file.
        self._mark_existence(response.results)
        response.elapsed_ms = (time.perf_counter() - started) * 1000

        # Only aggregate counters are logged: never the query text, never a
        # snippet, never a matched path.
        log.debug(
            "search complete | terms=%d files=%d returned=%d verify=%s | %.1f ms",
            len(parsed.terms),
            response.total_matched_files,
            len(response.results),
            parsed.needs_local_verification,
            response.elapsed_ms,
        )
        return response

    @staticmethod
    def _mark_existence(results: list[SearchResult]) -> None:
        """Flag results whose original file is no longer on disk.

        The UI uses this to show a missing-file state and disable Open File /
        Reveal in Explorer instead of failing when the user clicks.
        """
        for result in results:
            try:
                result.exists = pathutil.safe_path(result.display_path).is_file()
            except OSError:
                result.exists = False

    def count_indexed_files(self, root_id: int) -> int:
        return self.repos.files.count_for_root(root_id)

    def available_extensions(self, root_id: int) -> list[tuple[str, int]]:
        return self.repos.files.extensions_for_root(root_id)

    # -- execution --------------------------------------------------------
    def _execute_with_retry(
        self,
        request: SearchRequest,
        parsed: ParsedQuery,
        should_cancel: Callable[[], bool],
    ) -> list[SearchResult]:
        """Run the search, retrying once on a transient concurrency failure.

        Searching overlaps indexing by design: pressing Search refreshes the
        index in the background.  While that runs, SQLite can raise
        "database is locked" or "vtable constructor failed" — both are
        momentary, and both used to surface as an empty result list with an
        error message, which is exactly the wrong answer.

        The retry drops this thread's connection first so the second attempt
        re-prepares everything against the current schema.
        """
        try:
            return self._execute(request, parsed, should_cancel)
        except DatabaseTransientError as exc:
            if should_cancel():
                raise SearchCancelled from exc
            log.info("search retrying after a transient database error | %s", exc)
            with contextlib.suppress(DatabaseError):
                self.db.close_thread_connection()
            time.sleep(RETRY_DELAY_SECONDS)
            return self._execute(request, parsed, should_cancel)

    def _execute(
        self,
        request: SearchRequest,
        parsed: ParsedQuery,
        should_cancel: Callable[[], bool],
    ) -> list[SearchResult]:
        root_id = int(request.root_id)
        filters = request.filters or SearchFilters()
        scope = parsed.scope

        name_hits: dict[int, list[Highlight]] = {}
        content_hits: dict[int, _FileHit] = {}

        if scope in (SearchScope.BOTH, SearchScope.NAME_ONLY):
            name_hits = self._search_names(root_id, parsed, filters, should_cancel)
        if scope in (SearchScope.BOTH, SearchScope.CONTENT_ONLY):
            content_hits = self._search_content(root_id, parsed, filters, should_cancel)

        file_ids = set(name_hits) | set(content_hits)
        if not file_ids:
            return []

        rows = self._load_files(root_id, sorted(file_ids), filters)
        results: list[SearchResult] = []
        term_texts = [term.text for term in parsed.terms]
        content_patterns = [term.pattern for term in parsed.terms]

        for row in rows:
            if should_cancel():
                raise SearchCancelled
            file_id = int(row["id"])
            has_name = file_id in name_hits
            hit = content_hits.get(file_id)

            locations: list[MatchLocation] = []
            if hit is not None:
                locations = self._build_locations(
                    row, hit, content_patterns, parsed, should_cancel
                )
                if not locations:
                    # Every candidate unit failed verification: this file is a
                    # false positive for the content part of the query.
                    if not has_name:
                        continue
                    hit = None

            if hit is None and not has_name:
                continue

            source = (
                MatchSource.BOTH
                if (has_name and hit is not None)
                else (MatchSource.NAME if has_name else MatchSource.CONTENT)
            )

            score = 0.0
            if has_name:
                # A wildcard term ("utf8_*") matches the name without matching
                # any of the literal comparisons name_score performs, so the
                # band floor keeps a verified name hit above content hits.
                score = max(
                    score,
                    ranking.name_score(
                        str(row["file_name"]), term_texts, match_case=parsed.match_case
                    )
                    or ranking.SCORE_NAME_SUBSTRING,
                )
            if hit is not None:
                score = max(
                    score,
                    ranking.content_score(
                        phrase_match=any(term.is_phrase for term in parsed.terms),
                        match_count=len(hit.unit_ids),
                    ),
                )

            display = str(row["display_path"])
            results.append(
                SearchResult(
                    file_id=file_id,
                    root_id=root_id,
                    display_path=display,
                    relative_path=str(row["relative_path"]),
                    file_name=str(row["file_name"]),
                    extension=str(row["extension"]),
                    size_bytes=int(row["size_bytes"] or 0),
                    created_time=row["created_time"],
                    modified_time=row["modified_time"],
                    content_status=str(row["content_status"] or ""),
                    match_source=source,
                    score=score,
                    match_count=len(hit.unit_ids) if hit is not None else 0,
                    name_highlights=list(name_hits.get(file_id, ())),
                    locations=locations,
                    exists=True,
                    warning=str(row["error_code"] or ""),
                )
            )
        return results

    # -- name search ------------------------------------------------------
    def _search_names(
        self,
        root_id: int,
        parsed: ParsedQuery,
        filters: SearchFilters,
        should_cancel: Callable[[], bool],
    ) -> dict[int, list[Highlight]]:
        """Find files whose name or relative path matches every term."""
        candidate_ids: set[int] | None = None

        for term in parsed.terms:
            if should_cancel():
                raise SearchCancelled
            expression = build_fts_expression(list(term.fts_fragments))
            if expression:
                ids = self._name_fts_ids(root_id, expression)
            else:
                ids = self._name_like_ids(root_id, term)
            candidate_ids = ids if candidate_ids is None else (candidate_ids & ids)
            if not candidate_ids:
                return {}

        if not candidate_ids:
            return {}

        # Verify against the real name/path, which applies case sensitivity,
        # whole-word and wildcard semantics the index cannot express.
        patterns = [
            name_pattern_for(term, match_case=parsed.match_case) for term in parsed.terms
        ]
        verified: dict[int, list[Highlight]] = {}
        rows = self._load_files(root_id, sorted(candidate_ids), filters)
        for row in rows:
            if should_cancel():
                raise SearchCancelled
            name = str(row["file_name"])
            relative = str(row["relative_path"])
            if not self._all_patterns_match(patterns, (name, relative), parsed.match_case):
                continue
            verified[int(row["id"])] = list(
                highlight_name(name, patterns, match_case=parsed.match_case)
            )
        return verified

    @staticmethod
    def _all_patterns_match(
        patterns: Sequence[CompiledPattern], values: Iterable[str], match_case: bool
    ) -> bool:
        """Every pattern must match at least one of the candidate values."""
        value_list = list(values)
        for pattern in patterns:
            if not any(
                matches(pattern, value, match_case=match_case) for value in value_list
            ):
                return False
        return True

    def _name_fts_ids(self, root_id: int, expression: str) -> set[int]:
        rows = self.db.query_all(
            "SELECT f.id FROM name_fts "
            "JOIN files f ON f.id = name_fts.rowid "
            "WHERE name_fts MATCH ? AND f.root_id = ? LIMIT ?",
            (expression, root_id, MAX_CANDIDATE_ROWS),
        )
        return {int(row["id"]) for row in rows}

    def _name_like_ids(self, root_id: int, term: QueryTerm) -> set[int]:
        """Fallback for terms too short for the trigram index."""
        folded = _like_pattern(term.pattern.raw, fold=True)
        plain = _like_pattern(term.pattern.raw)
        rows = self.db.query_all(
            "SELECT id FROM files WHERE root_id = ? "
            "AND (file_name_folded LIKE ? ESCAPE '\\' "
            "     OR relative_path LIKE ? ESCAPE '\\') LIMIT ?",
            (root_id, folded, plain, MAX_FALLBACK_ROWS),
        )
        return {int(row["id"]) for row in rows}

    # -- content search ---------------------------------------------------
    def _search_content(
        self,
        root_id: int,
        parsed: ParsedQuery,
        filters: SearchFilters,
        should_cancel: Callable[[], bool],
    ) -> dict[int, _FileHit]:
        """Collect candidate content units per file, term by term."""
        per_term: list[dict[int, set[int]]] = []

        for term in parsed.terms:
            if should_cancel():
                raise SearchCancelled
            expression = build_fts_expression(list(term.fts_fragments))
            if expression:
                mapping = self._content_fts_units(root_id, expression)
            else:
                mapping = self._content_like_units(root_id, term)
            if not mapping:
                return {}
            per_term.append(mapping)

        if not per_term:
            return {}

        # A file qualifies only if it matched every term (terms may match in
        # different units, which is the behaviour users expect from a
        # multi-word search across a document).
        common_files = set(per_term[0])
        for mapping in per_term[1:]:
            common_files &= set(mapping)
            if not common_files:
                return {}

        hits: dict[int, _FileHit] = {}
        for file_id in list(common_files)[:MAX_VERIFY_FILES]:
            unit_ids: set[int] = set()
            for mapping in per_term:
                unit_ids |= mapping.get(file_id, set())
            hits[file_id] = _FileHit(
                file_id=file_id,
                unit_ids=unit_ids,
                terms_matched=set(range(len(per_term))),
            )
        return hits

    def _content_fts_units(self, root_id: int, expression: str) -> dict[int, set[int]]:
        rows = self.db.query_all(
            "SELECT cu.id AS unit_id, cu.file_id AS file_id "
            "FROM content_fts "
            "JOIN content_units cu ON cu.id = content_fts.rowid "
            "JOIN files f ON f.id = cu.file_id "
            "WHERE content_fts MATCH ? AND f.root_id = ? "
            "LIMIT ?",
            (expression, root_id, MAX_CANDIDATE_ROWS),
        )
        mapping: dict[int, set[int]] = {}
        for row in rows:
            mapping.setdefault(int(row["file_id"]), set()).add(int(row["unit_id"]))
        return mapping

    def _content_like_units(self, root_id: int, term: QueryTerm) -> dict[int, set[int]]:
        """Bounded LIKE scan for terms shorter than the trigram minimum."""
        like = _like_pattern(term.pattern.raw)
        rows = self.db.query_all(
            "SELECT cu.id AS unit_id, cu.file_id AS file_id "
            "FROM content_units cu "
            "JOIN files f ON f.id = cu.file_id "
            "WHERE f.root_id = ? AND cu.text LIKE ? ESCAPE '\\' "
            "LIMIT ?",
            (root_id, like, MAX_FALLBACK_ROWS),
        )
        mapping: dict[int, set[int]] = {}
        for row in rows:
            mapping.setdefault(int(row["file_id"]), set()).add(int(row["unit_id"]))
        return mapping

    # -- locations and snippets ------------------------------------------
    def _build_locations(
        self,
        file_row: sqlite3.Row,
        hit: _FileHit,
        patterns: list[CompiledPattern],
        parsed: ParsedQuery,
        should_cancel: Callable[[], bool],
    ) -> list[MatchLocation]:
        """Verify candidate units and build their snippets."""
        if not hit.unit_ids:
            return []
        unit_ids = sorted(hit.unit_ids)
        # Read a bounded number of candidate units; the UI shows at most
        # max_snippets_per_file anyway.
        fetch_limit = min(len(unit_ids), C.MAX_SNIPPETS_PER_FILE * 8)
        placeholders = ",".join("?" for _ in unit_ids[:fetch_limit])
        rows = self.db.query_all(
            # Only the number of "?" placeholders is interpolated below; every
            # value is still bound as a parameter.
            "SELECT id, sequence, location_type, location_label, location_json, text "  # noqa: S608
            f"FROM content_units WHERE id IN ({placeholders}) ORDER BY sequence",
            unit_ids[:fetch_limit],
        )

        locations: list[MatchLocation] = []
        for row in rows:
            if should_cancel():
                raise SearchCancelled
            text = str(row["text"] or "")
            # Verification: the trigram index is case-insensitive and
            # substring-only, so confirm the unit really satisfies the query
            # before it is shown as a match.
            if not self._unit_matches(text, patterns, parsed):
                continue
            snippet = build_snippet(text, patterns, match_case=parsed.match_case)
            if snippet is None:
                continue
            location_data = _decode_location(row["location_json"])
            display_text = snippet.display
            highlights = list(snippet.display_highlights())
            location_type = str(row["location_type"])
            if location_type == C.LOC_SHEET_CELL:
                display_text, highlights = self._with_row_context(
                    file_row, row, location_data, snippet, patterns, parsed
                )
            elif (
                location_type in NEIGHBOUR_CONTEXT_TYPES
                and len(display_text) < NEIGHBOUR_CONTEXT_MIN_CHARS
            ):
                display_text, highlights = self._with_neighbour_context(
                    file_row, row, display_text, highlights, patterns, parsed
                )
            locations.append(
                MatchLocation(
                    unit_id=int(row["id"]),
                    sequence=int(row["sequence"]),
                    location_type=str(row["location_type"]),
                    location_label=str(row["location_label"] or ""),
                    location_data=location_data,
                    snippet=display_text,
                    highlights=highlights,
                )
            )
            if len(locations) >= C.MAX_SNIPPETS_PER_FILE:
                break
        return locations

    @staticmethod
    def _unit_matches(
        text: str, patterns: list[CompiledPattern], parsed: ParsedQuery
    ) -> bool:
        """At least one term must match this unit, with full semantics.

        A file qualifies when *all* terms appear somewhere in it; an individual
        unit is shown when *any* term matches it, which is what makes a
        multi-word search list every relevant location.
        """
        return any(
            matches(pattern, text, match_case=parsed.match_case) for pattern in patterns
        )

    def _with_neighbour_context(
        self,
        file_row: sqlite3.Row,
        unit_row: sqlite3.Row,
        display_text: str,
        highlights: list[Highlight],
        patterns: list[CompiledPattern],
        parsed: ParsedQuery,
    ) -> tuple[str, list[Highlight]]:
        """Widen a short snippet using the units around it.

        The units are joined and the snippet is rebuilt over the joined text,
        so the highlight offsets come out right without any translation: the
        snippet builder always recomputes them on the string it returns.

        If anything is missing — the file has one unit, the neighbours are
        empty — the original snippet is returned unchanged.
        """
        sequence = int(unit_row["sequence"])
        rows = self.db.query_all(
            "SELECT sequence, text FROM content_units "
            "WHERE file_id = ? AND sequence BETWEEN ? AND ? "
            "ORDER BY sequence",
            (
                int(file_row["id"]),
                sequence - NEIGHBOUR_CONTEXT_UNITS,
                sequence + NEIGHBOUR_CONTEXT_UNITS,
            ),
        )
        if len(rows) <= 1:
            return display_text, highlights

        joined = " ".join(
            str(neighbour["text"] or "").strip()
            for neighbour in rows
            if str(neighbour["text"] or "").strip()
        )
        if not joined:
            return display_text, highlights

        widened = build_snippet(
            joined,
            patterns,
            match_case=parsed.match_case,
            context_chars=C.SNIPPET_CONTEXT_CHARS * 2,
        )
        if widened is None or len(widened.display) <= len(display_text):
            # The match sits in this unit only, or the join gained nothing.
            return display_text, highlights
        return widened.display, list(widened.display_highlights())

    def _with_row_context(
        self,
        file_row: sqlite3.Row,
        unit_row: sqlite3.Row,
        location_data: dict[str, object],
        snippet: Snippet,
        patterns: list[CompiledPattern],
        parsed: ParsedQuery,
    ) -> tuple[str, list[Highlight]]:
        """Expand a spreadsheet cell match with its row neighbours.

        A matching cell often holds only a number; showing the neighbouring
        cells of the same row makes the hit readable.  Row context is rebuilt
        at search time instead of being stored, so the index never holds a
        second copy of every value.
        """
        row_number = location_data.get("row")
        sheet = location_data.get("sheet")
        cell_text = str(unit_row["text"] or "")
        if not isinstance(row_number, int):
            return snippet.display, list(snippet.display_highlights())

        neighbours = self.db.query_all(
            "SELECT text, location_json FROM content_units "
            "WHERE file_id = ? AND location_type = ? AND id != ? "
            "ORDER BY sequence LIMIT 400",
            (int(file_row["id"]), C.LOC_SHEET_CELL, int(unit_row["id"])),
        )
        same_row: list[str] = []
        for neighbour in neighbours:
            data = _decode_location(neighbour["location_json"])
            if data.get("row") == row_number and data.get("sheet") == sheet:
                same_row.append(str(neighbour["text"] or ""))
            if len(same_row) >= 8:
                break
        if not same_row:
            return snippet.display, list(snippet.display_highlights())

        text = row_context(cell_text, same_row)
        spans: list[tuple[int, int]] = []
        for pattern in patterns:
            spans.extend(
                highlight_spans(pattern, text, match_case=parsed.match_case, limit=16)
            )
        return text, list(merge_highlights(spans))

    # -- file loading and filtering --------------------------------------
    def _load_files(
        self, root_id: int, file_ids: Sequence[int], filters: SearchFilters
    ) -> list[sqlite3.Row]:
        """Load file rows for the given ids, applying metadata filters in SQL."""
        if not file_ids:
            return []
        rows: list[sqlite3.Row] = []
        # Chunked so the IN list stays well inside SQLite's variable limit.
        chunk_size = 400
        for start in range(0, len(file_ids), chunk_size):
            chunk = file_ids[start : start + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            sql = [
                # Placeholders only; the ids travel as bound parameters.
                "SELECT id, display_path, relative_path, file_name, file_name_folded, "  # noqa: S608
                "extension, size_bytes, created_time, modified_time, content_status, "
                "error_code, normalized_path FROM files "
                f"WHERE root_id = ? AND id IN ({placeholders})"
            ]
            params: list[object] = [root_id, *chunk]

            if filters.extensions:
                ext_list = sorted(filters.extensions)
                sql.append(
                    "AND extension IN (" + ",".join("?" for _ in ext_list) + ")"
                )
                params.extend(ext_list)
            if filters.modified_after is not None:
                sql.append("AND modified_time >= ?")
                params.append(float(filters.modified_after))
            if filters.modified_before is not None:
                sql.append("AND modified_time <= ?")
                params.append(float(filters.modified_before))
            if filters.min_size_bytes is not None:
                sql.append("AND size_bytes >= ?")
                params.append(int(filters.min_size_bytes))
            if filters.max_size_bytes is not None:
                sql.append("AND size_bytes <= ?")
                params.append(int(filters.max_size_bytes))
            if filters.subfolder:
                prefix = pathutil.normalized_path(filters.subfolder)
                if prefix:
                    # Escape LIKE metacharacters so a folder containing % or _
                    # does not widen the filter.
                    sql.append("AND normalized_path LIKE ? ESCAPE '\\'")
                    params.append(_escape_like(prefix) + "%")
            rows.extend(self.db.query_all(" ".join(sql), params))
        return rows

    def _apply_sort(
        self, results: list[SearchResult], request: SearchRequest
    ) -> list[SearchResult]:
        field = request.sort_field
        if field is SortField.RELEVANCE:
            ordered = ranking.sort_by_relevance(results)
            return ordered if request.sort_descending else list(reversed(ordered))

        keyfunc = {
            SortField.NAME: lambda r: r.file_name.casefold(),
            SortField.TYPE: lambda r: (r.extension, r.file_name.casefold()),
            SortField.SIZE: lambda r: r.size_bytes,
            SortField.MODIFIED: lambda r: r.modified_time or 0.0,
            SortField.PATH: lambda r: r.display_path.casefold(),
        }.get(field)
        if keyfunc is None:  # pragma: no cover - closed enum
            return results
        return sorted(results, key=keyfunc, reverse=bool(request.sort_descending))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _escape_like(value: str) -> str:
    """Escape ``%``, ``_`` and ``\\`` for a LIKE pattern using ESCAPE '\\'."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _like_pattern(term: str, *, fold: bool = False) -> str:
    """Convert a user term into a LIKE pattern honouring ``*`` and ``?``.

    LIKE is only used for terms too short for the trigram index, and the result
    is always bound as a parameter.  ``fold`` is set only when comparing
    against a pre-casefolded column; SQLite's own LIKE folding is ASCII-only,
    and the final decision is made by the local verification pass anyway.
    """
    escaped = _escape_like(term)
    # Restore the wildcard meaning of * and ? after escaping everything else.
    escaped = escaped.replace("*", "%").replace("?", "_")
    if not escaped.startswith("%"):
        escaped = "%" + escaped
    if not escaped.endswith("%"):
        escaped = escaped + "%"
    return escaped.casefold() if fold else escaped


def _decode_location(raw: object) -> dict[str, object]:
    import json

    try:
        data = json.loads(str(raw or "{}"))
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _make_cancel(
    cancel: threading.Event | Callable[[], bool] | None,
) -> Callable[[], bool]:
    if cancel is None:
        return lambda: False
    if isinstance(cancel, threading.Event):
        return cancel.is_set
    return cancel
