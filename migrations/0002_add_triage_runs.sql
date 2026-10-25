-- One row per Stage 2b run, so runs with different models, prompts or label
-- rules can be compared. Spec: specs/backlog/llm_triage_cache.md.
-- Saved model replies (llm_triage_response) stay shared by every run: a run's
-- results point at them, so a later run with the same model input costs no call.

CREATE TABLE llm_triage_run (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL REFERENCES llm_triage_prompt(prompt_hash),
    prompt_version TEXT NOT NULL,
    temperature REAL NOT NULL,
    thinking_level TEXT NOT NULL,
    input_csv TEXT NOT NULL,
    cache_only INTEGER NOT NULL,
    git_commit TEXT,
    git_dirty INTEGER,
    note TEXT
);

-- llm_triage_result now holds every run's rows instead of one row per Stage 2a
-- row, so its key changes and it is dropped and recreated. That loses nothing
-- that can't be rebuilt: it is derived from llm_triage_response, and
-- `python llm_triage.py --cache-only` writes it again at no cost.
DROP TABLE llm_triage_result;
CREATE TABLE llm_triage_result (
    run_id INTEGER NOT NULL REFERENCES llm_triage_run(run_id),
    unitid TEXT NOT NULL,
    result_url TEXT NOT NULL,
    stage2a_decision TEXT NOT NULL,
    decision TEXT NOT NULL,
    input_hash TEXT,
    attempt INTEGER,
    title_evidence_for_page_type TEXT,
    url_evidence_for_page_type TEXT,
    page_type TEXT,
    page_type_certainty TEXT,
    title_evidence_for_institution TEXT,
    url_evidence_for_institution TEXT,
    institution TEXT,
    institution_certainty TEXT,
    triage_status TEXT,
    triage_model TEXT,
    triage_prompt_version TEXT,
    PRIMARY KEY (run_id, unitid, result_url)
);
