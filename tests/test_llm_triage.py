import csv
import json
from pathlib import Path

import pytest

import config
import gemini_client_util
import llm_triage
import schema
import triage_store

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
    return lambda triage_input, attempt: make_labels(**overrides)


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


@pytest.mark.parametrize(
    ("title", "evidence"),
    [
        (
            "Club ‘R’ and ’S’ use “T” and ”U”",
            "Club 'R' and 'S' use \"T\" and \"U\"",
        ),
        (
            "Club 'R' and 'S' use \"T\" and \"U\"",
            "Club ‘R’ and ’S’ use “T” and ”U”",
        ),
    ],
)
def test_check_evidence_normalizes_curly_quotes(title, evidence):
    triage_input = llm_triage.build_triage_input(make_row(result_title=title))
    labels = make_labels(
        title_evidence_for_page_type=evidence, title_evidence_for_institution=""
    )

    checked = llm_triage.check_evidence(labels, triage_input)

    assert checked["title_evidence_for_page_type"] == evidence
    assert checked["page_type_certainty"] == "clear"


@pytest.mark.parametrize(
    ("source", "source_text", "evidence"),
    [
        ("title", "Tabletop & Board Game Club", "Tabletop ＆ Board Game Club"),
        ("title", "Tabletop ＆ Board Game Club", "Tabletop & Board Game Club"),
        ("title", "Tabletop ﹠ Board Game Club", "Tabletop & Board Game Club"),
        ("title", "Tabletop & Board Game Club", "Tabletop ﹠ Board Game Club"),
        (
            "url",
            "https://example.edu/clubs/tabletop%26board-game",
            "tabletop&board-game",
        ),
        (
            "url",
            "https://example.edu/clubs/tabletop&board-game",
            "tabletop%26board-game",
        ),
    ],
)
def test_check_evidence_normalizes_ampersands(source, source_text, evidence):
    triage_input = llm_triage.build_triage_input(
        make_row(**{f"result_{source}": source_text})
    )
    evidence_field = f"{source}_evidence_for_page_type"
    labels = make_labels(
        **{evidence_field: evidence, "title_evidence_for_institution": ""}
    )

    checked = llm_triage.check_evidence(labels, triage_input)

    assert checked[evidence_field] == evidence
    assert checked["page_type_certainty"] == "clear"


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

    def label_result(triage_input, attempt):
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
    def label_result(triage_input, attempt):
        pytest.fail("a non-candidate must not be sent to the model")

    result = llm_triage.triage_row(row, label_result)

    assert result["decision"] == row["decision"]
    assert {result[f] for f in schema.TRIAGE_NEW_FIELDNAMES} == {""}


def test_api_error_keeps_the_row_with_blank_labels_and_does_not_retry():
    calls = []

    def label_result(triage_input, attempt):
        calls.append(triage_input)
        raise TimeoutError("boom")

    result = llm_triage.triage_row(make_row(), label_result)

    assert len(calls) == 1
    assert result["decision"] == "keep"
    assert result["triage_status"] == "api_error"
    assert {result[f] for f in schema.TRIAGE_LABEL_FIELDNAMES} == {""}


def test_invalid_output_is_retried_once_then_kept_with_blank_labels():
    calls = []

    def label_result(triage_input, attempt):
        calls.append(triage_input)
        return {"page_type": "other"}

    result = llm_triage.triage_row(make_row(), label_result)

    assert len(calls) == 2
    assert result["decision"] == "keep"
    assert result["triage_status"] == "invalid_output"
    assert {result[f] for f in schema.TRIAGE_LABEL_FIELDNAMES} == {""}


def test_invalid_output_that_is_fixed_by_the_retry_is_labeled():
    responses = iter([{"page_type": "other"}, make_labels(page_type="other")])

    result = llm_triage.triage_row(
        make_row(), lambda triage_input, attempt: next(responses)
    )

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

    def label_result(triage_input, attempt):
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


# --- saved replies: the database path --------------------------------------------------


