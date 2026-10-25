"""The SQLite database behind Stage 2b: opening it, keeping its schema current,
and saving the model's replies and each run's results.

The schema lives in `config.MIGRATIONS_DIR`, one `NNNN_name.sql` file per change
(numbered from 0001 with no gaps). The file's version is SQLite's
`PRAGMA user_version`: the number of the last migration applied. Add a new file
and never edit one that has shipped. Saved model replies
(`llm_triage_response`) cost money to recreate, so no migration may drop or
rewrite that table. Spec: specs/backlog/llm_triage_cache.md.

Importing this module reads no files and opens no database.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import Counter

from config import DATABASE_PATH, MIGRATIONS_DIR
from schema import (
    TRIAGE_RESULT_FIELDNAMES,
    TRIAGE_RESULT_ROW_FIELDNAMES,
    TRIAGE_RUN_FIELDNAMES,
    TRIAGE_USAGE_FIELDNAMES,
)

_MIGRATION_NAME = re.compile(r"(\d{4})_[A-Za-z0-9_]+\.sql")


class DatabaseTooNew(RuntimeError):
    """The file was written by newer code than this checkout."""


def migration_files(migrations_dir: str = MIGRATIONS_DIR) -> list[str]:
    """Paths of the migration files in order. Raises ValueError if a file is
    misnamed, or the numbers don't run 1, 2, 3... with no gap or repeat, since
    the number is what the database version is compared against.
    """
    names = sorted(os.listdir(migrations_dir))
    sql_names = [n for n in names if n.endswith(".sql")]
    for index, name in enumerate(sql_names, start=1):
        match = _MIGRATION_NAME.fullmatch(name)
        if not match or int(match.group(1)) != index:
            raise ValueError(
                f"{migrations_dir}: expected migration number {index:04d} "
                f"(NNNN_name.sql), found {name!r}"
            )
    return [os.path.join(migrations_dir, n) for n in sql_names]


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection, migrations_dir: str = MIGRATIONS_DIR) -> None:
    """Apply every migration file the database hasn't had, oldest first.

    Raises DatabaseTooNew rather than guess at a schema it doesn't know.
    """
    files = migration_files(migrations_dir)
    version = schema_version(conn)
    if version > len(files):
        raise DatabaseTooNew(
            f"database is at schema version {version}, but {migrations_dir} "
            f"only has {len(files)} migrations"
        )
    for number, path in enumerate(files[version:], start=version + 1):
        with open(path, encoding="utf-8") as f:
            script = f.read()
        # executescript commits first, so the transaction is opened in the
        # script text. Each file runs in one transaction together with its
        # version bump, so a file that fails leaves the previous version. The
        # version number can't be a bound parameter.
        try:
            conn.executescript(
                f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;"
            )
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise


def connect(
    path: str = DATABASE_PATH, migrations_dir: str = MIGRATIONS_DIR
) -> sqlite3.Connection:
    """Open the database (creating the file and its folder), enforce foreign
    keys, and bring the schema up to date. `":memory:"` works for tests.
    """
    if path != ":memory:":
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        # Off by default in SQLite, and per connection.
        conn.execute("PRAGMA foreign_keys = ON")
        migrate(conn, migrations_dir)
    except Exception:
        conn.close()
        raise
    return conn


# --- Saved model replies -----------------------------------------------------


class CacheMiss(LookupError):
    """No saved reply, and the caller asked not to call the model."""


RESPONSE_COLUMNS = [
    "input_hash", "attempt", "model", "prompt_hash", "temperature",
    "thinking_level", "triage_input_json", "raw_response", "finish_reason",
    *TRIAGE_USAGE_FIELDNAMES,
]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def input_hash(request: dict) -> str:
    """The key of a `gemini_client_util.build_request` dict.

    It covers everything the model sees (model, system prompt, reply schema,
    temperature, thinking level, contents), so changing any of them is a miss.
    Nothing outside the model's input is in it, so two CSV rows that differ only
    in `unitid` have the same key.
    """
    return _sha256(_canonical_json(request))


def prompt_hash(request: dict) -> str:
    """Key of the prompt version: the system prompt and the reply schema."""
    return _sha256(
        _canonical_json(
            {
                "system_instruction": request["system_instruction"],
                "response_json_schema": request["response_json_schema"],
            }
        )
    )


def _save_prompt(conn: sqlite3.Connection, request: dict) -> str:
    """Save the prompt version once and return its hash. Doesn't commit."""
    key = prompt_hash(request)
    conn.execute(
        "INSERT OR IGNORE INTO llm_triage_prompt"
        " (prompt_hash, system_prompt, response_schema) VALUES (?, ?, ?)",
        (
            key,
            request["system_instruction"],
            _canonical_json(request["response_json_schema"]),
        ),
    )
    return key


