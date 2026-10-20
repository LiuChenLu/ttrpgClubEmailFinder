# Stage 4 — `extract_contact_info.py`

**Input:** `data/rendered_results.csv` (Stage 3)

**Output:** `data/ttrpg_clubs_contacts.csv`

This stage is implemented as offline text processing, with no network calls. It
preserves every Stage 3 row and appends contact-signal fields. It does not
classify school attribution, identify club names, or split directory pages into
individual clubs. A draft design for an LLM-based version of this work lives in
[`specs/llm_contact_extraction.md`](../../specs/llm_contact_extraction.md); none
of it is implemented.

Rows with `decision` exactly `keep` are scanned for emails, Discord invite URLs,
and contact-related words. All other rows (`discard_*`) are passed through with
blank/false contact fields. Stage 2's keyword-hit debug columns are dropped by
Stage 3, so they are not in this stage's input.

## Pitfalls to know before touching extraction logic

1. **Contact signals rank differently.** Email > Discord invite > bare "contact
   us" wording with no address/link. The last case usually means a contact form
   or login wall — route it to manual review, don't discard it. (The code only
   sets `has_contact_signal` for it; no review queue exists.) Discarding it
   silently loses real clubs, not just noise.
2. **Page text format varies by source.** `result_raw_content` is markdown
   (Tavily) or plain text (Playwright), per `content_source`. Playwright text
   omits link hrefs, so a `mailto:` address or Discord invite behind link text
   is invisible on those rows; don't rely on markdown link syntax.

Output columns are in [`data_flow.md`](../data_flow.md).

## Open gaps

- `discord_found` is not deduplicated; see [known_bugs.md](../known_bugs.md).
- No disambiguation between multiple emails found on one page (e.g. club address
  vs. an individual officer's address); no contact-name extraction.
- `CONTACT_WORD_RE` is currently one flat boolean; strong and weak confidence
  tiers are not distinguished.
- No school-attribution verification, club classification, or directory-page
  splitting.
