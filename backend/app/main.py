"""FastAPI application entrypoint.

Run with: uvicorn app.main:app --reload --app-dir backend --port 8080
(see README for the full setup/run instructions).

Decoupled from the frontend on purpose: the frontend (a separate static
file server / nginx container) and this API are two independent
processes, always on different ports, talking over CORS rather than a
same-origin reverse proxy. See frontend/app.js's `API_BASE`.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings

app = FastAPI(title=f"Community Voices - {settings.community_name}")

# Permissive rather than an allowlisted origin: this API has no cookies,
# sessions, or auth to leak (allow_credentials stays False), so there's
# no security reason to hardcode "localhost:8000" and break the moment
# someone opens the frontend from a different host or port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