class FakeResponse:
    def __init__(self, text, **usage):
        self.text = text
        self.usage_metadata = type("Usage", (), usage)()


class FakeModel:
    """A send_request that records its calls and answers from a script."""

    def __init__(self, *texts, cached_content_token_count=0):
        self.texts = list(texts)
        self.requests = []
        self.cached_content_token_count = cached_content_token_count

    def __call__(self, request):
        self.requests.append(request)
        text = self.texts.pop(0) if self.texts else json.dumps(make_labels())
        if isinstance(text, Exception):
            raise text
        return FakeResponse(
            text,
            prompt_token_count=10,
            total_token_count=12,
            cached_content_token_count=self.cached_content_token_count,
        )


def run_triage(tmp_path, rows, send_request, cache_only=False, name="out.csv"):
    input_csv = tmp_path / "filtered.csv"
    output_csv = tmp_path / name
    write_filtered_csv(input_csv, rows)
    llm_triage.run_llm_triage(
        str(input_csv),
        str(output_csv),
        database_path=str(tmp_path / "database.sqlite"),
        cache_only=cache_only,
        send_request=send_request,
    )
    return read_csv(output_csv)[1]


def test_a_second_run_makes_zero_model_calls_and_gives_the_same_output(tmp_path):
    rows = [make_row(unitid="1"), make_row(unitid="2", result_title="Chess Club")]
    first_model = FakeModel()

    first = run_triage(tmp_path, rows, first_model, name="first.csv")
    second_model = FakeModel()
    second = run_triage(tmp_path, rows, second_model, name="second.csv")

    assert len(first_model.requests) == 2
    assert second_model.requests == []
    assert second == first


def test_two_unitids_with_the_same_model_input_share_one_call(tmp_path):
    rows = [
        make_row(unitid="100", city="Main campus"),
        make_row(unitid="200", city="Legacy campus"),
    ]
    model = FakeModel()

    result = run_triage(tmp_path, rows, model)

    assert len(model.requests) == 1
    assert [r["unitid"] for r in result] == ["100", "200"]
    assert result[0]["page_type"] == result[1]["page_type"] == "tabletop_club"


def test_a_different_model_input_is_a_miss(tmp_path):
    rows = [make_row(unitid="1"), make_row(unitid="2", college_name="Other College")]
    model = FakeModel()

    run_triage(tmp_path, rows, model)

    assert len(model.requests) == 2


def test_a_changed_model_or_prompt_calls_the_model_again(tmp_path, monkeypatch):
    rows = [make_row()]
    run_triage(tmp_path, rows, FakeModel(), name="a.csv")
    monkeypatch.setattr(gemini_client_util, "TRIAGE_MODEL", "another-model")
    other_model = FakeModel()

    run_triage(tmp_path, rows, other_model, name="b.csv")

    assert len(other_model.requests) == 1
    assert other_model.requests[0]["model"] == "another-model"


def test_an_invalid_reply_and_its_retry_are_saved_and_replayed_for_free(tmp_path):
    rows = [make_row()]
    first_model = FakeModel('{"page_type": "other"}', json.dumps(make_labels()))

    first = run_triage(tmp_path, rows, first_model, name="first.csv")
    second_model = FakeModel()
    second = run_triage(tmp_path, rows, second_model, name="second.csv")

    assert len(first_model.requests) == 2
    assert second_model.requests == []
    assert first[0]["triage_status"] == second[0]["triage_status"] == ""
    assert first[0]["page_type"] == second[0]["page_type"] == "tabletop_club"
    conn = triage_store.connect(str(tmp_path / "database.sqlite"))
    attempts = conn.execute(
        "SELECT attempt FROM llm_triage_response ORDER BY attempt"
    ).fetchall()
    assert attempts == [(1,), (2,)]


