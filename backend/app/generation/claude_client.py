"""Thin wrapper around the Anthropic SDK so the rest of the app depends on
one small function instead of the SDK directly (easy to mock in tests)."""
from __future__ import annotations

from functools import lru_cache

from app.config import settings


class MissingApiKeyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your own key."
        )


@lru_cache(maxsize=1)
def _client():
    import anthropic

    if not settings.anthropic_api_key:
        raise MissingApiKeyError()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def generate_text(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
    response = _client().messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
