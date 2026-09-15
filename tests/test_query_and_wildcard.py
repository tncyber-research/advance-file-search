"""Query parsing, FTS escaping and wildcard compilation."""

from __future__ import annotations

import time

import pytest

from advance_file_search.core import constants as C
from advance_file_search.core.models import SearchScope
from advance_file_search.search import wildcard
from advance_file_search.search.query_parser import (
    QueryError,
    build_fts_expression,
    escape_fts_literal,
    parse_query,
)


# ---------------------------------------------------------------------------
# FTS escaping
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("budget", '"budget"'),
        ('say "hi"', '"say ""hi"""'),
        ("NEAR(a b)", '"NEAR(a b)"'),
        ("a OR b", '"a OR b"'),
        ("'; DROP TABLE files; --", '"\'; DROP TABLE files; --"'),
        ("*", '"*"'),
        ("", '""'),
        ('""', '""""""'),
    ],
)
def test_escape_fts_literal(raw, expected):
    assert escape_fts_literal(raw) == expected


def test_escape_makes_every_quote_balanced():
    """An escaped literal always has an even number of quote characters.

    That is what guarantees the surrounding FTS5 expression stays well-formed
    no matter what the user typed.
    """
    for raw in ['a"b', '"', '""', 'x""""y', 'NEAR("a")']:
        assert escape_fts_literal(raw).count('"') % 2 == 0


def test_build_fts_expression_joins_with_and():
    assert build_fts_expression(["budget", "report"]) == '"budget" AND "report"'


def test_build_fts_expression_drops_short_fragments():
    # Trigram needs 3+ characters; shorter fragments cannot use the index.
    assert build_fts_expression(["ab"]) == ""
    assert build_fts_expression(["ab", "budget"]) == '"budget"'


# ---------------------------------------------------------------------------
# Query parsing
# ---------------------------------------------------------------------------
def test_parse_simple_terms():
    parsed = parse_query("equipment budget")
    assert [term.text for term in parsed.terms] == ["equipment", "budget"]
    assert not any(term.is_phrase for term in parsed.terms)


def test_parse_quoted_phrase():
    parsed = parse_query('"annual equipment" budget')
    assert parsed.terms[0].text == "annual equipment"
    assert parsed.terms[0].is_phrase
    assert parsed.terms[1].text == "budget"


def test_exact_phrase_flag_treats_whole_query_as_one_term():
    parsed = parse_query("annual equipment budget", exact_phrase=True)
    assert len(parsed.terms) == 1
    assert parsed.terms[0].text == "annual equipment budget"


def test_parse_thai_term():
    parsed = parse_query("งบประมาณ")
    assert parsed.terms[0].text == "งบประมาณ"
    assert parsed.terms[0].searchable_by_index


def test_short_term_is_not_index_searchable():
    parsed = parse_query("งบ")
    assert not parsed.terms[0].searchable_by_index
    assert parsed.uses_scan_fallback
    assert "short_term_scan" in parsed.warnings


def test_empty_query_raises():
    with pytest.raises(QueryError) as excinfo:
        parse_query("   ")
    assert excinfo.value.code == "query_empty"


def test_over_long_query_raises():
    with pytest.raises(QueryError) as excinfo:
        parse_query("x" * (C.MAX_QUERY_LENGTH + 1))
    assert excinfo.value.code == "query_too_long"


def test_too_many_terms_raises():
    with pytest.raises(QueryError) as excinfo:
        parse_query(" ".join(f"term{i}" for i in range(C.MAX_QUERY_TERMS + 5)))
    assert excinfo.value.code == "query_too_complex"


def test_excessive_wildcards_raise():
    with pytest.raises(QueryError) as excinfo:
        parse_query("a" + "*" * 40)
    assert excinfo.value.code == "query_too_complex"


def test_nul_byte_is_stripped_not_passed_through():
    """A NUL would abort the SQLite parameter, so it is removed up front."""
    parsed = parse_query("bud\x00get")
    assert parsed.terms[0].text == "budget"
    assert "\x00" not in parsed.raw


def test_punctuation_only_query_becomes_a_literal():
    parsed = parse_query("((((")
    assert parsed.terms[0].text == "(((("


