# Stage 3 — `extract_contact_info.py`

**Input:** `data/filtered_candidates.csv` (Stage 2)

**Output:** `data/contacts.csv`

**Status:** Not implemented — this stage doesn't exist yet. Everything below describes its planned design: rule-based and offline, no LLM call. A separate, early-stage draft for a possible LLM-based version instead is sketched in `LLM-proposal.md`; that's not implemented either, and not reconciled with this doc.

Offline text processing, no network calls. Re-derives the text gate and extracts emails/Discord invites/bare-word contact signal from the page text and snippets already in `filtered_candidates.csv`.

## Pitfalls to know before touching extraction logic

1. **Contact signals rank differently.** Email > Discord invite > bare "contact us" wording with no address/link. The last case usually means a contact form or login wall — route to manual/LLM review, don't discard it. Discarding it silently loses real clubs, not just noise.
2. **Page text format varies by source.** `result_raw_content` is markdown (Tavily) or plain text (Playwright), per `content_source`. Playwright text omits link hrefs, so a `mailto:` address or Discord invite behind link text is invisible on those rows; don't rely on markdown link syntax.

## Code specifics

- This stage reads the full-page-text rows in `filtered_candidates.csv`, so the same `csv.field_size_limit` increase applies when parsing the input CSV.

## Open gaps

- No disambiguation between multiple emails found on one page (e.g. club address vs. an individual officer's address); no contact-name extraction.
- `CONTACT_WORD_RE` is currently one flat boolean — planned split into strong/weak confidence tiers.