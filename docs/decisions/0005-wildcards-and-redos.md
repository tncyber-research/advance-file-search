# ADR 0005 — Wildcard matching without a regex engine

**Status:** Accepted · **Date:** 2026-09-11

## Context

Handoff §8.3 requires `*` (zero or more characters) and `?` (exactly one), and
§16 requires "search cancellation for expensive wildcard queries".

## What was tried first, and why it was wrong

The obvious implementation translates the pattern into a regular expression:
`a*a*a*b` becomes `a[\s\S]*a[\s\S]*a[\s\S]*b`. It is short, it is correct, and
it is a denial-of-service vector.

Measured on this machine, against a subject of repeated `a`:

| Pattern | Subject length | `re` time |
|---|---|---|
| `a*a*a*b` | 600 | **21.6 s** |
| `a*a*a*a*a*b` | 4,000 | did not complete |

Each `.*` can split the subject at any position, so *n* wildcards over a
subject of length *m* is O(m^n) backtracking. Document content units are capped
at 200,000 characters, and the pattern comes from a text box the user types
into freely. A wildcard limit does not fix this: three wildcards already hang
the application.

## Decision

Match wildcards directly, with no regex engine.

The pattern is split on `*` into **segments**, each containing only literal
characters and `?`. A segment is tested against a fixed-length window in linear
time. Segments are then matched left to right, each searched for at or after
the end of the previous match. Greedy-leftmost segment matching is the standard
correct algorithm for glob patterns: `*` absorbs anything, so taking the
earliest occurrence of the next segment always leaves the most text available
for the rest of the pattern.

Two details make the whole search linear rather than quadratic:

* When a required segment is absent from the remaining text, `_match_from`
  returns `_EXHAUSTED` and the caller stops trying later start positions — the
  cursor only ever moves forward, so no later start could succeed either.
* A pattern beginning with `*` needs exactly one start attempt; the leading
  wildcard already absorbs any prefix.

## Result

| Pattern | Subject length | Time |
|---|---|---|
| `a*a*a*a*a*b` | 4,000 | 0.04 ms |
| `*a*a*a*a*a*` | 20,000 | 0.04 ms |
| `a?a?a?a?a?b` | 20,000 | 17 ms |
| `งบ*ประมาณ*ครุ*ภัณฑ์*x` | 40,000 | 0.48 ms |

The `?` case is the slow one at 17 ms, because a `?`-bearing segment cannot use
`str.find` and is scanned position by position. That is O(n × m) with no
backtracking, and 17 ms is not a hang.

## Side benefits

* **Exact match spans come out of the matcher**, so highlight offsets are
  produced directly rather than recovered with a second pass.
* **User-typed regex syntax stays literal.** `a.c[0-9]+$` searches for that
  exact text, which is what someone typing it into a file-search box means.
  With a regex translation it would have to be escaped, and any gap in the
  escaping becomes an injection.

## Highlighting

For a wildcard pattern, only the **literal runs the user typed** are
highlighted, not the whole matched region: `bud*et` can span a whole paragraph,
and painting the paragraph yellow tells the reader nothing. The pattern is
still verified as a whole first, so fragments are only highlighted inside
values that genuinely match.

## Limits retained

`MAX_WILDCARDS_PER_TERM = 6` and `MAX_QUERY_LENGTH = 500` remain as
defence in depth, and the tests in `test_query_and_wildcard.py` marked
`@pytest.mark.security` assert a sub-second bound on each pathological pattern
so a future change cannot quietly reintroduce a regex.
