# Stage 1b — `render_candidates.py`

**Input:** `data/search_results.csv` (Stage 1a)

**Output:** `data/rendered_results.csv`

Re-fetches page content that Stage 1a left blank or suspiciously short. Blank pages are attempted first with Tavily `extract`, then with Playwright. Short pages from .edu domain are fetched with Playwright only. Every input row is written to the output (row count unchanged).

## Why this stage exists

JS-heavy club platforms such as Anthology Engage often return blank or script-stub content from Tavily. UConn and Skidmore return none. Not every such page fails (MIT's directory page renders fine), so the triggers below look at content, not vendor.

## Row handling

1. **Sentinel rows** (`result_url == "ERROR"` or `search_query` starting with `NO_RESULTS:`) pass through unchanged; `render_status` and `content_source` stay blank.
2. **Blank `result_raw_content`:** Tavily `extract`, up to 2 attempts. It covers transient failures only and renders JS no better than search. It runs on every blank row, even low-quality ones, so all filtering stays in Stage 2.
3. **Playwright runs** on a row if, after step 2, either:
   - `result_raw_content` is still blank, or
   - `raw_content_length` is under `SHORT_CONTENT_CHARS` defined in `config.py` (1000 at time of writing) and the `result_url` contains the string `.edu`.

   Short but non-blank rows skip `extract` and go straight to Playwright.
4. All other rows are unchanged.

Extract and Playwright failures are recorded on the real row, never as sentinels.

## Playwright

- Headless Chromium; one attempt per URL, no retry; one page at a time.
- `page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)`, with `PLAYWRIGHT_TIMEOUT_MS = 30_000`.
- Stored as plain body text, not markdown, so hrefs behind link text (`mailto:`, Discord invites) are absent. Tavily content is markdown; downstream stages must check `content_source` rather than assume a format.
- Playwright text replaces existing content only if it is non-empty and longer; otherwise the existing content is kept.
- A timeout or any other Playwright error sets `render_status` to `failed_per_url` and keeps the existing content.
- Requires `playwright install chromium` once.
- Takes a few seconds to a few minutes per page.

## Output columns

Schema is in [`pipeline_data_flow.md`](../pipeline_data_flow.md). Semantics:

- `render_status`:
  - `not_needed`: Playwright not triggered, including rows `extract` rescued.
  - `succeeded`: Playwright returned non-empty text; `content_source` shows whether it replaced the old content.
  - `failed_per_url`: Playwright raised (including the timeout) or returned empty text.
- `content_source`: `search`, `extract` or `playwright`; blank if the content is blank.
- `raw_content_status` keeps the search-time result; `raw_content_length` is recomputed from the final content.

## Accepted tradeoffs

- Long stub pages are not detected.
- Short stub pages on non-`.edu` hosts, including many vendor-hosted pages, are not detected; only blank content triggers Playwright there.
- The 1000-character threshold is arbitrary.

## Code specifics

- Constants in `config.py`: `SEARCH_RESULTS_CSV`, `RENDERED_RESULTS_CSV`, `SHORT_CONTENT_CHARS`, `PLAYWRIGHT_TIMEOUT_MS`.
- As in Stage 1a: `csv.field_size_limit` is raised for full-page rows, and the Tavily client is built lazily (`functools.cache`).

## Scale & budget

- `extract` credits are spent only on blank rows, at most 2 attempts each.
- Playwright is the slow step. Measure the trigger rate (blank rows plus short `.edu` rows) on a sample of `search_results.csv` before a full run.
- `result_raw_content` is written in full; we probably want to shard the CSV by college.

## Open gaps

- No checkpoint/resume for mid-run failures.
- Playwright is untuned: concurrency (currently sequential), browser reuse across pages, wait strategy (`networkidle` can time out on pages that keep polling, which counts as a failure), and the 30 s timeout.