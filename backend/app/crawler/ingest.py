"""Orchestrates crawling a forum into the `posts` table.

Platform-agnostic: every forum-specific URL/HTML/timestamp convention,
including how "recent activity" is discovered in the first place, lives
behind a `ForumAdapter` (see `crawler/forum_adapter.py`) - this module
never assumes SMF, XenForo, or any other specific software. Which adapter
to use is selected via `FORUM_ADAPTER` (see `config.py` and
`adapter_registry.py`).

Two-phase, deliberately bounded crawl:
  1. Discovery - delegated entirely to `adapter.discover_recent_topics()`,
     which finds topics with in-window activity however this platform's
     discovery actually works (see `forum_adapter.py`'s module docstring
     for why this is one adapter-owned method rather than several small
     shared pieces). Off-topic boards are dropped here, before any topic
     page is even fetched.
  2. Fetch - visit each discovered topic once and keep only the individual
     posts that fall inside the lookback window.
This keeps request volume proportional to *actual recent activity* rather
than the size of the whole forum - the spec's "think about ways to get
around overly large amounts of data".
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.crawler.adapter_registry import get_adapter
from app.crawler.forum_adapter import DiscoveredTopic, ForumAdapter, IngestReport
from app.crawler.http_client import PoliteForumClient
from app.crawler.parser import TopicPost
from app.models import IngestedPost

logger = logging.getLogger(__name__)


def crawl_recent_activity(
    client: PoliteForumClient,
    now: datetime | None = None,
    lookback_days: int | None = None,
    max_posts: int | None = None,
    excluded_boards: tuple[str, ...] | None = None,
    adapter: ForumAdapter | None = None,
    report: IngestReport | None = None,
) -> IngestReport:
    """`report` can be supplied by the caller (rather than always
    constructed here) so a long-running caller - this crawl can take
    minutes under a real rate limit - can hold a reference to the same
    mutable instance and poll its `phase`/`pages_fetched`/`topics_fetched`
    fields for a live progress readout while the crawl is still in
    flight. See api/ingest_job.py."""
    now = now or datetime.now(UTC)
    lookback_days = lookback_days if lookback_days is not None else settings.crawl_lookback_days
    max_posts = max_posts if max_posts is not None else settings.crawl_max_posts
    excluded_boards = excluded_boards if excluded_boards is not None else settings.forum_excluded_boards
    adapter = adapter if adapter is not None else get_adapter(settings.forum_adapter)
    cutoff = now - timedelta(days=lookback_days)
    report = report if report is not None else IngestReport()

    discovered = adapter.discover_recent_topics(client, now, cutoff, excluded_boards, report)
    report.phase = "fetching_topics"
    report.topics_total = len(discovered)

    for topic_id, topic in discovered.items():
        if len(report.posts) >= max_posts:
            break
        _fetch_topic_posts(client, adapter, topic_id, topic, now, cutoff, report)

    report.phase = "done"
    return report


def _fetch_topic_posts(
    client: PoliteForumClient,
    adapter: ForumAdapter,
    topic_id: int,
    topic: DiscoveredTopic,
    now: datetime,
    cutoff: datetime,
    report: IngestReport,
) -> None:
    result = client.fetch(topic.path)
    report.topics_fetched += 1
    if result.status_code != 200:
        report.errors.append(f"topic {topic_id} returned HTTP {result.status_code}")
        return

    subject = adapter.extract_topic_subject(result.html)
    for post in adapter.parse_topic_page(result.html):
        ingested = _build_ingested_post(
            adapter, post, topic_id, topic.board, subject, now, cutoff, client.base_url, report
        )
        if ingested is not None:
            report.posts.append(ingested)


def _build_ingested_post(
    adapter: ForumAdapter,
    post: TopicPost,
    topic_id: int,
    board: str,
    subject: str,
    now: datetime,
    cutoff: datetime,
    base_url: str,
    report: IngestReport,
) -> IngestedPost | None:
    """Build one `IngestedPost`, or None if it's out of the lookback window
    (or its timestamp couldn't be parsed at all)."""
    posted_at = adapter.parse_timestamp(post.posted_at_raw, now)
    if posted_at is None:
        report.skipped_unparsable_timestamp += 1
        return None
    if posted_at < cutoff:
        report.skipped_out_of_window += 1
        return None

    return IngestedPost(
        id=post.msg_id,
        topic_id=topic_id,
        board=board,
        subject=subject,
        author=post.author,
        posted_at=posted_at,
        body=post.body,
        url=adapter.post_url(base_url, topic_id, post.msg_id),
    )
