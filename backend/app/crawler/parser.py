"""HTML parsing for Simple Machines Forum (SMF) pages - the software that
powers Beemaster's Forum.

Design note - why this parser avoids CSS-class selectors:
SMF themes (Curve, Core, custom skins) all wrap posts in different CSS
classes, but two things are stable across every SMF install because the
software's own linking depends on them:
  1. Topic links always contain `topic=<id>.msg<id>` or `topic=<id>.<offset>`
     in the href - SMF's routing has used this URL shape since 1.x.
  2. Every individual post is a DOM node whose `id` attribute is `msg<id>`
     (or contains an `<a name="msg<id>">` anchor) - required so that
     "jump to this post" links (`#msgNNN`) work at all.
This parser is built around those two invariants instead of guessing at
theme-specific class names, so it is more likely to keep working if
Beemaster's theme changes, and it is testable against any HTML that
respects the SMF URL/anchor conventions (see tests/test_parser.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from bs4 import BeautifulSoup, Tag

_TOPIC_HREF_RE = re.compile(r"topic=(?P<topic_id>\d+)\.(?:msg(?P<msg_id>\d+)|\d+)")
_BOARD_HREF_RE = re.compile(r"board=(?P<board_id>\d+)\.\d+")
_MSG_ID_ATTR_RE = re.compile(r"^msg(\d+)$")

_TIME_RE = re.compile(
    # SMF's date/time format is an admin-configurable setting, so the
    # separator before the clock time varies by install - Beemaster's Forum
    # uses "Today at 8:04:12 PM" while others (e.g. smftricks.com) use
    # "Today, 8:04:12 PM" for the same underlying software.
    r"(?P<label>Today|Yesterday|[A-Z][a-z]+ \d{1,2}, \d{4})(?: at |, ?)"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2}) ?(?P<meridiem>[ap]m)",
    re.IGNORECASE,
)

# A container needs at least this much text to plausibly hold a whole post
# (author + timestamp + body) rather than just a stray link or icon.
_MIN_POST_CONTAINER_CHARS = 40
# Safety cap on how far up the DOM we'll walk looking for a container -
# real SMF markup is never nested deeper than this between a link and its
# enclosing post/row.
_MAX_ANCESTOR_WALK_DEPTH = 6
_BLOCK_CONTAINER_TAGS = ("tr", "li", "div")
_POST_CONTAINER_TAGS = ("div", "td", "article")


@dataclass(frozen=True)
class RecentPostEntry:
    """One row from the forum-wide action=recent feed."""

    topic_id: int
    msg_id: int | None
    subject: str
    board: str
    author: str
    posted_at_raw: str
    url: str


@dataclass(frozen=True)
class TopicPost:
    """One individual post extracted from a topic thread page."""

    msg_id: int
    author: str
    posted_at_raw: str
    body: str


def parse_recent_posts(html: str, base_url: str) -> list[RecentPostEntry]:
    """Parse the output of `index.php?action=recent` into structured entries.

    Each entry in SMF's recent-posts feed is anchored by a link to the topic
    (containing `topic=ID.msgID`); building one `RecentPostEntry` from that
    anchor is delegated to `_build_recent_entry` so this function's only job
    is "find the candidate anchors and keep the valid entries".
    """
    soup = BeautifulSoup(html, "lxml")
    seen_msg_ids: set[int] = set()
    entries = (
        _build_recent_entry(anchor, base_url, seen_msg_ids)
        for anchor in soup.find_all("a", href=_TOPIC_HREF_RE)
    )
    return [entry for entry in entries if entry is not None]


def _build_recent_entry(anchor: Tag, base_url: str, seen_msg_ids: set[int]) -> RecentPostEntry | None:
    """Build one entry from a topic-link anchor, or None if it isn't a
    genuine recent-post row - e.g. a duplicate icon link for a post we
    already captured, or a "jump to board" link with no author/timestamp.
    `seen_msg_ids` is updated in place so duplicates across the whole page
    are only ever recorded once."""
    match = _TOPIC_HREF_RE.search(anchor["href"])
    if not match:
        return None

    msg_id = int(match.group("msg_id")) if match.group("msg_id") else None
    if msg_id is not None and msg_id in seen_msg_ids:
        return None

    block = _nearest_block_container(anchor)
    block_text = block.get_text(" ", strip=True)
    author = _extract_author(block, block_text)
    posted_at_raw = _extract_timestamp_raw(block_text)
    if not author or not posted_at_raw:
        return None

    if msg_id is not None:
        seen_msg_ids.add(msg_id)

    return RecentPostEntry(
        topic_id=int(match.group("topic_id")),
        msg_id=msg_id,
        subject=anchor.get_text(strip=True) or "(no subject)",
        board=_extract_board(block, block_text) or "Unknown Board",
        author=author,
        posted_at_raw=posted_at_raw,
        url=_absolutize(anchor["href"], base_url),
    )


def extract_topic_subject(html: str) -> str:
    """Best-effort thread subject, read from the page `<title>` (SMF renders
    it as "Subject - Board Name" or similar, so we take the first segment)."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    return title.split(" - ")[0].strip() if title else "(untitled thread)"


