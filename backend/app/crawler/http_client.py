"""Thin, polite HTTP client wrapper for crawling the forum.

Kept separate from parsing on purpose: parser.py takes plain HTML strings
and is fully unit-testable with zero network access (see tests/test_parser.py).
This module is the only place that talks to the network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str


class PoliteForumClient:
    """Fetches pages with a fixed delay between requests and a descriptive
    User-Agent, per good-citizen crawling practice."""

    def __init__(
        self,
        base_url: str | None = None,
        delay_seconds: float | None = None,
        user_agent: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = (base_url or settings.forum_base_url).rstrip("/")
        self.delay_seconds = delay_seconds if delay_seconds is not None else settings.crawl_request_delay_seconds
        self._client = httpx.Client(
            headers={"User-Agent": user_agent or settings.crawl_user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self._last_request_time: float | None = None

    def fetch(self, path_or_url: str) -> FetchResult:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        self._throttle()
        response = self._client.get(url)
        self._last_request_time = time.monotonic()
        return FetchResult(url=url, status_code=response.status_code, html=response.text)

    def _throttle(self) -> None:
        if self._last_request_time is None:
            return
        elapsed = time.monotonic() - self._last_request_time
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteForumClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
