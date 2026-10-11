"""Stage 3: record keyword signals for each Stage 1 candidate and decide keep/discard.

A row is kept if its result title + snippet hit at least one club OR ttrpg
keyword. That is the only keyword gate: the page text is neither read nor
copied to the output.

Discarded rows are still written (decision="discard") so the gate can be
audited. NO_RESULTS/ERROR rows and PDF results are always discarded.

Reads only the input CSV (Stage 2's by default); needs no network access or
API key.
"""

from __future__ import annotations

import csv
from urllib.parse import urlsplit

from config import (
    CLUB_KEYWORDS_PATH, RENDERED_RESULTS_CSV, DEFAULT_FILTERED_CSV,
    TTRPG_KEYWORDS_PATH, load_word_list,
)

# The input still carries whole pages in result_raw_content. This stage never
# reads that column, but csv.DictReader parses every field of every row, so a
# page over csv's default 128 KB field limit would make the reader raise anyway.
# Remove this once Stage 1 stops writing page text.
csv.field_size_limit(2**31 - 1)

KEYWORD_FIELDNAMES = [
    "club_keywords_found_in_snippet", "ttrpg_keywords_found_in_snippet",
]

# Column order of the Stage 3 table in pipeline_data_flow.md.
# TODO pass along content_source from input csv as well
FILTERED_FIELDNAMES = [
    "decision", "unitid", "college_name", "city", "website",
    "result_title", "result_url", "result_snippet",
    "club_keywords_found_in_snippet", "ttrpg_keywords_found_in_snippet",
]

# The columns copied through from the input CSV; all of them are required.
INPUT_FIELDNAMES = [
    name for name in FILTERED_FIELDNAMES
    if name != "decision" and name not in KEYWORD_FIELDNAMES
]

# TODO: special-case club hosting vendors, each identifiable from the page
# source: CampusGroups ("Powered by CampusGroups"), Modern Campus Involve,
# Anthology Engage, Lounge, Corq. This is a keep-signal, so it has to run
# before the discard rules in decide(). Stage 3 no longer reads page text, so
# this would have to match on result_url instead, or move to a stage that has
# the page.

# Directory pages (an A-Z list of a school's clubs) are deliberately kept: they
# go through the snippet gate like any other result, so a club keyword alone
# passes one, whether or not it lists a TTRPG club. Stage 4 splits out the
# individual clubs, so Stage 3 doesn't need to detect them.


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [kw for kw in keywords if kw in lowered]


def is_sentinel(row: dict) -> bool:
    # NO_RESULTS rows have a blank result_url; ERROR rows have "ERROR" there
    # and hold the exception message in result_title.
    return row["result_url"] in ("", "ERROR")


def is_pdf_url(row: dict) -> bool:
    return urlsplit(row["result_url"]).path.lower().endswith(".pdf")


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


def decide(row: dict, keywords: dict) -> str:
    if is_sentinel(row) or is_pdf_url(row):
        return "discard"

    snippet_gate = (
        keywords["club_keywords_found_in_snippet"]
        or keywords["ttrpg_keywords_found_in_snippet"]
    )
    return "keep" if snippet_gate else "discard"


def main(
    input_csv: str = RENDERED_RESULTS_CSV, output_csv: str = DEFAULT_FILTERED_CSV
) -> None:
    ttrpg_kw = load_word_list(TTRPG_KEYWORDS_PATH)
    club_kw = load_word_list(CLUB_KEYWORDS_PATH)

    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)

        # Checked before the output file is opened, so a bad input can't
        # truncate a previous good output.
        missing = set(INPUT_FIELDNAMES) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{input_csv} is missing columns: {sorted(missing)}")

        with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
            # Input columns outside FILTERED_FIELDNAMES (search_query,
            # result_score, the page text, ...) are dropped.
            writer = csv.DictWriter(
                f_out, fieldnames=FILTERED_FIELDNAMES, extrasaction="ignore"
            )
            writer.writeheader()

            for row in reader:
                keywords = keyword_columns(row, ttrpg_kw, club_kw)
                writer.writerow({**row, **keywords, "decision": decide(row, keywords)})


if __name__ == "__main__":
    main()