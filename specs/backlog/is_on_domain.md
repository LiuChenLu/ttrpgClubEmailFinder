**Status:** in-progress
**Implements in:** `url_parsing_utils.py` (new), `llm_triage.py`, `build_institution_dataset.py`, `tests/test_url_parsing_utils.py` (new), `tests/test_llm_triage.py`
**Docs to update when it lands:** `docs/architecture.md` (shared helpers table), `docs/stages/stage2_filter_candidates.md` (Stubs, Open gaps), `specs/stage2b_llm_triage/spec.md` (header)

# Plan: implement `llm_triage.is_on_domain`

Goal: `is_on_domain(url, website)` is True when the URL's host is the website's
registrable domain or a subdomain of it.

## Decisions

- Schools that share a system domain (CUNY, KCTCS, PSU) count as `on_domain` for
  each other. That is accepted.
- Host parsing is shared with `build_institution_dataset.is_edu` through a new
  `url_parsing_utils.py`.
- No new dependency. IPEDS `WEBADDR` is `.edu` only (Stage 0), so the registrable
  domain is the last two labels. Wrong for multi-label suffixes such as
  `co.uk`; the result URL is never reduced, only suffix-matched.

## Phases

1. `url_parsing_utils.py`: `extract_host(url)` and `registrable_domain(url)`.
   - `extract_host`: add `//` when the scheme is missing, use `urlsplit(...).hostname`
     (lowercases, drops port, path, query, userinfo), strip trailing dots. Return
     None for non-strings, parse errors, empty hosts and IP addresses.
   - `registrable_domain`: last two labels of the host; None if fewer than two
     labels or any label is empty.
2. Rewire `build_institution_dataset.is_edu` and `llm_triage.is_on_domain`.
3. Tests: new `tests/test_url_parsing_utils.py`; replace the stub test in
   `tests/test_llm_triage.py`.
4. Docs, then `python -m pytest -q`.
