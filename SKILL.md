---
name: ttrpg-club-finder
description: Domain knowledge and pitfalls for the TTRPG-club contact-finding project — a pipeline that searches for university tabletop-RPG/gaming club pages via Tavily and extracts contact info (email/Discord) into a CSV. ALWAYS read this before touching search queries, matching/classification logic, contact extraction, or CSV assembly in this project (config.py, classify_club_pages.py, extract_contact_info.py, funnel_stats.py, or any successor stage) — even if the request doesn't say "ttrpg" explicitly. Also relevant for any college-club-finding or college-contact-scraping task built on Tavily at scale.
---

# TTRPG Club Finder — Project Knowledge

## Goal

Build a CSV of TTRPG/gaming club contacts across US colleges (~6,000). One row per club: **college name, contact info, source webpage, reason we believe it's correct.** The pipeline only gathers signals — "is this really a club page" is decided downstream (human/LLM), not by any current gate.

## Pitfalls to know before writing matching/search logic

1. **Names don't match pages.** "University of Connecticut" clubs may only ever say "UConn." No reliable abbreviation list exists — avoid exact-phrase matching on college name.
2. **Wrong-school attribution.** A query for UConn once surfaced a CCSU event instead — good relevance scores don't guarantee the result is about the _target_ school. Needs an explicit school-identity check, not just a score threshold.
3. **`WEBADDR` (IPEDS official site) is not a usable domain filter** — club pages routinely live off that domain (see #4).
4. **Vendor-hosted club pages.** Many clubs live on platforms like CampusGroups, Modern Campus Involve, Anthology Engage, Corq, or Lounge, not the university's own domain. Likely have identifiable markers (e.g. "Powered by CampusGroups" in header) — worth special-casing (not yet implemented; TODO in `classify_club_pages.py`).
5. **Amalgam/directory pages.** Some schools list every student org on one page. We should ideally pull only the contact information from the relevant club.
6. **Multi-campus systems** (SUNY, UC, Penn State) — match the specific campus, not the system name.
7. **Contact signals rank differently.** Email > Discord invite > bare "contact us" wording with no address/link. The last case usually means a contact form or login wall — route to manual/LLM review, don't discard.

## Pipeline (current)

- **Stage 0** `gen_institutions.py`, output `data/institutions.csv`— Pull only the relevant columns from the IPED database, and write them to a CSV.
- **Stage 1** `classify_club_pages.py`, output `data/ttrpg_clubs_search_results.csv` — Tavily search + extract, one row per search result. Records snippet and/or full text (AND) keyword signals only — not a verdict.
- **Stage 2** `extract_contact_info.py`, output `data/ttrpg_clubs_contacts.csv` — offline text processing, no network. Re-derives the text gate, extracts emails/Discord/bare-word contact signal.
- **Stage 3** — _not built yet._ Collapses Stage 2's rows to one-per-club in the final `college_name, contact_info, source_url, contact_reason` shape. Use closed reason codes, not free text:

| reason code                 | meaning                                                 |
| --------------------------- | ------------------------------------------------------- |
| `email_in_page_text`        | email found in extracted page text                      |
| `email_in_snippet`          | email found only in search snippet                      |
| `discord_in_page_text`      | Discord invite found in page text                       |
| `contact_form_needs_review` | contact wording present, no address — needs manual look |
| `no_signal`                 | passed text gate, no contact signal found               |

# Testing

Use `random_sample_institutions.py` to generate a small test set of institutions at `institutions_sample.csv` which can be used by `classify_club_pages.py`. It uses the full IPEDS csv and selects a small random sample.

There is also `ipeds_institution_has_ttrpg_club.csv` which can be used by `classify_club_pages.py`. It is a very small subset of the IPEDS database that has at least one TTRPG club.
m

## Scale & budget

~6,000 colleges × 3 query templates × up to 3 extracts ≈ 18K searches + 18K extracts. Before a full run:

- Reconsider always using Tavily's `SEARCH_DEPTH="advanced"` (2 credits) vs. a cheap `"basic"` first pass.
- Neither script checkpoints/resumes — add resumable writes so a mid-run failure doesn't require restarting from scratch.
- `SLEEP_BETWEEN_COLLEGES_S` may need to grow at ~20x current volume; check Tavily's rate limits.
- `result_raw_content` is currently written in full to the Stage 1 CSV (fine for test runs) — drop/truncate before a 6,000-row run.

## Tavily notes

`search()` runs per query template per college; a separate `extract()` fetches full text only for top-scoring candidates, avoiding extraction cost on every hit. `search_depth="advanced"` (2 credits) beats `"basic"`/`"fast"` (1 credit) on relevance — currently used everywhere, worth revisiting at scale. `include_domains=["*.edu"], mode="boost"` ranks `.edu` higher without excluding legitimate vendor-hosted pages — never use hard `include_domains` exclusion here. `exclude_domains` filters generic social/wiki/review sites. `extract()` reports per-URL failures in `failed_results` rather than raising, so that list must be checked explicitly. Batch `extract()` per college (already done), and track credit spend against budget before scaling up.
It may be wrothwhile to implement some sort of retry logic for when Tavily fails to return a result.

## Code conventions

- All constants/paths in `config.py`; word lists are line-delimited `.txt` files under `config/`.
- Stage 1 = network, Stage 2 = pure/offline — keep that split.
- `csv.field_size_limit` raised for full-page-text rows.
- Tavily client built lazily (`functools.cache`) so import doesn't require an API key.
- Comments explain _why_, not _what_ — several gating decisions are intentional; read them before changing gating logic.

## Open gaps

- No fix yet for wrong-school attribution; alternative search APIs under investigation.
- Vendor-platform special-casing and amalgam-page detection: not implemented.
- No disambiguation between multiple emails on one page (club vs. officer); no contact-name extraction.
- `CONTACT_WORD_RE` is one flat boolean — planned split into strong/weak confidence tiers.
- Stage 3 (final CSV + review queue) doesn't exist yet.
