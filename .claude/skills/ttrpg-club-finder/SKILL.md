---
name: ttrpg-club-finder
description:
  Entry point for the TTRPG-club contact-finding project, a pipeline that
  searches for university tabletop-RPG/gaming club pages via Tavily (rendering
  JS-heavy pages with Playwright) and extracts contact info (email/Discord) into
  a CSV. ALWAYS read this before touching config.py, tavily_client_util.py,
  search_row_format_util.py, build_institution_dataset.py, fetch_candidates.py,
  filter_candidates.py, rule_based_filtering.py, render_candidates.py, or
  extract_contact_info.py, even if the request doesn't say "ttrpg" explicitly.
---

# TTRPG Club Finder

All project documentation lives in the repository, not in this skill. Read
`AGENTS.md` at the repository root first. It says which documents describe the
code that exists (`docs/`) and which describe planned work (`specs/`), and it
lists the conventions to follow.

Then open only the doc for the stage you are editing, under `docs/stages/`.
