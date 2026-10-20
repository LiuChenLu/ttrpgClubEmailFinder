# CSV columns (implemented behaviour)

The column lists are defined in [`schema.py`](../schema.py), and
`tests/test_docs.py` fails if this file and `schema.py` disagree. Each column is
listed once, under the stage that introduces it. A stage's file has every column
from earlier stages first, in order, unless it says otherwise. Files in `data/`
are gitignored and may come from older code, so don't treat them as the schema.
Planned columns belong in [`specs/`](../specs/README.md), not here.

Every stage after Stage 1 writes one row per input row. Stage 1 writes one row per
search result.

## Stage 0: `institutions.csv`

One row per IPEDS institution that passes the filters in
[stage 0](stages/stage0_build_institution_dataset.md).

- `unitid`: IPEDS unit ID
- `college_name`: IPEDS institution name
- `aliases`: official IPEDS aliases (`IALIAS`), `|`-separated
- `generated_aliases`: generated shortened name variants, `|`-separated
- `city`: IPEDS city
- `distance`: miles from Hartford. Stage 1 drops it
- `website`: IPEDS official website (`WEBADDR`)

## Stage 1: `search_results.csv`

One row per de-duplicated search result per college, plus sentinel rows that log
an error (format in [stage 1](stages/stage1_fetch_candidates.md)). Starts with
the Stage 0 columns except `distance`.

- `search_query`: query of the best-scoring result across queries
- `result_title`: holds the exception text on error sentinel rows
- `result_url`: `ERROR` on error sentinels, blank on no-results sentinels
- `result_score`: search API relevance score
- `result_snippet`: snippets from every query that returned the hit, joined
- `raw_content_status`: search-time fetch outcome, `succeeded`, `empty` or `missing`
- `raw_content_length`: length of `result_raw_content`
- `result_raw_content`: page text as markdown; blank if the fetch failed

## Stage 2: `filtered_candidates.csv`

Rule-based only. Every input row is written, so the file is an audit trail.
Rules and decision values: [stage 2](stages/stage2_filter_candidates.md). The
columns are `decision`, then the Stage 1 columns **without `result_score`**
(dropped on purpose, so no later stage sees it), then the two audit columns.

- `decision`: `keep`, or `discard_` plus a reason from `schema.DISCARD_REASONS`
- `club_keywords_found_in_snippet`: club keywords found in title + snippet, `; `-separated
- `ttrpg_keywords_found_in_snippet`: TTRPG keywords found in title + snippet

## Stage 3: `rendered_results.csv`

Rows with `decision == "keep"` get blank or short page text repaired. All other
rows pass through with the three new columns blank. Details:
[stage 3](stages/stage3_render_candidates.md). Columns are the Stage 2 columns
**without the two keyword audit columns**, with `extract_status` inserted right
after `raw_content_status`, and `render_status` and `content_source` appended.
`raw_content_length` and `result_raw_content` are recomputed from the final text.

- `extract_status`: `succeeded`, `succeeded_empty`, `failed_per_url`,
  `failed_exception` or `no_response_entry`; blank if `extract` wasn't attempted
- `render_status`: `not_needed`, `succeeded` or `failed_per_url`; blank for
  discarded rows and sentinels
- `content_source`: `search`, `extract` or `playwright`; blank if the text is blank

`result_raw_content` is markdown or plain text depending on `content_source`.
Playwright text has no link hrefs (`mailto:`, Discord invites).

## Stage 4: `ttrpg_clubs_contacts.csv`

Offline text processing. Rows with `decision == "keep"` are scanned; all others
get the defaults below. Each row is still one search result, not one club.
Details: [stage 4](stages/stage4_extract_contact_info.md). Columns are all Stage 3
columns, then:

- `has_contact_signal`: bool; true if an email, Discord invite or contact word
  was found; `False` on unscanned rows
- `email_found`: deduplicated emails from page text and snippet, `; `-separated
- `discord_found`: Discord invites from page text, `; `-separated
