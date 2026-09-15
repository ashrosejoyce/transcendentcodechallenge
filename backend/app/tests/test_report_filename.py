from datetime import date

from app.generation.report_filename import build_report_filename, slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Beemaster's Forum") == "beemaster-s-forum"


def test_slugify_collapses_runs_of_punctuation_and_trims_edges():
    assert slugify("  --Weird!!  Name__ ") == "weird-name"


def test_slugify_falls_back_when_nothing_usable_remains():
    assert slugify("!!!") == "community"


def test_build_report_filename_includes_slug_and_date():
    filename = build_report_filename("r/climbing", when=date(2026, 9, 14))
    assert filename == "community-voices-r-climbing-2026-09-14.txt"


def test_build_report_filename_is_parameterized_by_community():
    """The whole point: two different communities analyzed produce two
    different filenames - nothing here is hardcoded to one forum."""
    beekeeping = build_report_filename("Beemaster's Forum beekeeping community", when=date(2026, 1, 1))
    climbing = build_report_filename("r/climbing", when=date(2026, 1, 1))
    assert beekeeping != climbing
    assert beekeeping == "community-voices-beemaster-s-forum-beekeeping-community-2026-01-01.txt"


def test_build_report_filename_respects_custom_extension():
    filename = build_report_filename("Test Forum", when=date(2026, 1, 1), extension="md")
    assert filename.endswith(".md")


def test_build_report_filename_includes_timeframe_label_when_given():
    filename = build_report_filename("r/climbing", when=date(2026, 9, 14), timeframe_label="month")
    assert filename == "community-voices-r-climbing-month-2026-09-14.txt"