def test_an_api_error_is_not_saved_so_the_next_run_tries_again(tmp_path):
    rows = [make_row()]

    failed = run_triage(
        tmp_path, rows, FakeModel(TimeoutError("boom")), name="failed.csv"
    )
    retry_model = FakeModel()
    retried = run_triage(tmp_path, rows, retry_model, name="retried.csv")

    assert failed[0]["triage_status"] == "api_error"
    assert len(retry_model.requests) == 1
    assert retried[0]["triage_status"] == ""


def test_the_label_rules_can_change_without_a_new_call(tmp_path, monkeypatch):
    rows = [make_row()]
    run_triage(
        tmp_path, rows, FakeModel(json.dumps(make_labels(page_type="other"))), name="a.csv"
    )
    monkeypatch.setattr(llm_triage, "drop_reason", lambda labels: None)
    model = FakeModel()

    tuned = run_triage(tmp_path, rows, model, name="b.csv")

    assert model.requests == []
    assert tuned[0]["page_type"] == "other"
    assert tuned[0]["decision"] == "keep"


def test_cache_only_uses_saved_replies_and_never_calls_the_model(tmp_path):
    saved_row = make_row(unitid="1")
    new_row = make_row(unitid="2", result_title="Chess Club")
    run_triage(tmp_path, [saved_row], FakeModel(), name="fill.csv")
    model = FakeModel()

    result = run_triage(
        tmp_path, [saved_row, new_row], model, cache_only=True, name="only.csv"
    )

    assert model.requests == []
    assert result[0]["triage_status"] == ""
    assert result[0]["page_type"] == "tabletop_club"
    assert result[1]["triage_status"] == "cache_miss"
    assert result[1]["decision"] == "keep"
    assert result[1]["page_type"] == ""


def test_cache_only_saves_nothing(tmp_path):
    run_triage(tmp_path, [make_row()], FakeModel(), cache_only=True)

    conn = triage_store.connect(str(tmp_path / "database.sqlite"))
    assert conn.execute("SELECT COUNT(*) FROM llm_triage_response").fetchone() == (0,)


def test_the_triage_model_column_is_still_written_on_a_replayed_row(tmp_path):
    rows = [make_row()]
    run_triage(tmp_path, rows, FakeModel(), name="a.csv")

    replayed = run_triage(tmp_path, rows, FakeModel(), name="b.csv")

    assert replayed[0]["triage_model"] == config.TRIAGE_MODEL


def test_a_bad_input_csv_creates_no_database(tmp_path):
    input_csv = tmp_path / "incomplete.csv"
    input_csv.write_text("unitid\n1\n", encoding="utf-8")
    database = tmp_path / "database.sqlite"

    with pytest.raises(ValueError, match="is missing columns"):
        llm_triage.run_llm_triage(
            str(input_csv), str(tmp_path / "out.csv"), database_path=str(database)
        )

    assert not database.exists()


def test_run_llm_triage_prints_reply_and_token_usage(tmp_path, capsys):
    rows = [make_row()]
    first_model = FakeModel(cached_content_token_count=3)
    run_triage(tmp_path, rows, first_model, name="a.csv")
    first_output = capsys.readouterr().out
    assert "model replies: 0 saved, 1 new calls" in first_output
    assert "token usage (new calls): 12 total, 3 cached-content" in first_output

    run_triage(tmp_path, rows, FakeModel(), name="b.csv")

    second_output = capsys.readouterr().out
    assert "model replies: 1 saved, 0 new calls" in second_output
    assert "token usage (new calls): 0 total, 0 cached-content" in second_output


# --- runs and the llm_triage_result table -------------------------------------------------

NO_GIT = lambda: (None, None)  # noqa: E731 - keeps the tests off the real repo


def run_saved(tmp_path, rows, send_request, name="out.csv", **kwargs):
    """Run Stage 2b on `rows` against the tmp database and return its run_id."""
    input_csv = tmp_path / "filtered.csv"
    write_filtered_csv(input_csv, rows)
    return llm_triage.run_llm_triage(
        str(input_csv),
        str(tmp_path / name),
        database_path=str(tmp_path / "database.sqlite"),
        send_request=send_request,
        get_git_state=kwargs.pop("get_git_state", NO_GIT),
        **kwargs,
    )


