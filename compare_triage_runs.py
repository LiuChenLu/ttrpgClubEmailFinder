"""Compare two Stage 2b runs: which rows got a different label or decision.

Every `llm_triage.py` (or `filter_candidates.py`) run is saved in the database
as a numbered run, with the model, prompt, settings, git commit and your `--note`.
Change one thing (the model, the prompt, or the label rules in `llm_triage.py`),
run Stage 2b again, then compare the two runs here. This script only reads the
database. It never calls Gemini, never writes, and never creates a missing file.

Usage (from the repository root, with .venv active):

    python compare_triage_runs.py --list
        Show every run: id, when, model, prompt version, git commit, row count and
        note. Start here to find the ids.

    python compare_triage_runs.py --a 1 --b 2
        Compare run 1 (the baseline) with run 2 (the new one). Prints both runs'
        settings, how many rows are identical, changed, or in only one run, a
        count of each decision change (for example keep -> discard_wrong_page_type),
        then the changed rows with the fields that differ.

    python compare_triage_runs.py --a 1 --b 2 --fields decision
        Only look at changes to the final decision. --fields takes a comma
        separated list from: decision, page_type, page_type_certainty,
        institution, institution_certainty, triage_status (the default is all).

    python compare_triage_runs.py --a 1 --b 2 --limit 0
        Print every changed row. The default prints the first 20 (a first look
        shouldn't scroll off the screen); 0 means no limit.

    python compare_triage_runs.py --a 1 --b 2 --database path/to/other.sqlite
        Read a different database file (default: config.DATABASE_PATH).

A row is matched between runs by (`unitid`, `result_url`). "Changed" means one of
the compared fields differs, where no value (NULL) and a value are different. Quote
fields (`*_evidence_*`) are not compared: a reworded quote is rarely worth reading.
A row can differ only in `triage_status` (for example `cache_miss` in a
`--cache-only` run), which is shown as a change like any other.

How to get a cheap comparison:
    - A new label rule (`drop_reason`, `check_evidence`): edit the code, then
      `python llm_triage.py --cache-only --note "what I changed"`. It reuses every
      saved model reply, so it costs nothing, and the git commit and the
      uncommitted-changes flag on the run say which code made it.
    - A new model or prompt: run Stage 2b normally. Rows whose model input has no
      saved reply call Gemini once, and those replies are saved for later runs.

Exit status: 0 on success (whether or not the runs differ), 1 on an error such as
an unknown run id or a missing database, so a script can tell the two apart.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from config import DATABASE_PATH
from schema import TRIAGE_COMPARE_FIELDNAMES

DEFAULT_LIMIT = 20


class RunNotFound(LookupError):
    """No run in the database has this id."""


@dataclass
class Comparison:
    run_a: dict
    run_b: dict
    in_both: int = 0
    identical: int = 0
    # Each is (unitid, result_url, {field: (value in a, value in b)}).
    changed: list = field(default_factory=list)
    only_in_a: list = field(default_factory=list)
    only_in_b: list = field(default_factory=list)
    decision_moves: Counter = field(default_factory=Counter)


def open_readonly(path: str) -> sqlite3.Connection:
    """Open an existing database without any chance of changing or creating it."""
    database = Path(path)
    if not database.is_file():
        raise FileNotFoundError(f"no database at {path}")
    return sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    cursor = conn.execute(sql, params)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def list_runs(conn: sqlite3.Connection) -> list[dict]:
    """Every run, oldest first, with its number of result rows."""
    return _rows(
        conn,
        "SELECT r.*, (SELECT COUNT(*) FROM llm_triage_result x"
        " WHERE x.run_id = r.run_id) AS result_rows"
        " FROM llm_triage_run r ORDER BY r.run_id",
    )


def get_run(conn: sqlite3.Connection, run_id: int) -> dict:
    runs = _rows(conn, "SELECT * FROM llm_triage_run WHERE run_id = ?", (run_id,))
    if not runs:
        raise RunNotFound(f"no run {run_id}; --list shows the runs")
    return runs[0]


def _load_results(conn: sqlite3.Connection, run_id: int) -> dict:
    results = _rows(
        conn, "SELECT * FROM llm_triage_result WHERE run_id = ?", (run_id,)
    )
    return {(r["unitid"], r["result_url"]): r for r in results}


def compare_runs(
    conn: sqlite3.Connection,
    a: int,
    b: int,
    fields: list[str] | None = None,
) -> Comparison:
    """Match the two runs' rows on (unitid, result_url) and find what changed."""
    fields = list(fields or TRIAGE_COMPARE_FIELDNAMES)
    unknown = [f for f in fields if f not in TRIAGE_COMPARE_FIELDNAMES]
    if unknown:
        raise ValueError(
            f"can't compare {unknown}; choose from {TRIAGE_COMPARE_FIELDNAMES}"
        )
    comparison = Comparison(run_a=get_run(conn, a), run_b=get_run(conn, b))
    rows_a, rows_b = _load_results(conn, a), _load_results(conn, b)

    for key in sorted(rows_a.keys() | rows_b.keys()):
        row_a, row_b = rows_a.get(key), rows_b.get(key)
        if row_b is None:
            comparison.only_in_a.append(key)
        elif row_a is None:
            comparison.only_in_b.append(key)
        else:
            comparison.in_both += 1
            differences = {
                f: (row_a[f], row_b[f]) for f in fields if row_a[f] != row_b[f]
            }
            if not differences:
                comparison.identical += 1
                continue
            comparison.changed.append((*key, differences))
            if "decision" in differences:
                comparison.decision_moves[differences["decision"]] += 1
    return comparison


