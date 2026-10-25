# Stage 2 — `filter_candidates.py` (rule-based filtering, then LLM triage)

**Input:** `data/search_results.csv` (Stage 1)

**Output:** `data/filtered_candidates.csv` (2a), then
`data/llm_filtered_candidates.csv` (2b). Stage 3 still reads the 2a file.

`filter_candidates.py` is a thin entry point. Its `main()` runs two steps in
order:

- **2a, rule-based:** `rule_based_filtering.run_rule_based_filter(input_csv,
  output_csv)` holds all the logic. It loads the keyword lists, reads the Stage 1
  CSV (raising `ValueError` if a Stage 1 column is missing), applies the rules to
  each row, writes every row to the output, and prints a count of rows discarded
  per reason.
- **2b, LLM triage:** `llm_triage.run_llm_triage(output_csv, llm_output_csv)`
  reads the 2a file. See [LLM triage (2b)](#llm-triage-2b).

`--llm-output` sets the 2b path. The full design is in
[`specs/stage2b_llm_triage/`](../../specs/stage2b_llm_triage/spec.md).

## Rules (2a)

A row is discarded for the first of these that matches, checked in this order:

1. **Sentinel row** (`search_row_format_util.is_sentinel`), reason `sentinel_row`.
2. **URL rule**, matched against the lowercased full URL:
   - `pdf`: the URL path ends in `.pdf`.
   - `news`: URL contains `blog`, `news`, `article`, `dailydigest`, `stories`,
     `story` or `forum`.
   - `event`: URL contains `rsvp`, `event` or `calendar`.
   - `storefront`: URL contains `store`, `shop` or `market`.
3. **Keyword gate**, reason `snippets_has_no_club_or_ttrpg_keywords`:
   `result_title` + `result_snippet`
   contains no club keyword and no TTRPG keyword. Keywords come from
   `config/club_keywords.txt` and `config/ttrpg_keywords.txt`, matched as
   case-insensitive substrings (not regexes). The page text
   (`result_raw_content`) is never read.

Every other row is `keep`.

URL terms are substring matches over the whole URL, host included, so they can
match inside a longer word (for example `store` in `restore`). This is accepted
for now.

## Output

Every input row is written, kept or discarded, so the file is an audit trail.
Stage 3 renders only `keep` rows. Column list:
[`data_flow.md`](../data_flow.md).

`decision` is `keep` or `discard_` plus a reason. The reasons are
`schema.DISCARD_REASONS`: `pdf`, `news`, `event`, `storefronts`,
`snippets_has_no_club_or_ttrpg_keywords` and `sentinel_row`. The reason names
are used for the decision, the printed counts and the code, so add a new one in
`schema.py` only.

Downstream stages test `schema.is_keep(row)` (exactly `keep`), so any other
value is treated as a discard.

Stage 2 drops Stage 1's `result_score` on purpose: the search engine's relevance
score wasn't a reliable signal, so it isn't in `SEARCH_FIELDNAMES` and no later
stage sees it.

## Design choices

- Filtering is conservative: it discards only on a clear negative signal and
  does **not** judge whether a result really is a club page.
- Directory pages (an A-Z list of a school's clubs) are deliberately kept. They
  pass the keyword gate like any other result. Splitting a directory into
  individual clubs is not implemented in any stage.
- Vendor-hosted club pages (CampusGroups, Modern Campus Involve, Anthology
  Engage, Lounge, Corq) are not special-cased. See the TODO in
  `rule_based_filtering.py`.

## Pitfalls to know before touching filtering logic

1. **Names don't match pages.** "University of Connecticut" clubs may only ever
   say "UConn." No reliable abbreviation list exists, so avoid exact-phrase
   matching on college name as a filter condition here.
2. **Wrong-school attribution.** A query for UConn once surfaced a CCSU event
   instead. A good relevance score doesn't guarantee the result is about the
   _target_ school. Nothing in the current pipeline checks this.
3. **Amalgam/directory pages.** These should generally be kept, not discarded.

## Code specifics

- `rule_based_filtering.py` reads no files and needs no network or API key at
  import time.
- The entry point is `rule_based_filtering.apply_rules(row, keyword_lists)`,
  which returns `decision` and the two keyword columns. `discard_reason` and
  `url_filtering_reason` return the reason name only.
- Tests: `tests/test_rule_based_filtering.py`,
  `tests/test_filter_candidates.py`.

## LLM triage (2b)

`llm_triage.py` holds all the pre and post processing and is deterministic. The
model call is `gemini_client_util.label_result`, passed to
`run_llm_triage`/`triage_row` as an argument, so tests and a future swap never
touch the logic. It calls `TRIAGE_MODEL` (`gemini-3.5-flash-lite`) at
`TRIAGE_TEMPERATURE` and `TRIAGE_THINKING_LEVEL`, with `config/triage_prompt.md`
and `config/llm_triage_examples.jsonl` as the system prompt and the row as the
message. The reply schema is built from `schema.py`. The client reads
`GEMINI_API_KEY` from `.env` on first use, and retries 429 and 5xx up to
`TRIAGE_API_ATTEMPTS` with backoff. A reply that isn't a JSON object comes back
as `{}`, so it is retried as invalid output. `label_result` is `build_request`
(a plain dict of everything the model sees) then `send_request`, the only code
that calls Gemini. Columns and decision values: [`data_flow.md`](../data_flow.md).

1. **Preprocessing.** Only rows where `schema.is_keep(row)` is true and that
   aren't sentinels are sent. `build_triage_input` sends the official name,
   official `aliases` (not `generated_aliases`), title, URL and
   `domain_relation`. Snippet and page text are not sent. `domain_relation` is
   `on_domain` when `is_on_domain` finds the result host equal to, or a
   subdomain of, the last two labels of `website`'s host (scheme, `www.`, port,
   case, trailing dots, path and query ignored). IP addresses and invalid input
   give `not_on_domain`.
2. **Response checks.** `validate_response` needs every field of
   `schema.TRIAGE_LABEL_FIELDNAMES` as a string, with enum values in
   `schema.TRIAGE_ENUM_VALUES`. `check_evidence` blanks a quote that isn't a
   case-insensitive substring of the title or URL as sent after normalizing
   curly quotes to straight quotes and encoded, full-width, and small
   ampersands to `&`, and sets its certainty to `probable`. `not_supported`
   with no passing evidence becomes `unknown`.
3. **Post processing.** `drop_reason` gives `wrong_institution` (`institution`
   is `not_supported`), `wrong_page_type` (`page_type` is `other`) or
   `wrong_institution_and_wrong_page_type`, written as `decision=discard_<reason>`.
   Anything else keeps the row, `unknown` included.
4. **Failure handling.** Fails open. An exception from the client gives
   `triage_status=api_error`. A response still invalid after
   `TRIAGE_MAX_ATTEMPTS` gives `invalid_output`. Either keeps the row with blank
   labels.

Rows 2a discarded are copied through, and the new columns are blank.

## Open gaps

- Deduplicate URLs across institutions to catch duplicate clubs from colleges
  that have multiple campuses. Not implemented.
- `TRIAGE_MODEL`, `TRIAGE_THINKING_LEVEL`, the prompt (`v0`) and the five
  few-shot examples are a first guess and haven't been evaluated. No eval exists.
- Stage 3 doesn't read the 2b file yet.
- Each call prints an "automatic function calling" warning from `google-genai`.
- `is_on_domain` takes the last two labels as the registrable domain, which is
  right for `.edu` only. Schools in one system (CUNY, KCTCS, PSU) share a domain,
  so their pages count as `on_domain` for each other (accepted).
