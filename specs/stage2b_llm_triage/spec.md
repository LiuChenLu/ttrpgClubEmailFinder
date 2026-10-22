# Spec: LLM triage in Stage 2b (`llm_triage.py`)

**Status:** in-progress. **Landed:** the harness, with the LLM call stubbed in
`gemini_client_util.py`, and `is_on_domain` (see
[stage 2](../../docs/stages/stage2_filter_candidates.md#llm-triage-2b)). **Not
landed:** the real call, `config/triage_prompt.md`,
`config/llm_triage_examples.jsonl`, retry with backoff, and Stage 3 reading the 2b
file. Where this file disagrees with the code, the code is what is true today.
**Implements in:** new
`llm_triage.py`; `filter_candidates.py` (call it after `rule_based_filtering`);
`config.py` (`TRIAGE_*` constants); new `config/triage_prompt.md` and
`config/llm_triage_examples.jsonl`; tests. **Docs to update when it lands:**
`docs/stages/stage2_filter_candidates.md` (add the 2b step), `docs/data_flow.md`
(Stage 2 columns, see "Planned CSV columns" below), `docs/architecture.md`
(pipeline table, "not implemented" list), and
`docs/stages/stage3_render_candidates.md` (decision handling).

This step would run in `filter_candidates.py` after the rule-based filters. It
labels each surviving search result using its URL and title and discards results
unlikely to be a TTRPG club page for the target school.

## Where each fact lives

Each fact has one home. Other files link to it instead of restating it.

| Fact                                                                   | Home                                               |
| ---------------------------------------------------------------------- | -------------------------------------------------- |
| Label meanings, ordered rules, examples, certainty levels, evidence    | [label_rules.md](label_rules.md)                   |
| Output field names, order and enum values                              | [schema.json](schema.json)                         |
| Worked examples                                                        | [llm_triage_examples.jsonl](../../config/llm_triage_examples.jsonl)                   |
| Fields sent to the model, how `domain_relation` is computed            | [Preprocessing](#preprocessing)                    |
| Code checks on the model's response                                    | [Model Response](#model-response)                  |
| Why the step leans toward keeping                                      | [Design priority: recall](#design-priority-recall) |
| Which labels cause a drop                                              | [Post processing](#post-processing)                |
| API errors and retries                                                 | [Failure handling](#failure-handling)              |
| CSV columns                                                            | [Planned CSV columns](#planned-csv-columns)        |
| Prompt construction, model, prompt version                             | [Prompt and config](#prompt-and-config)            |
| Eval dataset (generated, not trusted; no metrics or baselines written) | [evals/dataset.md](evals/dataset.md)               |

## Planned CSV columns

Stage 2b would write `data/llm_filtered_candidates.csv` (the name is not final).
It keeps every Stage 2a row, including the ones 2a discarded, and adds the
columns below to the existing Stage 2a columns. For discarded rows the label
columns are blank.

| Column                    | Type   | Notes                                                                                               |
| ------------------------- | ------ | --------------------------------------------------------------------------------------------------- |
| `decision`                | string | `keep`, or `discard_<reason>`.                                                                      |
| every `schema.json` field | varies | One column per field, same name and values as in [schema.json](schema.json)                         |
| `triage_status`           | string | Blank on success; an error value when the call failed and the row was kept (see "Failure handling") |
| model and prompt version  | string | Each row records which model and prompt version labeled it (column names not yet chosen)            |

## Why LLM is needed

There is no way to determine whether a club page belongs to a specific school
based on URL or title, but it is usually easy for a human to tell:

1. Club pages do not always use .edu domains. For example, Skidmore College
   hosts its club page at
   [skidmore.campuslab.com](https://skidmore.campuslabs.com/engage/organization/tabletop-gaming-club).
2. The institution's name may not appear on the club page and IPEDS may not have
   an alias. For example, University of Connecticut's IPEDS entry does not have
   any aliases listed and
   [UConn's club page](https://uconntact.uconn.edu/organization/tabletop_gaming_club)
   contains only variations of "UConn" in its text. There is no reliable way to
   determine an institution's nickname or abbreviation.
3. Club pages may contain no vocabulary identifying the institution. The UConn
   page does not contain terms such as "college," "university," "institute,"
   "undergraduate," "student," or "campus." The page assumes that readers
   already know it belongs to the university.

There is no way to programtically determine if a club is a TTRPG club based on
URL or title, but it is usually easy for a human to tell:

1. The club may roleplay as a fictional organization instead of using any "club"
   related vocabulary in its name. For example,
   [MIT Assassins' Guild](https://assassin.mit.edu/) is a TTRPG club.
2. Non-table top gaming clubs often show up in the search results, but it is
   hard to tell if they are relevant based on their name alone.

## Preprocessing

The following preprocessing steps are done in this stage in code before the LLM
is called.

1. Before rows are sent to an LLM, the sentinel row and every row where
   `is_keep(row)` (see `schema.py`) is false are skipped.
2. For every other row, we send the following fields to the LLM:
   - `domain_relation` is `on_domain` when the result host equals the registered
     domain of `website` (IPEDS `WEBADDR`) or is a subdomain of it, otherwise
     `not_on_domain`. How to read it is in
     [label_rules.md](label_rules.md#input).
   - We also send the official name of the school, the title of the result page,
     and the URL of the result page.
   - `aliases` are the official aliases only. `generated_aliases` are not sent.
   - Snippet and page text are not sent.

## Model Response

The model returns the fields in [schema.json](schema.json) as structured output,
with the evidence fields first so it quotes the text before committing to a
label. What evidence is: [label_rules.md](label_rules.md#evidence). Two checks
run in code on every response:

1. Each non-empty `title_evidence_*` must be a substring of the title as sent,
   and each `url_evidence_*` a substring of the URL. A failure blanks that
   evidence and sets the matching certainty to `probable`.
2. `not_supported` needs at least one evidence field that passed check 1.
   Otherwise `institution` becomes `unknown`. This enforces the "positive
   evidence" rule in [label_rules.md](label_rules.md#institution).

## Design priority: recall

A false drop loses a club page permanently. A false keep costs one render. So
the step leans toward keeping:

- Labeling guidance that serves this: [certainty](label_rules.md#certainty) and
  the `not_supported` rule in [institution](label_rules.md#institution).
- Only some labels drop a row ([Post processing](#post-processing)).
- Errors keep the row ([Failure handling](#failure-handling)).

## Post processing

Post processing computes `should_drop(bool)`. `should_drop` is true when
`institution` is `not_supported` or `page_type` is `other`, otherwise it is
`false`.

If `should_drop` is `true`, we output `decision=discard_REASON` in the csv. The
`REASONS` are either:

- `wrong_institution`: `institution` is `not_supported`
- `wrong_page_type`: `page_type` is `other`
- `wrong_institution_and_wrong_page_type`: `institution` is `not_supported` and
  `page_type` is `other`

If`should_drop` is `false`, and we output `decision=keep` in the csv.

These are both tunable in code on the `*_certainty` and `*_evidence_for_*`
fields (see [schema.json](schema.json)).

## Failure handling

The step fails open. An API error, timeout, refusal, or output still invalid
after one retry keeps the row, leaves the labels blank and sets `triage_status`
to an error value. Retry 429 and 5xx responses with backoff. The reason is in
[Design priority: recall](#design-priority-recall).

## Prompt and config

- `config/triage_prompt.md` is derived from [label_rules.md](label_rules.md),
  not pasted from it. Notes written for authors are left out.
- Order: rubric and examples first, identical for every row so they can be
  cached, then the row input.
- Few-shot examples are in
  [llm_triage_examples.jsonl](../../config/llm_triage_examples.jsonl), which
  holds dev examples only, never the held-out eval set. A unit test runs every example through the
  evidence check.
- `TRIAGE_MODEL`, `TRIAGE_PROMPT_VERSION` and temperature 0 are set in
  `config.py`.

## Open gaps

- `TRIAGE_MODEL` and the sampling settings are placeholders until the eval picks
  a model.
- Whether sending the snippet would improve accuracy has not been measured.
- No eval dataset, metrics or baselines exist yet. `evals/` holds generated
  files that are not trusted.
