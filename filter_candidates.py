"""Stage 2 entry point for rule-based candidate filtering."""

from __future__ import annotations

import rule_based_filtering


def main(
    input_csv: str = rule_based_filtering.SEARCH_RESULTS_CSV,
    output_csv: str = rule_based_filtering.DEFAULT_FILTERED_CSV,
) -> None:
    rule_based_filtering.run_rule_based_filter(input_csv, output_csv)


if __name__ == "__main__":
    main()
