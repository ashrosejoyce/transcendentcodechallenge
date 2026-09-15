"""Generates the Community Voices Document, RAG-empowered."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.generation.claude_client import generate_text
from app.generation.prompts import SYSTEM_PROMPT, build_rag_prompt
from app.generation.timeframe import Timeframe, resolve_timeframe
from app.rag.retrieval import RetrievedChunk, retrieve


@dataclass
class GeneratedDocument:
    text: str
    retrieved_chunks: list[RetrievedChunk]
    run_id: str


def generate_rag_document(
    conn: sqlite3.Connection,
    community_name: str,
    query: str,
    top_k: int | None = None,
    run_id: str | None = None,
    timeframe: Timeframe | None = None,
) -> GeneratedDocument:
    timeframe = timeframe or resolve_timeframe(None)
    retrieved = retrieve(conn, query, top_k=top_k, run_id=run_id, since=timeframe.cutoff())
    prompt = build_rag_prompt(community_name, retrieved, timeframe)
    text = generate_text(SYSTEM_PROMPT, prompt)
    return GeneratedDocument(text=text, retrieved_chunks=retrieved, run_id=run_id or "")