def read_results(tmp_path, run_id):
    conn = triage_store.connect(str(tmp_path / "database.sqlite"))
    cursor = conn.execute(
        "SELECT * FROM llm_triage_result WHERE run_id = ? ORDER BY unitid", (run_id,)
    )
    names = [c[0] for c in cursor.description]
    return {r[1]: dict(zip(names, r)) for r in cursor.fetchall()}


def read_run(tmp_path, run_id):
    conn = triage_store.connect(str(tmp_path / "database.sqlite"))
    cursor = conn.execute("SELECT * FROM llm_triage_run WHERE run_id = ?", (run_id,))
    names = [c[0] for c in cursor.description]
    return dict(zip(names, cursor.fetchone()))


def count(tmp_path, table):
    conn = triage_store.connect(str(tmp_path / "database.sqlite"))
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_results_hold_labels_decision_and_the_link_to_the_saved_reply(tmp_path):
    rows = [make_row(unitid="1"), make_row(unitid="2", result_title="Chess Club")]
    model = FakeModel(
        json.dumps(make_labels()), json.dumps(make_labels(page_type="other"))
    )

    run_id = run_saved(tmp_path, rows, model)
    results = read_results(tmp_path, run_id)

    kept, dropped = results["1"], results["2"]
    assert (kept["stage2a_decision"], kept["decision"]) == ("keep", "keep")
    assert dropped["stage2a_decision"] == "keep"
    assert dropped["decision"] == "discard_wrong_page_type"
    assert kept["page_type"] == "tabletop_club"
    assert dropped["page_type"] == "other"
    assert kept["triage_model"] == config.TRIAGE_MODEL
    assert kept["triage_prompt_version"] == config.TRIAGE_PROMPT_VERSION
    assert kept["triage_status"] is None
    assert kept["attempt"] == 1
    request = gemini_client_util.build_request(llm_triage.build_triage_input(rows[0]))
    assert kept["input_hash"] == triage_store.input_hash(request)


def test_the_run_records_its_settings_note_and_git_state(tmp_path):
    run_id = run_saved(
        tmp_path, [make_row()], FakeModel(), note="baseline",
        get_git_state=lambda: ("deadbeef", True),
    )

    run = read_run(tmp_path, run_id)

    assert run["model"] == config.TRIAGE_MODEL
    assert run["prompt_version"] == config.TRIAGE_PROMPT_VERSION
    assert run["temperature"] == config.TRIAGE_TEMPERATURE
    assert run["thinking_level"] == config.TRIAGE_THINKING_LEVEL
    assert run["note"] == "baseline"
    assert (run["git_commit"], run["git_dirty"]) == ("deadbeef", 1)
    assert run["cache_only"] == 0
    assert run["input_csv"].endswith("filtered.csv")
    assert run["started_at"].endswith("+00:00")


def test_a_cache_only_run_is_marked_as_one(tmp_path):
    run_saved(tmp_path, [make_row()], FakeModel(), name="a.csv")

    run_id = run_saved(tmp_path, [make_row()], FakeModel(), name="b.csv", cache_only=True)

    assert read_run(tmp_path, run_id)["cache_only"] == 1


def test_every_result_input_hash_has_a_saved_reply(tmp_path):
    rows = [make_row(unitid="1"), make_row(unitid="2", result_title="X")]
    run_saved(tmp_path, rows, FakeModel())
    conn = triage_store.connect(str(tmp_path / "database.sqlite"))

    orphans = conn.execute(
        "SELECT COUNT(*) FROM llm_triage_result r LEFT JOIN llm_triage_response p"
        " ON p.input_hash = r.input_hash AND p.attempt = r.attempt"
        " WHERE r.input_hash IS NOT NULL AND p.input_hash IS NULL"
    ).fetchone()

    assert orphans == (0,)


