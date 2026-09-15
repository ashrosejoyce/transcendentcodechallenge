"""Pydantic request/response models for the API layer."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import settings


class CommunityInfo(BaseModel):
    """Which community this deployment is configured for - lets the
    frontend display the right name without hardcoding one itself."""

    community_name: str


class IngestResponse(BaseModel):
    """Result of one crawl+index run - counts plus per-reason skip totals,
    so a caller can tell "nothing new" apart from "something went wrong"."""

    posts_saved: int
    posts_indexed: int
    chunks_created: int
    pages_fetched: int
    topics_fetched: int
    skipped_excluded_board: int
    skipped_out_of_window: int
    errors: list[str]


class StatsResponse(BaseModel):
    """Corpus-wide summary shown on the frontend's stat tiles, plus the
    most-retrieved-chunks leaderboard (spec item 3c)."""

    post_count: int
    chunk_count: int
    board_count: int
    earliest_post: str | None
    latest_post: str | None
    most_retrieved_chunks: list[dict]


class EmbeddingPoint(BaseModel):
    """One chunk's embedding, PCA-flattened to 2D for the frontend's
    scatter plot (spec item 3b) - see rag/visualization.py."""

    chunk_id: int
    x: float
    y: float
    board: str
    subject: str
    snippet: str
    retrieval_count: int


class GenerateRequest(BaseModel):
    # Defaults come from the configured COMMUNITY_NAME (see config.py),
    # not a hardcoded community - callers can still override either field
    # per-request.
    community_name: str = Field(default_factory=lambda: settings.community_name)
    query: str = "What has this community been discussing lately, and what will they discuss next?"
    top_k: int | None = None
    # "day" | "week" | "month" | "year" - see generation/timeframe.py.
    # Defaults to the spec's original "week": posts from the past week,
    # predicting the coming week.
    timeframe: str = "week"


class RetrievedChunkView(BaseModel):
    """One source chunk the RAG document was grounded in, with enough
    provenance (board/author/date/url) for a reader to verify the claim."""

    chunk_id: int
    board: str
    subject: str
    author: str
    posted_at: str
    url: str
    distance: float
    text: str


class GenerateResponse(BaseModel):
    community_name: str
    query: str
    timeframe: str
    rag_document: str
    baseline_document: str
    retrieved_chunks: list[RetrievedChunkView]
    grounded_claim_count: int
    # Suggested filename for downloading rag_document as a PDF,
    # parameterized by whichever community was actually analyzed for this
    # request (see generation/report_filename.py) - never a hardcoded
    # forum name.
    report_filename: str


class ReportPdfRequest(BaseModel):
    """Renders a PDF from a document /api/generate already produced -
    the frontend passes back exactly what it received, so this never
    re-runs retrieval or calls Claude again just to change the format."""

    community_name: str
    timeframe: str
    rag_document: str
    baseline_document: str
    retrieved_chunks: list[RetrievedChunkView]
    grounded_claim_count: int
    report_filename: str
