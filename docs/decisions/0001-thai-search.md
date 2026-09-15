# ADR 0001 — Thai search strategy

**Status:** Accepted · **Date:** 2026-09-11

## Context

Thai does not put spaces between words. A phrase such as
`งบประมาณครุภัณฑ์ประจำปี` is one unbroken run of characters. Handoff §8.2
requires Thai and English content to both be searchable, and §24 asks for a
prototype to settle the tokenizer before the UI is polished.

## Prototype result

A 300-document synthetic corpus (835,612 characters, mixed Thai and English,
Thai words concatenated without spaces) was indexed with each candidate
tokenizer and queried for a word occurring *inside* an unspaced run.

| Tokenizer | Index size | `"งบประมาณ"` exact | `งบประมาณ*` prefix | True occurrences |
|---|---|---|---|---|
| `unicode61 remove_diacritics 0` | 2.4 MB | 154 | 948 | 1882 |
| `trigram` | 5.9 MB | **1882** | 1882 | 1882 |

`unicode61` treats each Thai run as a single token, so an exact-token query
finds only rows where the search word happens to *start* the run, and even a
prefix query misses half the real matches. This is not a tuning problem; it is
the tokenizer doing exactly what it is designed to do on a script it cannot
segment.

`trigram` indexes overlapping three-character sequences, giving true substring
matching in any script. Query latency was 1.6–3.5 ms for both.

## Decision

Use `tokenize='trigram'` for both `content_fts` and `name_fts`.

A hybrid — `unicode61` for ranking plus `trigram` for recall — was considered
and rejected: it roughly doubles index size for a ranking signal we do not use
(results are ranked by our own explainable bands, not by bm25) and doubles the
write cost of every indexing run.

## Consequences

1. **Substring semantics everywhere.** Searching `budget` also matches
   `prebudgeting`. That matches what people expect from "find this text in my
   documents", and **Whole word** is available when it is not wanted.
2. **Queries shorter than 3 characters cannot use the index** — the trigram
   tokenizer produces no tokens for them. `SearchService` falls back to a
   row-limited `LIKE` scan scoped to the selected root
   (`MAX_FALLBACK_ROWS = 60,000`). The UI reports this as `short_term_scan`.
3. **Index matching is case-insensitive.** Match case is applied in the local
   verification pass against `content_units.text`.
4. **Whole word and `?`/`*` wildcards are verified locally** for the same
   reason. The index narrows candidates; the verification pass decides.
5. **Index size is roughly 6× the extracted text.** Measured at 1.8 MB for
   1,000 small text files — well inside the documented 3–5 GB free-space
   requirement for the target workload.

## Deliberately not done

No Thai word-segmentation library (PyThaiNLP, ICU) was added. Segmentation
would improve ranking, but it introduces a dictionary, a model file or an ICU
build — each a new supply-chain surface and, in some packagings, a download.
Substring search is honest about what it does and needs nothing extra. This can
be revisited if real documents show a need.
