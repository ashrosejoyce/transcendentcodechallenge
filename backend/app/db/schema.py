"""SQLite schema for the Community Voices data store.

Design:
- `posts`       one row per forum post we ingested.
- `chunks`      one row per text chunk carved out of a post (RAG unit of retrieval).
- `chunk_vectors` a sqlite-vec virtual table; rowid == chunks.id.
- `retrieval_events` one row per time a chunk is retrieved for a query -
  this is what "keeping stats on which embeddings get retrieved the most" is built on.
"""
from __future__ import annotations

CREATE_POSTS_TABLE = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,            -- SMF message id
    topic_id INTEGER NOT NULL,
    board TEXT NOT NULL,
    subject TEXT NOT NULL,
    author TEXT NOT NULL,
    posted_at TEXT NOT NULL,           -- ISO-8601 UTC
    body TEXT NOT NULL,
    url TEXT NOT NULL,
    crawled_at TEXT NOT NULL
);
"""

CREATE_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL
);
"""


def create_vector_table_sql(dimensions: int) -> str:
    return f"""
    CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
        embedding float[{dimensions}]
    );
    """


CREATE_RETRIEVAL_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS retrieval_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    rank INTEGER NOT NULL,
    distance REAL NOT NULL,
    retrieved_at TEXT NOT NULL,
    run_id TEXT NOT NULL
);
"""

ALL_TABLE_STATEMENTS = (
    CREATE_POSTS_TABLE,
    CREATE_CHUNKS_TABLE,
    CREATE_RETRIEVAL_EVENTS_TABLE,
)
