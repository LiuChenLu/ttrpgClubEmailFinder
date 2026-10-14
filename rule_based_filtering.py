"""Stage 2's rule-based filter: keyword signals plus a keep/discard decision.

A row is kept if its result title + snippet hit at least one club OR ttrpg
keyword. That is the only keyword gate: the page text (result_raw_content) is
never read. NO_RESULTS/ERROR rows, PDF results, and low-relevance URL types are
always discarded.

Matching is a case-insensitive substring test, not a regex: each line of a
keyword file is a literal string, so regex syntax in one matches literally.

The functions read only result_url, result_title and result_snippet from a row.
Importing this module reads no files and needs no network access or API key;
the word lists are read when load_keyword_lists() is called.
filter_candidates.py owns the CSV reading and writing and calls apply_rules()
once per row.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from config import CLUB_KEYWORDS_PATH, TTRPG_KEYWORDS_PATH, load_word_list

# The columns apply_rules() adds beside "decision".
KEYWORD_FIELDNAMES = [
    "club_keywords_found_in_snippet", "ttrpg_keywords_found_in_snippet",
]


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


def url_filtering_rules(url: str) -> bool:
    """Return whether a URL matches a low-relevance content or storefront term."""
    excluded_terms = (
        # news articles
        "blog", "news", "article", "dailydigest", "stories", "story",
        # one off events, often hosted by clubs not related to ttrpg
        "rsvp", "event", "calendar",
        # storefronts
        "store", "shop", "market",
        # not filtered: library
    )
    lowered_url = url.lower()
    has_excluded_term = any(term in lowered_url for term in excluded_terms)

    is_pdf_url = urlsplit(url).path.lower().endswith(".pdf")
    return has_excluded_term or is_pdf_url


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


def decide(row: dict, keywords: dict) -> str:
    if (
        is_sentinel(row)
        or url_filtering_rules(row["result_url"])
    ):
        return "discard"

    snippet_gate = (
        keywords["club_keywords_found_in_snippet"]
        or keywords["ttrpg_keywords_found_in_snippet"]
    )
    return "keep" if snippet_gate else "discard"


def apply_rules(row: dict, keyword_lists: KeywordLists) -> dict:
    """The Stage 2 columns this component owns: the keyword hits and decision."""
    keywords = keyword_columns(row, keyword_lists.ttrpg, keyword_lists.club)
    return {**keywords, "decision": decide(row, keywords)}