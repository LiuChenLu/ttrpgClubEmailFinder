"""Stage 2: record keyword signals for each Stage 1 candidate and decide keep/discard.

Currently a pass-through stub: keyword hits are computed and written, and every
row is kept. The discard rule is meant to be added inside decide().

Two keyword tiers are recorded, neither of them a gate yet:
  - snippet: what each list matched in the result title + snippet.
  - page: what each list matched in the extracted page text.

Reads only candidates.csv; needs no network access or API key.
"""

from __future__ import annotations
from config import (
    CLUB_KEYWORDS_PATH, DEFAULT_CANDIDATES_CSV, DEFAULT_FILTERED_CSV,
    TTRPG_KEYWORDS_PATH, load_word_list,
)

import csv

# Stage 1 writes whole pages into result_raw_content, which can exceed csv's
# default 128 KB field limit and make the reader raise.
csv.field_size_limit(2**31 - 1)

KEYWORD_FIELDNAMES = [
    "club_keywords_found_in_snippet", "ttrpg_keywords_found_in_snippet",
    "club_keywords_found_in_page", "ttrpg_keywords_found_in_page",
]

# TODO: special-case club hosting vendors, each identifiable from the page
# source: CampusGroups ("Powered by CampusGroups"), Modern Campus Involve,
# Anthology Engage, Lounge, Corq.

# TODO: detect when a URL is a directory of a university's clubs rather than
# one specific club's page. These often rank well and mention plenty of
# keywords (an A-Z list mentions "club" and often "tabletop"), but yield no
# single club's contact info, so they need separating before anything
# downstream treats a row as one club.


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [kw for kw in keywords if kw in lowered]


def keyword_columns(row: dict, ttrpg_kw: list[str], club_kw: list[str]) -> dict:
    # NO_RESULTS and ERROR rows aren't pages, and ERROR rows hold the exception
    # message in result_title, so it must not be scanned as if it were a title.
    if row["result_url"] in ("", "ERROR"):
        return dict.fromkeys(KEYWORD_FIELDNAMES, "")

    snippet = f"{row['result_title']} {row['result_snippet']}"
    page = row["result_raw_content"]
    return {
        "club_keywords_found_in_snippet": "; ".join(find_keywords(snippet, club_kw)),
        "ttrpg_keywords_found_in_snippet": "; ".join(find_keywords(snippet, ttrpg_kw)),
        "club_keywords_found_in_page": "; ".join(find_keywords(page, club_kw)),
        "ttrpg_keywords_found_in_page": "; ".join(find_keywords(page, ttrpg_kw)),
    }


def decide(row: dict) -> str:
    return "keep"


def main(
    input_csv: str = DEFAULT_CANDIDATES_CSV, output_csv: str = DEFAULT_FILTERED_CSV
) -> None:
    ttrpg_kw = load_word_list(TTRPG_KEYWORDS_PATH)
    club_kw = load_word_list(CLUB_KEYWORDS_PATH)

    with open(input_csv, newline="", encoding="utf-8") as f_in, \
            open(output_csv, "w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(
            f_out, fieldnames=["decision"] + (list(reader.fieldnames) + KEYWORD_FIELDNAMES if reader.fieldnames is not None else KEYWORD_FIELDNAMES)
        )
        writer.writeheader()

        for row in reader:
            writer.writerow({
                **row,
                "decision": decide(row),
                **keyword_columns(row, ttrpg_kw, club_kw),
            })


if __name__ == "__main__":
    main()