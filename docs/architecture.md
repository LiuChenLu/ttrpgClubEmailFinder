# Architecture and project knowledge (implemented behaviour)

This file describes the code as it is at HEAD. Planned work is in
[`specs/`](../specs/README.md), and known mismatches between code and intent are
in [known_bugs.md](known_bugs.md).

## Goal

Build a CSV of TTRPG/gaming club contacts across US colleges (about 6,000 in
IPEDS, 2,815 after Stage 0's filters at the time of writing). The long-term goal
is one row per club: college name, contact info, source webpage, and the reason
we believe it's correct. **Today the pipeline produces one row per search
result**, not per club (see [Stage 4](stages/stage4_extract_contact_info.md)).

## Pipeline

A sequential, file-handoff pipeline. Each stage is a separate script run, not
concurrent execution. Every stage writes its full output to CSV before the next
stage reads it. Column-by-column schemas are in [data_flow.md](data_flow.md);
read it before writing code that reads or writes one of these CSVs.

| Stage | Script                                                   | Output                          | Doc                                                  |
| ----- | -------------------------------------------------------- | ------------------------------- | ---------------------------------------------------- |
| 0     | `build_institution_dataset.py`                           | `data/institutions.csv`         | [stage0](stages/stage0_build_institution_dataset.md) |
| 1     | `fetch_candidates.py`                                    | `data/search_results.csv`       | [stage1](stages/stage1_fetch_candidates.md)          |
| 2     | `filter_candidates.py` (calls `rule_based_filtering.py`) | `data/filtered_candidates.csv`  | [stage2](stages/stage2_filter_candidates.md)         |
| 3     | `render_candidates.py`                                   | `data/rendered_results.csv`     | [stage3](stages/stage3_render_candidates.md)         |
| 4     | `extract_contact_info.py`                                | `data/ttrpg_clubs_contacts.csv` | [stage4](stages/stage4_extract_contact_info.md)      |

Stage 2 is rule-based only. No stage calls an LLM today.

Not implemented (see `specs/`): LLM triage after rule-based filtering; LLM club
identification, school attribution and directory-page splitting; URL
deduplication across campuses; checkpoint/resume for long runs.

## Pitfalls (quick index)

Full explanation, and which stage each applies to, is in the stage docs:

1. Institution names don't always match club pages (e.g. "University of
   Connecticut" clubs may only ever say "UConn").
2. Wrong-school attribution: a good relevance score from the search engine
   doesn't guarantee the result is about the _target_ school. Nothing in the
   pipeline checks this yet.
3. `WEBADDR` (IPEDS official site) isn't a usable domain filter. Club pages
   routinely live off that domain on vendor-hosted platforms (CampusGroups,
   Modern Campus Involve, Anthology Engage, Corq, Lounge).
4. Some schools have amalgam/directory pages that list every student org on one
   page. They are kept, and not split into clubs.
5. Multi-campus systems (SUNY, UC, Penn State) sometimes have separate clubs for
   each site and sometimes one club for all campuses.
6. Contact signals are valued differently: email > Discord invite > bare
   "contact us" wording.
7. JS-heavy vendor pages (e.g. Anthology Engage) can come back from Tavily blank
   or stubbed (UConn and Skidmore return nothing; MIT's directory page renders
   fine). Stage 3 re-fetches kept rows with `extract` and Playwright; long stubs
   and short stubs on non-`.edu` hosts are missed by design.

## Code conventions (pipeline-wide)

- All constants and paths are in `config.py`. Word lists are line-delimited
  `.txt` files under `config/`. `config/` only holds files the code reads.
- Code shared by Stages 1 and 3 is split by subject. `tavily_client_util.py`
  holds the Tavily client `tavily()` and `.env` loading.
  `search_row_format_util.py` holds `sanitize_for_csv`, the sentinel-row markers
  and `is_sentinel`, and the `csv.field_size_limit` setup. Import them rather
  than copying them, so the code that writes sentinel rows and the code that
  detects them can't drift apart. `config.py` and `search_row_format_util.py`
  stay free of the tavily dependency by design. Stage 2 keeps its own local
  sentinel check.
- Comments explain _why_, not _what_. Several gating decisions are intentional;
  read them before changing gating logic.
- Stage-specific conventions live in that stage's doc, not here.
