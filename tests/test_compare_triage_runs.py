"""Offline tests of compare_triage_runs.py. Builds runs with triage_store.save_run
in a temporary database; never calls Gemini."""

import sqlite3

import pytest

import compare_triage_runs as compare
import gemini_client_util
import schema
import triage_store

RUN_ARGS = dict(
    started_at="2026-10-25T12:00:00+00:00", prompt_version="v0",
    input_csv="filtered.csv", cache_only=False, git_commit="abc1234567890",
    git_dirty=False, note=None,
)


def result(unitid="1", url="https://example.edu/a", **overrides):
    values = dict.fromkeys(schema.TRIAGE_RESULT_ROW_FIELDNAMES)
    values.update(
        unitid=unitid, result_url=url, stage2a_decision="keep", decision="keep",
        page_type="tabletop_club", page_type_certainty="clear",
        institution="supported", institution_certainty="clear",
    )
    values.update(overrides)
    return values


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "database.sqlite")
    conn = triage_store.connect(path)
    request = gemini_client_util.build_request({})

    def save(results, **overrides):
        return triage_store.save_run(
            conn, request, results, **{**RUN_ARGS, **overrides}
        )

    return conn, save, path


def test_identical_runs_have_no_changes(db):
    conn, save, _ = db
    rows = [result("1"), result("2")]
    a, b = save(rows), save(rows)

    c = compare.compare_runs(conn, a, b)

    assert (c.in_both, c.identical, c.changed) == (2, 2, [])
    assert c.only_in_a == c.only_in_b == []


def test_a_changed_decision_is_found_with_the_fields_that_differ(db):
    conn, save, _ = db
    a = save([result("1"), result("2")])
    b = save([
        result("1"),
        result("2", decision="discard_wrong_page_type", page_type="other"),
    ])

    c = compare.compare_runs(conn, a, b)

    assert (c.in_both, c.identical) == (2, 1)
    (unitid, url, differences), = c.changed
    assert unitid == "2"
    assert differences == {
        "decision": ("keep", "discard_wrong_page_type"),
        "page_type": ("tabletop_club", "other"),
    }
    assert c.decision_moves == {("keep", "discard_wrong_page_type"): 1}


def test_rows_in_only_one_run_are_listed_separately(db):
    conn, save, _ = db
    a = save([result("1"), result("2")])
    b = save([result("2"), result("3")])

    c = compare.compare_runs(conn, a, b)

    assert c.only_in_a == [("1", "https://example.edu/a")]
    assert c.only_in_b == [("3", "https://example.edu/a")]
    assert (c.in_both, c.identical) == (1, 1)


def test_the_same_unitid_with_two_urls_is_two_rows(db):
    conn, save, _ = db
    rows = [result("1", "https://a"), result("1", "https://b")]
    a = save(rows)
    b = save([result("1", "https://a"), result("1", "https://b", decision="discard_pdf")])

    c = compare.compare_runs(conn, a, b)

    assert [(u, url) for u, url, _ in c.changed] == [("1", "https://b")]


def test_null_and_a_value_are_a_difference_but_two_nulls_are_not(db):
    conn, save, _ = db
    labeled = result("1")
    failed = result("1", page_type=None, page_type_certainty=None, institution=None,
                    institution_certainty=None, triage_status="api_error")
    a, b, c_run = save([labeled]), save([failed]), save([failed])

    changed = compare.compare_runs(conn, a, b)
    same = compare.compare_runs(conn, b, c_run)

    assert changed.changed[0][2]["page_type"] == ("tabletop_club", None)
    assert changed.changed[0][2]["triage_status"] == (None, "api_error")
    assert same.changed == [] and same.identical == 1


def test_evidence_quotes_are_not_compared(db):
    conn, save, _ = db
    a = save([result(title_evidence_for_page_type="Tabletop")])
    b = save([result(title_evidence_for_page_type="Tabletop Club")])

    assert compare.compare_runs(conn, a, b).changed == []


def test_fields_limits_what_counts_as_a_change(db):
    conn, save, _ = db
    a = save([result(page_type="tabletop_club")])
    b = save([result(page_type="other")])

    only_decision = compare.compare_runs(conn, a, b, ["decision"])
    only_type = compare.compare_runs(conn, a, b, ["page_type"])

    assert only_decision.changed == [] and only_decision.identical == 1
    assert len(only_type.changed) == 1