def _show(value: object) -> str:
    if value is None:
        return "NULL"
    return repr(value) if value == "" else str(value)


def _run_line(run: dict) -> str:
    commit = (run["git_commit"] or "unknown")[:10]
    if run["git_dirty"]:
        commit += " + uncommitted changes"
    mode = ", cache-only" if run["cache_only"] else ""
    note = f' note: "{run["note"]}"' if run["note"] else ""
    return (
        f"run {run['run_id']}  {run['model']}  prompt {run['prompt_version']}  "
        f"thinking {run['thinking_level']}  commit {commit}{mode}{note}"
    )


def format_runs(runs: list[dict]) -> str:
    if not runs:
        return "no runs yet (run llm_triage.py first)"
    lines = ["Runs:"]
    for run in runs:
        lines.append(f"  {_run_line(run)}")
        lines.append(
            f"      {run['started_at']}  {run['result_rows']} rows  "
            f"input {run['input_csv']}"
        )
    return "\n".join(lines)


def format_report(comparison: Comparison, limit: int = DEFAULT_LIMIT) -> str:
    """The text `main` prints. `limit` caps the changed rows listed (0 = all)."""
    c = comparison
    lines = ["Comparing", f"  a: {_run_line(c.run_a)}", f"  b: {_run_line(c.run_b)}"]
    if c.run_a["prompt_hash"] != c.run_b["prompt_hash"]:
        lines.append("  (the prompt or reply schema differs between the runs)")
    lines += [
        "",
        f"Rows in both runs: {c.in_both}",
        f"  identical: {c.identical}",
        f"  changed:   {len(c.changed)}",
        f"Only in a: {len(c.only_in_a)}",
        f"Only in b: {len(c.only_in_b)}",
    ]
    if c.decision_moves:
        lines += ["", "Decision changes (a -> b):"]
        for (old, new), count in c.decision_moves.most_common():
            lines.append(f"  {count:5}  {_show(old)} -> {_show(new)}")

    if c.changed:
        shown = c.changed if limit == 0 else c.changed[:limit]
        lines += ["", f"Changed rows ({len(shown)} of {len(c.changed)}):"]
        for unitid, url, differences in shown:
            lines.append(f"  unitid {unitid}  {url}")
            for name, (old, new) in differences.items():
                lines.append(f"      {name}: {_show(old)} -> {_show(new)}")
        if len(shown) < len(c.changed):
            lines.append(f"  ... {len(c.changed) - len(shown)} more (use --limit 0)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two Stage 2b runs. Run with --list to see run ids.",
        epilog="Full usage and examples: see the top of compare_triage_runs.py.",
    )
    parser.add_argument("--list", action="store_true", help="list the runs and exit")
    parser.add_argument("--a", type=int, help="run id of the baseline")
    parser.add_argument("--b", type=int, help="run id to compare against it")
    parser.add_argument(
        "--fields", default=None,
        help="comma separated fields to compare (default: "
        + ", ".join(TRIAGE_COMPARE_FIELDNAMES) + ")",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"changed rows to print, 0 for all (default {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--database", default=DATABASE_PATH,
        help=f"database file to read (default: {DATABASE_PATH})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.list and (args.a is None or args.b is None):
        parser.error("give --a and --b (or --list to see the run ids)")
    if args.limit < 0:
        parser.error("--limit can't be negative (0 means all)")
    if args.a is not None and args.a == args.b:
        parser.error("--a and --b are the same run")
    fields = [f.strip() for f in args.fields.split(",")] if args.fields else None

    try:
        conn = open_readonly(args.database)
        try:
            if args.list:
                print(format_runs(list_runs(conn)))
            else:
                comparison = compare_runs(conn, args.a, args.b, fields)
                print(format_report(comparison, args.limit))
        finally:
            conn.close()
    except (FileNotFoundError, RunNotFound, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except sqlite3.OperationalError as error:
        # A database from before run tracking has no run tables.
        print(
            f"error: {error}. If the database predates run tracking, run "
            "llm_triage.py once so it is upgraded.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
