"""Covers the ForumAdapter seam itself: that the registry resolves/rejects
platform names correctly, and - the actual point of the adapter pattern -
that ingest.py's crawl orchestration works with *any* ForumAdapter, not
just the shipped ones, including one whose discovery mechanics look
nothing like SMF's or XenForo's.
"""
from datetime import UTC, datetime

import pytest

from app.crawler.adapter_registry import get_adapter
from app.crawler.forum_adapter import DiscoveredTopic, IngestReport
from app.crawler.http_client import FetchResult
from app.crawler.ingest import crawl_recent_activity
from app.crawler.parser import TopicPost
from app.crawler.smf_adapter import SMFForumAdapter
from app.crawler.xenforo_adapter import XenForoForumAdapter

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


def test_get_adapter_returns_the_smf_adapter_by_name():
    adapter = get_adapter("smf")
    assert isinstance(adapter, SMFForumAdapter)
    assert adapter.name == "smf"


def test_get_adapter_returns_the_xenforo_adapter_by_name():
    adapter = get_adapter("xenforo")
    assert isinstance(adapter, XenForoForumAdapter)
    assert adapter.name == "xenforo"


def test_get_adapter_rejects_an_unregistered_platform_name():
    with pytest.raises(ValueError, match="Unknown forum adapter 'made-up-platform'"):
        get_adapter("made-up-platform")


class FakeClient:
    """No network access - matches PoliteForumClient's interface (base_url
    attribute + fetch(path) -> FetchResult)."""

    base_url = "https://example-forum.invalid"

    def __init__(self, pages: dict[str, str]):
        self._pages = pages
        self.requested: list[str] = []

    def fetch(self, path: str) -> FetchResult:
        self.requested.append(path)
        html = self._pages.get(path, "")
        return FetchResult(url=path, status_code=200 if html else 404, html=html)


class FakePlatformAdapter:
    """A minimal stand-in for a completely different, made-up forum
    platform - deliberately using discovery mechanics unrelated to either
    shipped adapter's (a single made-up "digest" page, no pagination at
    all) to prove ingest.py's orchestration never assumes anything about
    *how* discovery works and only ever talks to the ForumAdapter
    interface."""

    name = "fake-platform"

    def discover_recent_topics(
        self,
        client,
        now: datetime,
        cutoff: datetime,
        excluded_boards: tuple[str, ...],
        report: IngestReport,
    ) -> dict[int, DiscoveredTopic]:
        result = client.fetch("digest")
        report.pages_fetched += 1
        if result.status_code != 200:
            return {}
        return {1: DiscoveredTopic(board="General", path="topic/1")}

    def parse_topic_page(self, html: str) -> list[TopicPost]:
        if not html:
            return []
        return [TopicPost(msg_id=1, author="Ada", posted_at_raw="now", body="Hello from a made-up platform.")]

    def extract_topic_subject(self, html: str) -> str:
        return "Hello"

    def parse_timestamp(self, raw: str, now: datetime):
        return now if raw == "now" else None

    def post_url(self, base_url: str, topic_id: int, msg_id: int) -> str:
        return f"{base_url}/t/{topic_id}#p{msg_id}"


def test_crawl_recent_activity_works_with_any_forum_adapter():
    """Swap in a fake, non-SMF/non-XenForo platform adapter and confirm the
    crawl orchestration needs no changes to support it."""
    client = FakeClient({"digest": "<digest>", "topic/1": "<topic page>"})

    report = crawl_recent_activity(client, now=NOW, excluded_boards=(), adapter=FakePlatformAdapter())

    assert len(report.posts) == 1
    post = report.posts[0]
    assert post.subject == "Hello"
    assert post.body == "Hello from a made-up platform."
    assert post.url == "https://example-forum.invalid/t/1#p1"
    # Confirms it used the fake adapter's own discovery/URL shape, not
    # SMF's or XenForo's.
    assert "index.php" not in " ".join(client.requested)
    assert "threads" not in " ".join(client.requested)
