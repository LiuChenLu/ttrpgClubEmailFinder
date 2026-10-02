---
name: ttrpg-club-finder
description: Domain knowledge and pitfalls for the TTRPG-club contact-finding project — a pipeline that searches for university tabletop-RPG/gaming club pages via Tavily (rendering JS-heavy pages with Playwright) and extracts contact info (email/Discord) into a CSV. ALWAYS read this before touching config.py, build_institution_dataset.py, fetch_candidates.py, render_candidates.py, filter_candidates.py, or extract_contact_info.py — even if the request doesn't say "ttrpg" explicitly. Start here for pitfalls and conventions; see pipeline_data_flow.md for the exact CSV schema of each stage's output; then open the matching file under references/ for the stage you're actually editing — don't load all of them at once.
---

# TTRPG Club Finder — Project Knowledge

## Goal

Build a CSV of TTRPG/gaming club contacts across US colleges (~6,000 in IPEDS, ~4,000 after Stage 0's `.edu` filter). One row per club: **college name, contact info, source webpage, reason we believe it's correct.**

## Pipeline

A sequential, file-handoff pipeline — each stage is a separate script run, not concurrent execution. Every stage writes its full output to CSV before the next stage reads it.

**For the exact column-by-column schema of every stage's CSV — what each field means, which stage adds it, and how row cardinality changes stage to stage (e.g. one row per search result vs. one row per club) — see [`pipeline_data_flow.md`](pipeline_data_flow.md). It is the source of truth for data shape; this file covers pitfalls and conventions, not field-level schemas. Read it before writing any code that reads or writes one of these CSVs.**

| Stage | Script                                                                  | Output                         | Reference                                                     |
| ----- | ----------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------- |
| 0     | `build_institution_dataset.py`                                          | `data/institutions.csv`        | [stage0-instructions.md](references/stage0-instructions.md)   |
| 1a    | `fetch_candidates.py`                                                   | `data/search_results.csv`      | [stage1a-instructions.md](references/stage1a-instructions.md) |
| 1b    | `render_candidates.py`                                                  | `data/rendered_results.csv`    | [stage1b-instructions.md](references/stage1b-instructions.md) |
| 2     | `filter_candidates.py`                                                  | `data/filtered_candidates.csv` | [stage2-instructions.md](references/stage2-instructions.md)   |
| 3     | `extract_contact_info.py`                                               | `data/contacts.csv`            | [stage3-instructions.md](references/stage3-instructions.md)   |
| —     | `random_sample_institutions.py`, `ipeds_institution_has_ttrpg_club.csv` | test fixtures                  | [testing.md](references/testing.md)                           |

> **Known gap:** `extract_contact_info.py` (Stage 3) doesn't exist yet. `stage3-instructions.md` describes its planned rule-based design, not current behavior. `LLM-proposal.md` is a separate, early-stage draft for a possible LLM-based version instead. Neither is implemented.

Open the reference doc for the script you're actually editing — [stage0-instructions.md](references/stage0-instructions.md) for institution generation, [stage1a-instructions.md](references/stage1a-instructions.md) for search logic, [stage1b-instructions.md](references/stage1b-instructions.md) for `extract` and Playwright rendering, [stage2-instructions.md](references/stage2-instructions.md) for filtering logic, [stage3-instructions.md](references/stage3-instructions.md) for classification and contact-info extraction, or [testing.md](references/testing.md) for test fixtures — before writing that code. Each one only carries the pitfalls, API notes, and open gaps relevant to that stage; don't load all of them at once.

## Pitfalls — quick index

Full explanation, and which stage(s) each applies to, lives in the reference docs above. This list is just so nothing gets silently re-discovered:

1. Institution names don't always match club pages (e.g. "University of Connecticut" clubs may only ever say "UConn")
2. Wrong-school attribution — a good relevance score from the search engine doesn't guarantee the result is about the _target_ school
3. `WEBADDR` (IPEDS official site) isn't a usable domain filter — club pages routinely live off that domain on vendor-hosted club pages (CampusGroups, Modern Campus Involve, Anthology Engage, Corq, Lounge)
4. Some schools have amalgam/directory pages that list every student org on one page
5. Multi-campus systems (SUNY, UC, Penn State) — sometimes have seprate clubs for each site, sometimes only one for all campuses
6. Contact signals are valued differently: email > Discord invite > bare "contact us" wording
7. JS-heavy vendor pages (e.g. Anthology Engage) can come back from Tavily blank or stubbed (UConn and Skidmore return nothing; MIT's directory page renders fine). Stage 1b re-fetches them with `extract` and Playwright; long stubs and short stubs on non-`.edu` hosts are missed by design.

## Code conventions (pipeline-wide)

- All constants/paths in `config.py`; word lists are line-delimited `.txt` files under `config/`.
- Comments explain _why_, not _what_ — several gating decisions are intentional; read them before changing gating logic.
- Stage-specific conventions (Tavily client setup, CSV field-size handling, etc.) are documented in the relevant reference doc, not here.
