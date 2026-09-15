"""Local, offline embedding model wrapper.

Uses sentence-transformers so reviewers need zero extra API keys or signups
to run the RAG pipeline end-to-end - only the Anthropic key (for generation)
is required. See README for the tradeoff discussion (local vs. Voyage AI).
"""
from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from app.config import settings


@lru_cache(maxsize=1)
def _model():
    # Imported lazily so importing this module doesn't force a slow
    # sentence-transformers/torch import for code paths that don't embed.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def embedding_dimensions() -> int:
    return _model().get_sentence_embedding_dimension()


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = _model().encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    return [vector.tolist() for vector in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
