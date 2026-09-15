"""Vector similarity retrieval on top of sqlite-vec, with every retrieval
logged so we can report "which embeddings get retrieved the most"
(spec item 3c)."""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.config import settings
from app.db.repository import log_retrieval_events, vector_literal
from app.rag.embeddings import embed_query

# vec0's KNN has no notion of the joined posts.posted_at column, so a plain
# `k=top_k` MATCH returns the globally-nearest chunks *before* any date
# filtering happens - filtering those down by `since` afterward could leave
# fewer than top_k (or zero) even when plenty of good in-window matches
# exist further down the ranking. When a `since` cutoff is given we instead
# overfetch a wide candidate pool from vec0, date-filter it, then trim back
# to top_k - keeping the final results the closest *in-window* matches.
_SINCE_OVERFETCH_CANDIDATES = 500


@dataclass
class RetrievedChunk:
    chunk_id: int
    post_id: int
    text: str
    board: str
    subject: str
    author: str
    posted_at: str
    url: str
    distance: float


def retrieve(
    conn: sqlite3.Connection,
    query: str,
    top_k: int | None = None,
    run_id: str | None = None,
    since: datetime | None = None,
) -> list[RetrievedChunk]:
    """Embed `query`, find the top_k nearest chunks, log the retrieval event
    for each one, and return them ordered by relevance (closest first).

    When `since` is given, only chunks whose post was published on or after
    that timestamp are returned - this is what lets a report's timeframe
    (see `generation/timeframe.py`) narrow the RAG document to "the past
    day/week/month/year" independent of how far back the corpus itself
    goes."""
    top_k = top_k or settings.retrieval_top_k
    run_id = run_id or str(uuid.uuid4())
    query_vector = embed_query(query)
    fetch_k = _SINCE_OVERFETCH_CANDIDATES if since is not None else top_k

    rows = conn.execute(
        """
        SELECT c.id AS chunk_id, c.post_id, c.text,
               p.board, p.subject, p.author, p.posted_at, p.url,
               cv.distance
        FROM chunk_vectors cv
        JOIN chunks c ON c.id = cv.rowid
        JOIN posts p ON p.id = c.post_id
        WHERE cv.embedding MATCH ? AND k = ?
        ORDER BY cv.distance
        """,
        (vector_literal(query_vector), fetch_k),
    ).fetchall()

    results = [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            post_id=row["post_id"],
            text=row["text"],
            board=row["board"],
            subject=row["subject"],
            author=row["author"],
            posted_at=row["posted_at"],
            url=row["url"],
            distance=row["distance"],
        )
        for row in rows
    ]

    if since is not None:
        results = [r for r in results if datetime.fromisoformat(r.posted_at) >= since][:top_k]

    log_retrieval_events(conn, run_id, query, [(r.chunk_id, r.distance) for r in results])
    return results
