# Stage 1 — `fetch_candidates.py`

**Output:** `data/candidates.csv`

Tavily search + extract, one row per search result per college. This stage only fetches — it does not compute club/ttrpg keyword signals or render a keep/discard verdict; that happens in Stage 2 (`classify_candidates.py`).

## Pitfalls to know before touching search/fetch logic

1. **`WEBADDR` (IPEDS official site) is not a usable domain filter.** Club pages routinely live off that domain — see vendor-hosted pages below. Use it as a soft signal (`include_domains` / `mode="boost"` below), never a hard filter.
2. **Vendor-hosted club pages.** Many clubs live on platforms like CampusGroups, Modern Campus Involve, Anthology Engage, Corq, or Lounge, not the university's own domain. This is why extraction must not be restricted to `.edu` — the boost-not-filter approach above is what keeps these pages in the candidate pool. (Detecting these pages by header markers like "Powered by CampusGroups" is a classification signal, not a fetch concern — see Stage 2.)
3. **Multi-campus systems** (SUNY, UC, Penn State) — match the specific campus, not the system name, when constructing search queries. (Stage 0 should already give you campus-level rows; don't re-collapse them here.)

## Tavily notes

- `search()` runs per query template per college; a separate `extract()` fetches full text only for top-scoring candidates, avoiding extraction cost on every hit.
- `search_depth="advanced"` (2 credits) beats `"basic"`/`"fast"` (1 credit) on relevance — currently used everywhere; worth revisiting at scale (see Scale & budget below).
- `include_domains=["*.edu"], mode="boost"` ranks `.edu` higher **without excluding** legitimate vendor-hosted pages — never use hard `include_domains` exclusion here (ties back to pitfall #1/#2).
- `exclude_domains` filters generic social/wiki/review sites.
- `extract()` reports per-URL failures in `failed_results` rather than raising — that list must be checked explicitly, or failures silently vanish.
- Batch `extract()` per college (already done).
- Track credit spend against budget before scaling up.
- It may be worthwhile to implement retry logic for when Tavily fails to return a result — not yet implemented.

## Code specifics

- `csv.field_size_limit` is raised in this stage to accommodate full-page-text rows.
- The Tavily client is built lazily (`functools.cache`) so importing the module doesn't require an API key to be set.

## Scale & budget

~6,000 colleges × 3 query templates × up to 3 extracts ≈ 18K searches + 18K extracts. Before a full run:

- Reconsider always using `SEARCH_DEPTH="advanced"` (2 credits) vs. a cheap `"basic"` first pass.
- This script doesn't checkpoint/resume — add resumable writes so a mid-run failure doesn't require restarting from scratch.
- `SLEEP_BETWEEN_COLLEGES_S` may need to grow at ~20x current volume; check Tavily's rate limits.
- `result_raw_content` is currently written in full to this stage's CSV (fine for test runs) — drop/truncate before a 6,000-row run.

## Open gaps

- No retry logic yet for Tavily failures.
- No checkpoint/resume for mid-run failures.