def save_run(
    conn: sqlite3.Connection,
    request: dict,
    results: list[dict],
    *,
    started_at: str,
    prompt_version: str,
    input_csv: str,
    cache_only: bool,
    git_commit: str | None,
    git_dirty: bool | None,
    note: str | None,
) -> int:
    """Record one Stage 2b run and its `llm_triage_result` rows; return `run_id`.

    Rows are only ever inserted, so earlier runs are never touched: that is what
    makes two runs comparable. Everything is written in one transaction, so a
    run exists only if it finished and has all its rows. `request` is any
    `build_request` dict from the run (model, prompt, temperature and thinking
    level are the same for every row). Each of `results` holds every column in
    `schema.TRIAGE_RESULT_ROW_FIELDNAMES`. `run_id` is never part of a reply's
    cache key, so a new run can still reuse every saved reply.

    Raises ValueError, before writing anything, if two results share
    (`unitid`, `result_url`).
    """
    keys = Counter((r["unitid"], r["result_url"]) for r in results)
    duplicate = next((key for key, count in keys.items() if count > 1), None)
    if duplicate is not None:
        raise ValueError(
            f"two results for unitid={duplicate[0]!r}, result_url={duplicate[1]!r}"
        )

    run_values = {
        "started_at": started_at,
        "model": request["model"],
        "prompt_hash": prompt_hash(request),
        "prompt_version": prompt_version,
        "temperature": request["temperature"],
        "thinking_level": request["thinking_level"],
        "input_csv": input_csv,
        "cache_only": int(cache_only),
        "git_commit": git_commit,
        "git_dirty": None if git_dirty is None else int(git_dirty),
        "note": note,
    }
    run_columns = TRIAGE_RUN_FIELDNAMES[1:]
    with conn:
        _save_prompt(conn, request)
        cursor = conn.execute(
            f"INSERT INTO llm_triage_run ({', '.join(run_columns)})"
            f" VALUES ({', '.join('?' for _ in run_columns)})",
            [run_values[name] for name in run_columns],
        )
        run_id = cursor.lastrowid
        conn.executemany(
            f"INSERT INTO llm_triage_result ({', '.join(TRIAGE_RESULT_FIELDNAMES)})"
            f" VALUES ({', '.join('?' for _ in TRIAGE_RESULT_FIELDNAMES)})",
            [
                [run_id, *(result[name] for name in TRIAGE_RESULT_ROW_FIELDNAMES)]
                for result in results
            ],
        )
    return run_id


def get_response(conn: sqlite3.Connection, request: dict, attempt: int) -> dict | None:
    """The saved row for this request and attempt as a dict, or None."""
    cursor = conn.execute(
        "SELECT * FROM llm_triage_response WHERE input_hash = ? AND attempt = ?",
        (input_hash(request), attempt),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip((column[0] for column in cursor.description), row))


def put_response(
    conn: sqlite3.Connection, request: dict, attempt: int, details: dict
) -> None:
    """Save one reply; `details` is `gemini_client_util.response_details`.

    A row already saved for the same input and attempt is kept, never replaced:
    the first reply is the one every later tuning run must see. Commits at once,
    so a crash loses at most the call in flight.
    """
    values = {
        "input_hash": input_hash(request),
        "attempt": attempt,
        "model": request["model"],
        "prompt_hash": prompt_hash(request),
        "temperature": request["temperature"],
        "thinking_level": request["thinking_level"],
        "triage_input_json": request["contents"],
        "raw_response": details.get("raw_response"),
        "finish_reason": details.get("finish_reason"),
        **{name: details.get(name) for name in TRIAGE_USAGE_FIELDNAMES},
    }
    with conn:
        _save_prompt(conn, request)
        conn.execute(
            f"INSERT OR IGNORE INTO llm_triage_response ({', '.join(RESPONSE_COLUMNS)})"
            f" VALUES ({', '.join('?' for _ in RESPONSE_COLUMNS)})",
            [values[name] for name in RESPONSE_COLUMNS],
        )
