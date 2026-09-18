"""Snippet extraction and highlight ranges.

Snippets are generated here, not by FTS5's ``snippet()``, for three reasons:

* the trigram tokenizer highlights trigram spans rather than the user's term,
  which reads wrong;
* we need exact character offsets to highlight safely in Qt without injecting
  document content into markup;
* snippets must be produced identically for index hits and for locally
  verified matches.

Highlighting never returns markup.  It returns ``[start, end)`` offsets into
the plain-text snippet, and the UI escapes the text before wrapping those
ranges.  Document content therefore cannot inject HTML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from advance_file_search.core import constants as C
from advance_file_search.core.models import Highlight
from advance_file_search.search.wildcard import CompiledPattern, highlight_spans

_WHITESPACE_RUN = re.compile(r"\s+")

#: Characters that read as a sentence break when trimming a snippet edge.
_SOFT_BREAK = " \t\n,.;:!?)]}ๆ"


@dataclass(frozen=True)
class Snippet:
    """Display text plus the ranges to highlight inside it."""

    text: str
    highlights: tuple[Highlight, ...]
    #: True when the snippet does not start at the beginning of the unit.
    leading_ellipsis: bool = False
    trailing_ellipsis: bool = False

    @property
    def display(self) -> str:
        prefix = "… " if self.leading_ellipsis else ""
        suffix = " …" if self.trailing_ellipsis else ""
        return f"{prefix}{self.text}{suffix}"

    def display_highlights(self) -> tuple[Highlight, ...]:
        """Highlight ranges shifted to account for the leading ellipsis."""
        if not self.leading_ellipsis:
            return self.highlights
        offset = 2
        return tuple(
            Highlight(start=h.start + offset, end=h.end + offset) for h in self.highlights
        )


def normalize_for_display(text: str) -> str:
    """Collapse whitespace so a snippet fits on one or two lines.

    Only whitespace is altered.  Every other code point — Thai consonants,
    vowels, tone marks, combining characters — is preserved exactly, so the
    text still renders correctly and still matches what was searched.
    """
    return _WHITESPACE_RUN.sub(" ", str(text or "")).strip()


def build_snippet(
    unit_text: str,
    patterns: list[CompiledPattern],
    *,
    match_case: bool = False,
    context_chars: int = C.SNIPPET_CONTEXT_CHARS,
    max_length: int = C.MAX_SNIPPET_LENGTH,
) -> Snippet | None:
    """Extract a window of ``unit_text`` around the first match.

    Returns ``None`` when no pattern matches, which lets the caller drop a
    false-positive index candidate.
    """
    text = str(unit_text or "")
    if not text:
        return None

    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        spans.extend(highlight_spans(pattern, text, match_case=match_case, limit=32))
    if not spans:
        return None
    spans.sort()

    first_start, first_end = spans[0]
    start = max(0, first_start - context_chars)
    end = min(len(text), first_end + context_chars)

    # Grow the window to the end of the last match that still fits, so a
    # cluster of matches is shown together.
    for _span_start, span_end in spans:
        if span_end - start > max_length:
            break
        end = max(end, min(len(text), span_end + context_chars))

    start, end = _snap_to_soft_break(text, start, end)
    if end - start > max_length:
        end = start + max_length
        start, end = _snap_to_soft_break(text, start, end)

    window = text[start:end]
    # Whitespace collapsing changes offsets, so highlights are recomputed on
    # the final display string rather than translated.
    display = normalize_for_display(window)
    if not display:
        return None

    highlights = _highlights_in(display, patterns, match_case=match_case)
    return Snippet(
        text=display,
        highlights=highlights,
        leading_ellipsis=start > 0,
        trailing_ellipsis=end < len(text),
    )


def _snap_to_soft_break(text: str, start: int, end: int) -> tuple[int, int]:
    """Nudge window edges to a nearby separator for a cleaner read.

    Thai has no inter-word spaces, so if no separator is found within a short
    distance the original offset is kept: cutting mid-word is preferable to
    showing an arbitrarily long or empty snippet, and never corrupts text
    because Python string slicing works on whole code points.
    """
    look = 14
    if start > 0:
        for index in range(start, max(0, start - look), -1):
            if index < len(text) and text[index] in _SOFT_BREAK:
                start = index + 1
                break
    if end < len(text):
        for index in range(end, min(len(text), end + look)):
            if text[index] in _SOFT_BREAK:
                end = index + 1
                break
    return start, min(end, len(text))


def _highlights_in(
    display: str, patterns: list[CompiledPattern], *, match_case: bool
) -> tuple[Highlight, ...]:
    """Find and merge highlight ranges in the final display string."""
    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        spans.extend(highlight_spans(pattern, display, match_case=match_case, limit=32))
    return merge_highlights(spans)


def merge_highlights(spans: list[tuple[int, int]]) -> tuple[Highlight, ...]:
    """Sort and coalesce overlapping ranges so markup never nests."""
    if not spans:
        return ()
    ordered = sorted(spans)
    merged: list[list[int]] = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple(Highlight(start=start, end=end) for start, end in merged)


def highlight_name(
    file_name: str, patterns: list[CompiledPattern], *, match_case: bool = False
) -> tuple[Highlight, ...]:
    """Highlight ranges within a file name."""
    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        spans.extend(highlight_spans(pattern, file_name, match_case=match_case, limit=16))
    return merge_highlights(spans)


def row_context(
    cell_text: str, neighbours: list[str], *, max_length: int = C.MAX_SNIPPET_LENGTH
) -> str:
    """Build spreadsheet row context for a cell match.

    A single cell often reads as a bare number; showing the rest of its row
    makes the match understandable without storing every value twice.
    """
    pieces = [piece for piece in [cell_text, *neighbours] if piece and piece.strip()]
    joined = "  |  ".join(normalize_for_display(piece) for piece in pieces)
    if len(joined) > max_length:
        joined = joined[:max_length].rstrip() + "…"
    return joined
