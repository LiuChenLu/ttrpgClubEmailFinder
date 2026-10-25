"""Offline tests of the Stage 2b database: schema creation and migrations. Uses
temporary files and in-memory databases only.
"""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

import config
import gemini_client_util
import schema
import triage_store

ROOT = Path(__file__).parent.parent
TABLES = {"llm_triage_prompt", "llm_triage_response", "llm_triage_result"}
FIRST_MIGRATION = "0001_create_triage_tables.sql"


def latest_version():
    return len(triage_store.migration_files())


@pytest.fixture
def migrations_dir(tmp_path):
    """A temporary copy of the real migrations, so a test can add or break one."""
    folder = tmp_path / "migrations"
    shutil.copytree(ROOT / "migrations", folder)
    return folder


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {name for (name,) in rows}


def columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def insert_prompt(conn, prompt_hash="p1"):
    conn.execute(
        "INSERT INTO llm_triage_prompt (prompt_hash, system_prompt, response_schema)"
        " VALUES (?, 'rubric', '{}')",
        (prompt_hash,),
    )


def insert_response(conn, input_hash="h1", attempt=1, prompt_hash="p1"):
    conn.execute(
        "INSERT INTO llm_triage_response (input_hash, attempt, model, prompt_hash,"
        " temperature, thinking_level, triage_input_json) VALUES (?, ?, 'm', ?, 0,"
        " 'LOW', '{}')",
        (input_hash, attempt, prompt_hash),
    )


def test_the_default_paths():
    assert config.DATABASE_PATH == "./data/database.sqlite"
    assert config.MIGRATIONS_DIR == "./migrations"


def test_the_first_migration_file_is_where_the_tables_come_from():
    assert [Path(p).name for p in triage_store.migration_files()][0] == FIRST_MIGRATION


def test_connect_creates_the_tables_at_the_latest_version():
    conn = triage_store.connect(":memory:")

    assert TABLES <= table_names(conn)
    assert triage_store.schema_version(conn) == latest_version()


def test_connect_creates_the_file_and_its_folder(tmp_path):
    path = tmp_path / "new_folder" / "database.sqlite"

    triage_store.connect(str(path)).close()

    assert path.exists()


def test_connecting_again_keeps_the_saved_replies(tmp_path):
    path = str(tmp_path / "database.sqlite")
    conn = triage_store.connect(path)
    insert_prompt(conn)
    insert_response(conn)
    conn.commit()
    conn.close()

    conn = triage_store.connect(path)

    assert conn.execute("SELECT COUNT(*) FROM llm_triage_response").fetchone() == (1,)
    assert triage_store.schema_version(conn) == latest_version()


def test_response_columns_use_the_sdk_usage_metadata_names():
    conn = triage_store.connect(":memory:")

    assert {
        "prompt_token_count",
        "candidates_token_count",
        "thoughts_token_count",
        "cached_content_token_count",
        "tool_use_prompt_token_count",
        "total_token_count",
    } <= set(columns(conn, "llm_triage_response"))


def test_result_columns_hold_every_triage_label():
    conn = triage_store.connect(":memory:")

    assert set(schema.TRIAGE_LABEL_FIELDNAMES) <= set(
        columns(conn, "llm_triage_result")
    )


def test_a_response_needs_a_saved_prompt():
    conn = triage_store.connect(":memory:")

    with pytest.raises(sqlite3.IntegrityError):
        insert_response(conn, prompt_hash="never_saved")


def test_one_response_per_input_and_attempt_but_retries_are_kept():
    conn = triage_store.connect(":memory:")
    insert_prompt(conn)
    insert_response(conn, attempt=1)
    insert_response(conn, attempt=2)

    with pytest.raises(sqlite3.IntegrityError):
        insert_response(conn, attempt=1)




def test_a_later_migration_file_runs_once_and_keeps_existing_rows(
    tmp_path, migrations_dir
):
    path = str(tmp_path / "database.sqlite")
    conn = triage_store.connect(path, str(migrations_dir))
    insert_prompt(conn)
    insert_response(conn)
    conn.commit()
    conn.close()
    (migrations_dir / "0003_add_note.sql").write_text(
        "ALTER TABLE llm_triage_result ADD COLUMN note TEXT;"
    )

    conn = triage_store.connect(path, str(migrations_dir))

    assert "note" in columns(conn, "llm_triage_result")
    assert triage_store.schema_version(conn) == latest_version() + 1
    assert conn.execute("SELECT COUNT(*) FROM llm_triage_response").fetchone() == (1,)
    conn.close()
    triage_store.connect(path, str(migrations_dir)).close()  # must not re-apply 0003


