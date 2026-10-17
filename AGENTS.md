# AGENTS.md

Instructions for AI coding agents working in this repository. For a human
overview, see [README.md](README.md).

## What this project is

A pipeline (Stages 0 to 4, one script each) that finds contact info for TTRPG
clubs at US colleges. See [docs/architecture.md](docs/architecture.md).

## Which source is true

The repository separates what exists from what is planned. When sources
disagree, trust them in this order:

1. **The code** (`*.py`, `config/`).
2. **The tests** (`tests/`).
3. **`docs/`**: describes the code at HEAD, and must stay accurate.
4. **`specs/`**: planned behaviour that is **not implemented**. A spec is never
   evidence of how the code behaves today. Do not implement from a spec unless
   the user asks you to.

There is currently **no LLM stage**. Stage 2 is rule-based only. The LLM triage
and LLM contact extraction designs are specs.

## Before you edit code

1. Read [docs/architecture.md](docs/architecture.md) for pitfalls and
   conventions.
2. Read the doc for the stage you are editing in [docs/stages/](docs/stages/).
   Don't load them all.
3. Read [docs/data_flow.md](docs/data_flow.md) before changing any CSV column.
4. Check [docs/known_bugs.md](docs/known_bugs.md) so you don't "fix" a
   documented mismatch by accident.

## Conventions

- All constants and paths go in `config.py`. Word lists are line-delimited
  `.txt` files in `config/`. `config/` holds only files the code reads.
- Shared helpers: `tavily_client_util.py` (Tavily client, `.env` loading) and
  `search_row_format_util.py` (`sanitize_for_csv`, sentinel markers,
  `is_sentinel`, `csv.field_size_limit`). Import them; don't copy them.
  `config.py` and `search_row_format_util.py` must not import `tavily`.
- Downstream stages treat `decision == "keep"` as the only keep value. Any
  `discard_*` value is a discard.
- Comments explain why, not what.
- Tests must not need network access or API keys. Inject clients and renderers
  as arguments, as `render_candidates.render_row` does.

## Running tests

```bash
source .venv/bin/activate
python -m pytest -q --ignore=tests/test_search_providers.py
```

Known state: 2 tests in `tests/test_render_candidates.py` fail, and
`tests/test_search_providers.py` is stale. Both are in
[docs/known_bugs.md](docs/known_bugs.md). Don't add new failures.

Never run Stage 1 or Stage 3 against the full institution list without the
user's approval: they spend Tavily credits. `.env` holds the API key; never
print or commit it.

## Keeping the docs accurate

- **Changing code:** update the matching `docs/` files in the same change. If
  you add, remove or rename a CSV column, update
  [docs/data_flow.md](docs/data_flow.md).
- **`docs/` may only describe behaviour that exists at HEAD.** Known limits of
  built code go in the stage doc's "Open gaps" section. Planned behaviour goes
  in `specs/`.
- **Code differs from tests or intent?** Record it in
  [docs/known_bugs.md](docs/known_bugs.md) instead of describing the code as if
  it were correct. Remove the entry when fixed.
- **Implementing a spec:** build it, update the `docs/` files named in the
  spec's "Docs to update when it lands" header, then delete the spec or the part
  that landed. See [specs/README.md](specs/README.md).
- **New design work:** write or edit a spec with the required header (status,
  implements in, docs to update). Do not touch `docs/` for ideas that aren't
  built.
- Before finishing a docs change, check that relative links resolve and that
  column lists match `FILTERED_FIELDNAMES`, `output_fieldnames()` and the
  `NEW_FIELDNAMES` constants.
