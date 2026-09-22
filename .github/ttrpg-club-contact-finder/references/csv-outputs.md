# TTRPG Club Finder — CSV Field Reference

Stage 1 (`classify_club_pages.py`) creates the ttrpg_club_search_results.csv; stage 2 (`extract_contact_info.py`) appends columns and outputs to ttrpg_club_contacts.csv. Gotcha numbers → skill's known-gotchas list. Each row represents a search result. Each college can have multiple searches and multiple search results. Stage 3 is a planned stage that would append more columns to the contacts CSV and makes use of an LLM.

## Implemented

| Column | Type | Stage | Notes |
|---|---|---|---|
| `unitid` | string | 1 | IPEDS unit ID |
| `college_name` | string | 1 | IPEDS institution name |
| `search_query` | string | 1 | Query sent to search API |
| `result_url` | string | 1 | — |
| `result_title` | string | 1 | — |
| `result_snippet` | string | 1 | — |
| `result_score` | float | 1 | Search API relevance score |
| `club_keywords_found_in_snippet` | string | 1 | List of `club_keywords.txt` hits in snippet |
| `ttrpg_keywords_found_in_snippet` | string | 1 | List of `ttrpg_keywords.txt` hits in snippet |
| `raw_content_status` | string | 1 | category of what happened to the extraction |
| `raw_content_error` | string | 1 | optional human-readable detail for the failure |
| `result_raw_content` | string | 1 | Extracted page text |
| `raw_content_length` | int | 1 | Length of `result_raw_content` |
| `club_keywords_found_in_text` | bool | 2 | `club_keywords.txt` hit in `result_raw_content` |
| `ttrpg_keywords_found_in_text` | bool | 2 | `ttrpg_keywords.txt` hit in `result_raw_content` |
| `has_contact_signal` | bool | 2 | True for real email/Discord match **or** bare "contact/email/discord" wording — not proof a contact exists |
| `email_found` | string, not bool | 2 | Email found; blank if none |
| `discord_found` | string, not bool | 2 | Discord link found; blank if none |

## Planned (not yet implemented)

| Column | Type | Stage | Notes |
|---|---|---|---|
| `official_university_website` | string | 0 | Official website of the school, usually not where club pages are hosted |
| `result_domain` | string | 1 | Domain of `result_url` |
| `domain_matches_webaddr` | bool | 1 | Matches IPEDS WEBADDR (signal, not filter) |
| `is_edu` | bool | 1 | `.edu` domain (signal, not filter) |
| `contact_signal_tier` | enum | 2 | `email`/`discord`/`vague-wording`/`none` — replaces `has_contact_signal` |
| `school_identifying_terms_found` | string | 3 | Org-identifying terms on page (e.g. "UConn," "Waterloo High School," or "not a school") |
| `directory_page_suspected` | bool | 3 | Dedicated club page vs. campus-wide listing |
| `name_variant_matched` | string | 3 | Which alias/abbreviation matched |
| `contact_context_snippet` | string | 3 | Text around the matched email/Discord/keyword |