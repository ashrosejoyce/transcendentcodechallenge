"""Mocks the DB and embedding calls, so this verifies indexing's own
orchestration (which posts get chunked, how counts are tallied) without
needing sqlite-vec or a real embedding model installed."""
from app.rag import indexing


class FakePost(dict):
    """A dict subclass so `post["body"]` / `post["id"]` indexing (as used
    on real sqlite3.Row objects) works on a plain test double."""


class FakeConnection:
    """Stands in for sqlite3.Connection - index_pending_posts only ever
    calls .commit() on it directly (everything else goes through the
    mocked repository functions), so that's all this needs to provide."""

    def commit(self) -> None:
        pass


def test_posts_with_no_extractable_text_are_skipped(monkeypatch):
    monkeypatch.setattr(
        indexing.repository, "fetch_posts_without_chunks", lambda conn: [FakePost(id=1, body="   ")]
    )
    saved_chunks = []

    def fake_save_chunk(conn, post_id, index, text):
        saved_chunks.append(text)
        return 1

    monkeypatch.setattr(indexing.repository, "save_chunk", fake_save_chunk)
    monkeypatch.setattr(indexing.repository, "save_chunk_vector", lambda conn, chunk_id, vector: None)
    monkeypatch.setattr(indexing, "embed_texts", lambda texts: [[0.0]] * len(texts))

    report = indexing.index_pending_posts(conn=FakeConnection())

    assert report.posts_indexed == 0
    assert report.chunks_created == 0
    assert saved_chunks == []


def test_each_chunk_is_saved_with_its_own_embedding(monkeypatch):
    post = FakePost(id=42, body="First paragraph.\nSecond paragraph.")
    monkeypatch.setattr(indexing.repository, "fetch_posts_without_chunks", lambda conn: [post])

    saved_chunk_calls = []
    monkeypatch.setattr(
        indexing.repository,
        "save_chunk",
        lambda conn, post_id, index, text: saved_chunk_calls.append((post_id, index, text)) or (index + 1),
    )
    saved_vector_calls = []
    monkeypatch.setattr(
        indexing.repository,
        "save_chunk_vector",
        lambda conn, chunk_id, vector: saved_vector_calls.append((chunk_id, vector)),
    )
    monkeypatch.setattr(indexing, "embed_texts", lambda texts: [[float(i)] for i in range(len(texts))])

    report = indexing.index_pending_posts(conn=FakeConnection())

    assert report.posts_indexed == 1
    assert report.chunks_created == 1  # short post -> a single chunk
    assert saved_chunk_calls[0][0] == 42
    assert len(saved_vector_calls) == report.chunks_created
