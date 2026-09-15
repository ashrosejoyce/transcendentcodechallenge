"""These tests mock both the LLM call and the retrieval step, so they
verify the RAG-vs-baseline *orchestration* (what gets called, what gets
passed through) without needing a live Anthropic key or a populated
vector database."""
from app.generation import ab_comparison, baseline_generator, document_generator
from app.rag.retrieval import RetrievedChunk


def make_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=1,
        post_id=1,
        text="Swarm season started early this year.",
        board="General Beekeeping",
        subject="Early swarms",
        author="MikeyN.C.",
        posted_at="2026-09-10T12:00:00",
        url="https://beemaster.com/forum/index.php?topic=1.msg1",
        distance=0.05,
    )


def test_rag_document_is_grounded_in_retrieved_chunks(monkeypatch):
    monkeypatch.setattr(
        document_generator, "retrieve", lambda conn, query, top_k=None, run_id=None, since=None: [make_chunk()]
    )
    captured = {}

    def fake_generate_text(system_prompt, user_prompt, max_tokens=1500):
        captured["prompt"] = user_prompt
        return "Generated RAG document."

    monkeypatch.setattr(document_generator, "generate_text", fake_generate_text)

    result = document_generator.generate_rag_document(conn=None, community_name="beekeepers", query="what happened?")

    assert result.text == "Generated RAG document."
    assert len(result.retrieved_chunks) == 1
    assert "Swarm season started early this year." in captured["prompt"]


def test_baseline_document_never_sees_retrieved_content(monkeypatch):
    captured = {}

    def fake_generate_text(system_prompt, user_prompt, max_tokens=1500):
        captured["prompt"] = user_prompt
        return "Generated baseline document."

    monkeypatch.setattr(baseline_generator, "generate_text", fake_generate_text)

    text = baseline_generator.generate_baseline_document("beekeepers")

    assert text == "Generated baseline document."
    assert "Swarm season" not in captured["prompt"]


def test_ab_comparison_runs_both_strategies_and_reports_grounding_count(monkeypatch):
    def fake_generate_rag_document(conn, community_name, query, top_k=None, run_id=None, timeframe=None):
        return document_generator.GeneratedDocument(
            text="RAG output", retrieved_chunks=[make_chunk(), make_chunk()], run_id="abc"
        )

    monkeypatch.setattr(ab_comparison, "generate_rag_document", fake_generate_rag_document)
    monkeypatch.setattr(
        ab_comparison, "generate_baseline_document", lambda community_name, timeframe=None: "Baseline output"
    )

    result = ab_comparison.run_ab_comparison(conn=None, community_name="beekeepers", query="what happened?")

    assert result.rag.text == "RAG output"
    assert result.baseline_text == "Baseline output"
    assert result.grounded_claim_count == 2
    assert result.timeframe.label == "week"
