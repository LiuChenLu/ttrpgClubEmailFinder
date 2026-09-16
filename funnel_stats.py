"""Per-college diagnostic funnel over the CSV from find_ttrpg_clubs.py.

Shows *where* the pipeline loses contact info: at search, at the score/keyword
gate, at extraction, or on pages that genuinely have no email.

Usage:
    python funnel_stats.py [results.csv] [--sample N] [--seed 42]
                           [--inspect 15] [--top-errors 10]

--sample takes a random subset of that many colleges (seeded via --seed). If
the CSV has fewer, all are used and a note is printed.
"""

import argparse
import csv
import random
from collections import Counter, defaultdict

from config import (
    DEFAULT_RESULTS_CSV, HAND_INSPECT_MIN_LENGTH, TAVILY_RELEVANCE_THRESHOLD,
)

PERCENTILES = [("min", 0), ("p25", 25), ("median", 50), ("p75", 75), ("p90", 90), ("max", 100)]

# Funnel rows, in order: label -> key on the dict returned by classify_college.
FUNNEL_STAGES = [
    ("had >=1 search result", "had_any_result"),
    ("had >=1 result pass SCORE gate", "passed_score"),
    ("had >=1 result pass KEYWORD gate", "passed_keyword"),
    ("had >=1 result pass BOTH gates (extraction attempted)", "passed_both"),
    ("had >=1 successful extraction", "extract_success"),
    ("had >=1 email found", "email_found"),
    ("had ANY contact signal (email or discord)", "any_contact_signal"),
]


def parse_bool(value: str) -> bool:
    """CSV round-trip of a Python bool, so "True" is the only truthy spelling."""
    return value == "True"


def is_no_results_row(row) -> bool:
    return row["matched_query"].startswith("NO_RESULTS:")


def is_error_row(row) -> bool:
    return row["result_url"] == "ERROR"


def is_real_result_row(row) -> bool:
    return bool(row["result_url"]) and not is_no_results_row(row) and not is_error_row(row)


def classify_college(rows) -> dict:
    """Reduce one college's rows to "did *any* row reach each funnel stage".

    OR across rows, since a college only needs one result to make it through.
    """
    real = [r for r in rows if is_real_result_row(r)]
    extract_success = any(r["raw_content_status"] == "attempt_succeeded" for r in real)
    any_contact_signal = any(parse_bool(r["has_any_contact_signal"]) for r in real)
    return {
        "no_results": any(is_no_results_row(r) for r in rows),
        "all_error": bool(rows) and not real and all(is_error_row(r) for r in rows),
        "had_any_result": bool(real),
        "passed_score": any(parse_bool(r["passed_score_gate"]) for r in real),
        "passed_keyword": any(parse_bool(r["passed_keyword_gate"]) for r in real),
        "passed_both": any(
            parse_bool(r["passed_score_gate"]) and parse_bool(r["passed_keyword_gate"])
            for r in real
        ),
        "extract_success": extract_success,
        "email_found": any(r["emails_found"].strip() for r in real),
        "any_contact_signal": any_contact_signal,
        # Contact info found without a successful extraction means it was in
        # Tavily's short snippet all along. Worth tracking on its own.
        "signal_from_snippet_only": any_contact_signal and not extract_success,
    }


def percentile(sorted_values, pct):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * pct / 100
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def fmt_pct(part, whole) -> str:
    return f"{100 * part / whole:5.1f}%" if whole else "  n/a "


def header(title: str) -> None:
    print("\n" + "-" * 72)
    print(title)
    print("-" * 72)


def print_funnel(colleges) -> None:
    total = len(colleges)
    classified = [classify_college(rows) for rows in colleges.values()]
    counts = {key: sum(c[key] for c in classified) for _, key in FUNNEL_STAGES}

    print("=" * 72)
    print(f"FUNNEL  (n = {total} colleges)")
    print("=" * 72)
    print(f"{'Total colleges sampled':<58s} {total:>4d}")
    for label, key in FUNNEL_STAGES:
        count = counts[key]
        print(f"{'  -> ' + label:<58s} {count:>4d}  ({fmt_pct(count, total)} of total)")

    print("\nDiagnostic side-counts (context, not part of the funnel above):")
    for label, key in [
        ("zero search results (NO_RESULTS)", "no_results"),
        ("every query errored (all ERROR rows)", "all_error"),
        ("contact signal from search snippet only, no extraction", "signal_from_snippet_only"),
    ]:
        n = sum(c[key] for c in classified)
        print(f"  colleges with {label:<55s} {n:>4d}  ({fmt_pct(n, total)})")

    if counts["passed_score"] != counts["passed_keyword"]:
        tighter = "keyword" if counts["passed_keyword"] < counts["passed_score"] else "score"
        print(f"\n  Note: the {tighter} gate is the more restrictive of the two "
              f"(score passes {counts['passed_score']}, keyword passes {counts['passed_keyword']}).")