def parse_topic_page(html: str) -> list[TopicPost]:
    """Parse a topic/thread page into its individual posts.

    Relies on every post being reachable at an `id="msgNNN"` (or
    `<a name="msgNNN">`) anchor - see module docstring.
    """
    soup = BeautifulSoup(html, "lxml")
    posts: list[TopicPost] = []

    for node in soup.find_all(id=_MSG_ID_ATTR_RE):
        match = _MSG_ID_ATTR_RE.match(node.get("id", ""))
        if not match:
            continue
        msg_id = int(match.group(1))

        container = _nearest_post_container(node)
        body = _extract_post_body(container)
        block_text = container.get_text(" ", strip=True)

        author = _extract_author(container, block_text)
        posted_at_raw = _extract_timestamp_raw(block_text)

        if not body:
            continue

        posts.append(
            TopicPost(
                msg_id=msg_id,
                author=author or "Unknown",
                posted_at_raw=posted_at_raw or "",
                body=body,
            )
        )
    return posts


def parse_smf_timestamp(raw: str, now: datetime) -> datetime | None:
    """Convert SMF's "Today at 8:04:12 PM" style strings into a UTC datetime.

    `now` is injected (rather than read from the clock) so this function is
    deterministic and trivially unit-testable.
    """
    match = _TIME_RE.search(raw)
    if not match:
        return None

    hour = int(match.group("hour")) % 12
    if match.group("meridiem").lower() == "pm":
        hour += 12
    minute, second = int(match.group("minute")), int(match.group("second"))

    label = match.group("label")
    if label == "Today":
        day = now.date()
    elif label == "Yesterday":
        day = (now - timedelta(days=1)).date()
    else:
        day = datetime.strptime(label, "%B %d, %Y").date()

    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=now.tzinfo)


# --- internal helpers -------------------------------------------------


def _walk_ancestors(node: Tag, max_depth: int = _MAX_ANCESTOR_WALK_DEPTH):
    """Yield each ancestor of `node`, nearest first, up to `max_depth`
    levels - the shared traversal both container-finders below build on."""
    current = node
    for _ in range(max_depth):
        if current.parent is None:
            return
        current = current.parent
        yield current


def _looks_like_a_full_post(tag: Tag) -> bool:
    """Heuristic: enough text to plausibly be a whole post rather than a
    stray link or icon (see `_MIN_POST_CONTAINER_CHARS`)."""
    return len(tag.get_text(strip=True)) > _MIN_POST_CONTAINER_CHARS


def _spans_multiple_posts(tag: Tag) -> bool:
    """True if `tag` contains more than one `id="msgNNN"` node - i.e. it
    wraps at least two distinct posts, so it's not a safe container for
    "this one post"."""
    return len(tag.find_all(id=_MSG_ID_ATTR_RE)) > 1


def _nearest_block_container(anchor: Tag) -> Tag:
    """Walk up from a link to the nearest ancestor likely to hold a whole
    "recent post" row (a table row, list item, or div)."""
    for ancestor in _walk_ancestors(anchor):
        if ancestor.name in _BLOCK_CONTAINER_TAGS:
            return ancestor
    return anchor.parent or anchor


def _nearest_post_container(anchor: Tag) -> Tag:
    """Find the smallest ancestor that holds this one post's content.

    Unlike `_nearest_block_container`, this must never cross into an
    ancestor that also contains a *different* post - otherwise the author
    for post B could be mis-read as post A's author - so it stops walking
    up as soon as the next ancestor would span more than one post.
    """
    if _looks_like_a_full_post(anchor):
        return anchor

    node = anchor
    for ancestor in _walk_ancestors(anchor):
        if _spans_multiple_posts(ancestor):
            break
        node = ancestor
        if node.name in _POST_CONTAINER_TAGS and _looks_like_a_full_post(node):
            return node
    return node


def _extract_author(container: Tag | None, block_text: str) -> str:
    if container is not None:
        profile_link = container.find("a", href=re.compile(r"action=profile"))
        if profile_link and profile_link.get_text(strip=True):
            return profile_link.get_text(strip=True)
    match = re.search(r"\bby\s+([A-Za-z0-9_.\-]+)", block_text)
    return match.group(1) if match else ""


def _extract_board(container: Tag | None, block_text: str) -> str:
    if container is not None:
        board_link = container.find("a", href=_BOARD_HREF_RE)
        if board_link and board_link.get_text(strip=True):
            return board_link.get_text(strip=True)
    match = re.search(r"[»›>]\s*([A-Za-z][A-Za-z0-9 &/'\-]{2,60})$", block_text.strip())
    return match.group(1).strip() if match else ""


def _extract_timestamp_raw(block_text: str) -> str:
    match = _TIME_RE.search(block_text)
    return match.group(0) if match else ""


def _extract_post_body(container: Tag) -> str:
    working = BeautifulSoup(str(container), "lxml")
    for quote in working.select(".quote, blockquote, .quoteheader"):
        quote.decompose()
    for signature in working.select(".signature"):
        signature.decompose()

    # On themes where the post container (id="msgNNN") also wraps the
    # author sidebar and timestamp as siblings (rather than the fixture's
    # simpler flat layout), get_text() on the whole container leaks that
    # boilerplate into the body. SMF themes consistently isolate the
    # actual message text in a `.post` element (and, in most SMF 2.1
    # themes, a nested `.inner` within it) - prefer the narrowest match
    # that exists, falling back to the whole container for any theme that
    # doesn't use this wrapper at all.
    target = working.select_one(".post .inner") or working.select_one(".post") or working

    text = target.get_text("\n", strip=True)
    lines = [line for line in text.split("\n") if line.strip()]
    return "\n".join(lines).strip()


def _absolutize(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    return f"{base_url.rstrip('/')}/{href.lstrip('/')}"
