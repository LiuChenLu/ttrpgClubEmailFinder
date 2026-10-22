**Status:** in-progress
**Implements in:** `pyproject.toml`, `config.py`, `gemini_client_util.py`,
`llm_triage.py`, `schema.py`, new `config/triage_prompt.md`, new
`config/llm_triage_examples.jsonl`, `tests/test_llm_triage.py`
**Docs to update when it lands:** `docs/stages/stage2_filter_candidates.md`
(2b, Stubs, Open gaps), `docs/architecture.md` (pipeline note, "Where things
live"), `README.md` (google-genai install line)

Part of [stage2b_llm_triage/spec.md](../stage2b_llm_triage/spec.md): the first
real LLM call, with no eval. Goal: run Gemini on 1-3 real rows and see Stage 2b
work end to end.

## Decisions (from the user)

- Model: `gemini-3.5-flash-lite`.
- Response field list lives in `schema.py` (not copied from `schema.json`).
- Stage 3 keeps reading the 2a file.
- Few-shot file: `config/llm_triage_examples.jsonl`, moved (not copied) from
  `specs/stage2b_llm_triage/examples.jsonl`. Fix example 5: title evidence is
  `Tufts`, not `Tufts University`.

## Phases

1. **Dependencies and settings.** `google-genai` becomes a main dependency.
   `config.py` gets thinking level, API retry settings and the prompt and
   examples paths.
2. **Prompt files.** `config/triage_prompt.md` derived from `label_rules.md`
   (no author notes, no `unknown` certainty, since the schema forbids it). Move
   the examples file and fix links to it (spec.md, label_rules.md, tests).
3. **The call.** `gemini_client_util.label_result`: lazy client, retry 429/5xx
   with backoff, rubric and examples first and the row last, structured output
   built from `schema.py`, temperature `TRIAGE_TEMPERATURE`. Then set
   `TRIAGE_MODEL` and `TRIAGE_PROMPT_VERSION` (`v0`).
4. **Remove the stub.** Delete `STUB_VALUE` and its two exemptions in
   `llm_triage.py`. Replace the stub-dependent tests with a fake client. Add a
   test that every example passes the evidence check. Update the docs above.
5. **Sample run.** A 3-row CSV in `/tmp`, run with `--input`/`--output`. Never
   the full file.

## Where tuning should pay off (not optimised yet)

1. Prompt rules, especially the vague certainty definitions.
2. Few-shot coverage: no `unknown`, no plain "Gaming Club", no `probable`
   institution, no non-school `not_supported`.
3. Thinking level and model choice.
4. `drop_reason`: for example, drop only when certainty is `clear`.
5. Sending the snippet as well as title and URL.

## Notes

- `TRIAGE_MODEL` and `TRIAGE_PROMPT_VERSION` stay `stub` until phase 3, so no
  row claims a model that didn't label it, and the stub tests keep passing.