def test_a_failing_migration_file_changes_nothing_and_keeps_the_old_version(
    tmp_path, migrations_dir
):
    path = str(tmp_path / "database.sqlite")
    triage_store.connect(path, str(migrations_dir)).close()
    broken = migrations_dir / "0003_broken.sql"
    broken.write_text(
        "CREATE TABLE half_done (x TEXT); SELECT * FROM does_not_exist;"
    )

    with pytest.raises(sqlite3.Error):
        triage_store.connect(path, str(migrations_dir))

    broken.unlink()
    conn = triage_store.connect(path, str(migrations_dir))
    assert "half_done" not in table_names(conn)
    assert triage_store.schema_version(conn) == 2


def test_a_database_from_newer_code_is_refused(tmp_path):
    path = str(tmp_path / "database.sqlite")
    raw = sqlite3.connect(path)
    raw.execute(f"PRAGMA user_version = {latest_version() + 1}")
    raw.close()

    with pytest.raises(triage_store.DatabaseTooNew):
        triage_store.connect(path)


@pytest.mark.parametrize(
    "extra", ["0004_gap.sql", "0001_repeat.sql", "2_short_number.sql", "0003 spaces.sql"]
)
def test_misnumbered_or_misnamed_migration_files_are_rejected(migrations_dir, extra):
    (migrations_dir / extra).write_text("SELECT 1;")

    with pytest.raises(ValueError):
        triage_store.migration_files(str(migrations_dir))


def test_files_that_are_not_sql_are_ignored(migrations_dir):
    (migrations_dir / "README.md").write_text("notes")

    assert len(triage_store.migration_files(str(migrations_dir))) == latest_version()


# --- hashing and saved replies ---------------------------------------------------

TRIAGE_INPUT = {
    "university": "Example College",
    "aliases": ["EC"],
    "url": "https://example.edu/clubs/tabletop",
    "title": "Tabletop Club | Example College",
    "domain_relation": "on_domain",
}
DETAILS = {
    "raw_response": '{"page_type": "other"}',
    "finish_reason": "STOP",
    "prompt_token_count": 120,
    "candidates_token_count": 30,
    "thoughts_token_count": 7,
    "cached_content_token_count": None,
    "tool_use_prompt_token_count": None,
    "total_token_count": 157,
}


def make_request(**overrides):
    return {**gemini_client_util.build_request(TRIAGE_INPUT), **overrides}


def test_the_same_request_has_the_same_hash_whatever_the_key_order():
    request = make_request()
    reordered = dict(reversed(list(request.items())))

    assert triage_store.input_hash(request) == triage_store.input_hash(reordered)


@pytest.mark.parametrize(
    "change",
    [
        {"model": "another-model"},
        {"temperature": 0.7},
        {"thinking_level": "HIGH"},
        {"system_instruction": "a different rubric"},
        {"response_json_schema": {"type": "object"}},
        {"contents": '{"title": "Chess Club"}'},
    ],
    ids=lambda change: next(iter(change)),
)
def test_anything_the_model_sees_changes_the_hash(change):
    assert triage_store.input_hash(make_request(**change)) != triage_store.input_hash(
        make_request()
    )


def test_prompt_hash_changes_with_the_prompt_or_schema_only():
    base = triage_store.prompt_hash(make_request())

    assert triage_store.prompt_hash(make_request(model="x", contents="{}")) == base
    assert triage_store.prompt_hash(make_request(system_instruction="new")) != base
    assert triage_store.prompt_hash(make_request(response_json_schema={})) != base


def test_a_saved_reply_comes_back_with_everything_that_was_saved():
    conn = triage_store.connect(":memory:")
    request = make_request()

    triage_store.put_response(conn, request, 1, DETAILS)
    saved = triage_store.get_response(conn, request, 1)

    assert saved["input_hash"] == triage_store.input_hash(request)
    assert saved["attempt"] == 1
    assert saved["model"] == request["model"]
    assert saved["temperature"] == request["temperature"]
    assert saved["thinking_level"] == request["thinking_level"]
    assert saved["triage_input_json"] == request["contents"]
    assert json.loads(saved["triage_input_json"]) == TRIAGE_INPUT
    assert saved["raw_response"] == DETAILS["raw_response"]
    assert saved["finish_reason"] == "STOP"
    for name in schema.TRIAGE_USAGE_FIELDNAMES:
        assert saved[name] == DETAILS[name]
    assert saved["cached_content_token_count"] is None


