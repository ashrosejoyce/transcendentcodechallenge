from datetime import UTC, datetime
from pathlib import Path

from app.crawler.xenforo_parser import (
    extract_topic_subject,
    parse_board_list,
    parse_board_threads,
    parse_topic_page,
    parse_xenforo_timestamp,
)

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_board_list_extracts_boards_and_dedupes_by_id():
    html = read_fixture("xenforo_board_index.html")
    boards = parse_board_list(html)

    assert [b.name for b in boards] == ["Beekeeping Forum", "Honeybee Health Topics", "Off Topic Chat"]
    beekeeping = boards[0]
    assert beekeeping.board_id == 2
    assert beekeeping.path == "/forums/beekeeping-forum.2/"


def test_parse_board_threads_extracts_each_row():
    html = read_fixture("xenforo_board_threads.html")
    entries = parse_board_threads(html)

    assert [e.thread_id for e in entries] == [54369, 59604, 53806]
    bulk_honey = next(e for e in entries if e.thread_id == 59604)
    assert bulk_honey.subject == "Bulk Honey"
    assert bulk_honey.path == "/threads/bulk-honey.59604/"
    assert bulk_honey.latest_post_at_raw == "2026-09-14T09:36:00+0100"
    assert bulk_honey.is_sticky is False


def test_parse_board_threads_flags_sticky_threads():
    html = read_fixture("xenforo_board_threads.html")
    entries = parse_board_threads(html)

    sticky = next(e for e in entries if e.thread_id == 54369)
    assert sticky.is_sticky is True
    # A sticky can be very old despite being pinned to the top - that's
    # exactly why discovery must not treat its age as a stop signal.
    assert sticky.latest_post_at_raw == "2022-01-23T23:18:11+0000"


def test_extract_topic_subject_reads_title():
    html = read_fixture("xenforo_topic_page.html")
    assert extract_topic_subject(html) == "Bulk Honey"


def test_parse_topic_page_extracts_each_post():
    html = read_fixture("xenforo_topic_page.html")
    posts = parse_topic_page(html)

    assert len(posts) == 2
    assert posts[0].msg_id == 956001
    assert posts[0].author == "Beequiet"
    assert "bulk honey for sale" in posts[0].body
    assert posts[1].author == "OldTimer"


def test_parse_topic_page_strips_quoted_text_and_signature():
    html = read_fixture("xenforo_topic_page.html")
    posts = parse_topic_page(html)
    reply = next(p for p in posts if p.msg_id == 956002)

    assert "Anyone got bulk honey for sale this year?" not in reply.body
    assert "Sent from my apiary" not in reply.body
    assert "80kg going spare" in reply.body


def test_parse_xenforo_timestamp_parses_iso8601_with_and_without_colon_offset():
    now = datetime(2026, 9, 15, tzinfo=UTC)
    expected = datetime.fromisoformat("2026-09-15T19:20:09+01:00")
    assert parse_xenforo_timestamp("2026-09-15T19:20:09+0100", now) == expected
    assert parse_xenforo_timestamp("2026-01-30T06:43:40+0000", now) == datetime(2026, 1, 30, 6, 43, 40, tzinfo=UTC)


def test_parse_xenforo_timestamp_returns_none_for_garbage():
    assert parse_xenforo_timestamp("not a timestamp", datetime(2026, 1, 1)) is None
