# Stage 1 — `fetch_candidates.py`

**Output:** `data/search_results.csv`

Tavily search only, one row per search result per college, except for sentinel
rows used to log error. It deduplicates the results returned for each college.
When deduplicating, the snippets are appended together. This is because snippets
are not guaranteed to be the same across multiple search queries, and we later
look for keywords in any of the snippets.

Raw content comes from the search call (`include_raw_content`).
[Stage 3](stage3_render_candidates.md) repairs blank or suspiciously short
content after [Stage 2](stage2_filter_candidates.md) filters candidates.

## Pitfalls to know before touching search/fetch logic

1. **`website` (IPEDS official site) is not a domain filter.** Club pages
   routinely live off that domain.
2. **Vendor-hosted club pages.** Many clubs live on platforms like CampusGroups,
   Modern Campus Involve, Anthology Engage, Corq, or Lounge, not the
   university's own domain. This is why fetching must not be restricted to
   `.edu`. The only `.edu` condition is Stage 3's short-content trigger.
   Detecting these pages by header markers is not currently implemented.
3. **Multi-campus systems** (SUNY, UC, Penn State) — search queries search for
   campuses (e.g. Tricoci University of Beauty Culture-Elgin) rather than
   specific institutions. This allows for us to look for clubs that may only
   exist on a specific campus.
4. **Must check full results.** Even if we see an email, Discord, or other
   contact signal in the snippet, we still need to check the full result. For
   example, conglam pages can surface an email address in the snippet, but the
   email can be for a different club.
5. **JS-heavy pages come back blank or stubbed.** Tavily can't render pages like
   Anthology Engage (UConn and Skidmore return nothing; MIT's directory renders
   fine). Stage 3 handles these for candidates kept by Stage 2.

## Sentinel rows

Besides one row per search result, `main()` writes sentinel rows when Tavily
errors.

Here are two types of errors:

| Type        | Written when                                                 | `search_query`                            | `result_title`   | `result_url` |
| ----------- | ------------------------------------------------------------ | ----------------------------------------- | ---------------- | ------------ |
| Query error | A `tavily().search()` call raised. One row per failed query. | The failed query                          | `str(exception)` | `ERROR`      |
| No results  | The college has no hits and no errors. One row per college.  | `NO_RESULTS: ` + queries joined by `"; "` | blank            | blank        |

Here are example rows that they would write:

```csv
100001,Smalltown Bible College,Smalltown,www.smalltownbible.edu,NO_RESULTS: Smalltown Bible College tabletop RPG club; Smalltown Bible College D&D club,,,,,,,
129020,University of Connecticut,Storrs,www.uconn.edu,UConn Dungeons and Dragons club,429 Too Many Requests: usage limit exceeded,ERROR,,,,,
```

### Behavior

- Within a college, error rows are written before real rows.
- `NO_RESULTS` is suppressed if any query raised, even if the other queries
  returned nothing.
- `from_tavily` drops hits without a `url`, so a college whose hits all lack one
  gets `NO_RESULTS`.
- `extract()` and Playwright failures are never sentinels; Stage 3 records them
  in `extract_status` and `render_status` on kept rows.
- Detection: `result_url == "ERROR"` marks an error row, and a `search_query`
  starting with `NO_RESULTS:` marks a no-results row. Real rows always have a
  non-blank `raw_content_status`. The markers (`ERROR_URL`, `NO_RESULTS_PREFIX`)
  and the detector `is_sentinel(row)` live in `search_row_format_util.py`, so
  this stage's writer and Stage 3's reader share one definition. Stage 2 also
  discards sentinels by their blank or `ERROR` URL.

### Known gaps

- Error text is stored in `result_title` and bypasses `sanitize_for_csv`.
- The `NO_RESULTS` query list is packed into one string and is hard to parse
  back out.

## Tavily notes

- `search()` runs per query template per college
  - `search_depth="advanced"` (2 credits) beats `"basic"`/`"fast"` (1 credit) on
    relevance — currently used everywhere
  - `exclude_domains` filters generic social/wiki/review sites.
  - `country` is set to `"united states"` to boost content from the US.
  - `include_raw_content` is set to `True` for all fetches, which fetches the
    cleaned and parsed HTML content for each result.
- Track credit spend against budget before scaling up.
- It may be worthwhile to implement retry logic for when Tavily fails to return
  a result — not yet implemented.

## Code specifics

- Shared with Stage 3, not defined here. `tavily_client_util.py` holds the
  Tavily client `tavily()` (built lazily with `functools.cache`, so importing
  doesn't require an API key; importing the module also loads `.env`).
  `search_row_format_util.py` holds `sanitize_for_csv`, the sentinel markers,
  and `csv.field_size_limit` (raised for full-page-text rows; an import side
  effect). Don't copy them back into this script.

## Scale & budget

Stage 0 currently produces 2,815 institutions, and `config/query_templates.txt`
currently holds 1 template, so a full run is about 2,815 searches (more if
templates are added). Before a full run:

- Reconsider always using `SEARCH_DEPTH="advanced"` (2 credits) vs. a cheap
  `"basic"` first pass.
- This script doesn't checkpoint/resume — add resumable writes so a mid-run
  failure doesn't require restarting from scratch.
- `SLEEP_BETWEEN_COLLEGES_S` may need to grow at ~20x current volume; check
  Tavily's rate limits.
- `result_raw_content` is currently written in full to this stage's CSV (fine
  for test runs) — we probably want to shard this CSV by college.

## Open gaps

- No checkpoint/resume for mid-run failures.
