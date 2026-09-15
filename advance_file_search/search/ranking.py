"""Result ranking.

Order (handoff §8.4), highest first:

1. exact file-name match
2. file-name prefix match
3. other file-name match
4. exact content phrase
5. content term match

Recency is a mild tie-breaker only, so a fresh irrelevant file never outranks
an exact name match.  Scores are deliberately coarse and explainable rather
than a tuned black box.
"""

from __future__ import annotations

from advance_file_search.core.models import MatchSource, SearchResult

# Score bands.  The gaps are wide enough that within-band adjustments can never
# promote a result past a higher band.
SCORE_NAME_EXACT = 1000.0
SCORE_NAME_EXACT_STEM = 900.0
SCORE_NAME_PREFIX = 800.0
SCORE_NAME_WORD = 700.0
SCORE_NAME_SUBSTRING = 600.0
SCORE_CONTENT_PHRASE = 400.0
SCORE_CONTENT_TERM = 200.0

#: Added when both the name and the content match.
BONUS_BOTH_SOURCES = 60.0
#: Added per additional matching location, capped.
BONUS_PER_MATCH = 4.0
MAX_MATCH_BONUS = 40.0
#: Recency contributes at most this much (about one day of separation is worth
#: a fraction of a point, so it only breaks ties).
MAX_RECENCY_BONUS = 15.0


def name_score(
    file_name: str, query_terms: list[str], *, match_case: bool = False
) -> float:
    """Score how well a file name matches the query terms."""
    if not query_terms:
        return 0.0
    name = file_name if match_case else file_name.casefold()
    stem = name.rsplit(".", 1)[0] if "." in name else name
    best = 0.0
    for raw_term in query_terms:
        term = raw_term if match_case else raw_term.casefold()
        if not term:
            continue
        if name == term:
            best = max(best, SCORE_NAME_EXACT)
        elif stem == term:
            best = max(best, SCORE_NAME_EXACT_STEM)
        elif name.startswith(term):
            best = max(best, SCORE_NAME_PREFIX)
        elif _at_word_boundary(name, term):
            best = max(best, SCORE_NAME_WORD)
        elif term in name:
            best = max(best, SCORE_NAME_SUBSTRING)
    return best


def _at_word_boundary(name: str, term: str) -> bool:
    """True when ``term`` appears after a separator inside ``name``."""
    for separator in (" ", "_", "-", ".", "(", "[", ",", "+"):
        if separator + term in name:
            return True
    return False


def content_score(*, phrase_match: bool, match_count: int) -> float:
    base = SCORE_CONTENT_PHRASE if phrase_match else SCORE_CONTENT_TERM
    bonus = min(MAX_MATCH_BONUS, max(0, match_count - 1) * BONUS_PER_MATCH)
    return base + bonus


def recency_bonus(modified_time: float | None, newest_time: float | None) -> float:
    """Mild bonus for a recently modified file, normalized to the result set."""
    if not modified_time or not newest_time or newest_time <= 0:
        return 0.0
    age_days = max(0.0, (newest_time - modified_time) / 86400.0)
    # Halve the bonus roughly every 90 days of age.
    return MAX_RECENCY_BONUS / (1.0 + age_days / 90.0)


def finalize_scores(results: list[SearchResult]) -> None:
    """Apply cross-result adjustments (both-source bonus, recency) in place."""
    newest = 0.0
    for result in results:
        if result.modified_time and result.modified_time > newest:
            newest = result.modified_time
    for result in results:
        if result.match_source is MatchSource.BOTH:
            result.score += BONUS_BOTH_SOURCES
        result.score += recency_bonus(result.modified_time, newest)


def sort_by_relevance(results: list[SearchResult]) -> list[SearchResult]:
    """Stable sort by score, then name, so equal scores order predictably."""
    return sorted(
        results,
        key=lambda r: (-r.score, r.file_name.casefold(), r.display_path.casefold()),
    )
