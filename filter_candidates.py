"""Stage 2: decide keep/discard for each Stage 1 candidate before page rendering.

This file is the shell: it reads Stage 1's CSV, runs each row through
rule_based_filtering, and writes one output row per input row.

Discarded rows are still written (decision="discard") so the gate can be
audited.

Reads only the input CSV (Stage 1's by default); needs no network access or
API key.
"""

from __future__ import annotations

import csv

import rule_based_filtering
from config import SEARCH_RESULTS_CSV, DEFAULT_FILTERED_CSV

# The input still carries whole pages in result_raw_content. This stage never
# reads that column, but csv.DictReader parses every field of every row, so a
# page over csv's default 128 KB field limit would make the reader raise anyway.
# Remove this once Stage 1 stops writing page text.
csv.field_size_limit(2**31 - 1)

# Stage 1 fields are retained so Stage 3 can render kept rows from this audit.
SEARCH_FIELDNAMES = [
    "unitid", "college_name", "aliases", "generated_aliases", "city",
    "website", "search_query", "result_title", "result_url",
    "result_snippet",
    "raw_content_status", "raw_content_length", "result_raw_content",
]

# Keyword hits are debugging/audit fields for this stage; rendering drops them.
FILTERED_FIELDNAMES = [
    "decision", *SEARCH_FIELDNAMES, *rule_based_filtering.KEYWORD_FIELDNAMES,
]

INPUT_FIELDNAMES = SEARCH_FIELDNAMES


def main(
    input_csv: str = SEARCH_RESULTS_CSV, output_csv: str = DEFAULT_FILTERED_CSV
) -> None:
    keyword_lists = rule_based_filtering.load_keyword_lists()

    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)

        # Checked before the output file is opened, so a bad input can't
        # truncate a previous good output.
        missing = set(INPUT_FIELDNAMES) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{input_csv} is missing columns: {sorted(missing)}")

        with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(
                f_out, fieldnames=FILTERED_FIELDNAMES, extrasaction="ignore"
            )
            writer.writeheader()

            for row in reader:
                writer.writerow(
                    {**row, **rule_based_filtering.apply_rules(row, keyword_lists)}
                )


if __name__ == "__main__":
    main()