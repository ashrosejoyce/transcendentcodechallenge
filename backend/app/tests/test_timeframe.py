from datetime import UTC, datetime

import pytest

from app.generation.timeframe import resolve_timeframe


def test_resolve_timeframe_defaults_to_week():
    timeframe = resolve_timeframe(None)
    assert timeframe.label == "week"
    assert timeframe.days == 7


@pytest.mark.parametrize(
    "label,days",
    [("day", 1), ("week", 7), ("month", 30), ("year", 365)],
)
def test_resolve_timeframe_supports_presets(label, days):
    timeframe = resolve_timeframe(label)
    assert timeframe.days == days


def test_resolve_timeframe_is_case_and_whitespace_insensitive():
    assert resolve_timeframe(" Month ").label == "month"


def test_resolve_timeframe_rejects_unknown_labels():
    with pytest.raises(ValueError, match="fortnight"):
        resolve_timeframe("fortnight")


def test_past_heading_and_future_phrase_reflect_the_label():
    timeframe = resolve_timeframe("month")
    assert timeframe.past_heading == "This Past Month"
    assert timeframe.future_phrase == "the coming month"


def test_cutoff_subtracts_days_from_now():
    now = datetime(2026, 9, 15, tzinfo=UTC)
    timeframe = resolve_timeframe("week")
    assert timeframe.cutoff(now) == datetime(2026, 9, 8, tzinfo=UTC)
