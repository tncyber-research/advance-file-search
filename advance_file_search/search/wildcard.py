"""Wildcard semantics and bounded pattern matching.

Documented behaviour (handoff §8.3):

* ``*`` matches zero or more characters
* ``?`` matches exactly one character

Why this module does not use ``re``
-----------------------------------
Translating ``*`` into a regular expression is the obvious implementation and
it is **unsafe**.  ``a*a*a*b`` becomes ``a.*a.*a.*b``, and matching that
against a few hundred ``a`` characters sends Python's backtracking engine into
an exponential search: measured at 21 seconds for three wildcards over 600
characters, against document text that can be 200,000 characters long.  A
search box that a user can freely type into must not be able to freeze the
application, so wildcard matching is implemented directly.

The algorithm
-------------
A pattern is split on ``*`` into *segments*.  Each segment contains only
literal characters and ``?``, so a segment can be tested against a fixed-length
window in linear time.  Segments are then matched left to right, each one
searched for at or after the end of the previous match.  Greedy-leftmost
segment matching is the standard correct algorithm for glob patterns — ``*``
absorbs anything, so taking the earliest occurrence of the next segment always
leaves the most text available for the rest of the pattern.

Cost is O(len(text) x len(pattern)) in the worst case with no backtracking
blow-up, and the match position is produced directly, which also gives exact
highlight offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from advance_file_search.core import constants as C

#: Longest literal run considered useful for index lookup.
_MAX_FRAGMENT_LENGTH = 120

#: FTS5 trigram tokenizer needs at least this many characters to match.
TRIGRAM_MIN_CHARS = 3

#: Characters treated as part of a word for whole-word matching.  Python's
#: ``\w`` is Unicode-aware, so Thai letters count as word characters; a
#: whole-word search inside an unspaced Thai run therefore behaves like a
#: substring search, which is the honest behaviour for a script without word
#: separators.
_WORD_RE = re.compile(r"\w", re.UNICODE)


class PatternTooComplexError(ValueError):
    """The pattern exceeds the configured wildcard-complexity limit."""


@dataclass(frozen=True)
class CompiledPattern:
    """A user pattern ready for index lookup and for local verification."""

    raw: str
    #: Literal-and-``?`` runs between the ``*`` wildcards.
    segments: tuple[str, ...]
    #: True when the pattern does not begin with ``*``.
    anchored_start: bool
    #: True when the pattern does not end with ``*``.
    anchored_end: bool
    has_wildcards: bool
    whole_word: bool = False
    #: True when the pattern must match the entire value (file-name patterns).
    anchored: bool = False
    #: Literal substrings (no ``?``), longest first, used as FTS terms.
    fragments: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_literal(self) -> bool:
        """True when the pattern is a plain substring with no wildcards."""
        return not self.has_wildcards

    @property
    def indexable_fragments(self) -> tuple[str, ...]:
        """Fragments long enough for the trigram index."""
        return tuple(f for f in self.fragments if len(f) >= TRIGRAM_MIN_CHARS)

    @property
    def needs_scan_fallback(self) -> bool:
        """True when the index cannot narrow candidates for this pattern."""
        return not self.indexable_fragments


def has_wildcards(text: str) -> bool:
    return "*" in text or "?" in text


def count_wildcards(text: str) -> int:
    return text.count("*") + text.count("?")


def literal_fragments(pattern: str) -> tuple[str, ...]:
    """Literal runs of a pattern, longest first, with no wildcard characters.

    These drive candidate retrieval: any value matching the pattern must
    contain every literal run, so the longest run is the most selective FTS
    term.  ``?`` splits a run because the character at that position is
    unknown.
    """
    parts = [part for part in re.split(r"[*?]+", pattern) if part]
    trimmed = [part[:_MAX_FRAGMENT_LENGTH] for part in parts]
    return tuple(sorted(set(trimmed), key=lambda part: (-len(part), part)))


def compile_pattern(
    pattern: str,
    *,
    match_case: bool = False,
    whole_word: bool = False,
    anchored: bool = False,
) -> CompiledPattern:
    """Prepare a wildcard pattern for matching.

    ``anchored`` makes the pattern match the whole value (used for file-name
    patterns such as ``report_256?``); otherwise it matches anywhere.
    ``match_case`` is not baked in here — it is passed per call — so one
    compiled pattern can serve both a case-sensitive and an insensitive check.
    """
    raw = str(pattern or "")
    if len(raw) > C.MAX_QUERY_LENGTH:
        raise PatternTooComplexError("pattern too long")
    wildcards = count_wildcards(raw)
    if wildcards > C.MAX_WILDCARDS_PER_TERM:
        raise PatternTooComplexError("too many wildcards")
    del match_case  # accepted for call-site symmetry; applied at match time

    segments = tuple(raw.split("*"))
    return CompiledPattern(
        raw=raw,
        segments=segments,
        anchored_start=not raw.startswith("*"),
        anchored_end=not raw.endswith("*"),
        has_wildcards=wildcards > 0,
        whole_word=bool(whole_word),
        anchored=bool(anchored),
        fragments=literal_fragments(raw) if wildcards else (raw[:_MAX_FRAGMENT_LENGTH],),
    )


# ---------------------------------------------------------------------------
# Segment matching
# ---------------------------------------------------------------------------
def _segment_matches_at(segment: str, text: str, position: int, fold: bool) -> bool:
    """Test one ``?``-bearing literal run against a fixed window."""
    end = position + len(segment)
    if end > len(text):
        return False
    for offset, expected in enumerate(segment):
        if expected == "?":
            continue
        actual = text[position + offset]
        if fold:
            if actual.casefold() != expected.casefold():
                return False
        elif actual != expected:
            return False
    return True


def _find_segment(
    segment: str, text: str, start: int, fold: bool, *, limit: int | None = None
) -> int:
    """Leftmost position at or after ``start`` where ``segment`` matches.

    ``limit`` caps the last position tried (used to anchor a final segment to
    the end of the text).  Returns -1 when there is no match.
    """
    if not segment:
        return start if (limit is None or start <= limit) else -1
    last = len(text) - len(segment)
    if limit is not None:
        last = min(last, limit)
    if "?" not in segment:
        # No unknown positions: str.find is a fast C-level scan.
        haystack = text.casefold() if fold else text
        needle = segment.casefold() if fold else segment
        # Case folding can change length for a few code points; fall back to
        # the character-wise scan when that happens so offsets stay correct.
        if len(haystack) == len(text) and len(needle) == len(segment):
            found = haystack.find(needle, start)
            if found == -1 or found > last:
                return -1
            return found
    position = start
    while position <= last:
        if _segment_matches_at(segment, text, position, fold):
            return position
        position += 1
    return -1


#: Returned by :func:`_match_from` when no later start position can succeed.
_EXHAUSTED = "exhausted"


def _match_from(
    compiled: CompiledPattern,
    text: str,
    start: int,
    fold: bool,
    *,
    pin_last_to_end: bool = False,
) -> tuple[int, int] | str | None:
    """Match the pattern with its first literal run beginning at ``start``.

    Returns the ``[span_start, span_end)`` of the matched region, ``None`` when
    this start position fails, or :data:`_EXHAUSTED` when a required segment
    does not occur anywhere after ``start`` — in which case no later start can
    succeed either and the caller stops looking.  That early exit is what keeps
    the overall search linear instead of quadratic.

    ``pin_last_to_end`` requires the final segment to sit flush against the end
    of the text; it is used only for whole-value (file-name) matching.
    """
    segments = compiled.segments
    last_index = len(segments) - 1
    cursor = start
    span_start: int | None = None

    for index, segment in enumerate(segments):
        is_last = index == last_index

        if index == 0:
            if compiled.anchored_start:
                if not _segment_matches_at(segment, text, cursor, fold):
                    return None
                span_start = cursor
                cursor += len(segment)
            # A pattern beginning with '*' has an empty first segment: there
            # is nothing to anchor, the wildcard absorbs the prefix.
            if is_last:
                break
            continue

        if is_last and pin_last_to_end:
            # The final segment must end the text exactly.
            position = len(text) - len(segment)
            if position < cursor or not _segment_matches_at(
                segment, text, position, fold
            ):
                return None
            if span_start is None:
                span_start = position
            return (span_start, position + len(segment))

        position = _find_segment(segment, text, cursor, fold)
        if position == -1:
            # This segment is absent from the rest of the text entirely.
            return _EXHAUSTED
        if span_start is None and segment:
            span_start = position
        cursor = position + len(segment)

    if span_start is None:
        # The pattern is only wildcards: it matches anywhere, emptily.
        span_start = start
    return (span_start, max(span_start, cursor))


def _is_word_char(char: str) -> bool:
    return bool(_WORD_RE.match(char))


def _boundaries_ok(
    text: str, start: int, end: int, *, check_left: bool = True, check_right: bool = True
) -> bool:
    """Whole-word check on a match span.

    A pattern edge that is a ``*`` explicitly allows adjacent characters, so
    that side is not checked — otherwise ``*budget`` with Whole word on could
    never match anything.
    """
    if check_left and start > 0 and _is_word_char(text[start - 1]):
        return False
    return not (check_right and end < len(text) and _is_word_char(text[end]))


def _candidate_starts(compiled: CompiledPattern, text: str, start: int, fold: bool):
    """Yield the positions worth trying as a match start.

    When the pattern begins with a literal run, ``str.find`` jumps straight to
    each plausible start instead of testing every offset.  When it begins with
    ``*`` only one attempt is needed: the wildcard absorbs any prefix, so the
    leftmost search inside :func:`_match_from` already finds the earliest
    possible match.  That is what keeps a pattern like ``*a*a*a*b`` linear
    instead of quadratic in the length of the text.
    """
    if not compiled.anchored_start:
        yield start
        return
    first = compiled.segments[0]
    if not first:
        yield start
        return
    position = start
    while True:
        found = _find_segment(first, text, position, fold)
        if found == -1:
            return
        yield found
        position = found + 1


def matches(compiled: CompiledPattern, value: str, *, match_case: bool = False) -> bool:
    """Test ``value`` against a compiled pattern."""
    return _first_span(compiled, value, match_case=match_case) is not None


def _first_span(
    compiled: CompiledPattern, value: str, *, match_case: bool, start: int = 0
) -> tuple[int, int] | None:
    """Leftmost region of ``value`` matched by the pattern, or ``None``.

    Two modes:

    * **whole value** (``compiled.anchored``, used for file-name patterns) —
      the pattern must cover the entire string;
    * **substring** (the default, used for document content) — the pattern must
      cover some contiguous region.  Here ``anchored_start`` /``anchored_end``
      describe the *pattern*, not the text: ``bud*et`` has neither a leading nor
      a trailing wildcard, yet it still matches "the **budget** report".
    """
    text = str(value or "")
    if not compiled.raw:
        return None
    fold = not match_case

    if compiled.anchored:
        span = _match_from(
            compiled, text, 0, fold, pin_last_to_end=compiled.anchored_end
        )
        if not isinstance(span, tuple):
            return None
        if compiled.anchored_start and span[0] != 0:
            return None
        if compiled.anchored_end and span[1] != len(text):
            return None
        return (0, len(text))

    for position in _candidate_starts(compiled, text, start, fold):
        span = _match_from(compiled, text, position, fold)
        if span is _EXHAUSTED:
            # A required segment is missing from the remaining text; no later
            # start position can match.
            return None
        if not isinstance(span, tuple):
            continue
        if span[0] < start:
            continue
        if compiled.whole_word and not _boundaries_ok(
            text,
            span[0],
            span[1],
            check_left=compiled.anchored_start,
            check_right=compiled.anchored_end,
        ):
            continue
        return span
    return None


def find_all(
    compiled: CompiledPattern,
    value: str,
    *,
    match_case: bool = False,
    limit: int = 64,
) -> list[tuple[int, int]]:
    """Return non-overlapping ``[start, end)`` match ranges within ``value``.

    Bounded by ``limit`` so a pattern matching at every position in a large
    document cannot produce an unbounded list.
    """
    text = str(value or "")
    spans: list[tuple[int, int]] = []
    if not compiled.raw or not text:
        return spans

    if compiled.is_literal and not compiled.whole_word and not compiled.anchored:
        # Fast path for the common case: a plain substring search.
        needle = compiled.raw
        haystack = text if match_case else text.casefold()
        probe = needle if match_case else needle.casefold()
        if len(haystack) != len(text) or len(probe) != len(needle):
            haystack, probe = text, needle  # folding changed length; be exact
        position = haystack.find(probe)
        while position != -1 and len(spans) < limit:
            spans.append((position, position + len(needle)))
            position = haystack.find(probe, position + max(1, len(needle)))
        return spans

    cursor = 0
    while cursor <= len(text) and len(spans) < limit:
        span = _first_span(compiled, text, match_case=match_case, start=cursor)
        if span is None:
            break
        start, end = span
        if end <= start:
            # A pattern of only '*' matches emptily; record one hit and stop
            # rather than looping forever.
            spans.append((start, min(len(text), start + 1)))
            break
        spans.append((start, end))
        cursor = end
    return spans


def _fragment_spans(
    compiled: CompiledPattern, value: str, *, match_case: bool, limit: int
) -> list[tuple[int, int]]:
    """Spans of the pattern's literal runs."""
    text = str(value or "")
    spans: list[tuple[int, int]] = []
    fold = not match_case
    for fragment in compiled.fragments:
        if not fragment:
            continue
        position = 0
        while len(spans) < limit:
            found = _find_segment(fragment, text, position, fold)
            if found == -1:
                break
            spans.append((found, found + len(fragment)))
            position = found + len(fragment)
    return spans


def highlight_spans(
    compiled: CompiledPattern,
    value: str,
    *,
    match_case: bool = False,
    limit: int = 32,
) -> list[tuple[int, int]]:
    """Ranges to paint as matches inside ``value``.

    For a plain term this is every occurrence of the term.  For a wildcard
    pattern it is the *literal runs* the user typed, not the whole matched
    region: ``bud*et`` can span an entire paragraph, and painting the paragraph
    yellow tells the reader nothing.  The pattern is still verified as a whole
    first, so fragments are only highlighted in values that genuinely match.
    """
    if not compiled.has_wildcards:
        return find_all(compiled, value, match_case=match_case, limit=limit)
    if _first_span(compiled, value, match_case=match_case) is None:
        return []
    return _fragment_spans(compiled, value, match_case=match_case, limit=limit)
