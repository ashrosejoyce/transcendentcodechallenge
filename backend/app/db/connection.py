"""SQLite connection helper with the sqlite-vec extension loaded."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec

from app.config import settings
from app.db.schema import ALL_TABLE_STATEMENTS, create_vector_table_sql


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db(db_path: Path | None = None, embedding_dimensions: int = 384) -> sqlite3.Connection:
    """Create the schema (idempotent) and return an open connection."""
    conn = _connect(db_path or settings.database_path)
    for statement in ALL_TABLE_STATEMENTS:
        conn.execute(statement)
    conn.execute(create_vector_table_sql(embedding_dimensions))
    conn.commit()
    return conn


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = init_db(db_path)
    try:
        yield conn
    finally:
        conn.close()
