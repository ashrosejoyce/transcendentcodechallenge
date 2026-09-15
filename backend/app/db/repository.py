"""Persistence functions - small, focused wrappers around SQL so the rest
of the codebase never writes raw SQL inline."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from app.models import IngestedPost


def save_posts(conn: sqlite3.Connection, posts: Iterable[IngestedPost]) -> int:
    """Insert posts, skipping ones already stored (id is the SMF message id,
    so re-running the crawler is safe and idempotent)."""
    crawled_at = datetime.now(UTC).isoformat()
    rows = [
        (
            post.id,
            post.topic_id,
            post.board,
            post.subject,
            post.author,
            post.posted_at.isoformat(),
            post.body,
            post.url,
            crawled_at,
        )
        for post in posts
    ]
    cursor = conn.executemany(
        """
        INSERT OR IGNORE INTO posts
            (id, topic_id, board, subject, author, posted_at, body, url, crawled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return cursor.rowcount if cursor.rowcount is not None else 0


def fetch_posts_without_chunks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT p.* FROM posts p
        WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.post_id = p.id)
        ORDER BY p.posted_at ASC
        """
    ).fetchall()


def save_chunk(conn: sqlite3.Connection, post_id: int, chunk_index: int, text: str) -> int:
    cursor = conn.execute(
        "INSERT INTO chunks (post_id, chunk_index, text) VALUES (?, ?, ?)",
        (post_id, chunk_index, text),
    )
    return cursor.lastrowid


def save_chunk_vector(conn: sqlite3.Connection, chunk_id: int, embedding: Sequence[float]) -> None:
    conn.execute(
        "INSERT INTO chunk_vectors (rowid, embedding) VALUES (?, ?)",
        (chunk_id, vector_literal(embedding)),
    )


def all_chunks_with_vectors(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.id, c.post_id, c.text, cv.embedding,
               p.board, p.subject, p.author, p.posted_at, p.url
        FROM chunks c
        JOIN chunk_vectors cv ON cv.rowid = c.id
        JOIN posts p ON p.id = c.post_id
        """
    ).fetchall()


def log_retrieval_events(
    conn: sqlite3.Connection,
    run_id: str,
    query_text: str,
    ranked_chunk_ids: Sequence[tuple[int, float]],
) -> None:
    retrieved_at = datetime.now(UTC).isoformat()
    rows = [
        (chunk_id, query_text, rank, distance, retrieved_at, run_id)
        for rank, (chunk_id, distance) in enumerate(ranked_chunk_ids, start=1)
    ]
    conn.executemany(
        """
        INSERT INTO retrieval_events (chunk_id, query_text, rank, distance, retrieved_at, run_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def retrieval_counts(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.id AS chunk_id, p.subject, p.board, c.text,
               COUNT(re.id) AS retrieval_count
        FROM chunks c
        JOIN posts p ON p.id = c.post_id
        LEFT JOIN retrieval_events re ON re.chunk_id = c.id
        GROUP BY c.id
        ORDER BY retrieval_count DESC, c.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def corpus_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM posts) AS post_count,
            (SELECT COUNT(*) FROM chunks) AS chunk_count,
            (SELECT COUNT(DISTINCT board) FROM posts) AS board_count,
            (SELECT MIN(posted_at) FROM posts) AS earliest_post,
            (SELECT MAX(posted_at) FROM posts) AS latest_post
        """
    ).fetchone()
    return dict(row) if row else {}


def vector_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
