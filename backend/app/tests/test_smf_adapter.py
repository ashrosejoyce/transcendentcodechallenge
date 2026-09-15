"""SMF-specific discovery mechanics: single global feed, paginated by a
numeric offset, newest-first. See test_ingest.py for the platform-agnostic
fetch-phase orchestration, and test_forum_adapter.py for proof that
ingest.py works with a non-SMF adapter too.
"""
from datetime import UTC, datetime

from app.crawler.forum_adapter import IngestReport, is_excluded_board
from app.crawler.http_client import FetchResult
from app.crawler.ingest import crawl_recent_activity
from app.crawler.smf_adapter import SMFForumAdapter

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)

RECENT_PAGE_IN_WINDOW = """
<a href="index.php?topic=1.msg1#msg1">Fresh post</a>
by <a href="index.php?action=profile;u=1">Alice</a> - Today at 08:00:00 AM
&raquo; <a href="index.php?board=1.0">General Beekeeping</a>
"""

RECENT_PAGE_EXCLUDED_BOARD = """
<a href="index.php?topic=2.msg2#msg2">Off topic</a>
by <a href="index.php?action=profile;u=2">Bob</a> - Today at 08:00:00 AM
&raquo; <a href="index.php?board=2.0">Humor</a>
"""

TOPIC_PAGE = """
<html><head><title>Fresh post - General Beekeeping</title></head>
<body><div id="msg1">
<a href="index.php?action=profile;u=1">Alice</a>
<div class="smalltext">Today at 08:00:00 AM</div>
This is the actual post body about swarm season.
</div></body></html>
"""


class FakeClient:
    """Stands in for PoliteForumClient: returns canned pages without any
    network access, so ingest.py's orchestration logic is fully testable."""

    base_url = "https://beemaster.com/forum"

    def __init__(self, pages: dict[str, str]):
        self._pages = pages
        self.requested: list[str] = []

    def fetch(self, path: str) -> FetchResult:
        self.requested.append(path)
        html = self._pages.get(path, "")
        return FetchResult(url=path, status_code=200 if html else 404, html=html)


def test_excluded_boards_are_skipped_before_fetching_topics():
    pages = {
        "index.php?action=recent&start=0": RECENT_PAGE_EXCLUDED_BOARD,
    }
    client = FakeClient(pages)

    report = crawl_recent_activity(client, now=NOW, excluded_boards=("Humor",), adapter=SMFForumAdapter())

    assert report.skipped_excluded_board == 1
    assert report.posts == []
    assert not any("topic=2" in req for req in client.requested)


def test_in_window_post_is_ingested_with_full_body():
    pages = {
        "index.php?action=recent&start=0": RECENT_PAGE_IN_WINDOW,
        "index.php?topic=1.0": TOPIC_PAGE,
    }
    client = FakeClient(pages)

    report = crawl_recent_activity(client, now=NOW, excluded_boards=(), adapter=SMFForumAdapter())

    assert len(report.posts) == 1
    post = report.posts[0]
    assert post.id == 1
    assert post.board == "General Beekeeping"
    assert post.subject == "Fresh post"
    assert "swarm season" in post.body


def test_stops_paginating_once_recent_feed_is_empty():
    pages = {"index.php?action=recent&start=0": RECENT_PAGE_IN_WINDOW}
    client = FakeClient(pages)  # start=25 not defined -> parses to 0 entries

    crawl_recent_activity(client, now=NOW, excluded_boards=(), adapter=SMFForumAdapter())

    assert client.requested.count("index.php?action=recent&start=0") == 1
    assert "index.php?action=recent&start=50" not in client.requested


def test_out_of_window_posts_are_excluded():
    old_post_page = RECENT_PAGE_IN_WINDOW.replace("Today at 08:00:00 AM", "January 01, 2020 at 08:00:00 AM")
    pages = {"index.php?action=recent&start=0": old_post_page}
    client = FakeClient(pages)

    report = crawl_recent_activity(client, now=NOW, lookback_days=7, excluded_boards=(), adapter=SMFForumAdapter())

    assert report.posts == []


def test_discover_recent_topics_reports_pages_fetched():
    # Only start=0 is defined, so page 2 (start=25) 404s and stops
    # pagination - this fixture has just one, always-in-window post, so
    # nothing on page 1 itself signals a stop.
    pages = {"index.php?action=recent&start=0": RECENT_PAGE_IN_WINDOW}
    client = FakeClient(pages)
    report = IngestReport()

    discovered = SMFForumAdapter().discover_recent_topics(
        client, now=NOW, cutoff=NOW.replace(year=2020), excluded_boards=(), report=report
    )

    assert report.pages_fetched == 2
    assert discovered[1].board == "General Beekeeping"
    assert discovered[1].path == "index.php?topic=1.0"


def test_is_excluded_board_matching_is_substring_not_exact():
    # Real Beemaster board names drift ("Forum Bylaws 2019" this year, maybe
    # "Forum Bylaws 2027" later) - the exclusion list should still catch them.
    assert is_excluded_board("Forum Bylaws 2019", ("Forum Bylaws",)) is True
    assert is_excluded_board("Computer Tech Help Forum", ("Computer Tech Help",)) is True
    assert is_excluded_board("General Beekeeping", ("Humor", "2nd Amendment")) is False
