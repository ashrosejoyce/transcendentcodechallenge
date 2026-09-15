"""Adapter for forums running XenForo - the software powering
beekeepingforum.co.uk.

Discovery here works nothing like SMF's: XenForo has no site-wide
"recent activity" feed a crawler is allowed to use (its equivalent,
`/whats-new/`, is `Disallow`ed by this forum's robots.txt), so instead
this fetches the forum's board list once, then pages each non-excluded
board's own thread listing (which XenForo already sorts by most-recent-
activity) until it falls off the lookback window. See
`forum_adapter.py`'s module docstring for why that's a difference in
*shape*, not just URL/HTML conventions, and so belongs in this adapter's
own `discover_recent_topics` rather than a shared pagination loop.

This also means board exclusion works differently (and more cheaply)
here than in SMF: an excluded board's thread listing is never fetched at
all, rather than fetched and then filtered per-entry.

All the actual HTML-parsing logic lives in `xenforo_parser.py`, kept
separate so it stays independently unit-testable against plain HTML
strings with zero network access.
"""
from __future__ import annotations

from datetime import datetime

from app.crawler.forum_adapter import DiscoveredTopic, ForumAdapter, IngestReport, is_excluded_board
from app.crawler.http_client import ForumClient
from app.crawler.parser import TopicPost
from app.crawler.xenforo_parser import (
    ForumBoard,
    XenForoThreadEntry,
    extract_topic_subject,
    parse_board_list,
    parse_board_threads,
    parse_topic_page,
    parse_xenforo_timestamp,
)

# Bounded per board (unlike SMF's single global feed with one big page
# cap) because discovery here means paging *every* non-excluded board
# independently - a busy forum's front page of any one board almost
# always covers a week or more of activity already, so this stays small.
MAX_PAGES_PER_BOARD = 3


class XenForoForumAdapter(ForumAdapter):
    """See module docstring. Register new platforms in `adapter_registry.py`."""

    name = "xenforo"

    def discover_recent_topics(
        self,
        client: ForumClient,
        now: datetime,
        cutoff: datetime,
        excluded_boards: tuple[str, ...],
        report: IngestReport,
    ) -> dict[int, DiscoveredTopic]:
        discovered: dict[int, DiscoveredTopic] = {}

        for board in self._discover_boards(client, report):
            if is_excluded_board(board.name, excluded_boards):
                report.skipped_excluded_board += 1
                continue
            self._discover_board_topics(client, board, now, cutoff, report, discovered)

        return discovered

    def _discover_boards(self, client: ForumClient, report: IngestReport) -> list[ForumBoard]:
        result = client.fetch("")
        report.pages_fetched += 1
        if result.status_code != 200:
            report.errors.append(f"forum index returned HTTP {result.status_code}")
            return []
        return parse_board_list(result.html)

    def _discover_board_topics(
        self,
        client: ForumClient,
        board: ForumBoard,
        now: datetime,
        cutoff: datetime,
        report: IngestReport,
        discovered: dict[int, DiscoveredTopic],
    ) -> None:
        for page_num in range(1, MAX_PAGES_PER_BOARD + 1):
            path = board.path if page_num == 1 else f"{board.path}page-{page_num}"
            result = client.fetch(path)
            report.pages_fetched += 1
            if result.status_code != 200:
                report.errors.append(f"board {board.name!r} page {page_num} returned HTTP {result.status_code}")
                return

            entries = parse_board_threads(result.html)
            if not entries:
                return

            if self._collect_in_window_threads(entries, board.name, now, cutoff, report, discovered):
                return

    def _collect_in_window_threads(
        self,
        entries: list[XenForoThreadEntry],
        board_name: str,
        now: datetime,
        cutoff: datetime,
        report: IngestReport,
        discovered: dict[int, DiscoveredTopic],
    ) -> bool:
        """Add each in-window thread to `discovered` (mutated in place).
        Returns True once a *non-sticky* entry older than `cutoff` is seen
        - a sticky thread is always pinned to the top of page 1 regardless
        of its own last-activity date, so its age must never be treated as
        a "stop paginating" signal the way it would be in SMF's strictly
        newest-first feed."""
        for entry in entries:
            posted_at = parse_xenforo_timestamp(entry.latest_post_at_raw, now)
            if posted_at is None:
                report.skipped_unparsable_timestamp += 1
                continue
            if posted_at < cutoff:
                if entry.is_sticky:
                    continue
                return True
            discovered.setdefault(entry.thread_id, DiscoveredTopic(board=board_name, path=entry.path))
        return False

    def parse_topic_page(self, html: str) -> list[TopicPost]:
        return parse_topic_page(html)

    def extract_topic_subject(self, html: str) -> str:
        return extract_topic_subject(html)

    def parse_timestamp(self, raw: str, now: datetime) -> datetime | None:
        return parse_xenforo_timestamp(raw, now)

    def post_url(self, base_url: str, topic_id: int, msg_id: int) -> str:
        # XenForo's `/posts/<id>/` short-permalink form is slug/thread-
        # independent (it redirects to the post's canonical location), so
        # this needs neither the thread's slug nor its topic_id.
        return f"{base_url}/posts/{msg_id}/"
