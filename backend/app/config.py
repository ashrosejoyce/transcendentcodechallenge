"""Application configuration, loaded from environment variables / .env.

Centralizing settings here means every other module imports `settings`
instead of calling `os.environ` directly - the classic "one seam" pattern
that keeps configuration testable and self-documenting.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"

    # Human-readable name of the community being analyzed - used as the
    # default in generation prompts, the frontend header, and generated
    # report filenames. Deliberately generic here; a real deployment sets
    # this in .env (see .env.example) to name whatever forum FORUM_BASE_URL
    # actually points at. The codebase itself never hardcodes a community.
    community_name: str = "this community"

    forum_base_url: str = "https://beekeepingforum.co.uk"
    # Which forum platform `forum_base_url` runs, i.e. which ForumAdapter
    # to crawl it with (see crawler/adapter_registry.py). "xenforo" and
    # "smf" are shipped today - swapping to another forum running the same
    # platform needs no code changes, just this URL; a forum running
    # different software needs a new adapter registered under a new name.
    forum_adapter: str = "xenforo"
    # Boards to skip during ingestion because they're off-topic for the
    # target community. Empty by default (a generic forum has no known
    # off-topic boards); a real deployment fills this in per-target - see
    # .env.example for the list used for the current deployment target.
    forum_excluded_boards: tuple[str, ...] = ()
    crawl_lookback_days: int = 7
    crawl_max_posts: int = 400
    crawl_request_delay_seconds: float = 1.0
    crawl_user_agent: str = (
        "CommunityVoicesBot/1.0 (+coding challenge research crawler; contact via repo README)"
    )

    database_path: Path = PROJECT_ROOT / "data" / "community_voices.db"
    embedding_model: str = "all-MiniLM-L6-v2"
    retrieval_top_k: int = 8
    chunk_max_chars: int = 800
    chunk_overlap_chars: int = 120


def get_settings() -> Settings:
    """Return a fresh Settings instance (cheap; avoids stale-cache surprises in tests)."""
    return Settings()


settings = get_settings()
