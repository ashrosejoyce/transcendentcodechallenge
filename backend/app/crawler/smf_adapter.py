"""Adapter for forums running Simple Machines Forum (SMF) - the software
powering Beemaster's Forum.

Discovery here works off SMF's one global "recent activity" feed
(`action=recent`), paginated by a numeric `start` offset, newest-first:
once one entry older than the cutoff is seen, everything after it (this
page and every later page) is too old too, so we can stop outright. See
`forum_adapter.py`'s module docstring for why this is a fundamentally
different shape from `xenforo_adapter.py`'s per-board discovery, and thus
why each adapter owns its whole discovery method rather than sharing one
generic pagination loop.

All the actual HTML-parsing logic lives in `parser.py`, kept separate so
it stays independently unit-testable against plain HTML strings with zero
network access (see `tests/test_parser.py`).
"""
from __future__ import annotations

from datetime import datetime

from app.crawler.forum_adapter import DiscoveredTopic, ForumAdapter, IngestReport, is_excluded_board
from app.crawler.http_client import ForumClient
from app.crawler.parser import (
    RecentPostEntry,
    TopicPost,
    extract_topic_subject,
    parse_recent_posts,
    parse_smf_timestamp,
    parse_topic_page,
)

RECENT_PAGE_SIZE = 25
MAX_RECENT_PAGES = 20  # hard safety ceiling regardless of lookback window


class SMFForumAdapter(ForumAdapter):
    """See module docstring. Register new platforms in `adapter_registry.py`."""

    name = "smf"

    def discover_recent_topics(
        self,
        client: ForumClient,
        now: datetime,
        cutoff: datetime,
        excluded_boards: tuple[str, ...],
        report: IngestReport,
    ) -> dict[int, DiscoveredTopic]:
        discovered: dict[int, DiscoveredTopic] = {}
        start = 0

        for _ in range(MAX_RECENT_PAGES):
            entries, fetched_ok = self._fetch_recent_entries_page(client, start, report)
            if not fetched_ok or not entries:
                break

            reached_cutoff = self._collect_in_window_topics(entries, now, cutoff, excluded_boards, report, discovered)
            if reached_cutoff:
                break
            start += RECENT_PAGE_SIZE

        return discovered

    def _fetch_recent_entries_page(
        self, client: ForumClient, start: int, report: IngestReport
    ) -> tuple[list[RecentPostEntry], bool]:
        """Fetch one page of the recent-posts feed. Returns (entries, ok) -
        ok is False on a non-200 response, which the caller treats as
        "stop paginating" rather than a fatal error."""
        result = client.fetch(f"index.php?action=recent&start={start}")
        report.pages_fetched += 1
        if result.status_code != 200:
            report.errors.append(f"recent feed page start={start} returned HTTP {result.status_code}")
            return [], False
        return parse_recent_posts(result.html, client.base_url), True

    def _collect_in_window_topics(
        self,
        entries: list[RecentPostEntry],
        now: datetime,
        cutoff: datetime,
        excluded_boards: tuple[str, ...],
        report: IngestReport,
        discovered: dict[int, DiscoveredTopic],
    ) -> bool:
        """Add each in-window, non-excluded entry's topic to `discovered`
        (mutated in place). Returns True as soon as an entry older than
        `cutoff` is seen - the feed is newest-first, so that means every
        remaining entry (on this page and any later page) is too old too."""
        for entry in entries:
            if is_excluded_board(entry.board, excluded_boards):
                report.skipped_excluded_board += 1
                continue

            posted_at = parse_smf_timestamp(entry.posted_at_raw, now)
            if posted_at is None:
                report.skipped_unparsable_timestamp += 1
                continue
            if posted_at < cutoff:
                return True

            topic_path = f"index.php?topic={entry.topic_id}.0"
            discovered.setdefault(entry.topic_id, DiscoveredTopic(board=entry.board, path=topic_path))
        return False

    def parse_topic_page(self, html: str) -> list[TopicPost]:
        return parse_topic_page(html)

    def extract_topic_subject(self, html: str) -> str:
        return extract_topic_subject(html)

    def parse_timestamp(self, raw: str, now: datetime) -> datetime | None:
        return parse_smf_timestamp(raw, now)

    def post_url(self, base_url: str, topic_id: int, msg_id: int) -> str:
        return f"{base_url}/index.php?topic={topic_id}.msg{msg_id}#msg{msg_id}"
