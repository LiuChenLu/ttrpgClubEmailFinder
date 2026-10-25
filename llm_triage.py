"""Stage 2b: LLM triage of the results Stage 2a kept.

All the pre and post processing is here and is deterministic. The one
non-deterministic step, the LLM call, is `gemini_client_util.label_result`,
passed in as an argument so tests (and a future swap of model) never touch this
logic. Spec: specs/stage2b_llm_triage/spec.md.

Fails open: a row whose call fails is kept with blank labels and a
`triage_status`, because a false drop loses a club page for good.

Importing this module reads no files and needs no network access or API key.
run_llm_triage() reads Stage 2a's CSV and writes the Stage 2b CSV.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone

import gemini_client_util
import triage_store
from config import (
    DATABASE_PATH,
    DEFAULT_FILTERED_CSV,
    DEFAULT_LLM_FILTERED_CSV,
    TRIAGE_MAX_ATTEMPTS,
    TRIAGE_MODEL,
    TRIAGE_PROMPT_VERSION,
)
from schema import (
    CERTAINTY_PROBABLE,
    FILTERED_FIELDNAMES,
    INSTITUTION_NOT_SUPPORTED,
    INSTITUTION_UNKNOWN,
    KEEP,
    LLM_FILTERED_FIELDNAMES,
    PAGE_TYPE_OTHER,
    REASON_WRONG_INSTITUTION,
    REASON_WRONG_INSTITUTION_AND_PAGE_TYPE,
    REASON_WRONG_PAGE_TYPE,
    TRIAGE_DISCARD_REASONS,
    TRIAGE_ENUM_VALUES,
    TRIAGE_LABEL_FIELDNAMES,
    TRIAGE_NEW_FIELDNAMES,
    TRIAGE_STATUS_API_ERROR,
    TRIAGE_STATUS_CACHE_MISS,
    TRIAGE_STATUS_INVALID_OUTPUT,
    discard_decision,
    is_keep,
    require_columns,
)
from search_row_format_util import is_sentinel
from stage_cli import build_parser
from url_parsing_utils import extract_host, registrable_domain

ON_DOMAIN = "on_domain"
NOT_ON_DOMAIN = "not_on_domain"
_EVIDENCE_CHARACTERS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\uff06": "&",
        "\ufe60": "&",
    }
)


def _normalize_evidence_text(text: str) -> str:
    return text.replace("%26", "&").translate(_EVIDENCE_CHARACTERS).lower()


# (evidence field, the text it must quote, the certainty a failed quote lowers)
EVIDENCE_CHECKS = (
    ("title_evidence_for_page_type", "title", "page_type_certainty"),
    ("url_evidence_for_page_type", "url", "page_type_certainty"),
    ("title_evidence_for_institution", "title", "institution_certainty"),
    ("url_evidence_for_institution", "url", "institution_certainty"),
)
INSTITUTION_EVIDENCE_FIELDS = (
    "title_evidence_for_institution",
    "url_evidence_for_institution",
)


class InvalidResponse(ValueError):
    """The model's response doesn't match the response schema."""


# --- Preprocessing -------------------------------------------------------------


def is_on_domain(url: str, website: str) -> bool:
    """Whether `url`'s host is `website`'s registrable domain or a subdomain of it.

    Scheme, "www.", port, case, trailing dots, path and query don't matter.
    Invalid input and IP addresses are False, the weaker signal
    (label_rules.md says most true club pages are off the school's domain).
    Schools in one system (e.g. CUNY) share a domain, so they match each other.
    """
    domain = registrable_domain(website)
    host = extract_host(url)
    if domain is None or host is None:
        return False
    return host == domain or host.endswith("." + domain)


def is_triage_candidate(row: dict) -> bool:
    """Only rows Stage 2a kept go to the model; sentinels never do."""
    return is_keep(row) and not is_sentinel(row)


def build_triage_input(row: dict) -> dict:
    """The only fields of a row the model sees.

    Official aliases only: `generated_aliases`, the snippet and the page text
    are not sent.
    """
    url = row["result_url"]
    return {
        "university": row["college_name"],
        "aliases": [a.strip() for a in row["aliases"].split("|") if a.strip()],
        "url": url,
        "title": row["result_title"],
        "domain_relation": (
            ON_DOMAIN if is_on_domain(url, row["website"]) else NOT_ON_DOMAIN
        ),
    }


# --- Checks on the model's response ---------------------------------------------


def validate_response(response: object) -> dict:
    """Raise InvalidResponse unless every schema field is present, a string,
    and (for the enum fields) an allowed value.
    """
    if not isinstance(response, dict):
        raise InvalidResponse(f"expected an object, got {type(response).__name__}")
    if set(response) != set(TRIAGE_LABEL_FIELDNAMES):
        raise InvalidResponse(f"fields {sorted(response)} do not match the schema")
    for name in TRIAGE_LABEL_FIELDNAMES:
        if not isinstance(response[name], str):
            raise InvalidResponse(f"{name} is not a string")
    for name, allowed in TRIAGE_ENUM_VALUES.items():
        value = response[name]
        if value not in allowed:
            raise InvalidResponse(f"{name}={value!r} is not one of {allowed}")
    return dict(response)


def check_evidence(labels: dict, triage_input: dict) -> dict:
    """Repair evidence the model didn't actually quote. Returns a new dict.

    1. A non-empty evidence field that isn't a substring (ignoring case) of the
       title or URL as sent is blanked, and its certainty becomes `probable`.
    2. `not_supported` needs evidence that passed check 1, otherwise
       `institution` becomes `unknown`: never drop on missing evidence.
    """
    checked = dict(labels)
    for field, source, certainty_field in EVIDENCE_CHECKS:
        quote = checked[field]
        if not quote:
            continue
        if _normalize_evidence_text(quote) not in _normalize_evidence_text(
            triage_input[source]
        ):
            checked[field] = ""
            checked[certainty_field] = CERTAINTY_PROBABLE

    has_evidence = any(checked[f] for f in INSTITUTION_EVIDENCE_FIELDS)
    if checked["institution"] == INSTITUTION_NOT_SUPPORTED and not has_evidence:
        checked["institution"] = INSTITUTION_UNKNOWN
    return checked


# --- Post processing -------------------------------------------------------------


def drop_reason(labels: dict) -> str | None:
    """The Stage 2b reason to drop a row, or None to keep it.

    Only `not_supported` and `other` drop; `unknown` keeps. Tune this on the
    *_certainty and *_evidence_* fields.
    """
    wrong_institution = labels["institution"] == INSTITUTION_NOT_SUPPORTED
    wrong_page_type = labels["page_type"] == PAGE_TYPE_OTHER
    if wrong_institution and wrong_page_type:
        return REASON_WRONG_INSTITUTION_AND_PAGE_TYPE
    if wrong_institution:
        return REASON_WRONG_INSTITUTION
    if wrong_page_type:
        return REASON_WRONG_PAGE_TYPE
    return None


def should_drop(labels: dict) -> bool:
    return drop_reason(labels) is not None


# --- One row -----------------------------------------------------------------------


def uncached_label_result(triage_input: dict, attempt: int) -> dict:
    """A `label_result` that always calls the model and saves nothing."""
    return gemini_client_util.label_result(triage_input)


def cached_label_result(
    conn,
    send_request: Callable[[dict], object] | None = None,
    cache_only: bool = False,
    stats: Counter | None = None,
) -> Callable[[dict, int], dict]:
    """A `label_result` that reads the saved reply for (input, attempt) first.

    On a miss it calls `send_request` and saves the reply before returning it.
    An exception from `send_request` propagates and saves nothing, so a failed
    call is never replayed. An invalid reply is saved like any other: a later
    run replays the same bad answer, then the same retry, at no cost. With
    `cache_only` a miss raises `triage_store.CacheMiss` and the model is never
    called. `stats` counts "saved" and "called". `send_request` defaults to
    `gemini_client_util.send_request`; tests pass a fake.
    """
    stats = stats if stats is not None else Counter()
    send_request = send_request or gemini_client_util.send_request

    def label_result(triage_input: dict, attempt: int) -> dict:
        request = gemini_client_util.build_request(triage_input)
        saved = triage_store.get_response(conn, request, attempt)
        if saved is not None:
            stats["saved"] += 1
            return gemini_client_util.parse_reply(saved["raw_response"])
        if cache_only:
            raise triage_store.CacheMiss(f"no saved reply for attempt {attempt}")
        details = gemini_client_util.response_details(send_request(request))
        triage_store.put_response(conn, request, attempt, details)
        stats["called"] += 1
        total_tokens = details["total_token_count"]
        if total_tokens is None:
            stats["total_token_count_missing"] += 1
        else:
            stats["total_token_count"] += total_tokens
        stats["cached_content_token_count"] += (
            details["cached_content_token_count"] or 0
        )
        return gemini_client_util.parse_reply(details["raw_response"])

    return label_result


def label_with_retry(
    triage_input: dict, label_result: Callable[[dict, int], dict]
) -> tuple[dict, str, int | None]:
    """(checked labels, triage_status, attempt). Labels are blank when status
    isn't, and `attempt` is the try whose reply gave the labels (None if none).

    `label_result(triage_input, attempt)` gets the attempt number (1-based) so a
    saved reply can be found for each try. An exception from the client is
    final: it retries 429 and 5xx itself. An invalid response is retried until
    TRIAGE_MAX_ATTEMPTS. A `CacheMiss` is its own status, not an API error.
    """
    blank = dict.fromkeys(TRIAGE_LABEL_FIELDNAMES, "")
    for attempt in range(1, TRIAGE_MAX_ATTEMPTS + 1):
        try:
            response = label_result(triage_input, attempt)
        except triage_store.CacheMiss:
            return blank, TRIAGE_STATUS_CACHE_MISS, None
        except Exception:
            return blank, TRIAGE_STATUS_API_ERROR, None
        try:
            labels = check_evidence(validate_response(response), triage_input)
            return labels, "", attempt
        except InvalidResponse:
            continue
    return blank, TRIAGE_STATUS_INVALID_OUTPUT, None


def triage_row(
    row: dict,
    label_result: Callable[[dict, int], dict] = uncached_label_result,
    model: str = TRIAGE_MODEL,
    prompt_version: str = TRIAGE_PROMPT_VERSION,
) -> dict:
    """The Stage 2b columns for one Stage 2a row: `decision` and
    TRIAGE_NEW_FIELDNAMES, plus `attempt`, the try whose reply gave the labels
    (None if there are no labels). `attempt` is not a CSV column.

    A row that isn't a candidate keeps its decision and gets every new column
    blank, model and prompt version included, since nothing labeled it.
    """
    updates = dict.fromkeys(TRIAGE_NEW_FIELDNAMES, "")
    if not is_triage_candidate(row):
        return {**updates, "decision": row["decision"], "attempt": None}

    labels, status, attempt = label_with_retry(build_triage_input(row), label_result)
    reason = None if status else drop_reason(labels)
    return {
        **updates,
        **labels,
        "decision": discard_decision(reason) if reason else row["decision"],
        "triage_status": status,
        "triage_model": model,
        "triage_prompt_version": prompt_version,
        "attempt": attempt,
    }


def result_row(row: dict, result: dict) -> dict:
    """The `llm_triage_result` values for one Stage 2a row and its `triage_row`.

    Rows that weren't sent to the model have a NULL `input_hash`. A row with no
    labels (not sent, or failed) has NULL labels, so it can't be mistaken for a
    labeled row whose evidence quotes are legitimately empty. Blank status,
    model and prompt version are NULL too.
    """
    sent = is_triage_candidate(row)
    labeled = result["page_type"] != ""
    values = {
        "unitid": row["unitid"],
        "result_url": row["result_url"],
        "stage2a_decision": row["decision"],
        "decision": result["decision"],
        "input_hash": None,
        "attempt": result["attempt"],
    }
    if sent:
        request = gemini_client_util.build_request(build_triage_input(row))
        values["input_hash"] = triage_store.input_hash(request)
    for name in TRIAGE_LABEL_FIELDNAMES:
        values[name] = result[name] if labeled else None
    for name in ("triage_status", "triage_model", "triage_prompt_version"):
        values[name] = result[name] or None
    return values


# --- The CSV step ------------------------------------------------------------------


def git_state(cwd: str | None = None) -> tuple[str | None, bool | None]:
    """(HEAD commit, whether the working tree has uncommitted changes), so a run
    records which code made it. (None, None) when this isn't a git checkout or
    git isn't installed. Untracked files count as changes: a new file can change
    the labels too.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd, capture_output=True, text=True, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return head, bool(status.strip())


def run_llm_triage(
    input_csv: str = DEFAULT_FILTERED_CSV,
    output_csv: str = DEFAULT_LLM_FILTERED_CSV,
    label_result: Callable[[dict, int], dict] | None = None,
    database_path: str = DATABASE_PATH,
    cache_only: bool = False,
    send_request: Callable[[dict], object] | None = None,
    note: str | None = None,
    get_git_state: Callable[[], tuple[str | None, bool | None]] = git_state,
) -> int | None:
    """Read Stage 2a's CSV, triage the kept rows, and write every row out.

    By default every reply goes through the database at `database_path`: a
    saved reply is reused and Gemini is called only for a miss. `cache_only`
    never calls Gemini; a miss keeps the row with `triage_status=cache_miss`.
    `send_request` replaces the Gemini call but keeps the database (for tests).
    A `label_result` replaces all of that: the database isn't opened and
    `cache_only` is ignored.

    With the database, the run and one `llm_triage_result` row per input row
    are saved together at the end, under a new `run_id` that is returned (None
    without the database). Earlier runs are never changed, so runs with another
    model, prompt or label rules can be compared with compare_triage_runs.py.
    A run that crashes saves no run, but its model replies are already saved, so
    running again costs nothing for them. `note` is free text stored with the run.
    """
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decision_counts = Counter()
    status_counts = Counter()
    reply_counts = Counter()
    results = []
    run_id = None

    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        require_columns(input_csv, reader.fieldnames, FILTERED_FIELDNAMES)

        # Opened only after the column check, so a bad input creates no file.
        conn = None
        if label_result is None:
            conn = triage_store.connect(database_path)
            label_result = cached_label_result(
                conn, send_request, cache_only=cache_only, stats=reply_counts
            )
        try:
            with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
                writer = csv.DictWriter(
                    f_out, fieldnames=LLM_FILTERED_FIELDNAMES, extrasaction="ignore"
                )
                writer.writeheader()

                for row in reader:
                    result = triage_row(row, label_result)
                    writer.writerow({**row, **result})
                    if conn is not None:
                        results.append(result_row(row, result))
                    decision_counts[result["decision"]] += 1
                    if result["triage_status"]:
                        status_counts[result["triage_status"]] += 1
            if conn is not None:
                commit, dirty = get_git_state()
                run_id = triage_store.save_run(
                    conn,
                    # Model, prompt and settings don't depend on the row, so any
                    # request describes the run, even when no row was sent.
                    gemini_client_util.build_request({}),
                    results,
                    started_at=started_at,
                    prompt_version=TRIAGE_PROMPT_VERSION,
                    input_csv=input_csv,
                    cache_only=cache_only,
                    git_commit=commit,
                    git_dirty=dirty,
                    note=note,
                )
        finally:
            if conn is not None:
                conn.close()

    print("LLM triage rows by decision:")
    print(f"  {KEEP}: {decision_counts[KEEP]}")
    for reason in TRIAGE_DISCARD_REASONS:
        print(f"  {reason}: {decision_counts[discard_decision(reason)]}")
    for status in (
        TRIAGE_STATUS_API_ERROR,
        TRIAGE_STATUS_INVALID_OUTPUT,
        TRIAGE_STATUS_CACHE_MISS,
    ):
        print(f"  triage failed, kept ({status}): {status_counts[status]}")
    if conn is not None:
        print(
            f"  model replies: {reply_counts['saved']} saved, "
            f"{reply_counts['called']} new calls"
        )
        total_tokens = reply_counts["total_token_count"]
        if reply_counts["total_token_count_missing"]:
            total_usage = (
                f"{total_tokens} total "
                f"({reply_counts['total_token_count_missing']} response(s) "
                "missing total token usage)"
            )
        else:
            total_usage = f"{total_tokens} total"
        print(
            f"  token usage (new calls): {total_usage}, "
            f"{reply_counts['cached_content_token_count']} cached-content"
        )
        print(f"  saved as run {run_id} (compare runs: compare_triage_runs.py)")
    return run_id


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """The Stage 2b options shared by this script and filter_candidates.py."""
    parser.add_argument(
        "--cache-only", action="store_true",
        help="use saved model replies only; never call Gemini",
    )
    parser.add_argument(
        "--note", default=None,
        help="free text saved with the run, e.g. what you changed",
    )


if __name__ == "__main__":
    parser = build_parser(
        "Stage 2b: LLM triage of the rows Stage 2a kept.",
        DEFAULT_FILTERED_CSV,
        DEFAULT_LLM_FILTERED_CSV,
    )
    add_run_arguments(parser)
    args = parser.parse_args()
    run_llm_triage(
        args.input_csv, args.output_csv, cache_only=args.cache_only, note=args.note
    )
