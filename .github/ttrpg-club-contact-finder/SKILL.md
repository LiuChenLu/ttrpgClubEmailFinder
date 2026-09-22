---
name: ttrpg-club-finder
description: Domain knowledge and pitfalls for the TTRPG-club contact-finding project — a pipeline that searches for university tabletop-RPG/gaming club pages via Tavily and extracts contact info (email/Discord) into a CSV. ALWAYS read this before touching config.py, build_institution_dataset.py, fetch_candidates.py, filter_candidates.py, or extract_contact_info.py — even if the request doesn't say "ttrpg" explicitly. Start here for pitfalls and conventions; see pipeline_data_flow.md for the exact CSV schema of each stage's output; then open the matching file under references/ for the stage you're actually editing — don't load all of them at once.
---

# TTRPG Club Finder — Project Knowledge

## Goal

Build a CSV of TTRPG/gaming club contacts across US colleges (~6,000). One row per club: **college name, contact info, source webpage, reason we believe it's correct.** The pipeline only gathers signals — "is this really a club page" is decided downstream (human/LLM), not by any current gate.

## Pipeline

A sequential, file-handoff pipeline — each stage is a separate script run, not concurrent execution. Every stage writes its full output to CSV before the next stage reads it.

**For the exact column-by-column schema of every stage's CSV — what each field means, which stage adds it, and how row cardinality changes stage to stage (e.g. one row per search result vs. one row per club) — see [`pipeline_data_flow.md`](pipeline_data_flow.md). It is the source of truth for data shape; this file covers pitfalls and conventions, not field-level schemas. Read it before writing any code that reads or writes one of these CSVs.**

| Stage | Script                                                                  | Output                         | Reference                                                   |
| ----- | ----------------------------------------------------------------------- | ------------------------------ | ----------------------------------------------------------- |
| 0     | `build_institution_dataset.py`                                          | `data/institutions.csv`        | [stage0-instructions.md](references/stage0-instructions.md) |
| 1     | `fetch_candidates.py`                                                   | `data/candidates.csv`          | [stage1-instructions.md](references/stage1-instructions.md) |
| 2     | `filter_candidates.py`                                                  | `data/filtered_candidates.csv` | [stage2-instructions.md](references/stage2-instructions.md) |
| 3     | `extract_contact_info.py`                                               | `data/contacts.csv`            | [stage3-instructions.md](references/stage3-instructions.md) |
| —     | `random_sample_institutions.py`, `ipeds_institution_has_ttrpg_club.csv` | test fixtures                  | [testing.md](references/testing.md)                         |

> **Known gap:** this table reflects the redesigned 4-stage pipeline documented in `pipeline_data_flow.md` (the old Stage 1, `classify_club_pages.py`, is now split into a fetch step and a separate classify/filter step). The `references/*.md` docs below still describe the old 3-stage shape and script names and have not been updated to match — treat their stage numbers as stale until someone revises them.

Open the reference doc for the script you're actually editing — [stage0-institutions.md](references/stage0-institutions.md) for institution generation, [stage1-search.md](references/stage1-search.md) for search/fetch logic, [stage2-extraction.md](references/stage2-extraction.md) for filtering, extraction logic, or CSV assembly, [testing.md](references/testing.md) for test fixtures — before writing that code. Each one only carries the pitfalls, API notes, and open gaps relevant to that stage; don't load all of them at once.

## Pitfalls — quick index

Full explanation, and which stage(s) each applies to, lives in the reference docs above. This list is just so nothing gets silently re-discovered:

1. Names don't match pages (e.g. "University of Connecticut" clubs may only ever say "UConn")
2. Wrong-school attribution — a good relevance score doesn't guarantee the result is about the _target_ school
3. `WEBADDR` (IPEDS official site) isn't a usable domain filter — club pages routinely live off that domain
4. Vendor-hosted club pages (CampusGroups, Modern Campus Involve, Anthology Engage, Corq, Lounge)
5. Amalgam/directory pages that list every student org on one page
6. Multi-campus systems (SUNY, UC, Penn State) — match the specific campus, not the system
7. Contact signals rank differently: email > Discord invite > bare "contact us" wording

## Code conventions (pipeline-wide)

- All constants/paths in `config.py`; word lists are line-delimited `.txt` files under `config/`.
- Comments explain _why_, not _what_ — several gating decisions are intentional; read them before changing gating logic.
- Stage-specific conventions (Tavily client setup, CSV field-size handling, etc.) are documented in the relevant reference doc, not here.
