"""Flattens the high-dimensional chunk embeddings down to 2D for the
frontend's scatter-plot visualization (spec item 3b)."""
from __future__ import annotations

import sqlite3
import struct

from app.db.repository import all_chunks_with_vectors, retrieval_counts


def flattened_embeddings(conn: sqlite3.Connection) -> list[dict]:
    rows = all_chunks_with_vectors(conn)
    if len(rows) < 2:
        return []

    vectors = [_decode_vector(row["embedding"]) for row in rows]
    points_2d = _project_to_2d(vectors)

    counts_by_chunk = {row["chunk_id"]: row["retrieval_count"] for row in retrieval_counts(conn, limit=10_000)}

    return [
        {
            "chunk_id": row["id"],
            "x": round(float(point[0]), 4),
            "y": round(float(point[1]), 4),
            "board": row["board"],
            "subject": row["subject"],
            "snippet": row["text"][:140],
            "retrieval_count": counts_by_chunk.get(row["id"], 0),
        }
        for row, point in zip(rows, points_2d, strict=True)
    ]


def _project_to_2d(vectors: list[list[float]]):
    import numpy as np
    from sklearn.decomposition import PCA

    matrix = np.array(vectors)
    n_components = min(2, matrix.shape[0], matrix.shape[1])
    reduced = PCA(n_components=n_components, random_state=42).fit_transform(matrix)
    if n_components == 1:
        reduced = np.pad(reduced, ((0, 0), (0, 1)))
    return reduced


def _decode_vector(blob: bytes) -> list[float]:
    """sqlite-vec stores `float[N]` columns as raw little-endian float32 blobs."""
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))
