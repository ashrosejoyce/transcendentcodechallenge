"""FastAPI application entrypoint.

Run with: uvicorn app.main:app --reload --app-dir backend
(see README for the full setup/run instructions).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title=f"Community Voices - {settings.community_name}")
app.include_router(router)

if FRONTEND_DIR.is_dir():
    # Local/single-process convenience: serve the frontend from this same
    # app. In the Docker Compose setup the frontend is its own nginx
    # container and this directory doesn't exist in the backend image, so
    # this mount is skipped there - nginx serves the static files instead
    # and reverse-proxies /api/ to this service.
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logger.info("Frontend directory not found at %s; skipping static mount.", FRONTEND_DIR)