def test_needs_local_verification_rules():
    assert not parse_query("budget").needs_local_verification
    assert parse_query("budget", match_case=True).needs_local_verification
    assert parse_query("budget", whole_word=True).needs_local_verification
    assert parse_query("bud*").needs_local_verification


def test_scope_is_carried_through():
    parsed = parse_query("x y z", scope=SearchScope.NAME_ONLY)
    assert parsed.scope is SearchScope.NAME_ONLY


# ---------------------------------------------------------------------------
# Wildcards
# ---------------------------------------------------------------------------
def test_star_matches_any_run():
    pattern = wildcard.compile_pattern("bud*et")
    assert wildcard.matches(pattern, "budget")
    assert wildcard.matches(pattern, "budxxxet")
    assert not wildcard.matches(pattern, "budge")


def test_question_matches_exactly_one():
    pattern = wildcard.compile_pattern("need?e")
    assert wildcard.matches(pattern, "needle")
    assert not wildcard.matches(pattern, "needdle")
    assert not wildcard.matches(pattern, "neede")


def test_anchored_pattern_matches_whole_value():
    pattern = wildcard.compile_pattern("report_256?", anchored=True)
    assert wildcard.matches(pattern, "report_2568")
    assert not wildcard.matches(pattern, "my_report_2568.docx")


def test_unanchored_literal_is_a_substring_match():
    pattern = wildcard.compile_pattern("budget")
    assert pattern.is_literal
    assert wildcard.matches(pattern, "the budget report")


def test_inner_wildcard_still_matches_a_substring():
    """``bud*et`` has no leading or trailing ``*`` but is not end-anchored.

    Regression guard: an earlier version pinned the last segment to the end of
    the text, so this common pattern silently matched nothing.
    """
    pattern = wildcard.compile_pattern("bud*et")
    assert wildcard.matches(pattern, "the budget report")
    thai = wildcard.compile_pattern("งบ*ครุภัณฑ์")
    assert wildcard.matches(thai, "งบประมาณครุภัณฑ์ประจำปี")


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        ("*budget", "annual budget", True),
        ("budget*", "the budget report", True),
        ("a*b*c", "axxbxxc", True),
        ("a*b*c", "acb", False),
        ("*ab*b", "abb", True),
        ("*ab*ab", "abab", True),
        ("*ab*ab", "aab", False),
        ("*", "anything", True),
        ("?", "a", True),
    ],
)
def test_substring_glob_semantics(pattern, text, expected):
    assert wildcard.matches(wildcard.compile_pattern(pattern), text) is expected


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        ("report*", "report_2568.docx", True),
        ("*docx", "report.docx", True),
        ("*docx", "report.docx.bak", False),
        ("utf8_*", "utf8_thai.txt", True),
        ("utf8_*", "my_utf8_thai.txt", False),
        ("*.txt", "a.txt", True),
        ("exact", "exact", True),
        ("exact", "exactly", False),
    ],
)
def test_anchored_glob_semantics(pattern, text, expected):
    compiled = wildcard.compile_pattern(pattern, anchored=True)
    assert wildcard.matches(compiled, text) is expected


def test_case_sensitivity():
    insensitive = wildcard.compile_pattern("budget")
    assert wildcard.matches(insensitive, "BUDGET")
    sensitive = wildcard.compile_pattern("budget", match_case=True)
    assert not wildcard.matches(sensitive, "BUDGET", match_case=True)
    assert wildcard.matches(sensitive, "budget", match_case=True)


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        ("budget", "the budget report", True),
        ("budget", "prebudgeting", False),
        ("udge", "budget", False),
        ("budget", "budget", True),
        ("budget", "(budget)", True),
        # A '*' edge explicitly allows adjacent characters, so that side of
        # the whole-word constraint is not applied.
        ("bud*et", "the budget report", True),
        ("*budget", "prebudget", True),
    ],
)
def test_whole_word(pattern, text, expected):
    compiled = wildcard.compile_pattern(pattern, whole_word=True)
    assert wildcard.matches(compiled, text) is expected


def test_regex_metacharacters_in_a_term_are_literal():
    """A user typing regex syntax must get a literal search, not a regex."""
    pattern = wildcard.compile_pattern("a.c[0-9]+$", whole_word=False, anchored=True)
    assert wildcard.matches(pattern, "a.c[0-9]+$")
    assert not wildcard.matches(pattern, "abc5")


