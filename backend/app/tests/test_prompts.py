from app.generation.prompts import build_baseline_prompt, build_rag_prompt
from app.generation.timeframe import resolve_timeframe
from app.rag.retrieval import RetrievedChunk


def make_chunk(text="Bees are swarming early this year.") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=1,
        post_id=1,
        text=text,
        board="General Beekeeping",
        subject="Early swarm",
        author="MikeyN.C.",
        posted_at="2026-09-10T12:00:00",
        url="https://beemaster.com/forum/index.php?topic=1.msg1",
        distance=0.12,
    )


def test_rag_prompt_includes_retrieved_content():
    prompt = build_rag_prompt("beekeepers", [make_chunk()])
    assert "Bees are swarming early this year." in prompt
    assert "beekeepers" in prompt


def test_rag_prompt_handles_no_results_gracefully():
    prompt = build_rag_prompt("beekeepers", [])
    assert "no matching source material" in prompt


def test_baseline_prompt_never_includes_forum_content():
    prompt = build_baseline_prompt("beekeepers")
    assert "Bees are swarming" not in prompt
    assert "have not been given any specific" in prompt


def test_rag_and_baseline_prompts_differ():
    rag = build_rag_prompt("beekeepers", [make_chunk()])
    baseline = build_baseline_prompt("beekeepers")
    assert rag != baseline


def test_rag_prompt_defaults_to_week_phrasing():
    prompt = build_rag_prompt("beekeepers", [make_chunk()])
    assert "This Past Week" in prompt
    assert "the coming week" in prompt


def test_rag_prompt_reflects_a_custom_timeframe():
    prompt = build_rag_prompt("beekeepers", [make_chunk()], timeframe=resolve_timeframe("month"))
    assert "This Past Month" in prompt
    assert "the coming month" in prompt
    assert "This Past Week" not in prompt


def test_baseline_prompt_reflects_a_custom_timeframe():
    prompt = build_baseline_prompt("beekeepers", timeframe=resolve_timeframe("year"))
    assert "This Past Year" in prompt
    assert "the coming year" in prompt
