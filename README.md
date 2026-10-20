# TTRPG Club Email Finder

A pipeline that finds contact info (email, Discord) for tabletop-RPG and gaming
clubs at US colleges. It starts from the IPEDS institution list, searches for
club pages with Tavily, filters the results, re-fetches JavaScript-heavy pages
with Playwright, and extracts contact signals into a CSV.

**Current state:** the pipeline runs end to end and writes one row per search
result with contact signals. It does not yet identify individual clubs, check
which school a page belongs to, or use an LLM. Those are planned; see
[`specs/`](specs/README.md).

## Running it

Each stage is a script that reads the previous stage's CSV and writes its own
under `data/` (gitignored). The stage table is in
[`docs/architecture.md`](docs/architecture.md).

```bash
python build_institution_dataset.py
python fetch_candidates.py --limit 5     # Stage 1, a cheap sample
python filter_candidates.py
python render_candidates.py
python extract_contact_info.py
```

Every stage after Stage 0 takes `--input` and `--output`. Stage 1 reads a small
positive-control set by default. A full run is
`python fetch_candidates.py --input data/institutions.csv --yes`; it spends
Tavily credits, so check
[`docs/stages/stage1_fetch_candidates.md`](docs/stages/stage1_fetch_candidates.md)
first.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

- Create a `.env` file in the repository root with `TAVILY_API_KEY=...`
  (gitignored). Stages 1 and 3 need it.
- Stage 0 needs the IPEDS Access database at the path in `config.py`
  (`IPEDS_DB_PATH`) and the `mdb-export` command from `mdbtools`.
- The scratch scripts in `tmp/` also use `google-genai`: `pip install -e ".[scratch]"`.

## Tests

```bash
python -m pytest -q
```

They run offline. Known mismatches between code and intent are in
[`docs/known_bugs.md`](docs/known_bugs.md).

## Where to look

| Path               | What it holds                                                  |
| ------------------ | -------------------------------------------------------------- |
| `*.py` (top level) | Stage scripts and shared helpers                               |
| `schema.py`        | Column lists, decision values and discard reasons              |
| `config.py`        | Constants and paths                                            |
| `config/`          | Word lists and query templates the code reads                  |
| `tests/`           | pytest tests                                                   |
| `docs/`            | **What is implemented.** Describes the code at HEAD            |
| `specs/`           | **What is planned.** Not implemented; safe to iterate on       |
| `data/`, `tmp/`    | Local data and scratch scripts (gitignored)                    |
| `AGENTS.md`        | Instructions for AI coding agents                              |