def print_distribution(title, values, value_fmt="{:.3f}", flag=None) -> None:
    """Print percentiles for `values`, plus an optional "N of M match" line.

    `flag` is a (predicate, description) pair, e.g. (lambda v: v < 0.7, "below
    the gate threshold").
    """
    values = sorted(values)
    header(title.format(n=len(values)))
    if not values:
        print("  (none)")
        return
    for label, pct in PERCENTILES:
        print(f"  {label:<8s} {value_fmt.format(percentile(values, pct))}")
    if flag:
        predicate, description = flag
        n = sum(1 for v in values if predicate(v))
        print(f"  {n}/{len(values)} ({fmt_pct(n, len(values))}) {description}")


def print_extract_errors(rows, top_n) -> None:
    errors = Counter(r["extract_error"] for r in rows if r["extract_error"].strip())
    header(f"extract_error frequency ({sum(errors.values())} error rows total)")
    if not errors:
        print("  (no extract errors recorded)")
        return
    for message, count in errors.most_common(top_n):
        print(f"  {count:>4d}x  {message}")


def print_hand_inspect_candidates(rows, n) -> None:
    """Rows with substantial raw_content but no contact signal at all.

    The funnel can't say *why* (obfuscated email, mailto-only, genuinely no
    contact info); only reading a sample can.
    """
    candidates = [
        r for r in rows
        if r["raw_content_status"] == "attempt_succeeded"
        and int(r["raw_content_length"] or 0) >= HAND_INSPECT_MIN_LENGTH
        and not r["emails_found"].strip()
        and not r["discord_links_found"].strip()
    ]
    header(f"Hand-inspect candidates: substantial raw_content, zero contact signal "
           f"({len(candidates)} total, showing up to {n})")
    if not candidates:
        print("  (none found)")
        return
    for r in candidates[:n]:
        preview = r["result_raw_content"][:200].replace("\n", " ")
        print(f"  {r['college_name']} | {r['result_url']} | {r['raw_content_length']} chars")
        print(f"    {preview}...")


def load_colleges(path: str, sample: int | None, seed: int) -> dict:
    """Group rows by college, optionally down to a seeded random subset."""
    with open(path, newline="", encoding="utf-8") as f:
        colleges = defaultdict(list)
        for row in csv.DictReader(f):
            colleges[row["unitid"]].append(row)

    if sample is None or sample >= len(colleges):
        if sample is not None:
            print(f"Note: --sample {sample} requested but only {len(colleges)} "
                  f"colleges are present in the CSV -- using all of them.\n")
        return dict(colleges)

    random.seed(seed)
    keep = set(random.sample(list(colleges), sample))
    return {uid: rows for uid, rows in colleges.items() if uid in keep}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", nargs="?", default=DEFAULT_RESULTS_CSV)
    parser.add_argument("--sample", type=int, default=None,
                        help="Randomly use this many colleges instead of all of them")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for --sample")
    parser.add_argument("--top-errors", type=int, default=10)
    parser.add_argument("--inspect", type=int, default=10,
                        help="How many hand-inspect candidate rows to print")
    args = parser.parse_args()

    colleges = load_colleges(args.input_csv, args.sample, args.seed)
    rows = [r for college_rows in colleges.values() for r in college_rows]

    print_funnel(colleges)
    print_distribution(
        "result_score distribution across {n} real result rows",
        [float(r["result_score"]) for r in rows
         if is_real_result_row(r) and r["result_score"]],
        flag=(lambda s: s < TAVILY_RELEVANCE_THRESHOLD,
              f"score below the current {TAVILY_RELEVANCE_THRESHOLD} gate threshold"),
    )
    print_distribution(
        "raw_content_length distribution across {n} successful extractions",
        [int(r["raw_content_length"]) for r in rows
         if r["raw_content_status"] == "attempt_succeeded" and r["raw_content_length"]],
        value_fmt="{:.0f} chars",
        flag=(lambda l: l < HAND_INSPECT_MIN_LENGTH,
              f"are under {HAND_INSPECT_MIN_LENGTH} chars -- likely near-empty/JS-shell"),
    )
    print_extract_errors(rows, args.top_errors)
    print_hand_inspect_candidates(rows, args.inspect)


if __name__ == "__main__":
    main()