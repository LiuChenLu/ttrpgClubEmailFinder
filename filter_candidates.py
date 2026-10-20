"""Stage 2 entry point for rule-based candidate filtering."""

from __future__ import annotations

from config import DEFAULT_FILTERED_CSV, SEARCH_RESULTS_CSV
import rule_based_filtering
from stage_cli import build_parser


def main(
    input_csv: str = SEARCH_RESULTS_CSV,
    output_csv: str = DEFAULT_FILTERED_CSV,
) -> None:
    rule_based_filtering.run_rule_based_filter(input_csv, output_csv)


if __name__ == "__main__":
    args = build_parser(
        "Stage 2: rule-based filtering of search results.",
        SEARCH_RESULTS_CSV,
        DEFAULT_FILTERED_CSV,
    ).parse_args()
    main(args.input_csv, args.output_csv)
