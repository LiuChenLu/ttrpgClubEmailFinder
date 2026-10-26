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
from schema import (
    DISCARD_REASONS,
    FILTERED_FIELDNAMES,
    KEEP,
    KEYWORD_FIELDNAMES,
    REASON_EVENT,
    REASON_NEWS,
    REASON_FORUM,
    REASON_WIKI,
    REASON_NO_KEYWORDS,
    REASON_PDF,
    REASON_SENTINEL_ROW,
    REASON_STOREFRONTS,
    SEARCH_FIELDNAMES,
    discard_decision,
    require_columns,
)
from search_row_format_util import is_sentinel
from stage_cli import build_parser

# Ordered (reason, URL substrings) pairs. The first reason with a hit wins.
URL_TERMS = (
    (REASON_NEWS, ("news", "article", "dailydigest", "stories", "story", "journal")),
    (REASON_FORUM, ("blog", "forum", "thread")),
    (REASON_EVENT, ("rsvp", "event", "calendar", "2026")),
    (REASON_WIKI, ("wiki",)),
    (REASON_STOREFRONTS, ("store", "shop", "market")),
)


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


def url_filtering_reason(url: str) -> str | None:
    """Return the first matching URL discard reason, if any."""
    lowered_url = url.lower()
    if urlsplit(url).path.lower().endswith(".pdf"):
        return REASON_PDF

    for reason, terms in URL_TERMS:
        if any(term in lowered_url for term in terms):
            return reason
    return None


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
# before the discard rules in discard_reason(). Stage 2 doesn't read page text,
# so this would have to match on result_url instead, or move to a stage that
# has the page.

# Directory pages (an A-Z list of a school's clubs) are deliberately kept: they
# go through the snippet gate like any other result, so a club keyword alone
# passes one, whether or not it lists a TTRPG club. Splitting a directory into
# individual clubs is not implemented in any stage yet, so Stage 2 doesn't
# need to detect them.


def discard_reason(row: dict, keywords: dict) -> str | None:
    """The first matching reason from schema.DISCARD_REASONS, else None."""
    if is_sentinel(row):
        return REASON_SENTINEL_ROW
    url_reason = url_filtering_reason(row["result_url"])
    if url_reason:
        return url_reason
    snippet_gate = (
        keywords["club_keywords_found_in_snippet"]
        or keywords["ttrpg_keywords_found_in_snippet"]
    )
    return None if snippet_gate else REASON_NO_KEYWORDS


def apply_rules(row: dict, keyword_lists: KeywordLists) -> dict:
    """The Stage 2 columns this component owns: the keyword hits and decision."""
    keywords = keyword_columns(row, keyword_lists.ttrpg, keyword_lists.club)
    reason = discard_reason(row, keywords)
    decision = discard_decision(reason) if reason else KEEP
    return {**keywords, "decision": decision}


def run_rule_based_filter(
    input_csv: str = SEARCH_RESULTS_CSV,
    output_csv: str = DEFAULT_FILTERED_CSV,
) -> None:
    """Read Stage 1 results, apply rules, and write the Stage 2 audit CSV."""
    keyword_lists = load_keyword_lists()
    decision_counts = Counter()

    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        require_columns(input_csv, reader.fieldnames, SEARCH_FIELDNAMES)

        with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(
                f_out, fieldnames=FILTERED_FIELDNAMES, extrasaction="ignore"
            )
            writer.writeheader()

            for row in reader:
                result = apply_rules(row, keyword_lists)
                writer.writerow({**row, **result})
                decision_counts[result["decision"]] += 1

    print("Filtered rows by reason:")
    for reason in DISCARD_REASONS:
        print(f"  {reason}: {decision_counts[discard_decision(reason)]}")


if __name__ == "__main__":
    args = build_parser(
        "Stage 2: rule-based filtering of search results.",
        SEARCH_RESULTS_CSV,
        DEFAULT_FILTERED_CSV,
    ).parse_args()
    run_rule_based_filter(args.input_csv, args.output_csv)
