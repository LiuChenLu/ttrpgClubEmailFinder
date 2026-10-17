"""Stage 2's rule-based filter: keyword signals plus a keep/discard decision.

A row is kept if its result title + snippet hit at least one club OR ttrpg
keyword. That is the only keyword gate: the page text (result_raw_content) is
never read. NO_RESULTS/ERROR rows, PDF results, and low-relevance URL types are
always discarded.

Matching is a case-insensitive substring test, not a regex: each line of a
keyword file is a literal string, so regex syntax in one matches literally.

The functions read only result_url, result_title and result_snippet from a row.
Importing this module reads no files and needs no network access or API key.
run_rule_based_filter() loads the keyword lists, reads the previous stage's
CSV, applies the rules, and writes the filtered CSV.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlsplit

from config import (
    CLUB_KEYWORDS_PATH,
    DEFAULT_FILTERED_CSV,
    SEARCH_RESULTS_CSV,
    TTRPG_KEYWORDS_PATH,
    load_word_list,
)

# The columns apply_rules() adds beside "decision".
KEYWORD_FIELDNAMES = [
    "club_keywords_found_in_snippet", "ttrpg_keywords_found_in_snippet",
]

# Stage 1 fields are retained so Stage 3 can render kept rows from this audit.
SEARCH_FIELDNAMES = [
    "unitid", "college_name", "aliases", "generated_aliases", "city",
    "website", "search_query", "result_title", "result_url",
    "result_snippet",
    "raw_content_status", "raw_content_length", "result_raw_content",
]

FILTERED_FIELDNAMES = [
    "decision", *SEARCH_FIELDNAMES, *KEYWORD_FIELDNAMES,
]

DISCARD_REASON_LABELS = {
    "pdf": "pdf",
    "news": "news",
    "event": "event",
    "storefront": "storefronts",
    "no_keywords": "snippets_has_no_club_or_ttrpg_keywords",
    "sentinel": "sentinel_row",
}

# DictReader parses every field, including the page-text column Stage 2 ignores.
csv.field_size_limit(2**31 - 1)


@dataclass(frozen=True)
class KeywordLists:
    """The two lowercased word lists a row is matched against."""

    ttrpg: list[str]
    club: list[str]


def load_keyword_lists() -> KeywordLists:
    return KeywordLists(
        ttrpg=load_word_list(TTRPG_KEYWORDS_PATH),
        club=load_word_list(CLUB_KEYWORDS_PATH),
    )


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [kw for kw in keywords if kw in lowered]


def is_sentinel(row: dict) -> bool:
    # NO_RESULTS rows have a blank result_url; ERROR rows have "ERROR" there
    # and hold the exception message in result_title.
    return row["result_url"] in ("", "ERROR")


def url_filtering_reason(url: str) -> str | None:
    """Return the first matching URL discard category, if any."""
    lowered_url = url.lower()
    if urlsplit(url).path.lower().endswith(".pdf"):
        return "pdf"

    excluded_terms = (
        ("news", ("blog", "news", "article", "dailydigest", "stories", "story", "forum")),
        ("event", ("rsvp", "event", "calendar")),
        ("storefront", ("store", "shop", "market")),
    )
    for reason, terms in excluded_terms:
        if any(term in lowered_url for term in terms):
            return reason
    return None


def url_filtering_rules(url: str) -> bool:
    """Return whether a URL matches a low-relevance content or storefront term."""
    return url_filtering_reason(url) is not None


def keyword_columns(row: dict, ttrpg_kw: list[str], club_kw: list[str]) -> dict:
    # Sentinel rows aren't pages, so the exception message in an ERROR row's
    # result_title must not be scanned as if it were a title.
    if is_sentinel(row):
        return dict.fromkeys(KEYWORD_FIELDNAMES, "")

    snippet = f"{row['result_title']} {row['result_snippet']}"
    return {
        "club_keywords_found_in_snippet": "; ".join(find_keywords(snippet, club_kw)),
        "ttrpg_keywords_found_in_snippet": "; ".join(find_keywords(snippet, ttrpg_kw)),
    }


# TODO: special-case club hosting vendors, each identifiable from the page
# source: CampusGroups ("Powered by CampusGroups"), Modern Campus Involve,
# Anthology Engage, Lounge, Corq. This is a keep-signal, so it has to run
# before the discard rules in decide(). Stage 3 no longer reads page text, so
# this would have to match on result_url instead, or move to a stage that has
# the page.

# Directory pages (an A-Z list of a school's clubs) are deliberately kept: they
# go through the snippet gate like any other result, so a club keyword alone
# passes one, whether or not it lists a TTRPG club. Stage 4 splits out the
# individual clubs, so Stage 2 doesn't need to detect them.


def discard_reason(row: dict, keywords: dict) -> str | None:
    if is_sentinel(row):
        return "sentinel"
    url_reason = url_filtering_reason(row["result_url"])
    if url_reason:
        return url_reason
    snippet_gate = (
        keywords["club_keywords_found_in_snippet"]
        or keywords["ttrpg_keywords_found_in_snippet"]
    )
    return None if snippet_gate else "no_keywords"


def decide(row: dict, keywords: dict) -> str:
    return "discard" if discard_reason(row, keywords) else "keep"


def apply_rules_with_reason(
    row: dict, keyword_lists: KeywordLists
) -> tuple[dict, str | None]:
    """Return the Stage 2 output fields and the transient discard category."""
    keywords = keyword_columns(row, keyword_lists.ttrpg, keyword_lists.club)
    reason = discard_reason(row, keywords)
    decision = "discard" if reason else "keep"
    return {**keywords, "decision": decision}, reason


def apply_rules(row: dict, keyword_lists: KeywordLists) -> dict:
    """The Stage 2 columns this component owns: the keyword hits and decision."""
    result, _ = apply_rules_with_reason(row, keyword_lists)
    return result


def run_rule_based_filter(
    input_csv: str = SEARCH_RESULTS_CSV,
    output_csv: str = DEFAULT_FILTERED_CSV,
) -> None:
    """Read Stage 1 results, apply rules, and write the Stage 2 audit CSV."""
    keyword_lists = load_keyword_lists()
    discard_counts = Counter()

    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)

        missing = set(SEARCH_FIELDNAMES) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{input_csv} is missing columns: {sorted(missing)}")

        with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(
                f_out, fieldnames=FILTERED_FIELDNAMES, extrasaction="ignore"
            )
            writer.writeheader()

            for row in reader:
                result, reason = apply_rules_with_reason(row, keyword_lists)
                if reason is not None:
                    result["decision"] = (
                        f"discard_{DISCARD_REASON_LABELS[reason]}"
                    )
                writer.writerow({**row, **result})
                if reason is not None:
                    discard_counts[reason] += 1

    print("Filtered rows by reason:")
    for reason, label in DISCARD_REASON_LABELS.items():
        print(f"  {label}: {discard_counts[reason]}")