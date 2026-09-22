# Stage 2 — `classify_candidates.py`

**Output:** `data/filtered_candidates.csv`

Deduplicates and filters Stage 1's candidates. Computes club-keyword and ttrpg-keyword AND-matches (`club_keywords.txt` / `ttrpg_keywords.txt`) against both the snippet and any extracted page text, and discards results from excluded domains. Conservative by design — only discards on a clear negative signal; does **not** render a verdict on whether a result is really a club page. That's decided downstream in Stage 3 by the LLM.

## Pitfalls to know before touching filtering/classification logic

1. **Names don't match pages.** "University of Connecticut" clubs may only ever say "UConn." No reliable abbreviation list exists — avoid exact-phrase matching on college name as a filter condition here.
2. **Wrong-school attribution.** A query for UConn once surfaced a CCSU event instead — a good relevance score doesn't guarantee the result is about the *target* school. **Not fixed at this stage.** School-identity verification is deferred to Stage 3 (`school_identifying_terms_found`, `name_variant_matched`) — don't try to solve it here with a name-matching gate, since that risks discarding legitimate "UConn"-only pages (pitfall #1).
3. **Vendor-hosted club pages.** Platforms like CampusGroups, Modern Campus Involve, Anthology Engage, Corq, or Lounge often carry identifiable markers (e.g. "Powered by CampusGroups" in the header) — worth special-casing as an additional keep-signal. **Not yet implemented — TODO in this file.**
4. **Amalgam/directory pages.** Some schools list every student org on one page. These should generally be kept, not discarded — they'll contain club/ttrpg keyword hits like any other match. Splitting out the relevant club's contact info from the rest of the directory happens downstream in Stage 3, not here.

## Open gaps

- Dedup logic — `pipeline_data_flow.md` states this stage dedupes Stage 1's results, but the current implementation isn't documented here yet. Needs a pass once confirmed.
- Vendor-platform special-casing and amalgam-page detection (pitfalls #3, #4): not implemented.
- No fix yet for wrong-school attribution (pitfall #2) anywhere in the pipeline; alternative search APIs under investigation for Stage 1, LLM-based check planned for Stage 3.