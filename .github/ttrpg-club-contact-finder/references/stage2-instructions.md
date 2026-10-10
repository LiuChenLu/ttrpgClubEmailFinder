# Stage 2 — `filter_candidates.py`

**Input:** `data/rendered_results.csv` (Stage 1b)

**Output:** `data/filtered_candidates.csv`

Conservatively filters Stage 1b's candidates by:

1. Discarding results rows that don't contain any club-keyword OR ttrpg-keyword matches in the result title + snippet, as defined in `club_keywords.txt` / `ttrpg_keywords.txt`
2. Discarding results rows that don't contain any club-keyword AND ttrpg-keyword matches in the full result, as defined in `club_keywords.txt` / `ttrpg_keywords.txt`
3. Discarding PDF results where the url ends in `.pdf`.

`result_raw_content` is markdown (Tavily) or plain text (Playwright), per `content_source`. The keyword matching applies to both, and `content_source` is carried through to the output for Stage 3.

Filtering is conservative by design — only discards on a clear negative signal; does **not** render a verdict on whether a result is really a club page. That's decided downstream in Stage 3.

Note that we do not filter for institution keywords. As a result, a tabletop RPG club page for a local library, high school, gaming café, board game store, etc. may be found by a search for "UConn" and passed through to Stage 3. This is intentional because there is no reliable way to identify an institution's club page:

1. Club pages do not always use .edu domains. For example, Skidmore College hosts its club page at [skidmore.campuslab.com](https://skidmore.campuslabs.com/engage/organization/tabletop-gaming-club).
2. The institution's name may not appear on the club page. For example, [UConn's club page](https://uconntact.uconn.edu/organization/tabletop_gaming_club) contains only variations of "UConn" in its text. There is no reliable way to determine an institution's nickname or abbreviation.
3. Club pages may contain no vocabulary identifying the institution. The UConn page does not contain terms such as "college," "university," "institute," "undergraduate," "student," or "campus." The page assumes that readers already know it belongs to the university.

## Pitfalls to know before touching filtering logic

1. **Names don't match pages.** "University of Connecticut" clubs may only ever say "UConn." No reliable abbreviation list exists — avoid exact-phrase matching on college name as a filter condition here.
2. **Wrong-school attribution.** A query for UConn once surfaced a CCSU event instead — a good relevance score doesn't guarantee the result is about the *target* school. **Not fixed at this stage.** School-identity verification is deferred to Stage 3 — don't try to solve it here with a name-matching gate, since that risks discarding legitimate "UConn"-only pages (pitfall #1).
3. **Vendor-hosted club pages.** Platforms like CampusGroups, Modern Campus Involve, Anthology Engage, Corq, or Lounge often carry identifiable markers (e.g. "Powered by CampusGroups" in the header) — worth special-casing as an additional keep-signal. **Not yet implemented — TODO in this file.**
4. **Amalgam/directory pages.** Some schools list every student org on one page. These should generally be kept, not discarded — they'll contain club/ttrpg keyword hits like any other match. Splitting out the relevant club's contact info from the rest of the directory happens downstream in Stage 3, not here.

## Open gaps

- Vendor-platform special-casing and amalgam-page detection (pitfalls #3, #4): not implemented.
- No fix yet for wrong-school attribution (pitfall #2) anywhere in the pipeline; alternative search APIs under investigation for Stage 1a, LLM-based check planned for Stage 3.

# New TODOs
- We want to plumb `content_source` through to Stage 3, but it's not in the CSV yet.
- We want to deduplicate urls across institutions to catch duplicate clubs from colleges that have multiple campuses. 