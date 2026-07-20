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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from db import create_db_and_tables
from routers import concepts, decisions, diagnostic, evidence, goals, plan


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure the SQLite schema exists.
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
