"""FastAPI application for the Finance Analyzer chat server.

Provides:
- GET  /          — health check
- GET  /chat/stream  — SSE streaming chat endpoint
- POST /chat/approve — approval/rejection endpoint for write operations
- Static files at /static (for future frontend)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.sessions import SessionStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise session store on startup."""
    app.state.session_store = SessionStore()
    yield


app = FastAPI(
    title="Finance Analyzer",
    lifespan=lifespan,
)

# CORS for development — allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


# Import and include chat router AFTER app is created to avoid circular imports
from src.chat import router as chat_router  # noqa: E402

app.include_router(chat_router)

# Static files — mount at root after API routes so /chat/* takes priority.
# StaticFiles(html=True) serves index.html for "/" and falls back to
# index.html for unknown paths (SPA-style).
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")