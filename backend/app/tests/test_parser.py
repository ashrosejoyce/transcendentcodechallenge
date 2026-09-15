from datetime import datetime
from pathlib import Path

from app.crawler.parser import (
    extract_topic_subject,
    parse_recent_posts,
    parse_smf_timestamp,
    parse_topic_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_recent_posts_extracts_all_rows():
    html = read_fixture("recent_posts.html")
    entries = parse_recent_posts(html, base_url="https://beemaster.com/forum")

    assert len(entries) == 3
    first = entries[0]
    assert first.topic_id == 101
    assert first.msg_id == 9001
    assert first.author == "cidersabuzzin"
    assert first.board == "General Beekeeping"
    assert "Today at 08:04:12 PM" in first.posted_at_raw
    assert first.url.startswith("https://beemaster.com/forum/")


def test_parse_recent_posts_deduplicates_by_msg_id():
    html = read_fixture("recent_posts.html") + read_fixture("recent_posts.html")
    entries = parse_recent_posts(html, base_url="https://beemaster.com/forum")
    msg_ids = [e.msg_id for e in entries]
    assert len(msg_ids) == len(set(msg_ids))


def test_parse_topic_page_extracts_each_post():
    html = read_fixture("topic_page.html")
    posts = parse_topic_page(html)

    assert len(posts) == 2
    assert posts[0].msg_id == 9001
    assert "swarm timing" in posts[0].body
    assert posts[1].author == "MikeyN.C."


def test_parse_topic_page_strips_quoted_text():
    html = read_fixture("topic_page.html")
    posts = parse_topic_page(html)
    reply = next(p for p in posts if p.msg_id == 9004)
    assert "something quoted here" not in reply.body
    assert "backfilling with nectar" in reply.body


def test_extract_topic_subject_reads_title():
    html = read_fixture("topic_page.html")
    assert extract_topic_subject(html) == "Re: 319 square miles"


def test_parse_topic_page_excludes_author_sidebar_on_nested_themes():
    """Some SMF themes (e.g. STV6, seen on real-world installs) wrap the
    author sidebar and timestamp as siblings *inside* the same id="msgNNN"
    container as the message itself, rather than the simpler flat layout
    other fixtures use - get_text() on the whole container would leak
    "Posts: 332", "Logged", etc. into the body if not handled."""
    html = """
    <div id="msg42" class="post_wrapper">
      <div class="poster">
        <h4><a href="index.php?action=profile;u=9">Boban</a></h4>
        <ul class="user_info"><li class="postcount">Posts: 332</li><li class="poster_ip">Logged</li></ul>
      </div>
      <div class="postarea">
        <div class="postinfo">Today at 08:04:12 PM</div>
        <div class="post">
          <div class="inner">The actual message text goes here.</div>
          <em class="smalltext modified">Last Edit: Today at 09:00:00 PM by Someone</em>
        </div>
      </div>
    </div>
    """
    posts = parse_topic_page(html)

    assert len(posts) == 1
    assert posts[0].body == "The actual message text goes here."
    assert "Posts: 332" not in posts[0].body
    assert "Logged" not in posts[0].body
    assert "Last Edit" not in posts[0].body


def test_parse_smf_timestamp_today():
    now = datetime(2026, 9, 14, 23, 0, 0)
    result = parse_smf_timestamp("Today at 08:04:12 PM", now)
    assert result == datetime(2026, 9, 14, 20, 4, 12)


def test_parse_smf_timestamp_yesterday():
    now = datetime(2026, 9, 14, 23, 0, 0)
    result = parse_smf_timestamp("Yesterday at 04:31:36 PM", now)
    assert result == datetime(2026, 9, 13, 16, 31, 36)


def test_parse_smf_timestamp_absolute_date():
    now = datetime(2026, 9, 14, 23, 0, 0)
    result = parse_smf_timestamp("August 02, 2026 at 09:12:00 AM", now)
    assert result == datetime(2026, 8, 2, 9, 12, 0)


def test_parse_smf_timestamp_returns_none_for_garbage():
    assert parse_smf_timestamp("not a timestamp", datetime(2026, 1, 1)) is None


def test_parse_smf_timestamp_midnight_twelve_am_hour_rollover():
    now = datetime(2026, 9, 14, 23, 0, 0)
    result = parse_smf_timestamp("Today at 12:00:00 AM", now)
    assert result == datetime(2026, 9, 14, 0, 0, 0)


def test_parse_smf_timestamp_comma_separated_variant():
    """Some SMF installs use a comma instead of "at" before the clock time
    (an admin-configurable date format setting) - e.g. "August 19, 2026,
    12:48:51 PM" rather than Beemaster's "August 19, 2026 at 12:48:51 PM"."""
    now = datetime(2026, 9, 14, 23, 0, 0)
    result = parse_smf_timestamp("August 19, 2026, 12:48:51 PM", now)
    assert result == datetime(2026, 8, 19, 12, 48, 51)
