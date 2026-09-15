"""Shared data types used across layers.

`IngestedPost` lives here - rather than in `crawler/ingest.py` - so that
low-level modules (like `db/repository.py`) can depend on it without
reaching *up* into the crawler package. Both `crawler` (which produces
these) and `db` (which persists them) depend on this neutral module
instead of on each other, keeping the dependency direction correct
(persistence should never depend on a higher-level orchestration package).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class IngestedPost:
    id: int
    topic_id: int
    board: str
    subject: str
    author: str
    posted_at: datetime
    body: str
    url: str
