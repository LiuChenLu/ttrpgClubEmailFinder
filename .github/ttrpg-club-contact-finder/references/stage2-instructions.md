# Stage 2 — `extract_contact_info.py`

**Output:** `data/ttrpg_clubs_contacts.csv`

Offline text processing, no network calls. Re-derives the text gate from Stage 1 and extracts emails/Discord invites/bare-word contact signal from the page text and snippets Stage 1 already gathered.

## Pitfall to know before touching extraction logic

**Contact signals rank differently.** Email > Discord invite > bare "contact us" wording with no address/link. The last case usually means a contact form or login wall — route to manual/LLM review, don't discard it. Discarding it silently loses real clubs, not just noise.

## Code specifics

- This stage reads the full-page-text rows Stage 1 wrote, so the same `csv.field_size_limit` increase applies when parsing the input CSV.

## Open gaps

- No disambiguation between multiple emails found on one page (e.g. club address vs. an individual officer's address); no contact-name extraction.
- `CONTACT_WORD_RE` is currently one flat boolean — planned split into strong/weak confidence tiers.

## TODO: Stage 3 (not built yet)

Stage 3 doesn't exist as code yet. Its job will be to collapse this stage's one-row-per-search-result output down to one row per club, in the final `college_name, contact_info, source_url, contact_reason` shape, using closed reason codes rather than free text. The reason codes are a direct mapping from what this stage already detects, so keep them in mind if you're extending the extraction logic here — whatever new signal you add should map cleanly onto one of these (or a new one):

| reason code | meaning |
| --- | --- |
| `email_in_page_text` | email found in extracted page text |
| `email_in_snippet` | email found only in search snippet |
| `discord_in_page_text` | Discord invite found in page text |
| `contact_form_needs_review` | contact wording present, no address — needs manual look |
| `no_signal` | passed text gate, no contact signal found |
