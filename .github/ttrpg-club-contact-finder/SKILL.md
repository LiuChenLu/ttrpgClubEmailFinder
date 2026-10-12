---
name: ttrpg-club-finder
description: Domain knowledge and pitfalls for the TTRPG-club contact-finding project — a pipeline that searches for university tabletop-RPG/gaming club pages via Tavily (rendering JS-heavy pages with Playwright) and extracts contact info (email/Discord) into a CSV. ALWAYS read this before touching config.py, tavily_client_util.py, search_row_format_util.py, build_institution_dataset.py, fetch_candidates.py, render_candidates.py, filter_candidates.py, or extract_contact_info.py — even if the request doesn't say "ttrpg" explicitly. Start here for pitfalls and conventions; see pipeline_data_flow.md for the exact CSV schema of each stage's output; then open the matching file under references/ for the stage you're actually editing — don't load all of them at once.
---

# TTRPG Club Finder — Project Knowledge

## Goal

Build a CSV of TTRPG/gaming club contacts across US colleges (~6,000 in IPEDS, ~4,000 after Stage 0's `.edu` filter). One row per club: **college name, contact info, source webpage, reason we believe it's correct.**

## Pipeline

A sequential, file-handoff pipeline — each stage is a separate script run, not concurrent execution. Every stage writes its full output to CSV before the next stage reads it.

**For the exact column-by-column schema of every stage's CSV — what each field means, which stage adds it, and how row cardinality changes stage to stage (e.g. one row per search result vs. one row per club) — see [`pipeline_data_flow.md`](pipeline_data_flow.md). It is the source of truth for data shape; this file covers pitfalls and conventions, not field-level schemas. Read it before writing any code that reads or writes one of these CSVs.**

| Stage | Script                                                                  | Output                         | Reference                                                                             |
| ----- | ----------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------- |
| 0     | `build_institution_dataset.py`                                          | `data/institutions.csv`        | [stage0_build_institution_dataset.md](references/stage0_build_institution_dataset.md) |
| 1     | `fetch_candidates.py`                                                   | `data/search_results.csv`      | [stage1_fetch_candidates.md](references/stage1_fetch_candidates.md)                   |
| 2     | `filter_candidates.py`                                                  | `data/filtered_candidates.csv` | [stage2_filter_candidates.md](references/stage2_filter_candidates.md)                 |
| 3     | `render_candidates.py`                                                  | `data/rendered_results.csv`    | [stage3_render_candidates.md](references/stage3_render_candidates.md)                 |
| 4     | `extract_contact_info.py`                                               | `data/ttrpg_clubs_contacts.csv` | [stage4_extract_contact_info.md](references/stage4_extract_contact_info.md)           |
| —     | `random_sample_institutions.py`, `ipeds_institution_has_ttrpg_club.csv` | test fixtures                  | [testing.md](references/testing.md)                                                   |

> **Known gap:** Stage 4 currently extracts contact signals only; school attribution, club classification, and directory-page splitting are not implemented. `LLM-proposal.md` is an early design draft and is not implemented.

Open the reference doc for the script you're actually editing — [stage0_build_institution_dataset.md](references/stage0_build_institution_dataset.md) for institution generation, [stage1_fetch_candidates.md](references/stage1_fetch_candidates.md) for search logic, [stage2_filter_candidates.md](references/stage2_filter_candidates.md) for filtering, [stage3_render_candidates.md](references/stage3_render_candidates.md) for `extract` and Playwright rendering, [stage4_extract_contact_info.md](references/stage4_extract_contact_info.md) for contact-signal extraction, or [testing.md](references/testing.md) for test fixtures — before writing that code. Each one only carries the pitfalls, API notes, and open gaps relevant to that stage; don't load all of them at once.

## Pitfalls — quick index

Full explanation, and which stage(s) each applies to, lives in the reference docs above. This list is just so nothing gets silently re-discovered:

1. Institution names don't always match club pages (e.g. "University of Connecticut" clubs may only ever say "UConn")
2. Wrong-school attribution — a good relevance score from the search engine doesn't guarantee the result is about the _target_ school
3. `WEBADDR` (IPEDS official site) isn't a usable domain filter — club pages routinely live off that domain on vendor-hosted club pages (CampusGroups, Modern Campus Involve, Anthology Engage, Corq, Lounge)
4. Some schools have amalgam/directory pages that list every student org on one page
5. Multi-campus systems (SUNY, UC, Penn State) — sometimes have seprate clubs for each site, sometimes only one for all campuses
6. Contact signals are valued differently: email > Discord invite > bare "contact us" wording
7. JS-heavy vendor pages (e.g. Anthology Engage) can come back from Tavily blank or stubbed (UConn and Skidmore return nothing; MIT's directory page renders fine). Stage 3 re-fetches kept rows with `extract` and Playwright; long stubs and short stubs on non-`.edu` hosts are missed by design.

## Code conventions (pipeline-wide)

- All constants/paths in `config.py`; word lists are line-delimited `.txt` files under `config/`.
- Code shared by Stages 1 and 3 is split by subject. `tavily_client_util.py` holds the Tavily client `tavily()` and `.env` loading. `search_row_format_util.py` holds the conventions of the search-result rows: `sanitize_for_csv`, the sentinel-row markers and `is_sentinel`, and the `csv.field_size_limit` setup. Import them rather than copying them, so the code that writes sentinel rows and the code that detects them can't drift apart. `config.py` stays free of the tavily dependency by design, and so does `search_row_format_util.py`. Stage 2 keeps its own local sentinel check.
- Comments explain _why_, not _what_ — several gating decisions are intentional; read them before changing gating logic.
- Stage-specific conventions are documented in the relevant reference doc, not here.
