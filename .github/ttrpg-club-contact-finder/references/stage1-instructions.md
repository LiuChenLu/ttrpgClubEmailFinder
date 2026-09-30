# Stage 1 — `fetch_candidates.py`

**Output:** `data/candidates.csv`

Tavily search + extract, one row per search result per college, except for sentinel rows used to log error. It deduplicates the results returned for each college. When deduplicating, the snippets are appended together. This is because snippets are not guaranteed to be the same across multiple search queries, and we later look for keywords in any of the snippets.

## Pitfalls to know before touching search/fetch logic

1. **`website` (IPEDS official site) is not a domain filter.** Club pages routinely live off that domain.
2. **Vendor-hosted club pages.** Many clubs live on platforms like CampusGroups, Modern Campus Involve, Anthology Engage, Corq, or Lounge, not the university's own domain. This is why extraction must not be restricted to `.edu`. (Detecting these pages by header markers like "Powered by CampusGroups" is a classification signal, not a fetch concern — see Stage 2.)
3. **Multi-campus systems** (SUNY, UC, Penn State) — search queries search for campuses (e.g. Tricoci University of Beauty Culture-Elgin) rather than specific institutions. This allows for us to look for clubs that may only exist on a specific campus.

## Tavily notes

- `search()` runs per query template per college
  - `search_depth="advanced"` (2 credits) beats `"basic"`/`"fast"` (1 credit) on relevance — currently used everywhere
  - `exclude_domains` filters generic social/wiki/review sites.
  - `country` is set to `"united states"` to boost content from the US.
  - `include_raw_content` is set to `True` for all fetches, which fetches the cleaned and parsed HTML content for each result.
- A separate `extract()` fetches full text only for results where the raw_content failed to fetch. For simplicity, it fetches any results that failed to fetch the raw_content, even if they are low quality. We try to fetch 2 times with extract before leaving the field blank. This allows us to handle filtering all in one place in stage 2.
- Track credit spend against budget before scaling up.
- It may be worthwhile to implement retry logic for when Tavily fails to return a result — not yet implemented.

## Code specifics

- `csv.field_size_limit` is raised in this stage to accommodate full-page-text rows.
- The Tavily client is built lazily (`functools.cache`) so importing the module doesn't require an API key to be set.

## Scale & budget

Assuming a negligiable number of `extract` retries, ~4,000 colleges × 3 query templates × up to 3 extracts ≈ 12K searches + 12K extracts. Before a full run:

- Reconsider always using `SEARCH_DEPTH="advanced"` (2 credits) vs. a cheap `"basic"` first pass.
- This script doesn't checkpoint/resume — add resumable writes so a mid-run failure doesn't require restarting from scratch.
- `SLEEP_BETWEEN_COLLEGES_S` may need to grow at ~20x current volume; check Tavily's rate limits.
- `result_raw_content` is currently written in full to this stage's CSV (fine for test runs) — we probably want to shard this CSV by college.

## Open gaps

- No checkpoint/resume for mid-run failures.