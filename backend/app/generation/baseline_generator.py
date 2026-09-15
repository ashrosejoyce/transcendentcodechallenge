"""Generates the Community Voices Document WITHOUT retrieval - the "A" side
of the A/B comparison the spec asks for (item 5)."""
from __future__ import annotations

from app.generation.claude_client import generate_text
from app.generation.prompts import SYSTEM_PROMPT, build_baseline_prompt
from app.generation.timeframe import Timeframe


def generate_baseline_document(community_name: str, timeframe: Timeframe | None = None) -> str:
    prompt = build_baseline_prompt(community_name, timeframe)
    return generate_text(SYSTEM_PROMPT, prompt)
