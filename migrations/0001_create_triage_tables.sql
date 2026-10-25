-- Stage 2b tables. Described in docs/stages/stage2_filter_candidates.md.
-- No BEGIN/COMMIT and no PRAGMA user_version here: triage_store.migrate wraps
-- the file in one transaction together with the version bump.

-- One row per prompt version, so the several-KB prompt is stored once.
CREATE TABLE llm_triage_prompt (
    prompt_hash TEXT PRIMARY KEY,
    system_prompt TEXT NOT NULL,
    response_schema TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- The saved model replies: a hit means no API call. Never drop or rewrite this
-- table in a later migration, because the replies cost money to recreate.
-- The token columns use the SDK's usage_metadata names and are NULL when absent.
CREATE TABLE llm_triage_response (
    input_hash TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL REFERENCES llm_triage_prompt(prompt_hash),
    temperature REAL NOT NULL,
    thinking_level TEXT NOT NULL,
    triage_input_json TEXT NOT NULL,
    raw_response TEXT,
    finish_reason TEXT,
    prompt_token_count INTEGER,
    candidates_token_count INTEGER,
    thoughts_token_count INTEGER,
    cached_content_token_count INTEGER,
    tool_use_prompt_token_count INTEGER,
    total_token_count INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (input_hash, attempt)
);

-- Derived from the replies and rewritten every run, so it can be dropped and
-- rebuilt freely. input_hash and attempt are NULL for rows never sent to the model.
CREATE TABLE llm_triage_result (
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
    PRIMARY KEY (unitid, result_url)
);
