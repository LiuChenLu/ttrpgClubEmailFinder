# AGENTS.md

Instructions for AI coding agents. Human overview: [README.md](README.md).

## What this is

A pipeline (Stages 0 to 4, one script each) that finds contact info for TTRPG
clubs at US colleges. Map of stages, files and pitfalls:
[docs/architecture.md](docs/architecture.md). The only LLM call is Stage 2b triage (Gemini).

## Which source is true

When sources disagree, trust them in this order:

1. **Code** (`*.py`, `config/`) and `schema.py` for column names.
2. **Tests** (`tests/`).
3. **`docs/`**: describes the code at HEAD.
4. **`specs/`**: planned, **not implemented**. Never evidence of current
   behaviour. Don't implement a spec unless the user asks.

## Before you edit

1. Read [docs/architecture.md](docs/architecture.md), then only the doc for your
   stage in [docs/stages/](docs/stages/).
2. Changing a CSV column: edit `schema.py` first, then
   [docs/data_flow.md](docs/data_flow.md). `tests/test_docs.py` checks they match.
3. Check [docs/known_bugs.md](docs/known_bugs.md) before "fixing" a mismatch.

## Conventions

- Constants and paths go in `config.py`; column lists, decision values and
  discard reasons in `schema.py`; word lists in `config/*.txt`. Reuse the shared
  helpers listed in architecture.md instead of copying them.
- Only `schema.KEEP` (`is_keep(row)`) means keep. Anything else is a discard.
- Comments explain why, not what.
- Tests must not need network access or API keys. Inject clients and renderers
  as arguments, as `render_candidates.render_row` does.

## Commands

```bash
source .venv/bin/activate
python -m pytest -q          # offline; must pass before you finish
python fetch_candidates.py --limit 3     # a sample Stage 1 run
```

Stage 2b calls Gemini, which spends quota. `tests/test_llm_triage_gemini_live_network.py`
is skipped unless `RUN_GEMINI_LIVE_TESTS=1`; **never set it, or run
`llm_triage.py` on a real input, without the user's approval.** Use a small
`--input`/`--output` sample.

Stage 1 and Stage 3 spend Tavily credits. Stage 1 refuses a run estimated above
`MAX_UNCONFIRMED_SEARCH_CREDITS` unless given `--yes`; **never pass `--yes`, or
run either stage on the full institution list, without the user's approval.**
Use `--input`/`--output` for samples instead of editing `config.py`. `.env` holds
the API key; never print or commit it.

## Keeping docs accurate

- Changing code: update the matching `docs/` file in the same change.
- `docs/` describes behaviour that exists at HEAD only. Known limits of built
  code go in the stage doc's "Open gaps". Planned behaviour goes in `specs/`.
- Code differs from tests or intent: record it in `docs/known_bugs.md`; remove
  the entry when fixed.
- Implementing a spec: build it, update the docs its header names, then delete
  the spec or the part that landed ([specs/README.md](specs/README.md)).
- Each fact has one home. Link to it; don't restate it.
