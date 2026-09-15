"""The `ForumAdapter` interface: the seam between forum-platform-specific
crawling logic and the platform-agnostic orchestration in `ingest.py`.

Everything here is something that varies by forum software (SMF,
XenForo, phpBB, Discourse, ...): the URL/HTML shape, how a topic page is
structured, how timestamps are formatted - and, importantly, *how recent
activity is even discovered*. Adding support for a new platform means
writing one class that implements this interface and registering it in
`adapter_registry.py` - nothing else in the codebase needs to change
(Open/Closed: this module is closed for modification, open for extension
by new adapters).

Why discovery is a single adapter-owned method rather than several small
platform-agnostic pieces (as an earlier version of this interface tried):
SMF exposes one global "recent activity" feed, paginated by a numeric
offset, newest-first, where hitting one too-old entry means everything
after it is too old too. XenForo has no such feed reachable to a crawler
(its equivalent, `/whats-new/`, is disallowed by robots.txt on real
installs) - discovery instead means paging each board's own listing
independently, and a too-old entry in board A says nothing about board B.
Those aren't just different URLs; they're different *shapes* of
algorithm, right down to the stopping condition. Forcing every platform
through one shared pagination loop would mean either breaking XenForo or
smuggling SMF-specific assumptions into "platform-agnostic" code. Letting
each adapter own its full discovery method is what actually keeps
`ingest.py` closed for modification.

Adapters shipped today: `smf_adapter.SMFForumAdapter` (Beemaster's Forum)
and `xenforo_adapter.XenForoForumAdapter` (beekeepingforum.co.uk).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.crawler.http_client import PoliteForumClient
from app.crawler.parser import TopicPost
from app.models import IngestedPost


@dataclass
class IngestReport:
    """Shared stats vocabulary every adapter's discovery method reports
    into, so counts stay comparable across platforms even though the
    mechanics producing them differ. `skipped_excluded_board` in
    particular is counted at whatever granularity a platform can offer
    without extra requests - per-entry for SMF's single mixed feed,
    per-board for XenForo (which skips fetching an excluded board's
    listing at all rather than fetching-then-discarding it).

    `phase` and `topics_total` exist only so a caller can poll this same
    (mutable, in-progress) instance for a progress readout while a crawl
    that can take minutes (see PoliteForumClient's rate limiting) is
    still running - see api/ingest_job.py. They carry no meaning once the
    crawl has returned; `phase` just ends at "done"."""

    posts: list[IngestedPost] = field(default_factory=list)
    pages_fetched: int = 0
    topics_fetched: int = 0
    skipped_excluded_board: int = 0
    skipped_out_of_window: int = 0
    skipped_unparsable_timestamp: int = 0
    errors: list[str] = field(default_factory=list)
    phase: str = "discovering"  # "discovering" | "fetching_topics" | "done"
    topics_total: int = 0


@dataclass(frozen=True)
class DiscoveredTopic:
    """One topic/thread discovery found to have in-window activity - the
    board it belongs to, and the exact path to fetch for its content.
    Carrying `path` here (rather than a separate `topic_path(topic_id)`
    adapter method, as an earlier version of this interface had) means a
    platform whose thread URLs aren't derivable from the numeric id alone
    (XenForo's canonical `/threads/<slug>.<id>/` needs the slug) doesn't
    need to reconstruct anything - discovery already knows the URL it
    found the topic at."""

    board: str
    path: str


def is_excluded_board(board: str, excluded_boards: tuple[str, ...]) -> bool:
    """Substring, case-insensitive match rather than exact equality - board
    names drift (a year, a rename), and this keeps the exclusion list
    working without needing to be updated every time a board is renamed.
    Shared by every adapter's discovery method."""
    board_lower = board.lower()
    return any(excluded.lower() in board_lower for excluded in excluded_boards)


class ForumAdapter(Protocol):
    """One implementation per forum platform."""

    name: str

    def discover_recent_topics(
        self,
        client: PoliteForumClient,
        now: datetime,
        cutoff: datetime,
        excluded_boards: tuple[str, ...],
        report: IngestReport,
    ) -> dict[int, DiscoveredTopic]:
        """Find topics with in-window (>= `cutoff`) activity, using
        whatever discovery mechanism this platform actually exposes.
        Returns {topic_id: DiscoveredTopic}.

        Implementations do their own fetching via `client` and should
        record `report.pages_fetched`, `report.skipped_excluded_board`,
        `report.skipped_unparsable_timestamp`, and `report.errors` as
        they go - see `smf_adapter.py` and `xenforo_adapter.py` for the
        two different shapes this takes in practice."""
        ...

    def parse_topic_page(self, html: str) -> list[TopicPost]:
        """Parse a topic/thread page into its individual posts."""
        ...

    def extract_topic_subject(self, html: str) -> str:
        """Best-effort thread subject/title, read from a topic page."""
        ...

    def parse_timestamp(self, raw: str, now: datetime) -> datetime | None:
        """Parse this platform's raw timestamp string into a UTC datetime,
        or None if it can't be parsed. `now` is injected (rather than read
        from the clock) so implementations stay deterministic/testable."""
        ...

    def post_url(self, base_url: str, topic_id: int, msg_id: int) -> str:
        """Build a permalink URL for one specific post."""
        ...
