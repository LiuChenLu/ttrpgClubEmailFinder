import csv
import json
from pathlib import Path

import pytest

import gemini_client_util
import llm_triage
import schema

SPEC_SCHEMA = Path(__file__).parent.parent / "specs/stage2b_llm_triage/schema.json"


def make_row(**overrides):
    row = {
        "decision": "keep",
        "unitid": "1",
        "college_name": "Example College",
        "aliases": "Example U|EC",
        "generated_aliases": "Example",
        "city": "Town",
        "website": "https://example.edu",
        "search_query": "Example College gaming club",
        "result_title": "Tabletop Club | Example College",
        "result_url": "https://example.edu/clubs/tabletop",
        "result_snippet": "Join the group",
        "raw_content_status": "succeeded",
        "raw_content_length": "0",
        "result_raw_content": "",
        "club_keywords_found_in_snippet": "club",
        "ttrpg_keywords_found_in_snippet": "tabletop",
    }
    row.update(overrides)
    return row


def make_labels(**overrides):
    labels = {
        "title_evidence_for_page_type": "Tabletop Club",
        "url_evidence_for_page_type": "tabletop",
        "page_type": "tabletop_club",
        "page_type_certainty": "clear",
        "title_evidence_for_institution": "Example College",
        "url_evidence_for_institution": "example.edu",
        "institution": "supported",
        "institution_certainty": "clear",
    }
    labels.update(overrides)
    return labels


def fixed_labels(**overrides):
    """A label_result that returns the same labels for every row."""
    return lambda triage_input: make_labels(**overrides)


# --- schema and domain check --------------------------------------------------------


def test_schema_py_matches_the_spec_schema_json_in_field_order_and_enums():
    spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))

    assert list(spec_schema["properties"]) == schema.TRIAGE_LABEL_FIELDNAMES
    for name, allowed in schema.TRIAGE_ENUM_VALUES.items():
        assert list(allowed) == spec_schema["properties"][name]["enum"]


@pytest.mark.parametrize(
    "url, website",
    [
        ("https://example.edu/clubs", "https://example.edu"),
        ("example.edu", "https://example.edu"),
        ("https://www.example.edu/clubs", "example.edu"),
        ("https://EXAMPLE.edu./Clubs?x=1", "www.example.edu/"),
        ("https://example.edu:8443/clubs", "https://www.example.edu"),
        ("https://clubs.example.edu/tabletop", "https://www.example.edu/home"),
        ("https://example.edu/clubs", "https://sub.example.edu"),
        ("https://hartford.uconn.edu/", "https://www.uconn.edu"),
        ("https://www.qcc.cuny.edu/clubs", "https://www.bcc.cuny.edu/"),
    ],
)
def test_is_on_domain_true_for_the_websites_domain_or_a_subdomain(url, website):
    assert llm_triage.is_on_domain(url, website) is True


@pytest.mark.parametrize(
    "url, website",
    [
        ("https://notexample.edu/clubs", "https://example.edu"),
        ("https://example.edu.evil.com/", "https://example.edu"),
        ("https://other.edu/example.edu", "https://example.edu"),
        ("https://other.edu/?u=example.edu", "https://example.edu"),
        ("https://example.com/clubs", "https://example.edu"),
        ("https://192.168.0.1/clubs", "https://example.edu"),
        ("https://example.edu/clubs", "https://192.168.0.1"),
        ("", "https://example.edu"),
        ("https://example.edu/clubs", ""),
        ("https://example.edu/clubs", "not a url"),
        ("https://[bad/", "https://example.edu"),
    ],
)
def test_is_on_domain_false_for_other_hosts_ips_and_invalid_input(url, website):
    assert llm_triage.is_on_domain(url, website) is False


# --- preprocessing -----------------------------------------------------------------


def test_build_triage_input_sends_only_name_aliases_title_url_and_domain_relation():
    triage_input = llm_triage.build_triage_input(make_row())

    assert triage_input == {
        "university": "Example College",
        "aliases": ["Example U", "EC"],
        "url": "https://example.edu/clubs/tabletop",
        "title": "Tabletop Club | Example College",
        "domain_relation": "on_domain",
    }


