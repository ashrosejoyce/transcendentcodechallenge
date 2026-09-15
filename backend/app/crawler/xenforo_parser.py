"""HTML parsing for XenForo forums - the software powering
beekeepingforum.co.uk.

Design note, mirroring `parser.py`'s approach for SMF: built around
structural invariants rather than theme-specific styling, because those
are the things XenForo's own JS/templating depends on and so won't
change without breaking the site itself:
  1. A thread's canonical URL always contains `/threads/<slug>.<id>/` -
     that numeric id is stable even if the slug is edited later.
  2. Every individual post is an `<article>` whose `id` attribute is
     `js-post-<id>` - required for in-page "jump to this post" links and
     the quote/report/react JS to target the right element.
  3. Timestamps are rendered as semantic `<time datetime="...">` elements
     in ISO-8601 - no natural-language "Today at ..." guessing needed,
     unlike SMF.

One thing XenForo does that SMF doesn't: a board's thread listing always
pins "sticky" threads to the top of page 1, regardless of their own last-
activity date. `XenForoThreadEntry.is_sticky` surfaces that so
`xenforo_adapter.py`'s discovery loop can avoid treating an old sticky as
a signal that everything after it is too old too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from app.crawler.parser import TopicPost

_BOARD_HREF_RE = re.compile(r"/forums/[a-z0-9-]+\.(?P<board_id>\d+)/?(?:$|[?#])", re.IGNORECASE)
_THREAD_HREF_RE = re.compile(r"/threads/[a-z0-9-]+\.(?P<thread_id>\d+)/?(?:$|[?#])", re.IGNORECASE)
_MSG_ID_ATTR_RE = re.compile(r"^js-post-(\d+)$")


@dataclass(frozen=True)
class ForumBoard:
    """One sub-forum, as linked from the forum index page."""

    board_id: int
    name: str
    path: str


@dataclass(frozen=True)
class XenForoThreadEntry:
    """One row from a board's thread-listing page."""

    thread_id: int
    subject: str
    path: str
    latest_post_at_raw: str
    is_sticky: bool


def parse_board_list(html: str) -> list[ForumBoard]:
    """Parse the forum index page into its sub-forums. XenForo's index
    page always renders the full board tree as its main content - that's
    the standard behavior of the software, not a theme quirk - so this
    needs no special "recent activity" endpoint (XenForo's actual
    equivalent, `/whats-new/`, is `Disallow`ed by robots.txt on real
    installs anyway)."""
    soup = BeautifulSoup(html, "lxml")
    seen_ids: set[int] = set()
    boards: list[ForumBoard] = []
    for anchor in soup.find_all("a", href=_BOARD_HREF_RE):
        match = _BOARD_HREF_RE.search(anchor["href"])
        board_id = int(match.group("board_id"))
        if board_id in seen_ids:
            continue
        name = anchor.get_text(strip=True)
        if not name:
            continue
        seen_ids.add(board_id)
        boards.append(ForumBoard(board_id=board_id, name=name, path=anchor["href"]))
    return boards


def parse_board_threads(html: str) -> list[XenForoThreadEntry]:
    """Parse one page of a board's thread listing (sorted newest-activity-
    first by default, which is exactly the "recent activity" signal SMF
    gets from its global feed - just scoped to one board)."""
    soup = BeautifulSoup(html, "lxml")
    entries = (_build_thread_entry(row) for row in soup.select(".structItem--thread"))
    return [entry for entry in entries if entry is not None]


def _build_thread_entry(row: Tag) -> XenForoThreadEntry | None:
    title_link = row.select_one(".structItem-title a[href]")
    if title_link is None:
        return None
    match = _THREAD_HREF_RE.search(title_link["href"])
    if not match:
        return None

    latest_time = row.select_one(".structItem-cell--latest time[datetime]")
    if latest_time is None:
        return None

    return XenForoThreadEntry(
        thread_id=int(match.group("thread_id")),
        subject=title_link.get_text(strip=True),
        path=title_link["href"],
        latest_post_at_raw=latest_time["datetime"],
        is_sticky=row.select_one(".structItem-status--sticky") is not None,
    )


def extract_topic_subject(html: str) -> str:
    """Best-effort thread subject, read from the page `<title>` (XenForo
    renders it as "Thread Title | Forum Name")."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    return title.split(" | ")[0].strip() if title else "(untitled thread)"


def parse_topic_page(html: str) -> list[TopicPost]:
    """Parse a thread page into its individual posts.

    Relies on every post being an `<article id="js-post-NNN">` - see
    module docstring."""
    soup = BeautifulSoup(html, "lxml")
    posts: list[TopicPost] = []

    for node in soup.find_all(id=_MSG_ID_ATTR_RE):
        match = _MSG_ID_ATTR_RE.match(node.get("id", ""))
        if not match:
            continue

        body = _extract_post_body(node)
        if not body:
            continue

        posts.append(
            TopicPost(
                msg_id=int(match.group(1)),
                author=_extract_author(node),
                posted_at_raw=_extract_timestamp_raw(node),
                body=body,
            )
        )
    return posts


def parse_xenforo_timestamp(raw: str, now: datetime) -> datetime | None:
    """XenForo's timestamps are already ISO-8601 (from a `<time
    datetime="...">` attribute), so there's no natural-language format to
    guess at - just parse it, or report failure. `now` is accepted (and
    unused) only to keep this interchangeable with `parse_smf_timestamp`
    behind the `ForumAdapter.parse_timestamp` interface."""
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _extract_author(container: Tag) -> str:
    name_el = container.select_one(".message-name .username")
    return name_el.get_text(strip=True) if name_el else ""


def _extract_timestamp_raw(container: Tag) -> str:
    time_el = container.select_one(".message-attribution-main time[datetime]")
    return time_el["datetime"] if time_el else ""


def _extract_post_body(container: Tag) -> str:
    working = BeautifulSoup(str(container), "lxml")
    for quote in working.select(".bbCodeQuote"):
        quote.decompose()

    # Scoping to `.message-content .bbWrapper` (rather than the whole
    # container's get_text()) is what keeps the author sidebar and
    # attribution header out of the body - XenForo's signature block lives
    # in a sibling `.message-signature` outside `.message-content`
    # entirely, so unlike SMF's `.signature`, it never needs decomposing.
    content = working.select_one(".message-content .bbWrapper") or working
    text = content.get_text("\n", strip=True)
    lines = [line for line in text.split("\n") if line.strip()]
    return "\n".join(lines).strip()
