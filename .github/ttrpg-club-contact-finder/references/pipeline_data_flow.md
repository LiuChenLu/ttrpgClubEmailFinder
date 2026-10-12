# TTRPG Club Finder — CSV Field Reference

## Stage 0 — `build_institution_dataset.py` output institutions.csv

Stage 0 pulls only the relevant columns from the IPEDS database and writes them to a CSV. This stage also filter out institutions that do not have an .edu website registered on ipeds, as insitutions that do not have such an official website are likely too small to be worth searching. It also filters out institutions whose name contains a term from config/excluded_institution_names.txt (beauty and cosmetology schools).

Each row represents an IPEDS institution.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `distance` | float | 0 | IPEDS distance from Hartford |
| `website` | string | 0 | IPEDS official website |

## Stage 1 - Fetch candidates with Search API (`fetch_candidates.py`) output search_results.csv

Stage 1 involves a network call to the search API to fetch search hits for each college. Each college can have multiple searches and multiple search results. Page content comes from the search call only.

Each row represents a search result except for sentinel rows used to log error.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `search_query` | string | 1 | Query of the best scoring search result across queries |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `result_score` | float | 1 | Search API relevance score |
| `result_snippet` | string | 1 | — |
| `raw_content_status` | string | 1 | result of the search-time raw_content fetch |
| `raw_content_length` | int | 1 | Length of `result_raw_content` |
| `result_raw_content` | string | 1 | Page text in markdown; blank if the search-time fetch failed |

## Stage 2 - Filter candidates (`filter_candidates.py`) output filtered_candidates.csv

Stage 2 filters the Stage 1 search results by title and snippet before any page repair (see `stage2_filter_candidates.md`). It writes every row, including discards, so the decisions and keyword evidence remain auditable. The original search fields and page text pass through for Stage 3.

Each row represents a search result except for sentinel rows used to log error.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `decision` | enum | 2 | `keep` or `discard`; sentinel and PDF rows are discarded |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `search_query` | string | 1 | Query of the best scoring search result across queries |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `result_score` | float | 1 | Search API relevance score |
| `result_snippet` | string | 1 | — |
| `raw_content_status` | string | 1 | result of the search-time raw_content fetch |
| `raw_content_length` | int | 1 | Length of `result_raw_content` |
| `result_raw_content` | string | 1 | Search-time page text; preserved for Stage 3 |
| `club_keywords_found_in_snippet` | string | 2 | Matching club keywords in title + snippet; Stage 2 audit/debug only |
| `ttrpg_keywords_found_in_snippet` | string | 2 | Matching TTRPG keywords in title + snippet; Stage 2 audit/debug only |

## Stage 3 - Render candidates (`render_candidates.py`) output rendered_results.csv

Stage 3 reads Stage 2's full audit output. Kept rows are repaired with Tavily `extract` and, when needed, Playwright (see `stage3_render_candidates.md`). Discarded rows pass through without network or browser rendering. All input rows are written, so row count is unchanged. The two keyword-hit debug columns are omitted; `decision` is retained for Stage 4.

Each row represents a search result except for sentinel rows used to log error.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `decision` | enum | 2 | `keep` or `discard`; controls whether Stage 3 renders the row |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `search_query` | string | 1 | Query of the best scoring search result across queries |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `result_score` | float | 1 | Search API relevance score |
| `result_snippet` | string | 1 | — |
| `raw_content_status` | string | 1 | Search-time page-content fetch status |
| `extract_status` | string | 3 | Tavily extract outcome; blank if not attempted |
| `raw_content_length` | int | 1, 3 | Length of final `result_raw_content` |
| `result_raw_content` | string | 1, 3 | Final page text; may come from search, extract, or Playwright |
| `render_status` | string | 3 | `not_needed` / `succeeded` / `failed_per_url`; blank for discarded rows and sentinels |
| `content_source` | string | 3 | `search` / `extract` / `playwright`; blank if content is blank |

## Stage 4 - Extract contact signals (`extract_contact_info.py`) output ttrpg_clubs_contacts.csv

Stage 4 scans only rows with `decision=keep` and derives contact signals from the rendered text and snippet. It does not yet classify school attribution or split directory pages into individual clubs. The separate LLM proposal is an unimplemented design draft.

Stage 4 input is `rendered_results.csv`. It preserves all Stage 3 columns and appends the contact fields below. `result_raw_content` is markdown or plain text depending on `content_source`; Playwright text omits link hrefs (`mailto:`, Discord invites), so extraction must not rely on markdown links. Every input row is written once, including discards, which are not scanned.

Each row represents one search result, not necessarily one club. Multiple search results may describe the same club, and directory pages are not split into individual clubs at this stage.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| All Stage 3 columns | — | 0–3 | Preserved, including `decision`; Stage 2 keyword-hit debug fields are absent |
| `has_contact_signal` | bool | 4 | Whether email, Discord, or contact wording was found; false on unscanned rows |
| `email_found` | string | 4 | Deduplicated email address(es); blank if none |
| `discord_found` | string | 4 | Discord invite(s); blank if none |