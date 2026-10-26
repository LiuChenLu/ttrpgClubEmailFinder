"""Score llm_triage's output against the labeled coverage set.

Scores the pipeline output (after the evidence check and the drop rule), not
the raw model reply. Writes every row the LLM got wrong to a report CSV.

Usage: python eval_scorer.py LLM_OUTPUT_CSV [--labeled CSV] [--report CSV]
Exit status is 1 if a gate row was falsely dropped or a labeled row is missing.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from schema import is_keep

HERE = Path(__file__).parent

# Types of errors:
# false_drop: expected keep, got drop.
# missed_drop: expected drop, got keep.
# label_only: the decision is right but page_type or institution is wrong.
# call_failed: triage_status is set. These fail open to keep, so I flag them instead of counting them as model errors.
FLAG_ORDER = ["false_drop", "missed_drop", "label_only", "call_failed"]
DETAIL_FIELDS = [
    "page_type_certainty",
    "institution_certainty",
    "title_evidence_for_page_type",
    "url_evidence_for_page_type",
    "title_evidence_for_institution",
    "url_evidence_for_institution",
    "triage_status",
]
REPORT_FIELDS = [
    "flag", "in_gate", "id", "case", "college_name", "title", "url",
    "expected_page_type", "got_page_type",
    "expected_institution", "got_institution",
    "expected_decision", "got_decision",
    *DETAIL_FIELDS, "notes",
]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def flag_for(expected, got):
    """The kind of mistake, or "" when the row is right."""
    if got["triage_status"]:
        return "call_failed"
    expected_keep = expected["expected_decision"] == "keep"
    if expected_keep and not is_keep(got):
        return "false_drop"
    if not expected_keep and is_keep(got):
        return "missed_drop"
    if (got["page_type"], got["institution"]) != (
        expected["expected_page_type"],
        expected["expected_institution"],
    ):
        return "label_only"
    return ""


def score(labeled_rows, output_rows):
    outputs = {(r["college_name"], r["result_url"]): r for r in output_rows}
    missing = [r["id"] for r in labeled_rows if (r["institution"], r["url"]) not in outputs]
    if missing:
        sys.exit(f"No output row for labeled ids: {', '.join(missing)}")

    wrong, gate_total = [], 0
    for expected in labeled_rows:
        got = outputs[(expected["institution"], expected["url"])]
        in_gate = (
            expected["label_confidence"] == "clear"
            and expected["decision_confidence"] == "firm"
        )
        gate_total += in_gate
        flag = flag_for(expected, got)
        if flag:
            wrong.append({
                "flag": flag,
                "in_gate": in_gate,
                "id": expected["id"],
                "case": expected["case"],
                "college_name": expected["institution"],
                "title": expected["title"],
                "url": expected["url"],
                "expected_page_type": expected["expected_page_type"],
                "got_page_type": got["page_type"],
                "expected_institution": expected["expected_institution"],
                "got_institution": got["institution"],
                "expected_decision": expected["expected_decision"],
                "got_decision": got["decision"],
                "notes": expected["notes"],
                **{name: got[name] for name in DETAIL_FIELDS},
            })
    wrong.sort(key=lambda r: (FLAG_ORDER.index(r["flag"]), not r["in_gate"], r["id"]))
    return wrong, gate_total


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output_csv", help="the CSV run_llm_triage wrote")
    parser.add_argument("--labeled", default=HERE / "labeled_coverage.csv")
    parser.add_argument("--report", default=HERE / "wrong.csv")
    args = parser.parse_args()

    labeled = read_csv(args.labeled)
    wrong, gate_total = score(labeled, read_csv(args.output_csv))

    with open(args.report, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(wrong)

    in_gate = Counter(r["flag"] for r in wrong if r["in_gate"])
    overall = Counter(r["flag"] for r in wrong)
    print(f"{len(labeled)} rows, {gate_total} in the gate; {len(wrong)} wrong -> {args.report}")
    for name in FLAG_ORDER:
        print(f"  {name}: {overall[name]} (gate {in_gate[name]})")
    sys.exit(1 if in_gate["false_drop"] else 0)


if __name__ == "__main__":
    main()