def test_the_prompt_is_stored_once_for_many_replies():
    conn = triage_store.connect(":memory:")
    for title in ("A", "B", "C"):
        request = make_request(contents=json.dumps({"title": title}))
        triage_store.put_response(conn, request, 1, DETAILS)

    assert conn.execute("SELECT COUNT(*) FROM llm_triage_prompt").fetchone() == (1,)
    assert conn.execute("SELECT COUNT(*) FROM llm_triage_response").fetchone() == (3,)
    (system_prompt,) = conn.execute("SELECT system_prompt FROM llm_triage_prompt").fetchone()
    assert system_prompt == gemini_client_util.system_prompt()


def test_a_miss_is_none_and_attempts_are_separate():
    conn = triage_store.connect(":memory:")
    request = make_request()
    triage_store.put_response(conn, request, 1, DETAILS)

    assert triage_store.get_response(conn, request, 2) is None
    assert triage_store.get_response(conn, make_request(model="other"), 1) is None


def test_saving_again_keeps_the_first_reply():
    conn = triage_store.connect(":memory:")
    request = make_request()
    triage_store.put_response(conn, request, 1, DETAILS)

    triage_store.put_response(conn, request, 1, {**DETAILS, "raw_response": "changed"})

    assert triage_store.get_response(conn, request, 1)["raw_response"] == (
        DETAILS["raw_response"]
    )


def test_a_saved_reply_is_on_disk_after_put_without_an_explicit_commit(tmp_path):
    path = str(tmp_path / "database.sqlite")
    conn = triage_store.connect(path)
    triage_store.put_response(conn, make_request(), 1, DETAILS)

    other = triage_store.connect(path)  # a second connection sees it

    assert triage_store.get_response(other, make_request(), 1) is not None


# --- runs and results -----------------------------------------------------------------

RUN_ARGS = dict(
    started_at="2026-10-25T12:00:00+00:00",
    prompt_version="v0",
    input_csv="filtered.csv",
    cache_only=False,
    git_commit="abc123",
    git_dirty=False,
    note=None,
)


def make_result(**overrides):
    values = dict.fromkeys(schema.TRIAGE_RESULT_ROW_FIELDNAMES)
    values.update(unitid="1", result_url="https://example.edu/a", decision="keep")
    values.update(stage2a_decision="keep")
    values.update(overrides)
    return values


def read_table(conn, table):
    cursor = conn.execute(f"SELECT * FROM {table}")
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def save(conn, results, **overrides):
    return triage_store.save_run(
        conn, make_request(), results, **{**RUN_ARGS, **overrides}
    )


def test_result_and_run_fieldnames_are_exactly_the_table_columns():
    conn = triage_store.connect(":memory:")

    assert schema.TRIAGE_RESULT_FIELDNAMES == columns(conn, "llm_triage_result")
    assert schema.TRIAGE_RUN_FIELDNAMES == columns(conn, "llm_triage_run")
    assert schema.TRIAGE_RESULT_FIELDNAMES == [
        "run_id", *schema.TRIAGE_RESULT_ROW_FIELDNAMES
    ]


def test_compare_fields_are_all_result_columns_and_skip_the_quotes():
    assert set(schema.TRIAGE_COMPARE_FIELDNAMES) <= set(schema.TRIAGE_RESULT_FIELDNAMES)
    assert not [f for f in schema.TRIAGE_COMPARE_FIELDNAMES if "evidence" in f]


def test_save_run_records_the_run_settings_and_the_rows_under_its_id():
    conn = triage_store.connect(":memory:")
    request = make_request()
    values = make_result(page_type="other", attempt=2, input_hash="h")

    run_id = save(conn, [values], note="first try", git_dirty=True)

    (run,) = read_table(conn, "llm_triage_run")
    assert run["run_id"] == run_id
    assert run["model"] == request["model"]
    assert run["temperature"] == request["temperature"]
    assert run["thinking_level"] == request["thinking_level"]
    assert run["prompt_hash"] == triage_store.prompt_hash(request)
    assert (run["prompt_version"], run["input_csv"]) == ("v0", "filtered.csv")
    assert (run["started_at"], run["git_commit"]) == (
        RUN_ARGS["started_at"], "abc123"
    )
    assert (run["git_dirty"], run["cache_only"], run["note"]) == (1, 0, "first try")
    (result,) = read_table(conn, "llm_triage_result")
    assert result == {"run_id": run_id, **values}


