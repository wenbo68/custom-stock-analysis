# -*- coding: utf-8 -*-
"""Slim FastAPI app for the standalone tiered-analysis service.

Compared with the parent project this serves exactly four things:
- the tiered API under ``/api/v1/tiered``
- the chat API under ``/api/v1/chat``
- a health probe at ``/api/health``
- the built frontend (``web/`` -> ``static/``) as a single-page app

Startup housekeeping: runs execute as in-process threads, so any run
still "running" when the process starts belongs to a process that died
— it is marked failed. Runs still "queued" are resumed through the
global run queue. Old transcript and cache rows are pruned. Chat
message rows written before the token-count columns existed are
filled once (2026-10-10).

Startup also imports the model client (litellm) and the price-data
stack once, on the main thread, before the first request — see
``preload_libraries``.

CORS is narrowed to CORS_ALLOW_ORIGINS (none by default — the frontend
is served from the same origin, and the Vite dev server proxies /api).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Importing src.config loads .env. It has to be the first project import
# here: ``create_app()`` below reads CORS_ALLOW_ORIGINS at import time,
# and ``uvicorn api.app:app`` or a test's ``TestClient(api.app.app)``
# never goes through server.py, which used to be the only place that
# loaded the file (2026-10-10).
import src.config  # noqa: F401

from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import chat, tiered
from src.chat import store as chat_store
from src.tiered_analysis import run_service

logger = logging.getLogger(__name__)

#: Frontend build output (web/ builds into <repo root>/static).
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

#: Root-level files the SPA fallback may serve directly. Everything else
#: gets index.html — user-supplied paths never touch the filesystem.
ROOT_FILE_ALLOWLIST = frozenset({"favicon.ico", "favicon.svg", "robots.txt"})


def _cors_allow_origins() -> list:
    """Origins allowed to call the API from another site (comma list in
    CORS_ALLOW_ORIGINS). Empty by default: same-origin needs no CORS."""
    raw = os.getenv("CORS_ALLOW_ORIGINS") or ""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


#: Imported at startup, in this order, before the first request. litellm
#: first (about 4 s of the 7 s total), then the price-data stack from
#: the top down: the trading calendar pulls pandas, the exchange
#: calendars and the whole data_provider package; the vendor libraries
#: are what the fetchers import inside their own calls.
PRELOADED_LIBRARIES = (
    "litellm",
    "src.core.trading_calendar",
    "data_provider",
    "yfinance",
    "akshare",
    "efinance",
)


def preload_libraries() -> None:
    """Import the heavy libraries before the server takes requests
    (2026-10-10).

    litellm hooks itself into uvicorn's access-log logger the moment it
    is imported, and that hook imports more of litellm on every log
    line. The chat and analysis code import litellm lazily, inside
    worker threads; when the very first import ran in a chat turn's
    thread while the event loop logged the page's polling request, the
    two threads waited on each other's import locks, Python aborted the
    import ("deadlock detected by _ModuleLock"), and the half-installed
    hook then broke every log line with ``KeyError: 'litellm'`` until
    the process was restarted.

    The price-data stack had the same shape: the trading calendar (and
    with it pandas, the exchange calendars and every fetcher) was first
    imported from GET /status, POST /analyze and each chat turn, and the
    vendor libraries from inside run threads — several of which start at
    once when the queue resumes at startup. Importing everything here,
    alone on the main thread, leaves nothing to race; the lazy imports
    elsewhere then find the modules already loaded.

    A failed import fails startup. Every library here is a required
    dependency, and serving anyway would only move the import — and the
    deadlock — back into the first worker thread that needs it."""
    for name in PRELOADED_LIBRARIES:
        try:
            import_module(name)
        except Exception as exc:
            raise RuntimeError(
                f"required library {name} failed to import at startup: {exc}"
            ) from exc


def startup_housekeeping() -> None:
    """Mark orphaned runs failed, rename older ``done`` rows
    ``succeeded``, resume queued ones, and prune expired rows. Never
    fails startup: a housekeeping error is logged and the app serves
    anyway."""
    from src.tiered_analysis import history
    from src.tiered_analysis.cache_store import prune_cache

    try:
        orphaned = history.fail_stale_running_runs()
        if orphaned:
            logger.warning("marked %d orphaned run(s) failed at startup", orphaned)
    except Exception as exc:
        logger.warning("startup run cleanup skipped: %s", exc)
    try:
        renamed = history.rename_legacy_done_runs()
        if renamed:
            logger.info("renamed the status of %d older run(s) from done to succeeded", renamed)
    except Exception as exc:
        logger.warning("startup run status rename skipped: %s", exc)
    try:
        run_service.run_queue.resume()
    except Exception as exc:
        logger.warning("startup run queue resume skipped: %s", exc)
    try:
        history.prune_transcripts()
        prune_cache()
    except Exception as exc:
        logger.warning("startup pruning skipped: %s", exc)
    try:
        filled = chat_store.backfill_tokens()
        if filled:
            logger.info("filled the token counts of %d older chat message row(s)", filled)
    except Exception as exc:
        logger.warning("startup chat token backfill skipped: %s", exc)
    try:
        # Runs that ended while nobody could be told (the server was
        # down, or housekeeping just failed them) get their chat
        # notices now (2026-10-20).
        from api.v1.endpoints import chat as chat_endpoint

        chat_endpoint.harness.catch_up()
    except Exception as exc:
        logger.warning("startup chat run-notice catch-up skipped: %s", exc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    preload_libraries()
    startup_housekeeping()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Custom Stock Analysis",
        description="Standalone tiered stock analysis (the tiered alt page)",
        version="0.1.0",
        lifespan=_lifespan,
    )

    cors_origins = _cors_allow_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    add_error_handlers(app)

    app.include_router(tiered.router, prefix="/api/v1/tiered", tags=["TieredAnalysis"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    has_frontend = (STATIC_DIR / "index.html").is_file()
    if has_frontend:
        app.mount(
            "/assets",
            StaticFiles(directory=str(STATIC_DIR / "assets"), check_dir=False),
            name="assets",
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content={"error": "not_found",
                             "message": f"API endpoint /{full_path} not found"},
                )
            if full_path in ROOT_FILE_ALLOWLIST:
                candidate = STATIC_DIR / full_path
                if candidate.is_file():
                    return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")
    else:
        logger.warning(
            "frontend build not found at %s — API only. "
            "Build it with: cd web && npm install && npm run build",
            STATIC_DIR,
        )

    return app


app = create_app()
