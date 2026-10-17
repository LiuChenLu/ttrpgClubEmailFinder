# Stage 2 — `filter_candidates.py` (rule-based filtering)

**Input:** `data/search_results.csv` (Stage 1)

**Output:** `data/filtered_candidates.csv`

Stage 2 is rule-based only. There is no LLM step. A planned LLM triage step is
specified in
[`specs/stage2b_llm_triage/`](../../specs/stage2b_llm_triage/spec.md) and is
**not implemented**.

`filter_candidates.py` is a thin entry point. Its `main()` calls
`rule_based_filtering.run_rule_based_filter(input_csv, output_csv)`, which holds
all the logic. That function loads the keyword lists, reads the Stage 1 CSV
(raising `ValueError` if a Stage 1 column is missing), applies the rules to each
row, writes every row to the output, and prints a count of rows discarded per
reason.

## Rules

A row is discarded for the first of these that matches, checked in this order:

1. **Sentinel row** (`result_url` is blank or `ERROR`), reason `sentinel`.
2. **URL rule**, matched against the lowercased full URL:
   - `pdf`: the URL path ends in `.pdf`.
   - `news`: URL contains `blog`, `news`, `article`, `dailydigest`, `stories`,
     `story` or `forum`.
   - `event`: URL contains `rsvp`, `event` or `calendar`.
   - `storefront`: URL contains `store`, `shop` or `market`.
3. **Keyword gate**, reason `no_keywords`: `result_title` + `result_snippet`
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

`decision` is `keep` or `discard_<label>`:

| Reason                        | `decision` value                                 |
| ----------------------------- | ------------------------------------------------ |
| PDF                           | `discard_pdf`                                    |
| News/blog-like URL            | `discard_news`                                   |
| Event-like URL                | `discard_event`                                  |
| Storefront-like URL           | `discard_storefronts`                            |
| No keyword in title + snippet | `discard_snippets_has_no_club_or_ttrpg_keywords` |
| Sentinel row                  | `discard_sentinel_row`                           |

Downstream stages test `decision == "keep"` exactly, so any `discard_*` value is
treated as a discard.

Stage 2 does not carry `result_score` forward, because it isn't in
`SEARCH_FIELDNAMES`; see [Known bugs](../known_bugs.md).

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
- It keeps its own local `is_sentinel` (blank or `ERROR` URL); it does not
  import the one in `search_row_format_util.py`.
- Tests: `tests/test_rule_based_filtering.py`,
  `tests/test_filter_candidates.py`.

## Open gaps

- Deduplicate URLs across institutions to catch duplicate clubs from colleges
  that have multiple campuses. Not implemented.
- LLM-based triage (wrong-school and non-club detection): see the spec above.
