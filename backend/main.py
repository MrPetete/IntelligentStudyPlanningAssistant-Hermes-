"""
TraceLearn — FastAPI application entry point.

Phase 0 seed: wires the app, CORS, DB startup, and all routers.
All endpoints are stubbed (return mock data) so the three team members can
work in parallel against stable contracts before real logic exists.

Run:
    cd app/backend
    uvicorn main:app --reload
Docs at http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from db import create_db_and_tables
from logging_config import get_logger, setup_logging
from routers import concepts, decisions, diagnostic, evidence, goals, plan

_req_log = get_logger("request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize logging first (so schema-creation issues are logged),
    # then ensure the SQLite schema exists.
    setup_logging()
    create_db_and_tables()
    yield
    # Shutdown: nothing to clean up for local SQLite.


app = FastAPI(
    title="TraceLearn API",
    version="0.1.0-phase0",
    description="Material-Grounded Personal Learning Path Agent — Phase 0 skeleton.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log the OPERATIONAL shape of every request: method, path, status, and
    duration. Deliberately logs the URL path only (never query values or the
    body), so a goal's text / uploaded content never lands in the log file."""
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        # An unhandled error: log the traceback so the tester's file shows the
        # exact failure + timing, then re-raise so FastAPI still returns 500.
        _req_log.exception("%s %s -> unhandled error after %.0fms",
                           request.method, request.url.path, elapsed_ms)
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    log = _req_log.warning if response.status_code >= 500 else _req_log.info
    log("%s %s -> %d (%.0fms)", request.method, request.url.path,
        response.status_code, elapsed_ms)
    return response

# Routers — one per resource area. All handlers are Phase 0 stubs.
app.include_router(goals.router)
app.include_router(concepts.router)
app.include_router(diagnostic.router)
app.include_router(plan.router)
app.include_router(evidence.router)
app.include_router(decisions.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe + a reminder of what mode the seed is running in."""
    from config import MOCK_LLM

    return {"status": "ok", "mock_llm": MOCK_LLM, "phase": "0-seed"}
