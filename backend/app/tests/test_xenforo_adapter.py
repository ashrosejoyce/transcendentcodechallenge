"""XenForo-specific discovery mechanics: per-board pagination, with
board exclusion skipping a fetch entirely and a sticky thread's age never
counting as a "stop paginating" signal. See test_ingest.py for the
platform-agnostic fetch-phase orchestration, and test_forum_adapter.py
for proof that ingest.py works with a non-XenForo adapter too.
"""
from datetime import UTC, datetime

from app.crawler.forum_adapter import IngestReport
from app.crawler.http_client import FetchResult
from app.crawler.xenforo_adapter import MAX_PAGES_PER_BOARD, XenForoForumAdapter

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)

BOARD_INDEX = """
<a href="/forums/beekeeping-forum.2/">Beekeeping Forum</a>
<a href="/forums/off-topic-chat.4/">Off Topic Chat</a>
"""


def thread_row(thread_id: int, subject: str, iso_datetime: str, sticky: bool = False) -> str:
    sticky_html = '<i class="structItem-status structItem-status--sticky"></i>' if sticky else ""
    slug = subject.lower().replace(" ", "-")
    return f"""
    <div class="structItem structItem--thread">
      {sticky_html}
      <div class="structItem-title"><a href="/threads/{slug}.{thread_id}/">{subject}</a></div>
      <div class="structItem-cell structItem-cell--latest">
        <a href="/threads/x.{thread_id}/latest"><time datetime="{iso_datetime}">x</time></a>
      </div>
    </div>
    """


class FakeClient:
    base_url = "https://example-forum.invalid"

    def __init__(self, pages: dict[str, str]):
        self._pages = pages
        self.requested: list[str] = []

    def fetch(self, path: str) -> FetchResult:
        self.requested.append(path)
        html = self._pages.get(path, "")
        return FetchResult(url=path, status_code=200 if html else 404, html=html)


def test_excluded_board_listing_is_never_fetched():
    pages = {
        "": BOARD_INDEX,
        "/forums/beekeeping-forum.2/": thread_row(1, "Bulk Honey", "2026-09-15T09:00:00+0100"),
        "/forums/off-topic-chat.4/": thread_row(2, "Off Topic Post", "2026-09-15T09:00:00+0100"),
    }
    client = FakeClient(pages)
    report = IngestReport()

    discovered = XenForoForumAdapter().discover_recent_topics(
        client, now=NOW, cutoff=NOW.replace(year=2020), excluded_boards=("Off Topic",), report=report
    )

    assert report.skipped_excluded_board == 1
    assert "/forums/off-topic-chat.4/" not in client.requested
    assert 1 in discovered
    assert 2 not in discovered


def test_sticky_thread_does_not_stop_pagination():
    # Sticky is old (year 2020) and listed first, as XenForo always pins
    # it; a genuinely recent thread follows. A naive "stop on first old
    # entry" would wrongly discard the real one.
    page1 = thread_row(1, "Old Sticky", "2020-01-01T00:00:00+0000", sticky=True) + thread_row(
        2, "Fresh Post", "2026-09-15T09:00:00+0100"
    )
    pages = {"": BOARD_INDEX.split("\n")[1], "/forums/beekeeping-forum.2/": page1}
    client = FakeClient(pages)
    report = IngestReport()

    discovered = XenForoForumAdapter().discover_recent_topics(
        client, now=NOW, cutoff=NOW.replace(day=1), excluded_boards=(), report=report
    )

    assert 2 in discovered
    # The old sticky itself is genuinely out of window, so it's correctly
    # left out - the point is that it must not also suppress thread 2.
    assert 1 not in discovered


def test_stops_paginating_board_on_old_non_sticky_thread():
    page1 = thread_row(1, "Old Post", "2020-01-01T00:00:00+0000")
    pages = {"": BOARD_INDEX.split("\n")[1], "/forums/beekeeping-forum.2/": page1}
    client = FakeClient(pages)
    report = IngestReport()

    discovered = XenForoForumAdapter().discover_recent_topics(
        client, now=NOW, cutoff=NOW.replace(day=1), excluded_boards=(), report=report
    )

    assert discovered == {}
    # Never even tries page 2 of this board once a non-sticky old entry is seen.
    assert "/forums/beekeeping-forum.2/page-2" not in client.requested


def test_boards_paginate_independently():
    """The key XenForo-vs-SMF difference: running out of in-window
    activity in one board says nothing about another board."""
    old_board_page = thread_row(1, "Old Post", "2020-01-01T00:00:00+0000")
    active_board_page = thread_row(2, "Fresh Post", "2026-09-15T09:00:00+0100")
    pages = {
        "": BOARD_INDEX,
        "/forums/beekeeping-forum.2/": old_board_page,
        "/forums/off-topic-chat.4/": active_board_page,
    }
    client = FakeClient(pages)
    report = IngestReport()

    discovered = XenForoForumAdapter().discover_recent_topics(
        client, now=NOW, cutoff=NOW.replace(day=1), excluded_boards=(), report=report
    )

    assert 1 not in discovered
    assert 2 in discovered


def test_per_board_pagination_is_capped():
    # Every page looks identical and always-fresh, so without a cap this
    # would paginate one board forever.
    endless_fresh_page = thread_row(99, "Always Fresh", "2026-09-15T09:00:00+0100")
    client = FakeClient({"": BOARD_INDEX.split("\n")[1], "/forums/beekeeping-forum.2/": endless_fresh_page})
    for page_num in range(2, MAX_PAGES_PER_BOARD + 5):
        client._pages[f"/forums/beekeeping-forum.2/page-{page_num}"] = endless_fresh_page
    report = IngestReport()

    XenForoForumAdapter().discover_recent_topics(
        client, now=NOW, cutoff=NOW.replace(day=1), excluded_boards=(), report=report
    )

    board_page_requests = [p for p in client.requested if p.startswith("/forums/beekeeping-forum.2")]
    assert len(board_page_requests) == MAX_PAGES_PER_BOARD


def test_post_url_is_slug_and_topic_independent():
    url = XenForoForumAdapter().post_url("https://beekeepingforum.co.uk", topic_id=59604, msg_id=956001)
    assert url == "https://beekeepingforum.co.uk/posts/956001/"


def test_parse_timestamp_delegates_to_xenforo_parser():
    adapter = XenForoForumAdapter()
    assert adapter.parse_timestamp("2026-09-15T19:20:09+0100", NOW) is not None
    assert adapter.parse_timestamp("garbage", NOW) is None
