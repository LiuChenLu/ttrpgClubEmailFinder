# Testing utilities

- **`random_sample_institutions.py`** — generates a small test set of institutions at `institutions_sample.csv`, pulled at random from the full IPEDS CSV. Feed this into `classify_club_pages.py` for a cheap smoke test before spending Tavily credits on the full ~6,000-college run.
- **`ipeds_institution_has_ttrpg_club.csv`** — a very small, hand-picked subset of the IPEDS database consisting of institutions known to have at least one TTRPG club. Also usable as input to `classify_club_pages.py`. Useful as a positive-control set: if a change to the search/matching logic stops finding known clubs in this list, that's a regression, not just noise.
