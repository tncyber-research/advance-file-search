"""Query parsing and safe FTS5 expression construction.

Two hard rules:

1. **No user text ever reaches SQL as SQL.**  Every value is bound as a
   parameter.  The FTS5 *expression* is built here, but only from quoted string
   literals: each term is wrapped in double quotes with any internal double
   quote doubled, which is FTS5's own escaping rule.  A quoted FTS5 string is
   inert — operators such as ``AND``, ``OR``, ``NEAR(...)``, ``*`` and ``(``
   inside it are data, not syntax.
2. **Bounded work.**  Query length, term count and wildcard count are all
   capped, and pathological patterns are rejected with a clear message rather
   than being executed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from advance_file_search.core import constants as C
from advance_file_search.core.models import SearchScope
from advance_file_search.search.wildcard import (
    TRIGRAM_MIN_CHARS,
    CompiledPattern,
    PatternTooComplexError,
    compile_pattern,
    count_wildcards,
    has_wildcards,
)


class QueryError(ValueError):
    """The query cannot be executed as written."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: Splits a query into quoted phrases and bare terms.
_TOKEN_RE = re.compile(r'"([^"]*)"|(\S+)')

#: Characters stripped from the edge of a bare term (punctuation a user is
#: unlikely to have meant as part of the word).
_EDGE_PUNCTUATION = " \t\r\n,;:!"

#: Control characters removed from a query before it is used.  A NUL in
#: particular would truncate the value inside SQLite and raise an error rather
#: than simply matching nothing.
_QUERY_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class QueryTerm:
    """One user term with its matching semantics."""

    text: str
    is_phrase: bool
    pattern: CompiledPattern
    #: Literal fragments usable as FTS5 trigram terms.
    fts_fragments: tuple[str, ...] = ()

    @property
    def searchable_by_index(self) -> bool:
        return bool(self.fts_fragments)


@dataclass
class ParsedQuery:
    """A validated query ready for the search service."""

    raw: str
    terms: list[QueryTerm] = field(default_factory=list)
    match_case: bool = False
    whole_word: bool = False
    exact_phrase: bool = False
    scope: SearchScope = SearchScope.BOTH
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.terms

    @property
    def needs_local_verification(self) -> bool:
        """True when FTS candidates must be re-checked against the text.

        The trigram index is case-insensitive substring-only, so anything more
        specific than that is verified locally.
        """
        if self.match_case or self.whole_word:
            return True
        return any(term.pattern.has_wildcards for term in self.terms)

    @property
    def uses_scan_fallback(self) -> bool:
        """True when at least one term is too short for the trigram index."""
        return any(not term.searchable_by_index for term in self.terms)


def escape_fts_literal(text: str) -> str:
    '''Wrap ``text`` as an inert FTS5 string literal.

    FTS5 string syntax is a double-quoted run in which ``""`` denotes a literal
    quote.  Everything else — operators, parentheses, colons, asterisks — loses
    its special meaning inside the quotes.
    '''
    return '"' + str(text).replace('"', '""') + '"'


def build_fts_expression(fragments: list[str]) -> str:
    """Combine literal fragments into an FTS5 AND expression.

    ``fragments`` are literal substrings; a row must contain all of them, so
    they are joined with ``AND``.  Each is escaped, so the result cannot be
    influenced by user syntax.
    """
    usable = [
        fragment for fragment in fragments if len(fragment) >= TRIGRAM_MIN_CHARS
    ]
    if not usable:
        return ""
    return " AND ".join(escape_fts_literal(fragment) for fragment in usable)


def parse_query(
    raw: str,
    *,
    scope: SearchScope = SearchScope.BOTH,
    match_case: bool = False,
    exact_phrase: bool = False,
    whole_word: bool = False,
) -> ParsedQuery:
    """Validate and tokenize a user query.

    Raises :class:`QueryError` with a message code the UI can localize.
    """
    text = str(raw or "")
    if len(text) > C.MAX_QUERY_LENGTH:
        raise QueryError("query_too_long")
    text = _QUERY_CONTROL_RE.sub("", text)
    stripped = text.strip()
    if not stripped:
        raise QueryError("query_empty")

    parsed = ParsedQuery(
        raw=stripped,
        match_case=bool(match_case),
        whole_word=bool(whole_word),
        exact_phrase=bool(exact_phrase),
        scope=scope,
    )

    if exact_phrase:
        # The whole query is one phrase; quotes inside it are literal.
        raw_terms: list[tuple[str, bool]] = [(stripped.replace('"', ""), True)]
    else:
        raw_terms = []
        for match in _TOKEN_RE.finditer(stripped):
            phrase, bare = match.group(1), match.group(2)
            if phrase is not None:
                candidate = phrase.strip()
                if candidate:
                    raw_terms.append((candidate, True))
            elif bare is not None:
                candidate = bare.strip(_EDGE_PUNCTUATION)
                if candidate:
                    raw_terms.append((candidate, False))
        if not raw_terms:
            # The query was only punctuation/quotes; treat it as a literal.
            raw_terms = [(stripped, True)]

    if len(raw_terms) > C.MAX_QUERY_TERMS:
        raise QueryError("query_too_complex")

    total_wildcards = sum(count_wildcards(term) for term, _ in raw_terms)
    if total_wildcards > C.MAX_WILDCARDS_PER_TERM * 2:
        raise QueryError("query_too_complex")

    for term_text, is_phrase in raw_terms:
        try:
            pattern = compile_pattern(
                term_text,
                match_case=parsed.match_case,
                whole_word=parsed.whole_word,
            )
        except PatternTooComplexError as exc:
            raise QueryError("query_too_complex", str(exc)) from exc

        fragments = (
            pattern.indexable_fragments
            if pattern.has_wildcards
            else (
                (term_text,)
                if len(term_text) >= TRIGRAM_MIN_CHARS
                else ()
            )
        )
        parsed.terms.append(
            QueryTerm(
                text=term_text,
                is_phrase=is_phrase,
                pattern=pattern,
                fts_fragments=tuple(fragments),
            )
        )

    if parsed.uses_scan_fallback:
        parsed.warnings.append("short_term_scan")
    return parsed


def name_pattern_for(term: QueryTerm, *, match_case: bool) -> CompiledPattern:
    """Compile a term for file-name matching.

    A file-name term with wildcards is matched against the *whole* name, which
    is what ``report_256?`` means to a user; a term without wildcards is a
    substring match so that typing part of a name still finds it.
    """
    if not has_wildcards(term.text):
        return term.pattern
    try:
        return compile_pattern(term.text, match_case=match_case, anchored=True)
    except PatternTooComplexError:
        return term.pattern
