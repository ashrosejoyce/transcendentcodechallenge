"""Named report timeframes ("day", "week", "month", "year").

The spec's default is a week of posts predicting the coming week, but
that's just one choice of window - this module is the single place that
maps a user-facing label to how many days back a report should look and
how the two document sections should be phrased. It's deliberately
decoupled from the crawler's own `crawl_lookback_days` (see
`crawler/ingest.py`): the corpus can hold more or less history than a
given report asks for, and retrieval (see `rag/retrieval.py`) is what
actually narrows to the requested window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_PRESET_DAYS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
}

DEFAULT_TIMEFRAME_LABEL = "week"


@dataclass(frozen=True)
class Timeframe:
    label: str
    days: int

    @property
    def past_heading(self) -> str:
        return f"This Past {self.label.capitalize()}"

    @property
    def future_phrase(self) -> str:
        return f"the coming {self.label}"

    def cutoff(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now(UTC)
        return now - timedelta(days=self.days)


def resolve_timeframe(label: str | None) -> Timeframe:
    """Resolve a user-facing label to a `Timeframe`, defaulting to the
    spec's original "week" when none is given. Raises ValueError (callers
    at the API boundary turn this into a 400) for anything outside the
    supported presets, so a typo fails fast instead of silently becoming
    "no filtering"."""
    normalized = (label or DEFAULT_TIMEFRAME_LABEL).strip().lower()
    if normalized not in _PRESET_DAYS:
        allowed = ", ".join(sorted(_PRESET_DAYS))
        raise ValueError(f"Unknown timeframe '{label}'; expected one of: {allowed}")
    return Timeframe(label=normalized, days=_PRESET_DAYS[normalized])
