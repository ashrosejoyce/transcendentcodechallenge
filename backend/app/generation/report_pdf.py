"""Renders a Community Voices Document (RAG + baseline + sources) as a
downloadable PDF, styled to match the report's own identity rather than
being a plain text dump.

WeasyPrint converts real HTML+CSS into a PDF, so this stays a thin
templating layer - no manual drawing/positioning code, no separate
PDF-specific markup to maintain alongside the HTML the frontend already
renders. System (not web) fonts are used deliberately: fetching a webfont
at render time would make every single PDF request depend on an external
font host being reachable, for a difference a one-off downloaded document
isn't around long enough for a reader to notice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html import escape

from weasyprint import HTML

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*(.+?)\*")

_STYLE = """
@page {
    size: letter;
    margin: 2.1cm 2cm;
}
* { box-sizing: border-box; }
body {
    font-family: Georgia, "Times New Roman", "DejaVu Serif", serif;
    color: #2A2115;
    font-size: 10.5pt;
    line-height: 1.55;
}
.eyebrow {
    font-family: "Courier New", "DejaVu Sans Mono", monospace;
    font-size: 8pt;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: #A6690F;
    margin: 0 0 4pt;
}
h1 { font-size: 21pt; font-weight: 700; margin: 0 0 10pt; }
.meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4pt 16pt;
    font-family: "Courier New", "DejaVu Sans Mono", monospace;
    font-size: 8pt;
    border-top: 0.75pt solid #D8CBA9;
    border-bottom: 0.75pt solid #D8CBA9;
    padding: 6pt 0;
    margin: 0 0 18pt;
}
.meta div { display: flex; gap: 4pt; }
.meta dt { color: #8C7C60; text-transform: uppercase; margin: 0; }
.meta dd { margin: 0; font-weight: 700; }

.doc { margin-bottom: 20pt; }
.doc-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1pt solid #D8CBA9;
    padding-bottom: 4pt;
    margin-bottom: 8pt;
}
.doc-head h2 { font-size: 13pt; margin: 0; }
.badge {
    font-family: "Courier New", "DejaVu Sans Mono", monospace;
    font-size: 7pt;
    text-transform: uppercase;
    padding: 2pt 7pt;
    border-radius: 8pt;
    white-space: nowrap;
}
.badge-grounded { background: #F1DDAF; color: #7C4E0B; }
.badge-baseline { border: 0.75pt solid #C9BB98; color: #8C7C60; }

.rag { border-left: 2pt solid #A6690F; padding-left: 12pt; }
.baseline { color: #6C5D46; }
.baseline .note {
    font-style: italic;
    font-size: 9pt;
    color: #8C7C60;
    margin: 0 0 8pt;
}

h3 {
    font-family: "Courier New", "DejaVu Sans Mono", monospace;
    font-size: 8.5pt;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #A6690F;
    margin: 10pt 0 4pt;
}
.baseline h3 { color: #8C7C60; }
p { margin: 0 0 8pt; text-align: justify; orphans: 3; widows: 3; }

.sources h2 { font-size: 14pt; margin: 0 0 2pt; }
.sources .sub { color: #6C5D46; font-size: 9pt; margin: 0 0 10pt; }
.source-row {
    display: flex;
    gap: 10pt;
    padding: 6pt 0;
    border-bottom: 0.5pt solid #E3DCCC;
}
.rank, .source-meta, .distance {
    font-family: "Courier New", "DejaVu Sans Mono", monospace;
    color: #8C7C60;
}
.rank { font-size: 8pt; }
.source-main { flex: 1; }
.source-main a { color: #2A2115; text-decoration: none; font-weight: 700; font-size: 9.5pt; }
.source-meta { font-size: 7.5pt; margin-top: 2pt; }
.distance { font-size: 8pt; white-space: nowrap; }
"""


@dataclass(frozen=True)
class PdfSourceChunk:
    """The subset of a retrieved chunk actually needed to render one
    source-list row - kept separate from `rag.retrieval.RetrievedChunk`
    so this module has no dependency on the retrieval layer, only on
    plain data the API route already has in hand."""

    subject: str
    board: str
    author: str
    posted_at: str
    url: str
    distance: float


def render_report_pdf(
    community_name: str,
    timeframe_label: str,
    rag_document: str,
    baseline_document: str,
    retrieved_chunks: list[PdfSourceChunk],
    grounded_claim_count: int,
    generated_on: date | None = None,
) -> bytes:
    """Thin on purpose: building the report's HTML and converting HTML to
    PDF bytes are two different jobs (one is this app's content, the
    other is WeasyPrint's), so `_build_html` carries the first and is
    independently testable/inspectable as plain text without needing to
    parse a PDF."""
    html = _build_html(
        community_name,
        timeframe_label,
        rag_document,
        baseline_document,
        retrieved_chunks,
        grounded_claim_count,
        generated_on or datetime.now(UTC).date(),
    )
    return HTML(string=html).write_pdf()


def _build_html(
    community_name: str,
    timeframe_label: str,
    rag_document: str,
    baseline_document: str,
    retrieved_chunks: list[PdfSourceChunk],
    grounded_claim_count: int,
    generated_on: date,
) -> str:
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
  <header>
    <p class="eyebrow">Community Voices Document</p>
    <h1>{escape(community_name)}</h1>
    <dl class="meta">
      <div><dt>Timeframe</dt><dd>{escape(timeframe_label.capitalize())}</dd></div>
      <div><dt>Generated</dt><dd>{generated_on.isoformat()}</dd></div>
      <div><dt>Grounded posts</dt><dd>{grounded_claim_count}</dd></div>
    </dl>
  </header>

  <section class="doc rag">
    <div class="doc-head">
      <h2>RAG&#8209;Grounded</h2>
      <span class="badge badge-grounded">{grounded_claim_count} real posts retrieved</span>
    </div>
    {_markdown_lite_to_html(rag_document)}
  </section>

  <section class="doc baseline">
    <div class="doc-head">
      <h2>Ungrounded Baseline</h2>
      <span class="badge badge-baseline">no retrieval</span>
    </div>
    <p class="note">Compiled with zero access to real threads &mdash; for comparison only.</p>
    {_markdown_lite_to_html(baseline_document)}
  </section>

  <section class="sources">
    <h2>Retrieved Sources</h2>
    <p class="sub">Every claim above traces back to one of these real posts,
    ranked by embedding distance (closer = more relevant).</p>
    {_render_sources(retrieved_chunks)}
  </section>
</body>
</html>"""


def _markdown_lite_to_html(text: str) -> str:
    """Converts the limited markdown-lite shape the generation prompts
    produce (an optional leading "# Title" line, "## Section" headings,
    and blank-line-separated paragraphs - see generation/prompts.py) into
    real HTML. Not a general markdown parser, just enough for this app's
    own prompt format. The leading "# Title" line is dropped since it
    duplicates the page's own community-name heading."""
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]
    html_parts = []
    for block in blocks:
        if block.startswith("## "):
            html_parts.append(f"<h3>{_inline_markdown(escape(block[3:].strip()))}</h3>")
        elif block.startswith("# "):
            continue
        else:
            html_parts.append(f"<p>{_inline_markdown(escape(block))}</p>")
    return "\n".join(html_parts)


def _inline_markdown(escaped_text: str) -> str:
    """Handles the two inline markdown forms Claude's generated prose
    occasionally uses (**bold**, *italic*), applied to already-escaped
    text so this only ever turns literal ** / * markup into real tags,
    never anything from the model's own prose. Bold is resolved first so
    the italic pattern can't mistake half of a **bold** span for a
    *italic* one."""
    text = _BOLD_RE.sub(r"<strong>\1</strong>", escaped_text)
    return _ITALIC_RE.sub(r"<em>\1</em>", text)


def _render_sources(chunks: list[PdfSourceChunk]) -> str:
    if not chunks:
        return '<p class="sub">No sources were retrieved for this document.</p>'
    return "\n".join(_render_source_row(i, chunk) for i, chunk in enumerate(chunks, start=1))


def _render_source_row(rank: int, chunk: PdfSourceChunk) -> str:
    meta = f"{escape(chunk.board)} &middot; {escape(chunk.author)} &middot; {escape(chunk.posted_at[:10])}"
    return f"""<div class="source-row">
          <span class="rank">{rank:02d}</span>
          <div class="source-main">
            <a href="{escape(chunk.url)}">{escape(chunk.subject)}</a>
            <div class="source-meta">{meta}</div>
          </div>
          <span class="distance">{chunk.distance:.3f}</span>
        </div>"""
