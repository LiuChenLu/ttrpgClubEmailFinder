**Status:** draft
**Implements in:** `config.py`, `gemini_client_util.py`, new `triage_store.py`,
`llm_triage.py`, `schema.py`, `tests/`
**Docs to update when it lands:** `docs/stages/stage2_filter_candidates.md`,
`docs/data_flow.md` (2b), `docs/architecture.md`
Goal: keep every Gemini reply in SQLite so tuning costs no API calls; call only
on a miss. 2b writes `data/database.sqlite`, not a CSV; Stage 3 reads 2a's CSV.

## Decisions

- `sqlite3` only. `build_request(triage_input)` in `gemini_client_util.py`
  returns a plain dict of all the model sees; `send_request` is the only code
  that calls Gemini. Key = sha256 of that dict as JSON (`sort_keys`).
- `triage_store.py` owns hashing and SQL. `label_with_retry` passes the attempt
  number, so retries replay from the database.
- Store the raw reply only; parsing, checks and drop rule rerun on read. API
  errors are never stored; invalid replies are, one row per attempt.
- Token columns use the SDK's `usage_metadata` names, NULL when absent.

## Tables

The SQL is `migrations/0001_create_triage_tables.sql`: `llm_triage_prompt` (one
row per prompt version), `llm_triage_response` (the cache, keyed on
`(input_hash, attempt)`) and `llm_triage_result` (derived, rewritten every run).

## Phases

1. Request split; update `test_gemini_client_util.py`. **Done.**
2. Database: `config.DATABASE_PATH`; `triage_store.py` applies the numbered
   `migrations/*.sql` with `PRAGMA user_version` (never drop `llm_triage_response`).
   **Done.**
3. `label_with_retry` reads the store first; `--cache-only`. **Done.** Docs for
   it are in `stage2_filter_candidates.md` ("Saved model replies").
4. Write `llm_triage_result` (`schema.TRIAGE_RESULT_FIELDNAMES`). **Done.**
   `data_flow.md` is CSV-only, so the table is documented in the stage 2 doc.
4b. Runs: `migrations/0002_add_triage_runs.sql` adds `llm_triage_run`, and
   `llm_triage_result` is keyed on `run_id` and only inserted. `--note`, git
   commit and dirty flag per run, and `compare_triage_runs.py`. **Done.**
5. Tests (fake client, in-memory db: 2nd run makes zero calls) and docs.

## Decided
- `(unitid, result_url)` is unique. An institution can have several `unitid`s, and
  the same model input must share one saved reply, so `unitid` is not in the key.
- `triage_model` is kept in `llm_triage_result` as well as in the response table.
- The 2b CSV is removed later, not in this change.
- Results are never replaced: every run adds rows under a new `run_id`, so models,
  prompts and label rules can be compared. `run_id` is not in the cache key.
