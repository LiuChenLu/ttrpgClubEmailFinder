"""The SQLite database behind Stage 2b: opening it and keeping its schema current.

The schema lives in `config.MIGRATIONS_DIR`, one `NNNN_name.sql` file per change
(numbered from 0001 with no gaps). The file's version is SQLite's
`PRAGMA user_version`: the number of the last migration applied. Add a new file
and never edit one that has shipped. Saved model replies
(`llm_triage_response`) cost money to recreate, so no migration may drop or
rewrite that table. Spec: specs/backlog/llm_triage_cache.md.

Importing this module reads no files and opens no database.
"""

from __future__ import annotations

import os
import re
import sqlite3

from config import DATABASE_PATH, MIGRATIONS_DIR

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
