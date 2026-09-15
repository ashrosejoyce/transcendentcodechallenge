"""Runs a crawl+index pass in the background and tracks its progress, so
the frontend can poll for a live readout instead of one request blocking
for however long `PoliteForumClient`'s rate limit makes the crawl take
(minutes, under a real forum's own robots.txt crawl-delay).

This app is a single process with no auth or multi-tenancy, so "one job
at a time, visible to everyone who asks" is the right model - a full job
queue would be solving a problem this app doesn't have.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from app.crawler.forum_adapter import IngestReport
from app.crawler.http_client import PoliteForumClient
from app.crawler.ingest import crawl_recent_activity
from app.db.connection import get_connection
from app.db.repository import save_posts
from app.rag.indexing import index_pending_posts

logger = logging.getLogger(__name__)


@dataclass
class IngestJobState:
    status: str = "idle"  # "idle" | "running" | "done" | "error"
    report: IngestReport | None = None
    posts_saved: int | None = None
    posts_indexed: int | None = None
    chunks_created: int | None = None
    error: str | None = None


_lock = threading.Lock()
_state = IngestJobState()


def current_status() -> IngestJobState:
    return _state


def start_ingest_job() -> bool:
    """Starts a background ingest run. Returns False (and starts nothing
    new) if one is already running - the caller can just start polling
    `current_status()` either way, since that reflects whichever run is
    actually in flight."""
    with _lock:
        if _state.status == "running":
            return False
        _state.status = "running"
        _state.report = None
        _state.posts_saved = None
        _state.posts_indexed = None
        _state.chunks_created = None
        _state.error = None

    threading.Thread(target=_run_ingest, daemon=True).start()
    return True


def _run_ingest() -> None:
    report = IngestReport()
    _state.report = report  # set before the crawl starts so polling sees it update live
    try:
        with PoliteForumClient() as client:
            crawl_recent_activity(client, report=report)

        with get_connection() as conn:
            saved = save_posts(conn, report.posts)
            index_report = index_pending_posts(conn)

        _state.posts_saved = saved
        _state.posts_indexed = index_report.posts_indexed
        _state.chunks_created = index_report.chunks_created
        _state.status = "done"
    except Exception as exc:  # surfaced to the frontend via status.error, never swallowed
        logger.exception("Background ingest job failed")
        _state.error = str(exc)
        _state.status = "error"
