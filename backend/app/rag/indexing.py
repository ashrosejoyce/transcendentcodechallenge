"""Turns newly-crawled posts into chunks + stored embeddings."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.config import settings
from app.db import repository
from app.rag.chunking import chunk_text
from app.rag.embeddings import embed_texts


@dataclass
class IndexingReport:
    posts_indexed: int = 0
    chunks_created: int = 0


def index_pending_posts(conn: sqlite3.Connection) -> IndexingReport:
    """Chunk + embed every post that doesn't have chunks yet."""
    report = IndexingReport()
    posts = repository.fetch_posts_without_chunks(conn)

    for post in posts:
        pieces = chunk_text(
            post["body"],
            max_chars=settings.chunk_max_chars,
            overlap_chars=settings.chunk_overlap_chars,
        )
        if not pieces:
            continue

        vectors = embed_texts(pieces)
        for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
            chunk_id = repository.save_chunk(conn, post["id"], index, piece)
            repository.save_chunk_vector(conn, chunk_id, vector)
            report.chunks_created += 1

        report.posts_indexed += 1

    conn.commit()
    return report
