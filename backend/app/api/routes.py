"""API route handlers. Kept thin - each handler wires HTTP to a plain
function in app.crawler / app.rag / app.generation and shapes the response."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

from app.api.ingest_job import current_status, start_ingest_job
from app.api.schemas import (
    CommunityInfo,
    EmbeddingPoint,
    GenerateRequest,
    GenerateResponse,
    IngestStartResponse,
    IngestStatusResponse,
    ReportPdfRequest,
    RetrievedChunkView,
    StatsResponse,
)
from app.config import settings
from app.db.connection import get_connection
from app.db.repository import corpus_stats, retrieval_counts
from app.generation.ab_comparison import run_ab_comparison
from app.generation.claude_client import MissingApiKeyError
from app.generation.report_filename import build_report_filename
from app.generation.report_pdf import PdfSourceChunk, render_report_pdf
from app.generation.timeframe import resolve_timeframe
from app.rag.visualization import flattened_embeddings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/ingest", response_model=IngestStartResponse)
def ingest() -> IngestStartResponse:
    """Start a crawl+index run in the background (see api/ingest_job.py)
    and return immediately - a real crawl's rate limit can make it take
    minutes, so the frontend polls /api/ingest/status for progress rather
    than this request blocking the whole time. Safe to call repeatedly:
    both the crawl (primary-key skip) and indexing (only un-chunked
    posts) are idempotent, and calling this while one is already running
    just starts polling the run already in flight."""
    return IngestStartResponse(started=start_ingest_job())


@router.get("/ingest/status", response_model=IngestStatusResponse)
def ingest_status() -> IngestStatusResponse:
    """Current (or most recently finished) ingest job's progress."""
    state = current_status()
    report = state.report
    return IngestStatusResponse(
        status=state.status,
        phase=report.phase if report else "idle",
        pages_fetched=report.pages_fetched if report else 0,
        topics_fetched=report.topics_fetched if report else 0,
        topics_total=report.topics_total if report else 0,
        skipped_excluded_board=report.skipped_excluded_board if report else 0,
        skipped_out_of_window=report.skipped_out_of_window if report else 0,
        errors=report.errors if report else [],
        posts_saved=state.posts_saved,
        posts_indexed=state.posts_indexed,
        chunks_created=state.chunks_created,
        error=state.error,
    )


@router.get("/community", response_model=CommunityInfo)
def community() -> CommunityInfo:
    """Which community this deployment is configured for (COMMUNITY_NAME)
    - the frontend reads this instead of hardcoding a name itself."""
    return CommunityInfo(community_name=settings.community_name)


@router.get("/stats", response_model=StatsResponse)
def stats() -> StatsResponse:
    """Corpus summary + the top 10 most-retrieved chunks, for the
    frontend's stat tiles and retrieval bar chart."""
    with get_connection() as conn:
        summary = corpus_stats(conn)
        top_chunks = [dict(row) for row in retrieval_counts(conn, limit=10)]
    return StatsResponse(**summary, most_retrieved_chunks=top_chunks)


@router.get("/embeddings/visualization", response_model=list[EmbeddingPoint])
def embeddings_visualization() -> list[EmbeddingPoint]:
    """Every indexed chunk's embedding, PCA-flattened to 2D, for the
    frontend's scatter plot. Empty list until at least 2 chunks exist."""
    with get_connection() as conn:
        return flattened_embeddings(conn)


@router.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    """Run the RAG-grounded document and the no-retrieval baseline side by
    side (spec item 5) and return both, plus a suggested filename for
    downloading the RAG document.

    `request.timeframe` ("day"/"week"/"month"/"year") controls how far
    back the RAG document's source material reaches and what period
    "Looking Ahead" predicts - see generation/timeframe.py."""
    try:
        timeframe = resolve_timeframe(request.timeframe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        with get_connection() as conn:
            result = run_ab_comparison(
                conn, request.community_name, request.query, top_k=request.top_k, timeframe=timeframe
            )
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GenerateResponse(
        community_name=result.community_name,
        query=result.query,
        timeframe=result.timeframe.label,
        rag_document=result.rag.text,
        baseline_document=result.baseline_text,
        grounded_claim_count=result.grounded_claim_count,
        report_filename=build_report_filename(
            result.community_name, timeframe_label=result.timeframe.label, extension="pdf"
        ),
        retrieved_chunks=[
            RetrievedChunkView(
                chunk_id=c.chunk_id,
                board=c.board,
                subject=c.subject,
                author=c.author,
                posted_at=c.posted_at,
                url=c.url,
                distance=c.distance,
                text=c.text,
            )
            for c in result.rag.retrieved_chunks
        ],
    )


@router.post("/report/pdf")
def report_pdf(request: ReportPdfRequest) -> Response:
    """Render a document /api/generate already produced as a downloadable
    PDF. Takes exactly what /api/generate returned - never re-runs
    retrieval or calls Claude again just to change the output format."""
    pdf_bytes = render_report_pdf(
        community_name=request.community_name,
        timeframe_label=request.timeframe,
        rag_document=request.rag_document,
        baseline_document=request.baseline_document,
        grounded_claim_count=request.grounded_claim_count,
        retrieved_chunks=[
            PdfSourceChunk(
                subject=c.subject, board=c.board, author=c.author, posted_at=c.posted_at, url=c.url, distance=c.distance
            )
            for c in request.retrieved_chunks
        ],
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{request.report_filename}"'},
    )
