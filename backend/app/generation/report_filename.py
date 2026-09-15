"""Builds a filesystem-safe filename for a downloaded Community Voices
Document, parameterized by whichever community was actually analyzed -
so an exported report is never named after one hardcoded forum.

Kept as a pure string-building function (no I/O) so it's trivial to unit
test independently, matching the style of generation/prompts.py.
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, hyphen-separated, alphanumeric only - safe on every
    common filesystem. Falls back to "community" if nothing usable is
    left (e.g. an empty or all-punctuation community name)."""
    slug = _NON_SLUG_CHARS.sub("-", text.strip().lower()).strip("-")
    return slug or "community"


def build_report_filename(
    community_name: str,
    when: date | None = None,
    extension: str = "txt",
    timeframe_label: str | None = None,
) -> str:
    """e.g. build_report_filename("Beemaster's Forum beekeeping community")
    -> "community-voices-beemaster-s-forum-beekeeping-community-2026-09-14.txt"

    `timeframe_label` (e.g. "day"/"week"/"month"/"year", see
    generation/timeframe.py) is optional and, when given, is inserted
    before the date so two reports for the same community on the same day
    but different timeframes don't collide.
    """
    when = when or datetime.now(UTC).date()
    label_part = f"-{slugify(timeframe_label)}" if timeframe_label else ""
    return f"community-voices-{slugify(community_name)}{label_part}-{when.isoformat()}.{extension}"
