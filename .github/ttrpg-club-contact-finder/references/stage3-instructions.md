# Stage 3 — `extract_contact_info.py`

**Output:** `data/contacts.csv`

**Status:** Not implemented — this stage doesn't exist yet. Everything below describes its planned design: rule-based and offline, no LLM call. A separate, early-stage draft for a possible LLM-based version instead is sketched in `LLM-proposal.md`; that's not implemented either, and not reconciled with this doc.

Offline text processing, no network calls. Re-derives the text gate from Stage 1 and extracts emails/Discord invites/bare-word contact signal from the page text and snippets Stage 1 already gathered.

## Pitfall to know before touching extraction logic

**Contact signals rank differently.** Email > Discord invite > bare "contact us" wording with no address/link. The last case usually means a contact form or login wall — route to manual/LLM review, don't discard it. Discarding it silently loses real clubs, not just noise.

## Code specifics

- This stage reads the full-page-text rows Stage 1 wrote, so the same `csv.field_size_limit` increase applies when parsing the input CSV.

## Open gaps

- No disambiguation between multiple emails found on one page (e.g. club address vs. an individual officer's address); no contact-name extraction.
- `CONTACT_WORD_RE` is currently one flat boolean — planned split into strong/weak confidence tiers.