def test_the_prompt_text_is_saved_with_the_run_so_the_run_row_can_point_at_it():
    conn = triage_store.connect(":memory:")

    save(conn, [make_result()])

    (system_prompt,) = conn.execute(
        "SELECT p.system_prompt FROM llm_triage_run r JOIN llm_triage_prompt p"
        " USING (prompt_hash)"
    ).fetchone()
    assert system_prompt == gemini_client_util.system_prompt()


def test_a_second_run_adds_rows_and_leaves_the_first_run_unchanged():
    conn = triage_store.connect(":memory:")
    first = save(conn, [make_result(decision="keep", page_type="tabletop_club")])
    before = [r for r in read_table(conn, "llm_triage_result") if r["run_id"] == first]

    second = save(
        conn, [make_result(decision="discard_wrong_page_type", page_type="other")]
    )

    assert second != first
    rows = read_table(conn, "llm_triage_result")
    assert len(rows) == 2
    assert [r for r in rows if r["run_id"] == first] == before
    assert {r["run_id"]: r["decision"] for r in rows} == {
        first: "keep", second: "discard_wrong_page_type"
    }


def test_the_same_rows_saved_twice_make_two_runs_not_a_replacement():
    conn = triage_store.connect(":memory:")
    results = [make_result(unitid="1"), make_result(unitid="2")]

    save(conn, results)
    save(conn, results)

    assert len(read_table(conn, "llm_triage_run")) == 2
    assert len(read_table(conn, "llm_triage_result")) == 4


def test_run_ids_are_never_reused_after_a_run_is_deleted():
    conn = triage_store.connect(":memory:")
    first = save(conn, [make_result()])
    conn.execute("DELETE FROM llm_triage_result WHERE run_id = ?", (first,))
    conn.execute("DELETE FROM llm_triage_run WHERE run_id = ?", (first,))
    conn.commit()

    second = save(conn, [make_result()])

    assert second > first


def test_rows_for_other_units_and_urls_are_kept_in_one_run():
    conn = triage_store.connect(":memory:")

    save(
        conn,
        [
            make_result(unitid="1"),
            make_result(unitid="2"),
            make_result(unitid="1", result_url="https://b"),
        ],
    )

    assert len(read_table(conn, "llm_triage_result")) == 3


def test_a_duplicate_unitid_and_url_in_one_run_is_refused_and_nothing_is_written():
    conn = triage_store.connect(":memory:")

    with pytest.raises(ValueError, match="two results"):
        save(conn, [make_result(), make_result(decision="discard_pdf")])

    assert read_table(conn, "llm_triage_run") == []
    assert read_table(conn, "llm_triage_result") == []


def test_a_failure_part_way_leaves_no_run_and_no_rows():
    conn = triage_store.connect(":memory:")
    broken = make_result(unitid="2")
    del broken["decision"]  # raises after the run row has been inserted

    with pytest.raises(KeyError):
        save(conn, [make_result(unitid="1"), broken])

    assert read_table(conn, "llm_triage_run") == []
    assert read_table(conn, "llm_triage_result") == []


def test_an_empty_run_is_still_recorded():
    conn = triage_store.connect(":memory:")

    run_id = save(conn, [])

    assert [r["run_id"] for r in read_table(conn, "llm_triage_run")] == [run_id]


def test_the_run_id_is_not_part_of_the_reply_cache_key():
    request = make_request()

    assert "run_id" not in request
    assert triage_store.input_hash(request) == triage_store.input_hash(
        make_request()
    )


def test_upgrading_a_version_1_database_keeps_replies_and_adds_the_run_tables(
    tmp_path, migrations_dir
):
    path = str(tmp_path / "database.sqlite")
    only_first = tmp_path / "first_only"
    only_first.mkdir()
    shutil.copy(migrations_dir / FIRST_MIGRATION, only_first)
    conn = triage_store.connect(path, str(only_first))
    insert_prompt(conn)
    insert_response(conn)
    conn.commit()
    assert triage_store.schema_version(conn) == 1
    conn.close()

    conn = triage_store.connect(path, str(migrations_dir))

    assert triage_store.schema_version(conn) == latest_version()
    assert conn.execute("SELECT COUNT(*) FROM llm_triage_response").fetchone() == (1,)
    assert "llm_triage_run" in table_names(conn)
    assert columns(conn, "llm_triage_result")[0] == "run_id"
