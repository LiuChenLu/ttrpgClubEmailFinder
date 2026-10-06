# Stage 1b — `render_candidates.py`

**Input:** `data/search_results.csv` (Stage 1a)

**Output:** `data/rendered_results.csv`

Re-fetches page content that Stage 1a left blank and refetch some very short pages.

- Blank pages are attempted first with Tavily `extract`, then with Playwright.
- Short pages from `.edu` URLs (see [The `.edu` rule](#the-edu-rule)) are refetched with Playwright only.

Every input row is written to the output (row count unchanged).

## Why this stage exists

JS-heavy club platforms such as Anthology Engage often return blank or script-stub content from Tavily; for example, UConn and Skidmore return an empty result_raw_content. Not every page hosted by Engage fails (MIT's directory page renders fine), so the triggers below look at content, not vendor.

## Row handling

Here is how the input rows are handled:

1. **Sentinel rows** (`result_url == "ERROR"` or `search_query` starting with `NO_RESULTS:`, detected by `search_row_format_util.is_sentinel`) pass through unchanged; `extract_status`, `render_status` and `content_source` stay blank.
2. **Blank `result_raw_content`:** Tavily `extract` with `EXTRACT_DEPTH = "advanced"`, up to `EXTRACT_MAX_ATTEMPTS` attempts. Only failures are retried (`failed_per_url`, `failed_exception`, `no_response_entry`); `succeeded_empty` means the page itself is empty and is final. It runs on every blank row, even low-quality ones, so all filtering stays in Stage 2.
   - Its main job is covering transient failures. `advanced` is used because these rows already failed once at search time, so the cheap tier is the least likely to work on them; it is spent on blank rows only.
   - **Unverified:** whether `advanced` renders JS-heavy pages better than the search-time fetch. Tavily documents `search_depth` and `extract_depth` as separate controls on separate endpoints, so don't assume the search call and `extract` behave alike. To find out, run `extract` once with `basic` and once with `advanced` on a few known-blank URLs (UConn, Skidmore) and compare the lengths.
3. **Playwright runs** on a row if, after step 2, either:
   - `result_raw_content` is still blank, or
   - `raw_content_length` is under `SHORT_CONTENT_CHARS` defined in `config.py` and the `result_url` is a `.edu`.

   Short but non-blank rows skip `extract` and go straight to Playwright. A row that `extract` rescued but that is still short on a `.edu` URL also goes to Playwright.
4. All other rows are unchanged.

Extract and Playwright failures are recorded on the real row, never as sentinels.

## The `.edu` rule

`result_url`, stripped, matches the regex `\.edu(?=$|[./?:#])` (case-insensitive) anywhere in the string. So `.edu` must end the URL or be followed by `.`, `/`, `?`, `:` or `#`. This is deliberately not a hostname check: the URL may lack a scheme.

| Matches | Doesn't match |
| --- | --- |
| `https://www.uconn.edu` | `https://www.educause.org/` |
| `uconntact.uconn.edu/organization/...` | `https://www.education.com/x` |
| `HTTPS://WWW.UCONN.EDU/clubs` | `https://x.edu-prog.org/` |
| `https://x.edu:8080/a` | `https://skidmore.campuslabs.com/...` |

Known false positives, accepted because each only costs one unneeded Playwright run: `.edu.cn` / `.edu.au` hosts, and `.edu` inside a path or query string (`reddit.com/r/uconn.edu/`).

## Playwright Failure Behaviours

- Headless Chromium, launched **eagerly** at the start of `main()`: after the input header is validated, but before the output file is opened and before any API call. A missing install therefore aborts the run without truncating a previous output or spending credits.
- **Per-URL failure.** A timeout or any other Playwright error sets `render_status` to `failed_per_url` and keeps the existing content.
- **Browser death.** If a Playwright call fails and the browser is no longer connected, Chromium is relaunched before the next URL. The URL that was in flight is recorded as `failed_per_url` and is not retried.
- **Aborts.** `RenderAbort` is raised, with a `playwright install chromium` hint, when the browser can't be launched at startup, when a relaunch fails, or when it dies `PLAYWRIGHT_MAX_CONSECUTIVE_CRASHES` times in a row. The cap exists because a systemic problem (out of memory, a broken install) would otherwise silently mark every remaining row `failed_per_url`. A Playwright call that ends with the browser still alive, whether it succeeded or hit an ordinary timeout, resets the count. Rows already written stay flushed.

## Error Codes in CSV Output

Schema is in [`pipeline_data_flow.md`](../pipeline_data_flow.md). Semantics:

- `extract_status`: blank if Tavily `extract` wasn't attempted; otherwise the last attempt's result: `succeeded`, `succeeded_empty`, `failed_per_url`, `failed_exception` or `no_response_entry`.
- `render_status`:
  - `not_needed`: Playwright not triggered, including rows `extract` rescued.
  - `succeeded`: Playwright returned non-empty text; `content_source` shows whether it replaced the old content.
  - `failed_per_url`: Playwright raised (including the timeout) or returned empty text.
- `content_source`: `search`, `extract` or `playwright`; blank if the content is blank.
- `raw_content_status` keeps the search-time result; `raw_content_length` is recomputed from the final content.

## Accepted tradeoffs

- In Playwright, these are the tradeoffs:
  - Long stub pages are not detected.
  - The 1000-character threshold for what counts as "short"is arbitrary.
  - The `.edu` rule has the false positives listed above.
  - Short stub pages on non-`.edu` hosts, including some vendor-hosted pages, are not detected; only blank content triggers Playwright there.
  - A `networkidle` timeout discards whatever had already rendered. Pages that poll forever fail even though their text is on screen.
  - There is no URL cache across colleges. Multi-campus system pages that surface under several colleges are re-fetched, and re-rendered, each time.
  - Playwright text replaces existing non-empty content if and only if it is longer. "Longer" compares raw string length. That is a known bug since Tavily content is Markdown and Playwright is plain text, but this is expected to have a small impact.
  - Playwright does not check the HTTP status. A 403 or 404 page with body text counts as `succeeded` and can fill a blank row.
- `extract_once` turns every exception into `failed_exception`, so a missing `TAVILY_API_KEY` degrades every blank row silently (two attempts and a sleep each) instead of aborting. A fail-fast check at startup would match the eager browser launch.

## Code specifics

- Constants in `config.py`: `SEARCH_RESULTS_CSV`, `RENDERED_RESULTS_CSV`, `EXTRACT_DEPTH`, `EXTRACT_MAX_ATTEMPTS`, `EXTRACT_RETRY_SLEEP_S`, `SHORT_CONTENT_CHARS`, `PLAYWRIGHT_TIMEOUT_MS`, `PLAYWRIGHT_MAX_CONSECUTIVE_CRASHES`.
- Shared with Stage 1a, not redefined here. From `tavily_client_util.py`: `tavily()` (built lazily with `functools.cache`). From `search_row_format_util.py`: `sanitize_for_csv`, the sentinel markers and `is_sentinel`, and `csv.field_size_limit`, which is raised for full-page rows.
- `render_row(row, renderer, extract=...)` holds the per-row logic and takes its renderer and extract function as arguments, so it can be tested without a network or a browser. `PlaywrightRenderer` owns the browser lifecycle and accepts a `playwright_factory` for the same reason.
- Each row is written and flushed as it is processed, so a run that aborts or crashes leaves a salvageable partial file.
- Tests are in `test_render_candidates.py`. They are hermetic by default. The `test_real_*` tests drive a real Chromium against a local web server and skip themselves if it can't launch; the two that kill the browser process need Linux and `pkill`.

## Scale & budget

- `extract` (`advanced`) credits are spent only on blank rows, at most 2 attempts each.
- Playwright is the slow step. Measure the trigger rate (blank rows plus short `.edu` rows) on a sample of `search_results.csv` before a full run.
- Low priority: measure Playwright miss rate for stubs. Sample non-`.edu` rows under `SHORT_CONTENT_CHARS` and read a few. Stubs on vendor hosts (CampusGroups, Engage) that come back short but non-blank are the pages this stage skips by design.
- `result_raw_content` is written in full, which can make the csv file huge; we probably want to shard the CSV by college when there is a full run.

## Open gaps

- Playwright fetched results are stored as plain body text, not markdown, so hrefs behind link text (`mailto:`, Discord invites) are absent. This is a problem and NEEDS to be fixed before handoff to LLM.
- No checkpoint/resume for mid-run failures. After an abort the partial output looks like a complete file.
- Playwright is untuned: concurrency (currently sequential), the 30 s timeout, and the wait strategy. `networkidle` can time out on pages that keep polling, which counts as a failure. Catching that timeout and still taking `inner_text` is a cheap candidate fix.