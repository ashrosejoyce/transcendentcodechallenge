from datetime import date

from app.generation.report_pdf import PdfSourceChunk, _build_html, _markdown_lite_to_html, render_report_pdf


def make_chunk(subject="Early swarms") -> PdfSourceChunk:
    return PdfSourceChunk(
        subject=subject,
        board="General Beekeeping",
        author="MikeyN.C.",
        posted_at="2026-09-10T12:00:00+00:00",
        url="https://beemaster.com/forum/index.php?topic=1.msg1",
        distance=0.123,
    )


def test_render_report_pdf_produces_valid_pdf_bytes():
    pdf = render_report_pdf(
        community_name="beekeepers",
        timeframe_label="week",
        rag_document="# Community Voices Document: beekeepers\n\n## This Past Week\n\nBees swarmed early.",
        baseline_document="## This Past Week\n\nGeneric speculation.",
        retrieved_chunks=[make_chunk()],
        grounded_claim_count=1,
        generated_on=date(2026, 9, 15),
    )

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_render_report_pdf_handles_no_sources():
    pdf = render_report_pdf(
        community_name="beekeepers",
        timeframe_label="week",
        rag_document="## This Past Week\n\n(no matching source material was retrieved)",
        baseline_document="## This Past Week\n\nGeneric speculation.",
        retrieved_chunks=[],
        grounded_claim_count=0,
        generated_on=date(2026, 9, 15),
    )

    assert pdf.startswith(b"%PDF")


def test_markdown_lite_drops_the_leading_title_line():
    html = _markdown_lite_to_html("# Community Voices Document: beekeepers\n\n## This Past Week\n\nBody text.")
    assert "Community Voices Document" not in html
    assert "<h3>This Past Week</h3>" in html
    assert "<p>Body text.</p>" in html


def test_markdown_lite_escapes_html_in_content():
    html = _markdown_lite_to_html("## <script>alert(1)</script>\n\nA <b>bold</b> claim.")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_build_html_escapes_community_name_and_includes_real_counts():
    """_build_html is split out from render_report_pdf specifically so
    the report's actual content can be asserted on directly, as plain
    text, without going through a PDF parser."""
    html = _build_html(
        community_name="<Bees> & Co",
        timeframe_label="week",
        rag_document="## This Past Week\n\nSwarm season started.",
        baseline_document="## This Past Week\n\nGeneric speculation.",
        retrieved_chunks=[make_chunk()],
        grounded_claim_count=1,
        generated_on=date(2026, 9, 15),
    )

    assert "<Bees> & Co" not in html
    assert "&lt;Bees&gt; &amp; Co" in html
    assert "2026-09-15" in html
    assert "1 real posts retrieved" in html
    assert "Swarm season started." in html


def test_markdown_lite_handles_multiple_paragraphs_per_section():
    html = _markdown_lite_to_html("## Section\n\nFirst paragraph.\n\nSecond paragraph.")
    assert html.count("<p>") == 2


def test_markdown_lite_converts_inline_bold_and_italic():
    html = _markdown_lite_to_html("## Section\n\n**Note:** this is *important* context.")
    assert "<strong>Note:</strong>" in html
    assert "<em>important</em>" in html
    assert "**" not in html
    assert html.count("*") == 0
