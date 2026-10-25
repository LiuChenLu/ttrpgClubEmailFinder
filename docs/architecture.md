# Architecture (implemented behaviour)

Describes the code at HEAD. Planned work is in [`specs/`](../specs/README.md).
Where code differs from intent, see [known_bugs.md](known_bugs.md).

## Goal

Build a CSV of TTRPG/gaming club contacts across US colleges. The long-term goal
is one row per club: college name, contact info, source webpage, and why we
believe it. **Today the pipeline produces one row per search result**, not per
club.

## Pipeline

Sequential file handoff. Each stage is a separate script run that reads the
previous stage's CSV and writes its own to `data/` (gitignored). Every stage
except Stage 0 takes `--input` and `--output`. Column lists are in
[`schema.py`](../schema.py) and described in [data_flow.md](data_flow.md).

| Stage | Script                                                   | Output                          | Doc                                                  |
| ----- | -------------------------------------------------------- | ------------------------------- | ---------------------------------------------------- |
| 0     | `build_institution_dataset.py`                           | `data/institutions.csv`         | [stage0](stages/stage0_build_institution_dataset.md) |
| 1     | `fetch_candidates.py`                                    | `data/search_results.csv`       | [stage1](stages/stage1_fetch_candidates.md)          |
| 2     | `filter_candidates.py` (calls `rule_based_filtering.py`, then `llm_triage.py`) | `data/filtered_candidates.csv`, `data/llm_filtered_candidates.csv` | [stage2](stages/stage2_filter_candidates.md)         |
| 3     | `render_candidates.py`                                   | `data/rendered_results.csv`     | [stage3](stages/stage3_render_candidates.md)         |
| 4     | `extract_contact_info.py`                                | `data/ttrpg_clubs_contacts.csv` | [stage4](stages/stage4_extract_contact_info.md)      |

Only Stage 2b calls an LLM (Gemini, labels from URL and title), and Stage 3
still reads the 2a file. Not implemented (see `specs/`): club identification, school
attribution, directory-page splitting, URL deduplication across campuses,
checkpoint/resume.

## Where things live

| Need                                              | File                                                                 |
| ------------------------------------------------- | -------------------------------------------------------------------- |
| A constant, path or threshold                     | `config.py`                                                          |
| A word list or query template                     | `config/*.txt` (only files the code reads)                           |
| A column list, decision value or discard reason   | `schema.py`                                                          |
| The `--input` / `--output` options                | `stage_cli.py`                                                       |
| Tavily client, `.env` loading                     | `tavily_client_util.py`                                              |
| The Stage 2b LLM call, prompt and examples        | `gemini_client_util.py`, `config/triage_prompt.md`, `config/llm_triage_examples.jsonl` |
| The SQLite database (`config.DATABASE_PATH`) and its schema | `triage_store.py`; the schema is the numbered `migrations/*.sql` files (nothing writes to the database yet) |
| `sanitize_for_csv`, sentinel markers, `is_sentinel` | `search_row_format_util.py`                                        |
| URL host and registrable-domain parsing           | `url_parsing_utils.py`                                               |

Import these; never copy them. `config.py`, `schema.py` and
`search_row_format_util.py` must not import `tavily`, so tests and offline
stages need no API key. Importing `search_row_format_util` raises
`csv.field_size_limit`, which every stage that reads page text needs.

## Pitfalls

Each is explained in the stage doc that owns it:

- Institution names don't match club pages ("UConn"), and nothing checks that a
  result is about the *target* school: [stage 2](stages/stage2_filter_candidates.md).
- `website` (IPEDS `WEBADDR`) is not a domain filter, and club pages live on
  vendor platforms: [stage 1](stages/stage1_fetch_candidates.md).
- Directory pages are kept, not split; multi-campus systems vary:
  [stage 2](stages/stage2_filter_candidates.md).
- JS-heavy pages come back blank or stubbed, and Playwright text has no hrefs:
  [stage 3](stages/stage3_render_candidates.md).
- Contact signals rank email > Discord invite > bare "contact us" wording:
  [stage 4](stages/stage4_extract_contact_info.md).

## Conventions

- Comments explain *why*, not *what*. Several gating decisions are intentional;
  read their comments before changing them.
- Stage-specific conventions live in that stage's doc.
