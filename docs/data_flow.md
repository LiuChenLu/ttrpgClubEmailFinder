# CSV field reference (implemented behaviour)

Column lists below come from the code at HEAD: `build_institution_dataset.py`,
`fetch_candidates.py` (`NEW_FIELDNAMES`), `rule_based_filtering.py`
(`FILTERED_FIELDNAMES`), `render_candidates.py` (`output_fieldnames()`) and
`extract_contact_info.py` (`NEW_FIELDNAMES`). The files in `data/` are
gitignored and may have been produced by older code, so don't treat them as the
schema. Planned columns live under [`specs/`](../specs/README.md), not here.

Each stage reads the previous stage's CSV and writes its own. Paths are
constants in `config.py`.

| Stage | Output                          | One row per                                                  |
| ----- | ------------------------------- | ------------------------------------------------------------ |
| 0     | `data/institutions.csv`         | IPEDS institution that passes the filters                    |
| 1     | `data/search_results.csv`       | search result per college (deduplicated), plus sentinel rows |
| 2     | `data/filtered_candidates.csv`  | Stage 1 row (all kept)                                       |
| 3     | `data/rendered_results.csv`     | Stage 2 row (all kept)                                       |
| 4     | `data/ttrpg_clubs_contacts.csv` | Stage 3 row (all kept)                                       |

## Stage 0 — `build_institution_dataset.py` → `institutions.csv`

Pulls the relevant columns from IPEDS and drops institutions unlikely to have a
TTRPG club. The filter rules are in
[stage0_build_institution_dataset.md](stages/stage0_build_institution_dataset.md).

| Column              | Type   | Notes                                             |
| ------------------- | ------ | ------------------------------------------------- |
| `unitid`            | string | IPEDS unit ID                                     |
| `college_name`      | string | IPEDS institution name                            |
| `aliases`           | string | Official IPEDS aliases (`IALIAS`), `\|`-separated |
| `generated_aliases` | string | Generated shortened name variants, `\|`-separated |
| `city`              | string | IPEDS city                                        |
| `distance`          | float  | Distance from Hartford. Stage 1 drops it          |
| `website`           | string | IPEDS official website (`WEBADDR`)                |

## Stage 1 — `fetch_candidates.py` → `search_results.csv`

Network calls to the Tavily search API. Each college can have several queries
and several results. Page content comes from the search call only. Each row is a
search result, except for sentinel rows that log an error. Sentinel format is in
[stage1_fetch_candidates.md](stages/stage1_fetch_candidates.md).

| Column               | Type   | Added by | Notes                                                        |
| -------------------- | ------ | -------- | ------------------------------------------------------------ |
| `unitid`             | string | 0        |                                                              |
| `college_name`       | string | 0        |                                                              |
| `aliases`            | string | 0        |                                                              |
| `generated_aliases`  | string | 0        |                                                              |
| `city`               | string | 0        |                                                              |
| `website`            | string | 0        |                                                              |
| `search_query`       | string | 1        | Query of the best-scoring result across queries              |
| `result_title`       | string | 1        | Holds the exception text on error sentinel rows              |
| `result_url`         | string | 1        | `ERROR` on error sentinels, blank on no-results sentinels    |
| `result_score`       | float  | 1        | Search API relevance score                                   |
| `result_snippet`     | string | 1        | Snippets from every query that returned the hit, joined      |
| `raw_content_status` | string | 1        | Search-time fetch outcome: `succeeded`, `empty` or `missing` |
| `raw_content_length` | int    | 1        | Length of `result_raw_content`                               |
| `result_raw_content` | string | 1        | Page text as markdown; blank if the fetch failed             |

## Stage 2 — `filter_candidates.py` → `filtered_candidates.csv`

Rule-based only; there is no LLM step. Every input row is written. Rules and
`decision` values:
[stage2_filter_candidates.md](stages/stage2_filter_candidates.md).

