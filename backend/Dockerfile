# Build context is the repo root (see docker-compose.yml) so this can
# reach both requirements.txt and backend/ - `docker build -f backend/Dockerfile .`
FROM python:3.12-slim

# ca-certificates: HTTPS calls to the forum + the Anthropic API
# curl: used by the HEALTHCHECK below only
# libpango-1.0-0/libpangoft2-1.0-0/libgdk-pixbuf-2.0-0: WeasyPrint's text
# layout and image handling (generation/report_pdf.py) - it only looks
# pure-Python; it dlopen()s these at import time and fails immediately
# without them. fonts-dejavu-core: so the PDF's serif/mono type actually
# renders with real glyphs instead of a bare fallback in a container that
# ships no fonts of its own.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache the local embedding model under /app so it survives the later
# chown to `appuser` below (its default location is under $HOME, which
# would otherwise belong to `root` and be unreadable after we switch user).
ENV HF_HOME=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1

# Install the CPU-only PyTorch build first. Left to its own resolution,
# sentence-transformers pulls in the full CUDA build - a few GB of NVIDIA
# libraries that are dead weight in a container with no GPU. Installing
# the CPU wheel first means pip finds `torch` already satisfied when it
# processes requirements.txt below instead of replacing it.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model at build time so the image is fully
# self-contained: no first-run download delay, and ingestion/embedding
# work with zero network access afterward (only generation needs one, for
# the Anthropic API).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY backend/ backend/

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

ENV DATABASE_PATH=/app/data/community_voices.db

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/stats || exit 1

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
