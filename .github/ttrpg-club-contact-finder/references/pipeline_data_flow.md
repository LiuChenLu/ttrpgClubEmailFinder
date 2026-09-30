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

## Stage 1 - Fetch candidates with Search API (`fetch_candidates.py`) output candidates.csv

Stage 1 involves a network call to the search API to fetch search hits for each college. Each college can have multiple searches and multiple search results.

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
| `raw_content_status` | string | 1 | result of the raw_content fetch |
| `extract_status` | string | 1 | result of the extract fetch |
| `raw_content_length` | int | 1 | Length of `result_raw_content` |
| `result_raw_content` | string | 1 | Extracted page text |

## Stage 2 - Filter candidates (`filter_candidates.py`) output filtered_candidates.csv

Stage 2 filters the results from stage 1 to remove low quality hits. It is conservative with what it discards.

Each row represents a search result except for sentinel rows used to log error.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `decision` | enum | 2 | one of `keep`/`discard` |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `result_snippet` | string | 1 | — |
| `club_keywords_found_in_snippet` | string | 2 | List of `club_keywords.txt` hits in snippet |
| `ttrpg_keywords_found_in_snippet` | string | 2 | List of `ttrpg_keywords.txt` hits in snippet |
| `result_raw_content` | string | 1 | Extracted page text in markdown |
| `club_keywords_found_in_page` | string | 2 | List of `club_keywords.txt` hits in page |
| `ttrpg_keywords_found_in_page` | string | 2 | List of `ttrpg_keywords.txt` hits in page |
| `raw_content_length` | int | 1 | Length of `result_raw_content` |

## Stage 3 - Classify and extract contact info (`extract_contact_info.py`) output contacts.csv

**Status:** Not implemented — this stage doesn't exist yet, so nothing in the table below is populated by real output today. It describes the target schema: once built, Stage 3 is meant to classify each filtered candidate as a university club page, a conglomerate clubs page for the university, or not a club page, and pull out contact info from the page if it exists (see `stage3-instructions.md`). A separate LLM-based approach is proposed in `LLM-proposal.md`, an early design draft; its schema doesn't match this table.

Each row represents a club from a result. Each page can have multiple clubs, thus create multiple rows. Each club can also have multiple web results about it, thus each club could have mulitiple rows.

| Column | Type | Stage | Notes |
| --- | --- | --- | --- |
| `club_name` | string | 3 | The club name, if any |
| `unitid` | string | 1 | IPEDS unit ID |
| `college_name` | string | 1 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `classification` | enum | 3 | one of `club`/`conglam`/`not-a-club` |
| `school_identifying_terms_found` | string | 3 | Org-identifying terms on page (e.g. "UConn," "Waterloo High School") |
| `name_variant_matched` | string | 3 | Which alias/abbreviation matched |
| `contact_signal_tier` | enum | 3 | `email`/`discord`/`vague-wording`/`none` — TODO replaces `has_contact_signal` |
| `email_found` | string, not bool | 3 | Email found; blank if none |
| `discord_found` | string, not bool | 3 | Discord link found; blank if none |
| `contact_context_snippet` | string | 3 | Text around the matched email/Discord/keyword |