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

import csv
from collections import Counter
from collections.abc import Callable

import gemini_client_util
from config import (
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
        if quote.lower() not in triage_input[source].lower():
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


def label_with_retry(
    triage_input: dict, label_result: Callable[[dict], dict]
) -> tuple[dict, str]:
    """(checked labels, triage_status). Labels are blank when status isn't.

    An exception from the client is final: it retries 429 and 5xx itself. An
    invalid response is retried until TRIAGE_MAX_ATTEMPTS.
    """
    blank = dict.fromkeys(TRIAGE_LABEL_FIELDNAMES, "")
    for _ in range(TRIAGE_MAX_ATTEMPTS):
        try:
            response = label_result(triage_input)
        except Exception:
            return blank, TRIAGE_STATUS_API_ERROR
        try:
            return check_evidence(validate_response(response), triage_input), ""
        except InvalidResponse:
            continue
    return blank, TRIAGE_STATUS_INVALID_OUTPUT


def triage_row(
    row: dict,
    label_result: Callable[[dict], dict] = gemini_client_util.label_result,
    model: str = TRIAGE_MODEL,
    prompt_version: str = TRIAGE_PROMPT_VERSION,
) -> dict:
    """The Stage 2b columns for one Stage 2a row: `decision` and
    TRIAGE_NEW_FIELDNAMES.

    A row that isn't a candidate keeps its decision and gets every new column
    blank, model and prompt version included, since nothing labeled it.
    """
    updates = dict.fromkeys(TRIAGE_NEW_FIELDNAMES, "")
    if not is_triage_candidate(row):
        return {**updates, "decision": row["decision"]}

    labels, status = label_with_retry(build_triage_input(row), label_result)
    reason = None if status else drop_reason(labels)
    return {
        **updates,
        **labels,
        "decision": discard_decision(reason) if reason else row["decision"],
        "triage_status": status,
        "triage_model": model,
        "triage_prompt_version": prompt_version,
    }


# --- The CSV step ------------------------------------------------------------------


def run_llm_triage(
    input_csv: str = DEFAULT_FILTERED_CSV,
    output_csv: str = DEFAULT_LLM_FILTERED_CSV,
    label_result: Callable[[dict], dict] = gemini_client_util.label_result,
) -> None:
    """Read Stage 2a's CSV, triage the kept rows, and write every row out."""
    decision_counts = Counter()
    status_counts = Counter()

    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        require_columns(input_csv, reader.fieldnames, FILTERED_FIELDNAMES)

        with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(
                f_out, fieldnames=LLM_FILTERED_FIELDNAMES, extrasaction="ignore"
            )
            writer.writeheader()

            for row in reader:
                result = triage_row(row, label_result)
                writer.writerow({**row, **result})
                decision_counts[result["decision"]] += 1
                if result["triage_status"]:
                    status_counts[result["triage_status"]] += 1

    print("LLM triage rows by decision:")
    print(f"  {KEEP}: {decision_counts[KEEP]}")
    for reason in TRIAGE_DISCARD_REASONS:
        print(f"  {reason}: {decision_counts[discard_decision(reason)]}")
    for status in (TRIAGE_STATUS_API_ERROR, TRIAGE_STATUS_INVALID_OUTPUT):
        print(f"  triage failed, kept ({status}): {status_counts[status]}")


if __name__ == "__main__":
    args = build_parser(
        "Stage 2b: LLM triage of the rows Stage 2a kept.",
        DEFAULT_FILTERED_CSV,
        DEFAULT_LLM_FILTERED_CSV,
    ).parse_args()
    run_llm_triage(args.input_csv, args.output_csv)