def test_two_unitids_with_the_same_input_have_separate_results_and_one_reply(tmp_path):
    run_id = run_saved(
        tmp_path, [make_row(unitid="100"), make_row(unitid="200")], FakeModel()
    )
    results = read_results(tmp_path, run_id)

    assert set(results) == {"100", "200"}
    assert results["100"]["input_hash"] == results["200"]["input_hash"]
    assert count(tmp_path, "llm_triage_response") == 1


def test_rows_not_sent_to_the_model_have_null_hash_labels_and_model(tmp_path):
    rows = [
        make_row(unitid="1", decision="discard_pdf"),
        make_row(unitid="2", result_url="ERROR", decision="discard_sentinel_row"),
    ]
    model = FakeModel()

    run_id = run_saved(tmp_path, rows, model)
    results = read_results(tmp_path, run_id)

    assert model.requests == []
    for unitid, decision in (("1", "discard_pdf"), ("2", "discard_sentinel_row")):
        row = results[unitid]
        assert row["decision"] == row["stage2a_decision"] == decision
        for name in (
            "input_hash", "attempt", "triage_status", "triage_model",
            "triage_prompt_version", *schema.TRIAGE_LABEL_FIELDNAMES,
        ):
            assert row[name] is None, name


def test_a_failed_row_is_kept_with_null_labels_and_its_status(tmp_path):
    run_id = run_saved(tmp_path, [make_row()], FakeModel(TimeoutError("boom")))

    row = read_results(tmp_path, run_id)["1"]

    assert row["decision"] == "keep"
    assert row["triage_status"] == "api_error"
    assert row["attempt"] is None
    assert row["page_type"] is None
    assert row["input_hash"] is not None
    assert row["triage_model"] == config.TRIAGE_MODEL


def test_a_labeled_row_with_empty_evidence_is_not_mistaken_for_an_unlabeled_one(tmp_path):
    labels = make_labels(
        title_evidence_for_page_type="", url_evidence_for_page_type="",
        page_type="unknown",
    )

    run_id = run_saved(tmp_path, [make_row()], FakeModel(json.dumps(labels)))

    row = read_results(tmp_path, run_id)["1"]
    assert row["page_type"] == "unknown"
    assert row["title_evidence_for_page_type"] == ""


def test_a_cache_miss_row_is_recorded_without_labels(tmp_path):
    run_id = run_saved(tmp_path, [make_row()], FakeModel(), cache_only=True)

    row = read_results(tmp_path, run_id)["1"]

    assert row["triage_status"] == "cache_miss"
    assert row["decision"] == "keep"
    assert row["page_type"] is None


def test_the_attempt_that_gave_the_labels_is_recorded_after_a_retry(tmp_path):
    model = FakeModel('{"page_type": "other"}', json.dumps(make_labels()))

    run_id = run_saved(tmp_path, [make_row()], model)

    assert read_results(tmp_path, run_id)["1"]["attempt"] == 2


def test_rerunning_the_same_rows_adds_a_run_and_replaces_nothing(tmp_path):
    rows = [make_row(unitid="1"), make_row(unitid="2", result_title="X")]

    first = run_saved(tmp_path, rows, FakeModel(), name="a.csv")
    second = run_saved(tmp_path, rows, FakeModel(), name="b.csv")

    assert second != first
    assert count(tmp_path, "llm_triage_run") == 2
    assert count(tmp_path, "llm_triage_result") == 4
    assert set(read_results(tmp_path, first)) == set(read_results(tmp_path, second))


def test_a_small_rerun_keeps_every_row_of_the_earlier_run(tmp_path):
    full = run_saved(
        tmp_path,
        [make_row(unitid="1"), make_row(unitid="2", result_title="X")],
        FakeModel(), name="a.csv",
    )

    small = run_saved(tmp_path, [make_row(unitid="1")], FakeModel(), name="b.csv")

    assert set(read_results(tmp_path, full)) == {"1", "2"}
    assert set(read_results(tmp_path, small)) == {"1"}


