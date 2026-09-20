
# Stage 1 — `classify_club_pages.py`

**Output:** `data/ttrpg_clubs_search_results.csv`

Tavily search + extract, one row per search result. Records snippet and/or full-text keyword (AND) signals only — this stage does **not** render a verdict on whether a result is really a club page; that's decided downstream.

## Pitfalls to know before touching matching/search logic

1. **Names don't match pages.** "University of Connecticut" clubs may only ever say "UConn." No reliable abbreviation list exists — avoid exact-phrase matching on college name.
2. **Wrong-school attribution.** A query for UConn once surfaced a CCSU event instead — a good relevance score doesn't guarantee the result is about the *target* school. Needs an explicit school-identity check, not just a score threshold.
3. **`WEBADDR` (IPEDS official site) is not a usable domain filter.** Club pages routinely live off that domain — see vendor-hosted pages below. Use it as a soft signal (see `include_domains` / `mode="boost"` below), never a hard filter.
4. **Vendor-hosted club pages.** Many clubs live on platforms like CampusGroups, Modern Campus Involve, Anthology Engage, Corq, or Lounge, not the university's own domain. These likely have identifiable markers (e.g. "Powered by CampusGroups" in the header) — worth special-casing. **Not yet implemented — TODO in this file.**
5. **Amalgam/directory pages.** Some schools list every student org on one page. Ideally we pull only the contact information for the relevant club, not the whole directory.
6. **Multi-campus systems** (SUNY, UC, Penn State) — match the specific campus, not the system name. (Stage 0 should already give you campus-level rows; don't re-collapse them here.)

## Tavily notes

- `search()` runs per query template per college; a separate `extract()` fetches full text only for top-scoring candidates, avoiding extraction cost on every hit.
- `search_depth="advanced"` (2 credits) beats `"basic"`/`"fast"` (1 credit) on relevance — currently used everywhere; worth revisiting at scale (see Scale & budget below).
- `include_domains=["*.edu"], mode="boost"` ranks `.edu` higher **without excluding** legitimate vendor-hosted pages — never use hard `include_domains` exclusion here (ties back to pitfall #3/#4).
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

- No fix yet for wrong-school attribution (pitfall #2); alternative search APIs under investigation.
- Vendor-platform special-casing and amalgam-page detection (pitfalls #4, #5): not implemented.
