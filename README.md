# TTRPG Club Email Finder

A pipeline that finds contact info (email, Discord) for tabletop-RPG and gaming
clubs at US colleges. It starts from the IPEDS institution list, searches for
club pages with Tavily, filters the results, re-fetches JavaScript-heavy pages
with Playwright, and extracts contact signals into a CSV.

**Current state:** the pipeline runs end to end and writes one row per search
result with contact signals. It does not yet identify individual clubs, check
which school a page belongs to, or use an LLM. Those are planned; see
[`specs/`](specs/README.md).

## Pipeline

Each stage is a separate script. It reads the previous stage's CSV and writes
its own, under `data/` (gitignored).

| Stage | Script                                | Output                          |
| ----- | ------------------------------------- | ------------------------------- |
| 0     | `python build_institution_dataset.py` | `data/institutions.csv`         |
| 1     | `python fetch_candidates.py`          | `data/search_results.csv`       |
| 2     | `python filter_candidates.py`         | `data/filtered_candidates.csv`  |
| 3     | `python render_candidates.py`         | `data/rendered_results.csv`     |
| 4     | `python extract_contact_info.py`      | `data/ttrpg_clubs_contacts.csv` |

Paths and tunable constants are in `config.py`. Stage 1 reads
`data/iped_institution_has_ttrpg_club.csv` (a small positive-control set), so a
plain run is cheap. Point `DEFAULT_INPUT_CSV` at `data/institutions.csv` for a
full run, and check Tavily credit use first (see
[`docs/stages/stage1_fetch_candidates.md`](docs/stages/stage1_fetch_candidates.md)).

## Setup

The code imports `pandas`, `python-dotenv`, `tavily-python`, `playwright` and
`pytest`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install pandas python-dotenv tavily-python playwright pytest
playwright install chromium
```

- Create a `.env` file in the repository root with `TAVILY_API_KEY=...`
  (gitignored). Stages 1 and 3 need it.
- Stage 0 needs the IPEDS Access database at
  `data/ipeds/IPEDS_2024-25_Provisional/IPEDS202425.accdb` and the `mdb-export`
  command from `mdbtools`.

## Tests

```bash
python -m pytest -q --ignore=tests/test_search_providers.py
```

Two tests currently fail and one test file is stale; both are tracked in
[`docs/known_bugs.md`](docs/known_bugs.md).

## Repository layout

| Path               | What it holds                                                       |
| ------------------ | ------------------------------------------------------------------- |
| `*.py` (top level) | Stage scripts and shared helpers                                    |
| `config/`          | Keyword lists, query templates, and other data files the code reads |
| `tests/`           | pytest tests                                                        |
| `docs/`            | **What is implemented.** Describes the code at HEAD                 |
| `specs/`           | **What is planned.** Not implemented; safe to iterate on            |
| `data/`, `tmp/`    | Local data and scratch scripts (gitignored)                         |
| `AGENTS.md`        | Instructions for AI coding agents                                   |

## Documentation

- [`docs/architecture.md`](docs/architecture.md): pipeline overview, pitfalls
  and conventions
- [`docs/data_flow.md`](docs/data_flow.md): the columns of every stage's CSV
- [`docs/stages/`](docs/stages/): one doc per stage
- [`docs/known_bugs.md`](docs/known_bugs.md): where code differs from intent
- [`specs/README.md`](specs/README.md): planned work and how specs become docs
