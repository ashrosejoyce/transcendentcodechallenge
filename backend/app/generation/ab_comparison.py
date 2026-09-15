"""Runs both generation strategies and packages a side-by-side comparison.

This directly answers spec item 5: "how does an LLM handle the generation
of this document without your RAG-empowered system? How does your
RAG-empowered system generate that document instead?"
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass

from app.generation.baseline_generator import generate_baseline_document
from app.generation.document_generator import GeneratedDocument, generate_rag_document
from app.generation.timeframe import Timeframe, resolve_timeframe


@dataclass
class ComparisonResult:
    community_name: str
    query: str
    rag: GeneratedDocument
    baseline_text: str
    grounded_claim_count: int
    timeframe: Timeframe


def run_ab_comparison(
    conn: sqlite3.Connection,
    community_name: str,
    query: str,
    top_k: int | None = None,
    timeframe: Timeframe | None = None,
) -> ComparisonResult:
    timeframe = timeframe or resolve_timeframe(None)
    run_id = str(uuid.uuid4())
    rag_result = generate_rag_document(conn, community_name, query, top_k=top_k, run_id=run_id, timeframe=timeframe)
    baseline_text = generate_baseline_document(community_name, timeframe=timeframe)

    return ComparisonResult(
        community_name=community_name,
        query=query,
        rag=rag_result,
        baseline_text=baseline_text,
        grounded_claim_count=len(rag_result.retrieved_chunks),
        timeframe=timeframe,
    )
