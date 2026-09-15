"""RateLimiter is the one piece of http_client.py with no network I/O -
split out of PoliteForumClient specifically so it's testable on its own,
deterministically, with time.monotonic/time.sleep mocked out rather than
actually waiting."""
from app.crawler import http_client


def test_first_wait_does_not_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(http_client.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(http_client.time, "monotonic", lambda: 100.0)

    limiter = http_client.RateLimiter(delay_seconds=5)
    limiter.wait()

    assert sleeps == []


def test_wait_sleeps_for_remaining_delay_since_last_completed_request(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(http_client.time, "monotonic", lambda: clock[0])
    sleeps = []
    monkeypatch.setattr(http_client.time, "sleep", lambda seconds: sleeps.append(seconds))

    limiter = http_client.RateLimiter(delay_seconds=5)
    limiter.mark_done()  # a request "completed" at t=100

    clock[0] = 102.0  # only 2s have passed
    limiter.wait()

    assert sleeps == [3.0]


def test_wait_does_not_sleep_once_the_delay_has_already_elapsed(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(http_client.time, "monotonic", lambda: clock[0])
    sleeps = []
    monkeypatch.setattr(http_client.time, "sleep", lambda seconds: sleeps.append(seconds))

    limiter = http_client.RateLimiter(delay_seconds=5)
    limiter.mark_done()

    clock[0] = 110.0  # well past the 5s delay
    limiter.wait()

    assert sleeps == []
