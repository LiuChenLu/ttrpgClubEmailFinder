# Known bugs (code differs from intent)

Places where the code at HEAD does not do what the tests or design say it
should. `docs/` describes the code as it is. Remove an entry when it is fixed.
Limits of working code are not bugs; they go in the stage doc's "Open gaps".

- **Stage 3 length comparison.** Playwright text replaces existing content only
  if it is longer, but Tavily content is markdown and Playwright's is plain
  text, so the lengths aren't comparable (`render_candidates.render_row`).
  Expected to have a small effect.
- **Stage 2a `wiki` rule matches single letters.** `URL_TERMS` in
  `rule_based_filtering.py` has `(REASON_WIKI, ("wiki,"))`. That is a string, not
  a one-item tuple (the comma is inside the quotes), so
  `any(term in url for term in terms)` tests the characters `w`, `i`, `k`, `,`.
  Almost every URL (every `www.` one) is discarded as `wiki`. Fix: `("wiki",)`.
  `tests/test_pipeline_contract.py::test_decisions_survive_every_stage_and_only_keep_is_scanned`
  fails because of it.
- **Stage 4 duplicate invites.** `discord_found` isn't deduplicated, unlike
  `email_found` (`extract_contact_info.contact_columns`).
