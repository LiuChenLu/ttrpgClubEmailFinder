# TTRPG Club Finder — CSV Field Reference

## Stage 0 — `build_institution_dataset.py` output institutions.csv

Stage 0 pulls only the relevant columns from the IPEDS database and writes them to a CSV. This stage also filter out institutions that do not have an .edu website registered on ipeds, as insitutions that do not have such an official website are likely too small to be worth searching.

Each row represents an IPEDS institution.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `distance` | float | 0 | IPEDS distance from Hartford |
| `website` | string | 0 | IPEDS official website |

## Stage 1a - Fetch candidates with Search API (`fetch_candidates.py`) output search_results.csv

Stage 1a involves a network call to the search API to fetch search hits for each college. Each college can have multiple searches and multiple search results. Page content comes from the search call only.

Each row represents a search result except for sentinel rows used to log error.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `search_query` | string | 1a | Query of the best scoring search result across queries |
| `result_title` | string | 1a | — |
| `result_url` | string | 1a | — |
| `result_score` | float | 1a | Search API relevance score |
| `result_snippet` | string | 1a | — |
| `raw_content_status` | string | 1a | result of the search-time raw_content fetch |
| `raw_content_length` | int | 1a | Length of `result_raw_content` |
| `result_raw_content` | string | 1a | Page text in markdown; blank if the search-time fetch failed |

## Stage 1b - Render candidates (`render_candidates.py`) output rendered_results.csv

Stage 1b repairs blank or suspiciously short page content with Tavily `extract`, then Playwright (see `stage1b-instructions.md`). It reads search_results.csv and writes every row, so row count is unchanged; sentinel rows pass through with `render_status` and `content_source` blank.

Each row represents a search result except for sentinel rows used to log error.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `search_query` | string | 1a | Query of the best scoring search result across queries |
| `result_title` | string | 1a | — |
| `result_url` | string | 1a | — |
| `result_score` | float | 1a | Search API relevance score |
| `result_snippet` | string | 1a | — |
| `raw_content_status` | string | 1a | result of the search-time raw_content fetch |
| `extract_status` | string | 1b | result of the Tavily extract attempts; blank if not attempted |
| `raw_content_length` | int | 1a, 1b | Length of the final `result_raw_content` |
| `result_raw_content` | string | 1a, 1b | Page text: markdown if `content_source` is `search` or `extract`, plain text if `playwright`; blank if every attempt failed |
| `render_status` | string | 1b | `not_needed` / `succeeded` / `failed_per_url`; blank on sentinel rows |
| `content_source` | string | 1b | `search` / `extract` / `playwright`; blank if content is blank or on sentinel rows |

## Stage 2 - Filter candidates (`filter_candidates.py`) output filtered_candidates.csv

Stage 2 filters the results from stage 1b (rendered_results.csv) to remove low quality hits. It is conservative with what it discards.

Each row represents a search result except for sentinel rows used to log error.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `decision` | enum | 2 | one of `keep`/`discard` |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `result_title` | string | 1a | — |
| `result_url` | string | 1a | — |
| `result_snippet` | string | 1a | — |
| `club_keywords_found_in_snippet` | string | 2 | List of `club_keywords.txt` hits in snippet |
| `ttrpg_keywords_found_in_snippet` | string | 2 | List of `ttrpg_keywords.txt` hits in snippet |
| `result_raw_content` | string | 1a, 1b | Page text: markdown if `content_source` is `search` or `extract`, plain text if `playwright` |
| `club_keywords_found_in_page` | string | 2 | List of `club_keywords.txt` hits in page |
| `ttrpg_keywords_found_in_page` | string | 2 | List of `ttrpg_keywords.txt` hits in page |
| `raw_content_length` | int | 1a, 1b | Length of `result_raw_content` |
| `content_source` | string | 1b | `search` / `extract` / `playwright`; carried through from Stage 1b |

## Stage 3 - Classify and extract contact info (`extract_contact_info.py`) output contacts.csv

**Status:** Not implemented — this stage doesn't exist yet, so nothing in the table below is populated by real output today. It describes the target schema: once built, Stage 3 is meant to classify each filtered candidate as a university club page, a conglomerate clubs page for the university, or not a club page, and pull out contact info from the page if it exists (see `stage3-instructions.md`). A separate LLM-based approach is proposed in `LLM-proposal.md`, an early design draft; its schema doesn't match this table.

Stage 3 input is `filtered_candidates.csv`. `result_raw_content` is markdown or plain text depending on `content_source`; Playwright text omits link hrefs (`mailto:`, Discord invites), so extraction must not rely on markdown links.

Each row represents a club from a result. Each page can have multiple clubs, thus create multiple rows. Each club can also have multiple web results about it, thus each club could have mulitiple rows.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `club_name` | string | 3 | The club name, if any |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `result_title` | string | 1a | — |
| `result_url` | string | 1a | — |
| `classification` | enum | 3 | one of `club`/`conglam`/`not-a-club` |
| `school_identifying_terms_found` | string | 3 | Org-identifying terms on page (e.g. "UConn," "Waterloo High School") |
| `name_variant_matched` | string | 3 | Which alias/abbreviation matched |
| `contact_signal_tier` | enum | 3 | `email`/`discord`/`vague-wording`/`none` — TODO replaces `has_contact_signal` |
| `email_found` | string, not bool | 3 | Email found; blank if none |
| `discord_found` | string, not bool | 3 | Discord link found; blank if none |
| `contact_context_snippet` | string | 3 | Text around the matched email/Discord/keyword |