def test_a_new_run_with_new_label_rules_costs_no_call_and_keeps_the_old_decisions(
    tmp_path, monkeypatch
):
    rows = [make_row()]
    first = run_saved(
        tmp_path, rows, FakeModel(json.dumps(make_labels(page_type="other"))),
        name="a.csv",
    )
    monkeypatch.setattr(llm_triage, "drop_reason", lambda labels: None)
    model = FakeModel()

    second = run_saved(tmp_path, rows, model, name="b.csv", cache_only=True)

    assert model.requests == []
    assert read_results(tmp_path, first)["1"]["decision"] == "discard_wrong_page_type"
    assert read_results(tmp_path, second)["1"]["decision"] == "keep"
    assert read_results(tmp_path, second)["1"]["page_type"] == "other"


def test_a_new_run_finds_the_saved_replies_of_an_earlier_run(tmp_path):
    rows = [make_row(unitid="1"), make_row(unitid="2", result_title="X")]
    first_model = FakeModel()
    run_saved(tmp_path, rows, first_model, name="a.csv")
    second_model = FakeModel()

    run_saved(tmp_path, rows, second_model, name="b.csv", note="same everything")

    assert len(first_model.requests) == 2
    assert second_model.requests == []


def test_a_new_model_makes_a_new_run_with_its_own_replies_and_keeps_the_old_run(
    tmp_path, monkeypatch
):
    rows = [make_row()]
    first = run_saved(tmp_path, rows, FakeModel(), name="a.csv")
    monkeypatch.setattr(gemini_client_util, "TRIAGE_MODEL", "another-model")
    other = FakeModel(json.dumps(make_labels(page_type="other")))

    second = run_saved(tmp_path, rows, other, name="b.csv")

    assert len(other.requests) == 1
    assert read_run(tmp_path, first)["model"] == config.TRIAGE_MODEL
    assert read_run(tmp_path, second)["model"] == "another-model"
    assert read_results(tmp_path, first)["1"]["page_type"] == "tabletop_club"
    assert read_results(tmp_path, second)["1"]["page_type"] == "other"
    assert count(tmp_path, "llm_triage_response") == 2


def test_a_run_that_crashes_saves_no_run_but_keeps_its_replies(tmp_path, monkeypatch):
    rows = [make_row()]
    monkeypatch.setattr(
        llm_triage, "result_row", lambda row, result: (_ for _ in ()).throw(OSError())
    )

    with pytest.raises(OSError):
        run_saved(tmp_path, rows, FakeModel(), name="a.csv")

    assert count(tmp_path, "llm_triage_run") == 0
    assert count(tmp_path, "llm_triage_result") == 0
    assert count(tmp_path, "llm_triage_response") == 1


def test_the_summary_prints_the_run_id(tmp_path, capsys):
    run_id = run_saved(tmp_path, [make_row()], FakeModel())

    assert f"saved as run {run_id}" in capsys.readouterr().out


def test_run_llm_triage_with_a_label_result_saves_no_run_and_no_database(tmp_path):
    input_csv = tmp_path / "filtered.csv"
    write_filtered_csv(input_csv, [make_row()])
    database = tmp_path / "database.sqlite"

    run_id = llm_triage.run_llm_triage(
        str(input_csv), str(tmp_path / "out.csv"), fixed_labels(),
        database_path=str(database),
    )

    assert run_id is None
    assert not database.exists()


def test_git_state_reports_the_commit_and_uncommitted_changes(tmp_path):
    import subprocess

    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path, check=True, capture_output=True,
        )

    git("init")
    (tmp_path / "a.txt").write_text("one")
    git("add", "a.txt")
    git("commit", "-m", "first")
    clean = llm_triage.git_state(str(tmp_path))
    (tmp_path / "b.txt").write_text("untracked")
    dirty = llm_triage.git_state(str(tmp_path))

    assert len(clean[0]) == 40 and clean[1] is False
    assert dirty == (clean[0], True)


def test_git_state_is_none_outside_a_git_checkout(tmp_path):
    assert llm_triage.git_state(str(tmp_path)) == (None, None)
