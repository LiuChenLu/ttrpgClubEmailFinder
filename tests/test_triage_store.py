"""Offline tests of the Stage 2b database: schema creation and migrations. Uses
temporary files and in-memory databases only.
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

import config
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
    import schema

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
    (migrations_dir / "0002_add_note.sql").write_text(
        "ALTER TABLE llm_triage_result ADD COLUMN note TEXT;"
    )

    conn = triage_store.connect(path, str(migrations_dir))

    assert "note" in columns(conn, "llm_triage_result")
    assert triage_store.schema_version(conn) == 2
    assert conn.execute("SELECT COUNT(*) FROM llm_triage_response").fetchone() == (1,)
    conn.close()
    triage_store.connect(path, str(migrations_dir)).close()  # must not re-apply 0002


def test_a_failing_migration_file_changes_nothing_and_keeps_the_old_version(
    tmp_path, migrations_dir
):
    path = str(tmp_path / "database.sqlite")
    triage_store.connect(path, str(migrations_dir)).close()
    broken = migrations_dir / "0002_broken.sql"
    broken.write_text(
        "CREATE TABLE half_done (x TEXT); SELECT * FROM does_not_exist;"
    )

    with pytest.raises(sqlite3.Error):
        triage_store.connect(path, str(migrations_dir))

    broken.unlink()
    conn = triage_store.connect(path, str(migrations_dir))
    assert "half_done" not in table_names(conn)
    assert triage_store.schema_version(conn) == 1


def test_a_database_from_newer_code_is_refused(tmp_path):
    path = str(tmp_path / "database.sqlite")
    raw = sqlite3.connect(path)
    raw.execute(f"PRAGMA user_version = {latest_version() + 1}")
    raw.close()

    with pytest.raises(triage_store.DatabaseTooNew):
        triage_store.connect(path)


@pytest.mark.parametrize(
    "extra", ["0003_gap.sql", "0001_repeat.sql", "2_short_number.sql", "0002 spaces.sql"]
)
def test_misnumbered_or_misnamed_migration_files_are_rejected(migrations_dir, extra):
    (migrations_dir / extra).write_text("SELECT 1;")

    with pytest.raises(ValueError):
        triage_store.migration_files(str(migrations_dir))


def test_files_that_are_not_sql_are_ignored(migrations_dir):
    (migrations_dir / "README.md").write_text("notes")

    assert len(triage_store.migration_files(str(migrations_dir))) == latest_version()
