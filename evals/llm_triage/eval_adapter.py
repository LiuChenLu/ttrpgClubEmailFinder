"""Turn eval_v2.csv into a Stage 2a-shaped CSV that run_llm_triage can read.

Official aliases come from institutions.csv, matched on college name.

Usage:
    python eval_adapter.py [eval_csv] evals/llm_triage/coverage.csv [--institutions institutions.csv]

We can use the output of this script with llm_triage.py
    python llm_triage.py --input=evals/llm_triage/coverage.csv --output=evals/llm_triage/coverage_output.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from llm_triage import build_triage_input
from schema import FILTERED_FIELDNAMES, KEEP

EVAL_CSV = "eval_v2.csv"
ADAPTED_CSV = "eval_v2_stage2a.csv"
INSTITUTIONS_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "institutions.csv"


def load_official_aliases(institutions_csv: str) -> dict[str, set[str]]:
    """college_name -> the distinct `aliases` values of its institutions.csv rows."""
    by_name = defaultdict(set)
    with open(institutions_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_name[row["college_name"]].add(row["aliases"])
    return by_name


def adapt_row(eval_row: dict, official_aliases: str) -> dict:
    """One eval row as a Stage 2a row. Columns the eval doesn't have stay blank."""
    row = dict.fromkeys(FILTERED_FIELDNAMES, "")
    row.update(
        # Eval ids are unique; URLs repeat across targets (e.g. C01 and C02).
        unitid=eval_row["id"],
        college_name=eval_row["institution"],
        # "|"-separated, as in the pipeline. A value in the eval row wins.
        aliases=eval_row["aliases"] or official_aliases,
        result_url=eval_row["url"],
        result_title=eval_row["title"],
        website=eval_row["institution_domain"],
        # Pretend Stage 2a kept every row, so the model sees all of them.
        decision=KEEP,
    )
    return row


def domain_relation_mismatches(eval_rows: list[dict], rows: list[dict]) -> list[str]:
    """Eval ids whose domain_relation, as the pipeline computes it, differs from
    the value the eval was labeled with.
    """
    return [
        e["id"]
        for e, r in zip(eval_rows, rows)
        if build_triage_input(r)["domain_relation"] != e["domain_relation"]
    ]


def adapt_eval_csv(
    eval_csv: str = EVAL_CSV,
    out_csv: str = ADAPTED_CSV,
    institutions_csv: str = INSTITUTIONS_CSV,
) -> int:
    """Write the adapted CSV and return its row count."""
    with open(eval_csv, newline="", encoding="utf-8") as f:
        eval_rows = list(csv.DictReader(f))

    by_name = load_official_aliases(institutions_csv)
    names = {r["institution"] for r in eval_rows}
    missing = sorted(n for n in names if n not in by_name)
    ambiguous = sorted(n for n in names if len(by_name.get(n, ())) > 1)
    if missing:
        print(f"not in {institutions_csv}, aliases left blank: {missing}")
    if ambiguous:
        print(f"several alias values in {institutions_csv}, left blank: {ambiguous}")

    rows = []
    for eval_row in eval_rows:
        found = by_name.get(eval_row["institution"], set())
        rows.append(adapt_row(eval_row, next(iter(found)) if len(found) == 1 else ""))

    mismatches = domain_relation_mismatches(eval_rows, rows)
    if mismatches:
        print(f"domain_relation differs from the eval's value for: {mismatches}")

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FILTERED_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("eval_csv", nargs="?", default=EVAL_CSV)
    parser.add_argument("out_csv", nargs="?", default=ADAPTED_CSV)
    parser.add_argument("--institutions", default=INSTITUTIONS_CSV)
    args = parser.parse_args()
    count = adapt_eval_csv(args.eval_csv, args.out_csv, args.institutions)
    print(f"wrote {count} rows to {args.out_csv}")