def test_regex_metacharacters_in_content_search():
    pattern = wildcard.compile_pattern("(a|b)+")
    assert wildcard.matches(pattern, "value (a|b)+ here")
    assert not wildcard.matches(pattern, "aaabbb")


def test_literal_fragments_are_longest_first():
    fragments = wildcard.literal_fragments("ab*cdef?gh")
    assert fragments[0] == "cdef"
    assert set(fragments) == {"ab", "cdef", "gh"}


def test_indexable_fragments_filter_short_runs():
    pattern = wildcard.compile_pattern("ab*budget*x")
    assert pattern.indexable_fragments == ("budget",)


def test_pattern_with_only_short_fragments_needs_scan():
    pattern = wildcard.compile_pattern("a*b")
    assert pattern.needs_scan_fallback


@pytest.mark.security
@pytest.mark.parametrize(
    ("pattern", "repeat", "filler"),
    [
        # Regex translation of these takes >20 s; the segment matcher is linear.
        ("a*a*a*a*a*b", 4000, "a"),
        ("*a*a*a*a*a*", 20_000, "a"),
        ("a?a?a?a?a?b", 20_000, "a"),
        ("*" * 6, 50_000, "a"),
        ("งบ*ประมาณ*ครุ*ภัณฑ์*x", 20_000, "งบ"),
    ],
)
def test_pathological_patterns_are_bounded(pattern, repeat, filler):
    """A search box the user can type into must not be able to freeze the app.

    Translating ``*`` to a regex ``.*`` makes ``a*a*a*a*a*b`` take over twenty
    seconds against a few hundred characters.  The segment matcher runs these
    in well under a second against text far larger than any real document
    unit.
    """
    compiled = wildcard.compile_pattern(pattern)
    subject = filler * repeat
    start = time.perf_counter()
    wildcard.matches(compiled, subject)
    assert time.perf_counter() - start < 1.0


@pytest.mark.security
def test_find_all_on_pathological_pattern_is_bounded():
    compiled = wildcard.compile_pattern("a*a*a*b")
    start = time.perf_counter()
    assert wildcard.find_all(compiled, "a" * 5000) == []
    assert time.perf_counter() - start < 1.0


def test_too_many_wildcards_rejected():
    with pytest.raises(wildcard.PatternTooComplexError):
        wildcard.compile_pattern("*" * (C.MAX_WILDCARDS_PER_TERM + 1))


def test_over_long_pattern_rejected():
    with pytest.raises(wildcard.PatternTooComplexError):
        wildcard.compile_pattern("x" * (C.MAX_QUERY_LENGTH + 1))


def test_find_all_returns_non_overlapping_spans():
    pattern = wildcard.compile_pattern("aa")
    spans = wildcard.find_all(pattern, "aaaa")
    assert spans == [(0, 2), (2, 4)]


def test_find_all_is_bounded():
    pattern = wildcard.compile_pattern("a")
    spans = wildcard.find_all(pattern, "a" * 1000, limit=10)
    assert len(spans) == 10


def test_find_all_handles_zero_width_pattern():
    """A pattern of only '*' matches emptily; it must not loop forever."""
    pattern = wildcard.compile_pattern("*")
    spans = wildcard.find_all(pattern, "abc")
    assert len(spans) <= 1


def test_thai_matching_is_substring_based():
    pattern = wildcard.compile_pattern("ครุภัณฑ์")
    # Thai runs together without spaces; a substring match is what users want.
    assert wildcard.matches(pattern, "งบประมาณครุภัณฑ์ประจำปี")


def test_highlight_spans_for_literal_covers_every_occurrence():
    compiled = wildcard.compile_pattern("needle")
    spans = wildcard.highlight_spans(compiled, "needle and needle")
    assert spans == [(0, 6), (11, 17)]


def test_highlight_spans_for_wildcard_marks_the_typed_fragments():
    """``bud*et`` must not paint the whole matched region."""
    compiled = wildcard.compile_pattern("bud*et")
    spans = sorted(wildcard.highlight_spans(compiled, "the budget report"))
    assert spans == [(4, 7), (8, 10)]


def test_highlight_spans_empty_when_pattern_does_not_match():
    compiled = wildcard.compile_pattern("bud*et")
    assert wildcard.highlight_spans(compiled, "nothing here") == []
