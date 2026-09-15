"""Prompt templates for the Community Voices Document.

Kept as pure string-building functions (no network, no I/O) so they are
trivial to unit test independently of the LLM call itself.
"""
from __future__ import annotations

from app.generation.timeframe import Timeframe, resolve_timeframe
from app.rag.retrieval import RetrievedChunk

SYSTEM_PROMPT = (
    "You are an analyst producing a periodic 'Community Voices Document' "
    "for an online community. You write in clear, engaging prose (no "
    "bullet spam), you are specific rather than generic, and you clearly "
    "separate what you know happened from what you are predicting will "
    "happen next. You never fabricate specific usernames, dates, or "
    "claims you were not given evidence for."
)

DOCUMENT_INSTRUCTIONS = """\
Write a Community Voices Document about the {community_name} community, covering:

1. A "{past_heading}" section summarizing the main topics, questions, and
   notable discussions from the source material below - group related
   points into a coherent narrative rather than listing every post.
2. A "Looking Ahead" section predicting what the community is likely to
   discuss in {future_phrase}, reasoning from the patterns, open questions,
   and seasonal/topical cues visible in the source material.

Keep it to roughly 300-450 words total. Use plain paragraphs with short
section headings, not bullet lists.
"""


def build_rag_prompt(
    community_name: str,
    retrieved_chunks: list[RetrievedChunk],
    timeframe: Timeframe | None = None,
) -> str:
    """Prompt that grounds generation in retrieved forum content."""
    timeframe = timeframe or resolve_timeframe(None)

    if not retrieved_chunks:
        source_material = "(no matching source material was retrieved)"
    else:
        source_material = "\n\n".join(
            f"- [{chunk.board} | {chunk.author} | {chunk.posted_at}] {chunk.text}"
            for chunk in retrieved_chunks
        )

    return (
        f"{_instructions(community_name, timeframe)}\n\n"
        f"Source material (retrieved forum posts from {timeframe.past_heading.lower()}):\n{source_material}\n\n"
        f"Base every claim in the '{timeframe.past_heading}' section on the source "
        "material above. You may reason more freely in 'Looking Ahead'."
    )


def build_baseline_prompt(community_name: str, timeframe: Timeframe | None = None) -> str:
    """Prompt with NO retrieved context - this is the A/B baseline: what a
    plain LLM produces from its own general knowledge alone."""
    timeframe = timeframe or resolve_timeframe(None)
    return (
        f"{_instructions(community_name, timeframe)}\n\n"
        "You have not been given any specific recent posts or data from "
        "this community. Write the document based only on your general "
        "knowledge of what a community like this typically discusses. "
        "If you are extrapolating rather than reporting real facts, keep "
        "the tone appropriately general rather than inventing specifics."
    )


def _instructions(community_name: str, timeframe: Timeframe) -> str:
    return DOCUMENT_INSTRUCTIONS.format(
        community_name=community_name,
        past_heading=timeframe.past_heading,
        future_phrase=timeframe.future_phrase,
    )
