"""Platform-agnostic fetch-phase orchestration: given a (pre-scripted)
discovery result, does crawl_recent_activity correctly respect max_posts,
filter individual out-of-window posts, handle unparsable timestamps, and
record topic-fetch errors? Discovery mechanics themselves are each
platform's own concern - see test_smf_adapter.py and
test_xenforo_adapter.py - and test_forum_adapter.py separately proves
ingest.py works with a completely unrelated fake platform end-to-end.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.crawler.forum_adapter import DiscoveredTopic
from app.crawler.http_client import FetchResult
from app.crawler.ingest import crawl_recent_activity
from app.crawler.parser import TopicPost

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


class FakeClient:
    """Stands in for PoliteForumClient: returns canned pages without any
    network access."""

    base_url = "https://example-forum.invalid"

    def __init__(self, pages: dict[str, str]):
        self._pages = pages
        self.requested: list[str] = []

    def fetch(self, path: str) -> FetchResult:
        self.requested.append(path)
        html = self._pages.get(path, "")
        return FetchResult(url=path, status_code=200 if html else 404, html=html)


class StubAdapter:
    """Discovery is pre-scripted (a fixed `discovered` dict) so tests can
    drive crawl_recent_activity's *fetch-phase* behavior directly, without
    depending on any real platform's discovery mechanics."""

    name = "stub"

    def __init__(self, discovered: dict[int, DiscoveredTopic], posts_by_html: dict[str, list[TopicPost]]):
        self._discovered = discovered
        self._posts_by_html = posts_by_html

    def discover_recent_topics(self, client, now, cutoff, excluded_boards, report):
        return self._discovered

    def parse_topic_page(self, html: str) -> list[TopicPost]:
        return self._posts_by_html.get(html, [])

    def extract_topic_subject(self, html: str) -> str:
        return "Some Subject"

    def parse_timestamp(self, raw: str, now: datetime) -> datetime | None:
        return None if raw == "unparsable" else datetime.fromisoformat(raw)

    def post_url(self, base_url: str, topic_id: int, msg_id: int) -> str:
        return f"{base_url}/t/{topic_id}#p{msg_id}"


def test_respects_max_posts_cap():
    discovered = {
        1: DiscoveredTopic(board="General", path="/t/1"),
        2: DiscoveredTopic(board="General", path="/t/2"),
    }
    posts_by_html = {
        "<t1>": [TopicPost(msg_id=1, author="Alice", posted_at_raw="2026-09-14T00:00:00+00:00", body="one")],
        "<t2>": [TopicPost(msg_id=2, author="Bob", posted_at_raw="2026-09-14T00:00:00+00:00", body="two")],
    }
    client = FakeClient({"/t/1": "<t1>", "/t/2": "<t2>"})
    adapter = StubAdapter(discovered, posts_by_html)

    report = crawl_recent_activity(client, now=NOW, max_posts=1, excluded_boards=(), adapter=adapter)

    assert len(report.posts) == 1
    assert "/t/2" not in client.requested


def test_topic_fetch_http_error_is_recorded_and_skipped():
    discovered = {1: DiscoveredTopic(board="General", path="/t/missing")}
    client = FakeClient({})  # no pages defined -> every fetch 404s
    adapter = StubAdapter(discovered, {})

    report = crawl_recent_activity(client, now=NOW, excluded_boards=(), adapter=adapter)

    assert report.posts == []
    assert any("404" in e for e in report.errors)


def test_post_outside_window_is_excluded_and_counted():
    discovered = {1: DiscoveredTopic(board="General", path="/t/1")}
    old_post = TopicPost(msg_id=1, author="Alice", posted_at_raw="2020-01-01T00:00:00+00:00", body="old")
    posts_by_html = {"<t1>": [old_post]}
    client = FakeClient({"/t/1": "<t1>"})
    adapter = StubAdapter(discovered, posts_by_html)

    report = crawl_recent_activity(client, now=NOW, lookback_days=7, excluded_boards=(), adapter=adapter)

    assert report.posts == []
    assert report.skipped_out_of_window == 1


def test_post_with_unparsable_timestamp_is_recorded_and_skipped():
    discovered = {1: DiscoveredTopic(board="General", path="/t/1")}
    posts_by_html = {"<t1>": [TopicPost(msg_id=1, author="Alice", posted_at_raw="unparsable", body="?")]}
    client = FakeClient({"/t/1": "<t1>"})
    adapter = StubAdapter(discovered, posts_by_html)

    report = crawl_recent_activity(client, now=NOW, excluded_boards=(), adapter=adapter)

    assert report.posts == []
    assert report.skipped_unparsable_timestamp == 1


def test_ingested_post_fields_are_built_from_discovery_and_topic_page():
    discovered = {42: DiscoveredTopic(board="General Beekeeping", path="/t/42")}
    posts_by_html = {
        "<t42>": [TopicPost(msg_id=7, author="Alice", posted_at_raw="2026-09-14T00:00:00+00:00", body="hello")]
    }
    client = FakeClient({"/t/42": "<t42>"})
    adapter = StubAdapter(discovered, posts_by_html)

    report = crawl_recent_activity(client, now=NOW, excluded_boards=(), adapter=adapter)

    assert len(report.posts) == 1
    post = report.posts[0]
    assert post.id == 7
    assert post.topic_id == 42
    assert post.board == "General Beekeeping"
    assert post.subject == "Some Subject"
    assert post.author == "Alice"
    assert post.body == "hello"
    assert post.url == "https://example-forum.invalid/t/42#p7"
