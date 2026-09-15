"""Thin, polite HTTP client wrapper for crawling the forum.

Kept separate from parsing on purpose: parser.py takes plain HTML strings
and is fully unit-testable with zero network access (see tests/test_parser.py).
This module is the only place that talks to the network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import settings


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str


class ForumClient(Protocol):
    """What `ingest.py` and every `ForumAdapter` actually need from an
    HTTP client - just enough to fetch a page relative to some base URL.
    Declared explicitly so the dependency inversion already used for
    forum platforms (see `ForumAdapter`) is reflected consistently for
    the HTTP layer too: tests have always substituted duck-typed fakes
    here, so a type checker should be able to see that as a Protocol
    conformance, not treat `PoliteForumClient` as the type of record."""

    base_url: str

    def fetch(self, path_or_url: str) -> FetchResult: ...


class RateLimiter:
    """Enforces a minimum delay between successive completed requests.
    Split out of `PoliteForumClient` so "how to pace requests" isn't
    tangled up with "how to reach the network" in one class - each is
    independently testable/reusable now."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self._last_completed_at: float | None = None

    def wait(self) -> None:
        """Blocks until at least `delay_seconds` have passed since the
        last `mark_done()` call - a no-op the very first time."""
        if self._last_completed_at is None:
            return
        elapsed = time.monotonic() - self._last_completed_at
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def mark_done(self) -> None:
        self._last_completed_at = time.monotonic()


class PoliteForumClient:
    """Fetches pages with a fixed delay between requests (via
    `RateLimiter`) and a descriptive User-Agent, per good-citizen
    crawling practice."""

    def __init__(
        self,
        base_url: str | None = None,
        delay_seconds: float | None = None,
        user_agent: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = (base_url or settings.forum_base_url).rstrip("/")
        self._rate_limiter = RateLimiter(
            delay_seconds if delay_seconds is not None else settings.crawl_request_delay_seconds
        )
        self._client = httpx.Client(
            headers={"User-Agent": user_agent or settings.crawl_user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def fetch(self, path_or_url: str) -> FetchResult:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        self._rate_limiter.wait()
        response = self._client.get(url)
        self._rate_limiter.mark_done()
        return FetchResult(url=url, status_code=response.status_code, html=response.text)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteForumClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
