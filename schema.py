"""The CSV handoff contract between stages: column lists, decision values, and
the column check each stage runs on its input.

This is the single source of truth for column names. docs/data_flow.md
describes it, and tests/test_docs.py fails if the two disagree. Has no
dependency on the tavily package and reads no files at import time.

The sections run in stage order. From Stage 1 on, each stage's columns are
derived the same way:

    <STAGE>_FIELDNAMES = PREVIOUS_FIELDNAMES - <STAGE>_DROPPED_FIELDNAMES
                         + <STAGE>_NEW_FIELDNAMES

where "+" puts the new columns where the stage's comment says (usually the end).
"""

from __future__ import annotations

from collections.abc import Sequence


def require_columns(
    path: str, fieldnames: Sequence[str] | None, required: Sequence[str]
) -> None:
    """Raise before any output is opened if the input lacks a column."""
    present = set(fieldnames or [])
    missing = [c for c in required if c not in present]
    if missing:
        raise ValueError(f"{path} is missing columns: {missing}")


# --- Stage 0: institutions.csv ------------------------------------------------

INSTITUTION_FIELDNAMES = [
    "unitid", "college_name", "aliases", "generated_aliases", "city",
    "distance", "website",
]


# --- Stage 1: search_results.csv ----------------------------------------------

# Input columns that are not copied onto search_results.csv rows.
SEARCH_DROPPED_FIELDNAMES =  ["distance"]
# Appended after the institution columns Stage 1 carries over.
SEARCH_NEW_FIELDNAMES = [
    "search_query", "result_title", "result_url", "result_score",
    "result_snippet", "raw_content_status", "raw_content_length",
    "result_raw_content",
]
SEARCH_RESULTS_FIELDNAMES = [
    *(c for c in INSTITUTION_FIELDNAMES if c not in SEARCH_DROPPED_FIELDNAMES),
    *SEARCH_NEW_FIELDNAMES,
]


# --- Stage 2: filtered_candidates.csv -----------------------------------------

# Dropped on purpose: the search engine's score wasn't a reliable signal, so no
# later stage sees it.
FILTERED_DROPPED_FIELDNAMES = ["result_score"]
# "decision" goes first; the two audit columns go last.
FILTERED_PREPENDED_FIELDNAMES = ["decision"]
KEYWORD_FIELDNAMES = [
    "club_keywords_found_in_snippet", "ttrpg_keywords_found_in_snippet",
]
# What Stage 2 requires of Stage 1's output: every column it carries forward.
SEARCH_FIELDNAMES = [
    c for c in SEARCH_RESULTS_FIELDNAMES if c not in FILTERED_DROPPED_FIELDNAMES
]
FILTERED_FIELDNAMES = [
    *FILTERED_PREPENDED_FIELDNAMES, *SEARCH_FIELDNAMES, *KEYWORD_FIELDNAMES,
]

# Decisions (written by Stage 2, read by Stages 3 and 4).

# Downstream stages treat exactly this value as keep. Any other value, whatever
# its text, is a discard.
KEEP = "keep"
DISCARD_PREFIX = "discard_"

# Discard reasons in the order Stage 2 reports them. A row's decision is
# DISCARD_PREFIX + reason. Add new reasons here and nowhere else.
REASON_PDF = "pdf"
REASON_NEWS = "news"
REASON_EVENT = "event"
REASON_STOREFRONTS = "storefronts"
REASON_NO_KEYWORDS = "snippets_has_no_club_or_ttrpg_keywords"
REASON_SENTINEL_ROW = "sentinel_row"
DISCARD_REASONS = (
    REASON_PDF,
    REASON_NEWS,
    REASON_EVENT,
    REASON_STOREFRONTS,
    REASON_NO_KEYWORDS,
    REASON_SENTINEL_ROW,
)


def discard_decision(reason: str) -> str:
    return DISCARD_PREFIX + reason


def is_keep(row: dict) -> bool:
    return row.get("decision") == KEEP


# --- Stage 3: rendered_results.csv --------------------------------------------

# The keyword audit columns are only for checking Stage 2's work.
RENDERED_DROPPED_FIELDNAMES = KEYWORD_FIELDNAMES
# Inserted right after raw_content_status, so the two status columns sit together.
RENDERED_INSERT_AFTER = "raw_content_status"
RENDERED_INSERTED_FIELDNAMES = ["extract_status"]
# Appended after every other column.
RENDERED_APPENDED_FIELDNAMES = ["render_status", "content_source"]
RENDERED_NEW_FIELDNAMES = [
    *RENDERED_INSERTED_FIELDNAMES, *RENDERED_APPENDED_FIELDNAMES,
]


def rendered_fieldnames(input_fieldnames: Sequence[str]) -> list[str]:
    """Stage 3's output columns for a given Stage 2 header.

    Raises ValueError if the header lacks RENDERED_INSERT_AFTER, rather than
    silently leaving out the inserted column.
    """
    names = [c for c in input_fieldnames if c not in RENDERED_DROPPED_FIELDNAMES]
    insert_at = names.index(RENDERED_INSERT_AFTER) + 1
    names[insert_at:insert_at] = RENDERED_INSERTED_FIELDNAMES
    return names + RENDERED_APPENDED_FIELDNAMES


RENDERED_FIELDNAMES = rendered_fieldnames(FILTERED_FIELDNAMES)


# --- Stage 4: ttrpg_clubs_contacts.csv ----------------------------------------

# Stage 4 drops nothing; it appends to every Stage 3 column.
CONTACT_DROPPED_FIELDNAMES: list[str] = []
CONTACT_NEW_FIELDNAMES = ["has_contact_signal", "email_found", "discord_found"]
CONTACT_FIELDNAMES = [
    *(c for c in RENDERED_FIELDNAMES if c not in CONTACT_DROPPED_FIELDNAMES),
    *CONTACT_NEW_FIELDNAMES,
]
