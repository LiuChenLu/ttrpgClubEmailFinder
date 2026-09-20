---
name: ttrpg-club-finder
description: Domain knowledge and pitfalls for the TTRPG-club contact-finding project — a pipeline that searches for university tabletop-RPG/gaming club pages via Tavily and extracts contact info (email/Discord) into a CSV. ALWAYS read this before touching config.py, gen_institutions.py, classify_club_pages.py, extract_contact_info.py, funnel_stats.py, random_sample_institutions.py, or any successor stage — even if the request doesn't say "ttrpg" explicitly. Also relevant for any college-club-finding or college-contact-scraping project built on Tavily at scale. Start here, then open the matching file under references/ for the stage you're actually editing — don't load all of them at once.
---

# TTRPG Club Finder — Project Knowledge

## Goal

Build a CSV of TTRPG/gaming club contacts across US colleges (~6,000). One row per club: **college name, contact info, source webpage, reason we believe it's correct.** The pipeline only gathers signals — "is this really a club page" is decided downstream (human/LLM), not by any current gate.

## Pipeline

A sequential, file-handoff pipeline — each stage is a separate script run, not concurrent execution. Every stage writes its full output to CSV before the next stage reads it.

| Stage | Script                                                                  | Output                                | Reference                                                                                                     |
| ----- | ----------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| 0     | `gen_institutions.py`                                                   | `data/institutions.csv`               | [stage0-institutions.md](references/stage0-institutions.md)                                                   |
| 1     | `classify_club_pages.py`                                                | `data/ttrpg_clubs_search_results.csv` | [stage1-search.md](references/stage1-search.md)                                                               |
| 2     | `extract_contact_info.py`                                               | `data/ttrpg_clubs_contacts.csv`       | [stage2-extraction.md](references/stage2-extraction.md) (also covers the not-yet-built Stage 3 assembly step) |
| —     | `random_sample_institutions.py`, `ipeds_institution_has_ttrpg_club.csv` | test fixtures                         | [testing.md](references/testing.md)                                                                           |

Open the reference doc for the script you're actually editing — [stage0-institutions.md](references/stage0-institutions.md) for institution generation, [stage1-search.md](references/stage1-search.md) for matching/search logic, [stage2-extraction.md](references/stage2-extraction.md) for extraction logic or CSV assembly, [testing.md](references/testing.md) for test fixtures — before writing that code. Each one only carries the pitfalls, API notes, and open gaps relevant to that stage; don't load all of them at once.

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
