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
REASON_FORUM = "forum"
REASON_EVENT = "event"
REASON_WIKI = "wiki"
REASON_STOREFRONTS = "storefronts"
REASON_NO_KEYWORDS = "snippets_has_no_club_or_ttrpg_keywords"
REASON_SENTINEL_ROW = "sentinel_row"
DISCARD_REASONS = (
    REASON_PDF,
    REASON_FORUM,
    REASON_NEWS,
    REASON_WIKI,
    REASON_EVENT,
    REASON_STOREFRONTS,
    REASON_NO_KEYWORDS,
    REASON_SENTINEL_ROW,
)


def discard_decision(reason: str) -> str:
    return DISCARD_PREFIX + reason


def is_keep(row: dict) -> bool:
    return row.get("decision") == KEEP


# --- Stage 2b: llm_filtered_candidates.csv ------------------------------------

# Evidence fields come first in the model's response so it quotes the text
# before it commits to a label.
TRIAGE_LABEL_FIELDNAMES = [
    "title_evidence_for_page_type", "url_evidence_for_page_type",
    "page_type", "page_type_certainty",
    "title_evidence_for_institution", "url_evidence_for_institution",
    "institution", "institution_certainty",
]
# Appended after every Stage 2a column. `decision` keeps its Stage 2a position
# and is rewritten by 2b for the rows it drops.
TRIAGE_NEW_FIELDNAMES = [
    *TRIAGE_LABEL_FIELDNAMES,
    "triage_status", "triage_model", "triage_prompt_version",
]
LLM_FILTERED_FIELDNAMES = [*FILTERED_FIELDNAMES, *TRIAGE_NEW_FIELDNAMES]

# The database tables of Stage 2b are not CSV files. tests/test_triage_store.py
# checks each list below against the table in migrations/.
#
# `llm_triage_run`: one row per run, saved with its results.
TRIAGE_RUN_FIELDNAMES = [
    "run_id", "started_at", "model", "prompt_hash", "prompt_version",
    "temperature", "thinking_level", "input_csv", "cache_only",
    "git_commit", "git_dirty", "note",
]
# `llm_triage_result`: the same labels as the 2b CSV plus the link to the saved
# model reply. The row fields are everything but `run_id`, which is only known
# once the run is saved.
TRIAGE_RESULT_ROW_FIELDNAMES = [
    "unitid", "result_url", "stage2a_decision", "decision",
    "input_hash", "attempt",
    *TRIAGE_LABEL_FIELDNAMES,
    "triage_status", "triage_model", "triage_prompt_version",
]
TRIAGE_RESULT_FIELDNAMES = ["run_id", *TRIAGE_RESULT_ROW_FIELDNAMES]
# What compare_triage_runs.py compares. The evidence quotes are left out: a
# reworded quote is rarely a change worth reading.
TRIAGE_COMPARE_FIELDNAMES = [
    "decision", "page_type", "page_type_certainty",
    "institution", "institution_certainty", "triage_status",
]

PAGE_TYPE_OTHER = "other"
INSTITUTION_NOT_SUPPORTED = "not_supported"
INSTITUTION_UNKNOWN = "unknown"
CERTAINTY_PROBABLE = "probable"
# The allowed values of each enum field in a model response.
TRIAGE_ENUM_VALUES = {
    "page_type": ("tabletop_club", "conglomerate", PAGE_TYPE_OTHER, "unknown"),
    "page_type_certainty": ("clear", CERTAINTY_PROBABLE),
    "institution": ("supported", INSTITUTION_NOT_SUPPORTED, INSTITUTION_UNKNOWN),
    "institution_certainty": ("clear", CERTAINTY_PROBABLE),
}

# usage_metadata fields saved with each model reply in the database (not CSV
# columns), named as the google-genai SDK names them.
TRIAGE_USAGE_FIELDNAMES = [
    "prompt_token_count", "candidates_token_count", "thoughts_token_count",
    "cached_content_token_count", "tool_use_prompt_token_count",
    "total_token_count",
]

# `triage_status` values. Blank means the row was labeled. `cache_miss` is only
# from `--cache-only`: no saved reply, and the model was not called.
TRIAGE_STATUS_API_ERROR = "api_error"
TRIAGE_STATUS_INVALID_OUTPUT = "invalid_output"
TRIAGE_STATUS_CACHE_MISS = "cache_miss"

# Reasons Stage 2b adds to `decision`, in the order it reports them. Kept apart
# from DISCARD_REASONS, which is Stage 2a's list.
REASON_WRONG_INSTITUTION = "wrong_institution"
REASON_WRONG_PAGE_TYPE = "wrong_page_type"
REASON_WRONG_INSTITUTION_AND_PAGE_TYPE = "wrong_institution_and_wrong_page_type"
TRIAGE_DISCARD_REASONS = (
    REASON_WRONG_INSTITUTION,
    REASON_WRONG_PAGE_TYPE,
    REASON_WRONG_INSTITUTION_AND_PAGE_TYPE,
)


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
