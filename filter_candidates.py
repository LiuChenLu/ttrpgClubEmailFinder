"""Stage 2 entry point: rule-based filtering (2a), then LLM triage (2b)."""

from __future__ import annotations

from config import DEFAULT_FILTERED_CSV, DEFAULT_LLM_FILTERED_CSV, SEARCH_RESULTS_CSV
import llm_triage
import rule_based_filtering
from stage_cli import build_parser


def main(
    input_csv: str = SEARCH_RESULTS_CSV,
    output_csv: str = DEFAULT_FILTERED_CSV,
    llm_output_csv: str = DEFAULT_LLM_FILTERED_CSV,
) -> None:
    rule_based_filtering.run_rule_based_filter(input_csv, output_csv)
    llm_triage.run_llm_triage(output_csv, llm_output_csv)


if __name__ == "__main__":
    parser = build_parser(
        "Stage 2: rule-based filtering, then LLM triage of search results.",
        SEARCH_RESULTS_CSV,
        DEFAULT_FILTERED_CSV,
    )
    parser.add_argument(
        "--llm-output", dest="llm_output_csv", default=DEFAULT_LLM_FILTERED_CSV,
        help=f"Stage 2b output CSV (default: {DEFAULT_LLM_FILTERED_CSV})",
    )
    args = parser.parse_args()
    main(args.input_csv, args.output_csv, args.llm_output_csv)
