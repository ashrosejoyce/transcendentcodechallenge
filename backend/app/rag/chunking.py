"""Splits a post body into overlapping chunks sized for embedding.

Kept deliberately simple (paragraph-aware, character-bounded) rather than
token-exact, since forum posts are short and this is easy to reason about
and to unit test.
"""
from __future__ import annotations


def chunk_text(text: str, max_chars: int = 800, overlap_chars: int = 120) -> list[str]:
    """Split `text` into chunks of at most `max_chars`, breaking on paragraph
    or sentence boundaries where possible, with `overlap_chars` of repeated
    context between consecutive chunks so retrieval doesn't lose meaning at
    a cut point."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = _pack_paragraphs_into_chunks(text, max_chars, overlap_chars)
    return _apply_overlap(chunks, overlap_chars) if len(chunks) > 1 else chunks


def _pack_paragraphs_into_chunks(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Greedily pack whole paragraphs into chunks up to `max_chars`; a
    single paragraph longer than `max_chars` on its own is hard-split."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
        current = paragraph
        while len(current) > max_chars:
            chunks.append(current[:max_chars])
            current = current[max(max_chars - overlap_chars, 1):]

    if current:
        chunks.append(current)
    return chunks


def _apply_overlap(chunks: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars <= 0:
        return chunks
    overlapped = [chunks[0]]
    for previous, current in zip(chunks, chunks[1:], strict=False):
        tail = previous[-overlap_chars:]
        overlapped.append(f"{tail} {current}".strip())
    return overlapped
