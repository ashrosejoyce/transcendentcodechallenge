"""vector_literal is tested as a pure function. Everything else here runs
against a real in-memory SQLite database - the `posts`/`chunks`/
`retrieval_events` tables need no extension, so this exercises the actual
SQL (not a mock) without requiring sqlite-vec to be installed. The one
exception is `chunk_vectors` (a sqlite-vec virtual table): functions that
touch it - `save_chunk_vector`, `all_chunks_with_vectors` - need the real
extension and are exercised by hand once it's installed, not here.
"""
import sqlite3
from datetime import UTC, datetime

import pytest

from app.db import repository
from app.db.schema import CREATE_CHUNKS_TABLE, CREATE_POSTS_TABLE, CREATE_RETRIEVAL_EVENTS_TABLE
from app.models import IngestedPost


def test_vector_literal_formats_as_sqlite_vec_array_syntax():
    assert repository.vector_literal([0.1, -0.2, 0.3]) == "[0.10000000,-0.20000000,0.30000000]"


def test_vector_literal_handles_empty_vector():
    assert repository.vector_literal([]) == "[]"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    for statement in (CREATE_POSTS_TABLE, CREATE_CHUNKS_TABLE, CREATE_RETRIEVAL_EVENTS_TABLE):
        connection.execute(statement)
    yield connection
    connection.close()


def make_post(post_id: int, board: str = "General Beekeeping", body: str = "Some post body.") -> IngestedPost:
    return IngestedPost(
        id=post_id,
        topic_id=100 + post_id,
        board=board,
        subject=f"Subject {post_id}",
        author="MikeyN.C.",
        posted_at=datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC),
        body=body,
        url=f"https://beemaster.com/forum/index.php?topic={100 + post_id}.msg{post_id}",
    )


def test_save_posts_inserts_new_rows(conn):
    saved = repository.save_posts(conn, [make_post(1), make_post(2)])
    assert saved == 2
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 2


def test_save_posts_is_idempotent_on_id(conn):
    repository.save_posts(conn, [make_post(1)])
    saved_again = repository.save_posts(conn, [make_post(1)])

    assert saved_again == 0  # already stored - INSERT OR IGNORE, not a duplicate
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 1


def test_fetch_posts_without_chunks_excludes_already_chunked_posts(conn):
    repository.save_posts(conn, [make_post(1), make_post(2)])
    repository.save_chunk(conn, post_id=1, chunk_index=0, text="a chunk")

    pending = repository.fetch_posts_without_chunks(conn)

    assert [row["id"] for row in pending] == [2]


def test_retrieval_counts_orders_by_count_descending(conn):
    repository.save_posts(conn, [make_post(1), make_post(2)])
    chunk_1 = repository.save_chunk(conn, post_id=1, chunk_index=0, text="chunk one")
    chunk_2 = repository.save_chunk(conn, post_id=2, chunk_index=0, text="chunk two")

    repository.log_retrieval_events(conn, "run-a", "query one", [(chunk_1, 0.1)])
    repository.log_retrieval_events(conn, "run-b", "query two", [(chunk_1, 0.2), (chunk_2, 0.3)])

    counts = repository.retrieval_counts(conn)

    assert counts[0]["chunk_id"] == chunk_1
    assert counts[0]["retrieval_count"] == 2
    assert counts[1]["chunk_id"] == chunk_2
    assert counts[1]["retrieval_count"] == 1


def test_retrieval_counts_includes_never_retrieved_chunks_at_zero(conn):
    repository.save_posts(conn, [make_post(1)])
    repository.save_chunk(conn, post_id=1, chunk_index=0, text="never retrieved")

    counts = repository.retrieval_counts(conn)

    assert len(counts) == 1
    assert counts[0]["retrieval_count"] == 0


def test_corpus_stats_reports_post_and_board_counts(conn):
    repository.save_posts(
        conn, [make_post(1, board="General Beekeeping"), make_post(2, board="Disease & Pest Control")]
    )
    repository.save_chunk(conn, post_id=1, chunk_index=0, text="chunk")

    stats = repository.corpus_stats(conn)

    assert stats["post_count"] == 2
    assert stats["chunk_count"] == 1
    assert stats["board_count"] == 2


def test_corpus_stats_on_empty_database_returns_zeros_not_an_error(conn):
    stats = repository.corpus_stats(conn)
    assert stats["post_count"] == 0
    assert stats["earliest_post"] is None
