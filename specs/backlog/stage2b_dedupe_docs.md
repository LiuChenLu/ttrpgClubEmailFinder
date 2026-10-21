# Plan: dedupe docs in `specs/stage2b_llm_triage/`

**Goal:** every fact has one home; other mentions are section links, so a
definition changes in one place.

**Ownership**

| File | Owns |
| --- | --- |
| `schema.json` | Output field names, order, allowed values. No meanings. |
| `label_rules.md` | Label meanings and how to choose them: rules, examples as sub-bullets, certainty, evidence. The prompt is built from it. |
| `spec.md` | How the step runs: inputs, code checks, drop rule, failure handling, CSV columns, prompt build, index of where facts live. |
| `examples.jsonl` | Worked examples. Overlap with rules is expected. |
| `evals/` | Generated, not trusted. One status line only. Do not read or edit `eval.csv`. |

## Phase 1: `label_rules.md` (done when the checklist below holds)

- Merge the two case tables into the rules as sub-bullet examples; delete
  `## Example Classifications`.
- Add `## Evidence`. Reword `not_supported` (different school, or an
  organization unconnected to any school; never on missing evidence).
- Event page: `tabletop_club` if from a clearly tabletop club, else `other`.
- `clear`/`probable` meanings stay here; "Gaming Club" is `probable`, and the
  certainty section links to that bullet instead of a second example.
- Shorten Scope and Input to links; one line on reading `domain_relation`.
- Remove the duplicate "source of truth" sentence in the header.

## Phase 2: `spec.md`

- File table becomes a "where each fact lives" index (incl. `evals/`).
- Add `## Design priority: recall` (false drop loses a club, false keep costs
  one render). Failure handling and Post processing link to it; drop the link
  to the missing "Downstream use" section.
- Post processing: remove certainty and `not_supported` wording; link to
  `label_rules.md`.
- CSV table: one row for "every `schema.json` field"; keep `decision`,
  `triage_status`, model and prompt version rows.
- Preprocessing: skip rows where `is_keep(row)` is false (replaces the stale
  `discard, REASON`).
- Prompt and config: keep build steps only; remove repeated model/version and
  dev-only-examples sentences.
- Open gaps: registered domain of `lccc.wy.edu` may come out as `wy.edu`
  (unchecked).

## Phase 3: `evals/dataset.md`

- Add one status line at the top: generated, does not match `label_rules.md`,
  not ground truth, not a source for label meanings. Nothing else.

## Phase 4: check

- Grep for leftover repeated phrases and broken anchors.
- `python -m pytest -q`.

## Decisions already made

- Event page from a clearly tabletop club: `tabletop_club`; from an unrelated
  group (e.g. a postdoc association): `other`.
- "Gaming Club" with no qualifier: `tabletop_club`, `probable`.
- Campus and system rule goes in the intro paragraph before the ordered rules.
- Dropped the "clubs are deduplicated later" note: URL dedup across
  institutions is still an open gap in `docs/stages/stage2_filter_candidates.md`.
