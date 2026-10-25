"""Live Stage 2b tests: these call the real Gemini API over the network.

They spend Gemini quota, so they are skipped unless RUN_GEMINI_LIVE_TESTS=1 is
set. An agent must never set it without the user's approval (see AGENTS.md).

    RUN_GEMINI_LIVE_TESTS=1 python -m pytest tests/test_llm_triage_gemini_live_network.py

Model output varies, so these check the shape of the result (a valid, evidence
checked reply) and not one exact label.
"""

import csv
import os

import pytest

import config
import gemini_client_util
import llm_triage
import schema

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_GEMINI_LIVE_TESTS") != "1",
    reason="live Gemini test: set RUN_GEMINI_LIVE_TESTS=1 to run (spends quota)",
)

ROW = {
    "decision": "keep",
    "unitid": "1",
    "college_name": "Champlain College",
    "aliases": "",
    "generated_aliases": "",
    "city": "Burlington",
    "website": "https://www.champlain.edu",
    "search_query": "Champlain College tabletop club",
    "result_title": "Tabletop Games Club | Champlain College, Burlington, VT",
    "result_url": (
        "https://www.champlain.edu/clubs-activities-affinity-groups/"
        "tabletop-games-club"
    ),
    "result_snippet": "",
    "raw_content_status": "succeeded",
    "raw_content_length": "0",
    "result_raw_content": "",
    "club_keywords_found_in_snippet": "",
    "ttrpg_keywords_found_in_snippet": "",
}


def test_label_result_returns_a_reply_that_passes_the_response_checks():
    triage_input = llm_triage.build_triage_input(ROW)

    response = gemini_client_util.label_result(triage_input)

    labels = llm_triage.check_evidence(
        llm_triage.validate_response(response), triage_input
    )
    assert set(labels) == set(schema.TRIAGE_LABEL_FIELDNAMES)


def test_run_llm_triage_labels_a_row_and_records_the_model(tmp_path):
    input_csv = tmp_path / "filtered.csv"
    output_csv = tmp_path / "llm_filtered.csv"
    with input_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=schema.FILTERED_FIELDNAMES)
        writer.writeheader()
        writer.writerow(ROW)

    llm_triage.run_llm_triage(
        str(input_csv),
        str(output_csv),
        database_path=str(tmp_path / "database.sqlite"),
    )

    with output_csv.open(newline="", encoding="utf-8") as f:
        (row,) = list(csv.DictReader(f))
    assert row["triage_status"] == ""
    assert row["triage_model"] == config.TRIAGE_MODEL
    assert row["triage_prompt_version"] == config.TRIAGE_PROMPT_VERSION
    assert row["page_type"] in schema.TRIAGE_ENUM_VALUES["page_type"]