def test_build_triage_input_handles_a_school_with_no_aliases():
    assert llm_triage.build_triage_input(make_row(aliases=""))["aliases"] == []


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (make_row(), True),
        (make_row(decision="discard_pdf"), False),
        (make_row(decision="discard_wrong_institution"), False),
        (make_row(result_url=""), False),
        (make_row(result_url="ERROR"), False),
        (make_row(search_query="NO_RESULTS: Example"), False),
    ],
)
def test_only_kept_non_sentinel_rows_are_triage_candidates(row, expected):
    assert llm_triage.is_triage_candidate(row) is expected


# --- response checks -----------------------------------------------------------------


def test_validate_response_accepts_a_valid_response():
    assert llm_triage.validate_response(make_labels()) == make_labels()


@pytest.mark.parametrize(
    "response",
    [
        "not a dict",
        {},
        {**make_labels(), "extra": "x"},
        {k: v for k, v in make_labels().items() if k != "institution"},
        make_labels(page_type=None),
        make_labels(page_type="club"),
        make_labels(institution_certainty="certain"),
    ],
)
def test_validate_response_rejects_malformed_responses(response):
    with pytest.raises(llm_triage.InvalidResponse):
        llm_triage.validate_response(response)


def test_check_evidence_keeps_quotes_found_in_the_input_ignoring_case():
    triage_input = llm_triage.build_triage_input(make_row())
    labels = make_labels(title_evidence_for_page_type="tabletop club")

    assert llm_triage.check_evidence(labels, triage_input) == labels


def test_check_evidence_blanks_a_made_up_quote_and_makes_its_certainty_probable():
    triage_input = llm_triage.build_triage_input(make_row())
    labels = make_labels(
        url_evidence_for_page_type="chess-club", page_type_certainty="clear"
    )

    checked = llm_triage.check_evidence(labels, triage_input)

    assert checked["url_evidence_for_page_type"] == ""
    assert checked["page_type_certainty"] == "probable"
    assert checked["institution_certainty"] == "clear"


def test_check_evidence_does_not_accept_a_title_quote_that_is_only_in_the_url():
    triage_input = llm_triage.build_triage_input(make_row())
    labels = make_labels(title_evidence_for_institution="example.edu")

    checked = llm_triage.check_evidence(labels, triage_input)

    assert checked["title_evidence_for_institution"] == ""
    assert checked["institution_certainty"] == "probable"


def test_not_supported_without_passing_evidence_becomes_unknown():
    triage_input = llm_triage.build_triage_input(make_row())
    labels = make_labels(
        institution="not_supported",
        title_evidence_for_institution="Other University",
        url_evidence_for_institution="",
    )

    checked = llm_triage.check_evidence(labels, triage_input)

    assert checked["institution"] == "unknown"


def test_not_supported_with_one_passing_evidence_field_stays_not_supported():
    triage_input = llm_triage.build_triage_input(make_row())
    labels = make_labels(
        institution="not_supported",
        title_evidence_for_institution="Other University",
        url_evidence_for_institution="example.edu",
    )

    checked = llm_triage.check_evidence(labels, triage_input)

    assert checked["institution"] == "not_supported"


# --- post processing -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, None),
        ({"page_type": "other"}, "wrong_page_type"),
        ({"institution": "not_supported"}, "wrong_institution"),
        (
            {"page_type": "other", "institution": "not_supported"},
            "wrong_institution_and_wrong_page_type",
        ),
        ({"page_type": "unknown", "institution": "unknown"}, None),
        ({"page_type": "conglomerate"}, None),
    ],
)
def test_drop_reason(overrides, expected):
    labels = make_labels(**overrides)

    assert llm_triage.drop_reason(labels) == expected
    assert llm_triage.should_drop(labels) is (expected is not None)


def test_every_drop_reason_is_a_listed_triage_discard_reason():
    reasons = {
        llm_triage.drop_reason(make_labels(page_type=p, institution=i))
        for p in ("other", "tabletop_club")
        for i in ("not_supported", "supported")
    } - {None}

    assert reasons == set(schema.TRIAGE_DISCARD_REASONS)


# --- one row ----------------------------------------------------------------------------


def test_triage_row_sends_the_model_only_the_triage_input():
    sent = []

    def label_result(triage_input):
        sent.append(triage_input)
        return make_labels()

    llm_triage.triage_row(make_row(), label_result)

    assert sent == [llm_triage.build_triage_input(make_row())]


