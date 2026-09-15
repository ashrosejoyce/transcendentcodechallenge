"""Tests the background-job state machine in isolation. `_run_ingest` has
no threading logic of its own (that lives entirely in `start_ingest_job`),
so it's called directly here with its collaborators (the crawl, the DB,
indexing) mocked out - deterministic, no real threads or timing involved.
"""
from datetime import UTC, datetime

from app.api import ingest_job
from app.models import IngestedPost


def reset_state():
    ingest_job._state = ingest_job.IngestJobState()


def make_post(post_id: int = 1) -> IngestedPost:
    return IngestedPost(
        id=post_id,
        topic_id=1,
        board="General",
        subject="subject",
        author="author",
        posted_at=datetime(2026, 9, 15, tzinfo=UTC),
        body="body",
        url="https://example.invalid/1",
    )


class FakeContextManager:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeIndexReport:
    posts_indexed = 1
    chunks_created = 4


def test_current_status_starts_idle():
    reset_state()
    assert ingest_job.current_status().status == "idle"


def test_start_ingest_job_returns_false_if_already_running():
    reset_state()
    ingest_job._state.status = "running"
    assert ingest_job.start_ingest_job() is False


def test_start_ingest_job_marks_running_and_spawns_a_background_thread(monkeypatch):
    reset_state()
    started_targets = []

    class FakeThread:
        def __init__(self, target, daemon):
            started_targets.append(target)

        def start(self):
            pass  # deliberately never runs - this test only checks the synchronous setup

    monkeypatch.setattr(ingest_job.threading, "Thread", FakeThread)

    result = ingest_job.start_ingest_job()

    assert result is True
    assert ingest_job.current_status().status == "running"
    assert started_targets == [ingest_job._run_ingest]


def test_run_ingest_happy_path_marks_done_with_counts(monkeypatch):
    reset_state()

    def fake_crawl(client, report):
        # Mirrors crawl_recent_activity's real contract: mutate the
        # caller-supplied report in place (so a concurrent status poll
        # sees it update live) rather than building a separate one.
        report.posts = [make_post()]
        report.pages_fetched = 3
        report.topics_fetched = 2
        report.topics_total = 2
        report.phase = "done"
        return report

    monkeypatch.setattr(ingest_job, "PoliteForumClient", lambda: FakeContextManager())
    monkeypatch.setattr(ingest_job, "crawl_recent_activity", fake_crawl)
    monkeypatch.setattr(ingest_job, "get_connection", lambda: FakeContextManager())
    monkeypatch.setattr(ingest_job, "save_posts", lambda conn, posts: len(posts))
    monkeypatch.setattr(ingest_job, "index_pending_posts", lambda conn: FakeIndexReport())

    ingest_job._run_ingest()

    status = ingest_job.current_status()
    assert status.status == "done"
    assert status.report.phase == "done"
    assert status.report.topics_total == 2
    assert status.posts_saved == 1
    assert status.posts_indexed == 1
    assert status.chunks_created == 4
    assert status.error is None


def test_run_ingest_records_error_and_never_raises(monkeypatch):
    reset_state()

    def boom(client, report):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(ingest_job, "PoliteForumClient", lambda: FakeContextManager())
    monkeypatch.setattr(ingest_job, "crawl_recent_activity", boom)

    ingest_job._run_ingest()  # must not raise

    status = ingest_job.current_status()
    assert status.status == "error"
    assert "network exploded" in status.error
    assert status.posts_saved is None
