# TTRPG Club Finder — CSV Field Reference

## Stage 0 — `build_institution_dataset.py` output institutions.csv

Stage 0 pulls only the relevant columns from the IPEDS database and writes them to a CSV.

Each row represents an IPEDS institution. 

| Column | Type | Stage | Notes |
|---|---|---|---|
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name <!-- TODO change NAME to college_name and lower case all the csv headers -->|
| `city` | string | 0 | IPEDS city |
| `distance` | float | 0 | IPEDS distance from Hartford |
| `website` | string | 0 | IPEDS official website |

## Stage 1 - Fetch candidates with Search API (`fetch_candidates.py`) output candidates.csv

Stage 1 involves a network call to the search API to fetch search hits for each college that is significant enough to be considered. We use "does this college have an official .edu website registered on ipeds" as the signal for significant. Each college can have multiple searches and multiple search results. If raw_content fails to fetch and the website that has a `.edu` domain, has the college name in the address, or matches the IPEDS WEBADDR, we try to extract the page text.

Each row represents a search result.

| Column | Type | Stage | Notes |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `website` | string | 0 | IPEDS official website |
| `search_query` | string | 1 | Query sent to search API |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `result_score` | float | 1 | Search API relevance score |
| `result_snippet` | string | 1 | — |
| `raw_content_error` | string | 1 | optional human-readable detail for the failure |
| `raw_content_status` | string | 1 | category of what happened to the extraction |
| `raw_content_length` | int | 1 | Length of `result_raw_content` |
| `result_raw_content` | string | 1 | Extracted page text |

## Stage 2 - Filter candidates (`filter_candidates.py`) output filtered_candidates.csv

Stage 2 deduplicates and filters the results from stage 1 to remove low quality hits. It is conservative with what it discards.

It discards any website that does not mention a club related term and a ttrpg related term in the snippet or raw results. It also discards any webpage from a domain that is in the list of excluded domains.

Each row represents a search result.

| Column | Type | Stage | Notes |
| `decision` | enum | 2 | one of `keep`/`discard` |
| `unitid` | string | 0 | IPEDS unit ID |
| `college_name` | string | 0 | IPEDS institution name |
| `city` | string | 0 | IPEDS city |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `result_snippet` | string | 1 | — |
| `club_keywords_found_in_snippet` | string | 1 | List of `club_keywords.txt` hits in snippet |
| `ttrpg_keywords_found_in_snippet` | string | 1 | List of `ttrpg_keywords.txt` hits in snippet |
| `result_raw_content` | string | 1 | Extracted page text |
| `club_keywords_found_in_page` | string | 1 | List of `club_keywords.txt` hits in page |
| `ttrpg_keywords_found_in_page` | string | 1 | List of `ttrpg_keywords.txt` hits in page |
| `raw_content_length` | int | 1 | Length of `result_raw_content` |
| `extraction_status` | string | 1 | category of what happened to the extraction |
| `raw_content_error` | string | 1 | optional human-readable detail for the failure |

## Stage 3 - Classify with LLM contact info (`extract_contact_info.py`) output contacts.csv

Stage 3 feeds the filtered candidates to an LLM to classify them as a university club page, a conglamorate clubs page for the university, or not a club page. The LLM will also pull out contact info from the page if it exists.

Each row represents a club from a result. Each page can have multiple clubs, thus create multiple rows. Each club can also have multiple web results about it, thus each club could have mulitiple rows.

| Column | Type | Stage | Notes |
| `club_name` | string | 3 | The club name, if any |
| `unitid` | string | 1 | IPEDS unit ID |
| `college_name` | string | 1 | IPEDS institution name |
| `result_title` | string | 1 | — |
| `result_url` | string | 1 | — |
| `classification` | enum | 3 | one of `club`/`conglam`/`not-a-club` |
| `school_identifying_terms_found` | string | 3 | Org-identifying terms on page (e.g. "UConn," "Waterloo High School") |
| `name_variant_matched` | string | 3 | Which alias/abbreviation matched |
| `contact_signal_tier` | enum | 3 | `email`/`discord`/`vague-wording`/`none` — TODO replaces `has_contact_signal` |
| `email_found` | string, not bool | 3 | Email found; blank if none |
| `discord_found` | string, not bool | 3 | Discord link found; blank if none |
| `contact_context_snippet` | string | 3 | Text around the matched email/Discord/keyword |