def test_triage_row_discards_with_the_reason_in_decision():
    result = llm_triage.triage_row(
        make_row(), fixed_labels(page_type="other"), "m", "v1"
    )

    assert result["decision"] == "discard_wrong_page_type"
    assert result["page_type"] == "other"
    assert (result["triage_model"], result["triage_prompt_version"]) == ("m", "v1")


@pytest.mark.parametrize(
    "row",
    [
        make_row(decision="discard_pdf"),
        make_row(decision="discard_sentinel_row", result_url="ERROR"),
    ],
)
def test_triage_row_does_not_call_the_model_for_non_candidates(row):
    def label_result(triage_input):
        pytest.fail("a non-candidate must not be sent to the model")

    result = llm_triage.triage_row(row, label_result)

    assert result["decision"] == row["decision"]
    assert {result[f] for f in schema.TRIAGE_NEW_FIELDNAMES} == {""}


def test_api_error_keeps_the_row_with_blank_labels_and_does_not_retry():
    calls = []

    def label_result(triage_input):
        calls.append(triage_input)
        raise TimeoutError("boom")

    result = llm_triage.triage_row(make_row(), label_result)

    assert len(calls) == 1
    assert result["decision"] == "keep"
    assert result["triage_status"] == "api_error"
    assert {result[f] for f in schema.TRIAGE_LABEL_FIELDNAMES} == {""}


def test_invalid_output_is_retried_once_then_kept_with_blank_labels():
    calls = []

    def label_result(triage_input):
        calls.append(triage_input)
        return {"page_type": "other"}

    result = llm_triage.triage_row(make_row(), label_result)

    assert len(calls) == 2
    assert result["decision"] == "keep"
    assert result["triage_status"] == "invalid_output"
    assert {result[f] for f in schema.TRIAGE_LABEL_FIELDNAMES} == {""}


def test_invalid_output_that_is_fixed_by_the_retry_is_labeled():
    responses = iter([{"page_type": "other"}, make_labels(page_type="other")])

    result = llm_triage.triage_row(make_row(), lambda triage_input: next(responses))

    assert result["decision"] == "discard_wrong_page_type"
    assert result["triage_status"] == ""


# --- the CSV step ------------------------------------------------------------------------


def write_filtered_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=schema.FILTERED_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        return reader.fieldnames, list(reader)


def test_run_llm_triage_writes_every_row_with_the_schema_columns_and_counts(
    tmp_path, capsys
):
    input_csv = tmp_path / "filtered.csv"
    output_csv = tmp_path / "llm_filtered.csv"
    rows = [
        make_row(unitid="1"),
        make_row(unitid="2", decision="discard_pdf"),
        make_row(unitid="3", result_title="Chess Club"),
        make_row(unitid="4", result_url="", decision="discard_sentinel_row"),
    ]
    write_filtered_csv(input_csv, rows)

    def label_result(triage_input):
        if triage_input["title"] == "Chess Club":
            return make_labels(page_type="other")
        return make_labels()

    llm_triage.run_llm_triage(str(input_csv), str(output_csv), label_result)

    fieldnames, result_rows = read_csv(output_csv)
    assert fieldnames == schema.LLM_FILTERED_FIELDNAMES
    assert [r["unitid"] for r in result_rows] == ["1", "2", "3", "4"]
    assert [r["decision"] for r in result_rows] == [
        "keep",
        "discard_pdf",
        "discard_wrong_page_type",
        "discard_sentinel_row",
    ]
    assert result_rows[1]["page_type"] == ""
    assert result_rows[0]["page_type"] == "tabletop_club"
    assert result_rows[0]["result_raw_content"] == rows[0]["result_raw_content"]

    output = capsys.readouterr().out
    assert "keep: 1" in output
    assert "wrong_page_type: 1" in output
    assert "wrong_institution: 0" in output


def test_run_llm_triage_rejects_missing_columns_without_truncating_output(tmp_path):
    input_csv = tmp_path / "incomplete.csv"
    output_csv = tmp_path / "existing.csv"
    input_csv.write_text("unitid,college_name\n1,Example College\n", encoding="utf-8")
    output_csv.write_text("previous output\n", encoding="utf-8")

    with pytest.raises(ValueError, match="is missing columns"):
        llm_triage.run_llm_triage(str(input_csv), str(output_csv))

    assert output_csv.read_text(encoding="utf-8") == "previous output\n"