| Column                            | Type   | Added by | Notes                                                                                                                                                      |
| --------------------------------- | ------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `decision`                        | string | 2        | `keep`, or `discard_pdf`, `discard_news`, `discard_event`, `discard_storefronts`, `discard_snippets_has_no_club_or_ttrpg_keywords`, `discard_sentinel_row` |
| `unitid` … `website`              | string | 0        | Same six columns as Stage 1                                                                                                                                |
| `search_query`                    | string | 1        |                                                                                                                                                            |
| `result_title`                    | string | 1        |                                                                                                                                                            |
| `result_url`                      | string | 1        |                                                                                                                                                            |
| `result_snippet`                  | string | 1        |                                                                                                                                                            |
| `raw_content_status`              | string | 1        |                                                                                                                                                            |
| `raw_content_length`              | int    | 1        |                                                                                                                                                            |
| `result_raw_content`              | string | 1        | Preserved for Stage 3                                                                                                                                      |
| `club_keywords_found_in_snippet`  | string | 2        | Club keywords found in title + snippet, `; `-separated. Audit only                                                                                         |
| `ttrpg_keywords_found_in_snippet` | string | 2        | TTRPG keywords found in title + snippet. Audit only                                                                                                        |

`result_score` is not carried forward (known bug 2 in
[known_bugs.md](known_bugs.md)).

## Stage 3 — `render_candidates.py` → `rendered_results.csv`

Rows with `decision == "keep"` get blank or short content repaired with Tavily
`extract` and then Playwright. All other rows pass through with the three new
columns blank. Row count is unchanged. Details:
[stage3_render_candidates.md](stages/stage3_render_candidates.md).

Columns are all Stage 2 columns in the same order, with `extract_status`
inserted right after `raw_content_status`, and `render_status` and
`content_source` appended at the end.

| Column               | Type   | Added by | Notes                                                                                                                            |
| -------------------- | ------ | -------- | -------------------------------------------------------------------------------------------------------------------------------- |
| All Stage 2 columns  | —      | 0–2      | Including `decision` and, because of known bug 1, the two keyword debug columns                                                  |
| `extract_status`     | string | 3        | `succeeded`, `succeeded_empty`, `failed_per_url`, `failed_exception` or `no_response_entry`; blank if `extract` wasn't attempted |
| `raw_content_length` | int    | 1, 3     | Recomputed from the final content                                                                                                |
| `result_raw_content` | string | 1, 3     | Final page text: markdown from search or extract, plain text from Playwright                                                     |
| `render_status`      | string | 3        | `not_needed`, `succeeded` or `failed_per_url`; blank for discarded rows and sentinels                                            |
| `content_source`     | string | 3        | `search`, `extract` or `playwright`; blank if content is blank                                                                   |

## Stage 4 — `extract_contact_info.py` → `ttrpg_clubs_contacts.csv`

Offline text processing. Rows with `decision == "keep"` are scanned; all other
rows get the defaults shown below. Each row is still one search result, not one
club: multiple results may describe the same club, and directory pages are not
split. School attribution is not checked. Details:
[stage4_extract_contact_info.md](stages/stage4_extract_contact_info.md).

`result_raw_content` is markdown or plain text depending on `content_source`.
Playwright text has no link hrefs (`mailto:`, Discord invites), so extraction
can't rely on markdown links.

| Column               | Type   | Added by | Notes                                                                                 |
| -------------------- | ------ | -------- | ------------------------------------------------------------------------------------- |
| All Stage 3 columns  | —      | 0–3      | Preserved                                                                             |
| `has_contact_signal` | bool   | 4        | True if an email, Discord invite or contact word was found; `False` on unscanned rows |
| `email_found`        | string | 4        | Deduplicated emails from page text and snippet, `; `-separated; blank if none         |
| `discord_found`      | string | 4        | Discord invites from page text, `; `-separated; blank if none                         |
