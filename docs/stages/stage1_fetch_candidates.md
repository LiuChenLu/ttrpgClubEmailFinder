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
3. **Multi-campus systems** (SUNY, UC, Penn State) — queries use each campus's
   own name (e.g. "SUNY Oneonta") rather than the system name, so we find clubs
   that exist on only one campus.
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
100001,Smalltown Bible College,,,Smalltown,www.smalltownbible.edu,NO_RESULTS: Smalltown Bible College tabletop RPG club; Smalltown Bible College D&D club,,,,,,,
129020,University of Connecticut,,UConn,Storrs,www.uconn.edu,UConn Dungeons and Dragons club,429 Too Many Requests: usage limit exceeded,ERROR,,,,,
```

### Behavior

- Within a college, error rows are written before real rows.
- `NO_RESULTS` is suppressed if any query raised, even if the other queries
  returned nothing.
- `from_tavily` drops hits without a `url`, so a college whose hits all lack one
  gets `NO_RESULTS`.
- `extract()` and Playwright failures are never sentinels; Stage 3 records them
  in `extract_status` and `render_status` on kept rows.
- Detection: a blank or `ERROR` `result_url`, or a `search_query` starting with
  `NO_RESULTS:`. The markers (`ERROR_URL`, `NO_RESULTS_PREFIX`) and the one
  detector `is_sentinel(row)` live in `search_row_format_util.py`. Stages 1, 2
  and 3 all use it; don't write another.

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

## Running it and the credit guard

```bash
python fetch_candidates.py --limit 5            # sample, default input
python fetch_candidates.py --input data/institutions.csv --yes   # full run
```

`--input`, `--output`, `--limit N` (first N colleges) and `--yes` are the options.
Before opening the output, `main()` estimates credits as colleges x templates x
credits per search (2 at `advanced`). Above `MAX_UNCONFIRMED_SEARCH_CREDITS` in
`config.py` it exits without searching or touching the output, unless `--yes` is
given. A full run is a few thousand searches, so only the user starts one.

## Open gaps

- No checkpoint/resume for mid-run failures.
- Consider a cheap `"basic"` first pass instead of always using `"advanced"`.
- `SLEEP_BETWEEN_COLLEGES_S` may need to grow at full volume; check Tavily's
  rate limits.
- `result_raw_content` is written in full, which makes the CSV huge on a full
  run. Sharding it by college is an option.