def test_an_unknown_field_is_refused(db):
    conn, save, _ = db
    a, b = save([result()]), save([result()])

    with pytest.raises(ValueError, match="unitid"):
        compare.compare_runs(conn, a, b, ["unitid"])


def test_an_unknown_run_id_is_refused(db):
    conn, save, _ = db
    a = save([result()])

    with pytest.raises(compare.RunNotFound, match="no run 99"):
        compare.compare_runs(conn, a, 99)


def test_list_runs_shows_row_counts_and_the_note(db):
    conn, save, _ = db
    save([result("1"), result("2")], note="baseline")
    save([result("1")], git_dirty=True, cache_only=True)

    runs = compare.list_runs(conn)
    text = compare.format_runs(runs)

    assert [r["result_rows"] for r in runs] == [2, 1]
    assert 'note: "baseline"' in text
    assert "uncommitted changes" in text and "cache-only" in text
    assert "2 rows" in text


def test_the_report_summarises_decision_moves_and_flags_a_different_prompt(db):
    conn, save, _ = db
    a = save([result("1")], note="before")
    other = dict(gemini_client_util.build_request({}), system_instruction="changed")
    b = triage_store.save_run(
        conn, other, [result("1", decision="discard_wrong_page_type")],
        **{**RUN_ARGS, "note": "after"},
    )

    text = compare.format_report(compare.compare_runs(conn, a, b))

    assert "keep -> discard_wrong_page_type" in text
    assert "prompt or reply schema differs" in text
    assert 'note: "before"' in text and 'note: "after"' in text
    assert "changed:   1" in text


def test_the_report_limits_changed_rows_and_says_how_to_see_the_rest(db):
    conn, save, _ = db
    ids = [str(i) for i in range(5)]
    a = save([result(i) for i in ids])
    b = save([result(i, decision="discard_pdf") for i in ids])
    c = compare.compare_runs(conn, a, b)

    limited = compare.format_report(c, limit=2)
    everything = compare.format_report(c, limit=0)

    assert "Changed rows (2 of 5)" in limited and "3 more (use --limit 0)" in limited
    assert "Changed rows (5 of 5)" in everything and "more" not in everything


def test_main_lists_and_compares_and_exits_zero(db, capsys):
    conn, save, path = db
    a = save([result("1")])
    b = save([result("1", decision="discard_pdf")])
    conn.close()

    assert compare.main(["--list", "--database", path]) == 0
    assert "run 1" in capsys.readouterr().out
    assert compare.main(["--a", str(a), "--b", str(b), "--database", path]) == 0
    assert "keep -> discard_pdf" in capsys.readouterr().out


def test_main_reports_errors_on_stderr_and_exits_one(db, capsys, tmp_path):
    _, save, path = db
    save([result()])

    assert compare.main(["--a", "1", "--b", "9", "--database", path]) == 1
    assert "no run 9" in capsys.readouterr().err
    missing = str(tmp_path / "nope.sqlite")
    assert compare.main(["--list", "--database", missing]) == 1
    assert "no database" in capsys.readouterr().err


def test_main_needs_both_runs_and_refuses_the_same_run_twice(db):
    _, save, path = db
    save([result()])

    for argv in (["--a", "1"], [], ["--a", "1", "--b", "1"]):
        with pytest.raises(SystemExit) as exit_info:
            compare.main([*argv, "--database", path])
        assert exit_info.value.code == 2


def test_a_missing_database_is_not_created(tmp_path):
    missing = tmp_path / "nope.sqlite"

    compare.main(["--list", "--database", str(missing)])

    assert not missing.exists()


def test_the_connection_is_read_only(db):
    _, _, path = db
    conn = compare.open_readonly(path)

    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM llm_triage_run")


def test_a_database_from_before_run_tracking_gives_a_clear_error(tmp_path, capsys):
    path = tmp_path / "old.sqlite"
    sqlite3.connect(path).close()

    assert compare.main(["--list", "--database", str(path)]) == 1
    assert "predates run tracking" in capsys.readouterr().err


def test_the_docstring_documents_every_option():
    doc = compare.__doc__

    for flag in ("--list", "--a", "--b", "--fields", "--limit", "--database"):
        assert flag in doc, flag
    for name in schema.TRIAGE_COMPARE_FIELDNAMES:
        assert name in doc, name
