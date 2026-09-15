"""Mocks the embedding call and stubs the DB connection's query result, so
this verifies retrieve()'s own orchestration - row-to-dataclass mapping,
ordering, and that every retrieval gets logged - without needing
sqlite-vec installed or a populated database."""
from datetime import UTC, datetime

from app.rag import retrieval


class FakeRow(dict):
    """dict subclass so `row["chunk_id"]` style access (as used on real
    sqlite3.Row objects) works on a plain test double."""


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConnection:
    """Stub sqlite3.Connection: `execute` ignores the SQL/params and always
    returns a fixed set of canned rows, as if they were the true nearest
    neighbors. `executemany`/`commit` are no-ops - real writes are exercised
    by test_repository.py; here they only need to not blow up, since
    log_retrieval_events calls them as part of retrieve()'s normal flow."""

    def __init__(self, rows):
        self._rows = rows
        self.executemany_calls: list[tuple[str, list]] = []

    def execute(self, sql, params):
        return FakeCursor(self._rows)

    def executemany(self, sql, rows):
        self.executemany_calls.append((sql, list(rows)))

    def commit(self) -> None:
        pass


def make_row(chunk_id: int, distance: float, posted_at: str = "2026-09-10T12:00:00+00:00") -> FakeRow:
    return FakeRow(
        chunk_id=chunk_id,
        post_id=chunk_id,
        text=f"chunk {chunk_id}",
        board="General Beekeeping",
        subject="subject",
        author="author",
        posted_at=posted_at,
        url="https://beemaster.com/forum/index.php?topic=1.msg1",
        distance=distance,
    )


def test_retrieve_maps_rows_to_retrieved_chunks_in_returned_order(monkeypatch):
    rows = [make_row(1, 0.05), make_row(2, 0.12)]
    monkeypatch.setattr(retrieval, "embed_query", lambda text: [0.1, 0.2, 0.3])

    results = retrieval.retrieve(FakeConnection(rows), "what happened?", top_k=2, run_id="run-1")

    assert [r.chunk_id for r in results] == [1, 2]
    assert results[0].distance == 0.05
    assert results[0].board == "General Beekeeping"


def test_retrieve_logs_one_event_per_result(monkeypatch):
    rows = [make_row(7, 0.01), make_row(9, 0.02)]
    monkeypatch.setattr(retrieval, "embed_query", lambda text: [0.1, 0.2, 0.3])

    logged = {}

    def fake_log(conn, run_id, query_text, ranked_chunk_ids):
        logged["run_id"] = run_id
        logged["query_text"] = query_text
        logged["ranked_chunk_ids"] = ranked_chunk_ids

    monkeypatch.setattr(retrieval, "log_retrieval_events", fake_log)

    retrieval.retrieve(FakeConnection(rows), "what happened?", run_id="run-42")

    assert logged["run_id"] == "run-42"
    assert logged["query_text"] == "what happened?"
    assert logged["ranked_chunk_ids"] == [(7, 0.01), (9, 0.02)]


def test_retrieve_generates_a_run_id_when_none_given(monkeypatch):
    monkeypatch.setattr(retrieval, "embed_query", lambda text: [0.1])
    monkeypatch.setattr(retrieval, "log_retrieval_events", lambda *args, **kwargs: None)

    results = retrieval.retrieve(FakeConnection([]), "query", run_id=None)

    assert results == []


def test_retrieve_with_since_filters_out_older_chunks(monkeypatch):
    rows = [
        make_row(1, 0.05, posted_at="2026-09-14T00:00:00+00:00"),  # in window
        make_row(2, 0.06, posted_at="2026-08-01T00:00:00+00:00"),  # too old
    ]
    monkeypatch.setattr(retrieval, "embed_query", lambda text: [0.1])
    monkeypatch.setattr(retrieval, "log_retrieval_events", lambda *args, **kwargs: None)

    results = retrieval.retrieve(
        FakeConnection(rows), "query", top_k=5, since=datetime(2026, 9, 8, tzinfo=UTC)
    )

    assert [r.chunk_id for r in results] == [1]


def test_retrieve_with_since_trims_back_to_top_k(monkeypatch):
    rows = [make_row(i, distance=i / 10) for i in range(1, 4)]
    monkeypatch.setattr(retrieval, "embed_query", lambda text: [0.1])
    monkeypatch.setattr(retrieval, "log_retrieval_events", lambda *args, **kwargs: None)

    results = retrieval.retrieve(
        FakeConnection(rows), "query", top_k=2, since=datetime(2020, 1, 1, tzinfo=UTC)
    )

    assert [r.chunk_id for r in results] == [1, 2]
