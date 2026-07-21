"""
TraceLearn — central configuration (single source of truth).

Everything tunable lives here. Nothing tunable should be hardcoded in logic.
This is Phase 0 seed scope: values are sensible defaults, tuned later in Phase 2.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = "sqlite:///./tracelearn.db"

# ---------------------------------------------------------------------------
# LLM / Agent  (Phase 2: env-driven so the real endpoint is config, not code)
# ---------------------------------------------------------------------------
# MOCK_LLM = True  ->  no network calls; llm_client returns canned JSON.
# Defaults to True so nobody goes live by accident and the offline demo (D18)
# keeps working. Flip to False ONLY via a local .env once the endpoint is set.
import os

MOCK_LLM = os.getenv("MOCK_LLM", "true").strip().lower() in ("1", "true", "yes")

# "Hermes" is the project's name for the swappable tool-calling model behind
# llm_client (02_AGENT_BACKEND_CONTEXT.md). The team's endpoint is a native
# Anthropic Messages API (LMU AI). These come from a git-ignored .env — the
# API key is NEVER committed. See backend/.env.example for the shape.
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.lmuai.com")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# The LMU endpoint (confirmed 2026-07-21) serves three claude tiers:
#   claude-haiku-4-5-20251001  — cheap/fast (concept extraction, diagnostics)
#   claude-sonnet-4-6          — balanced (plan generation)  [default]
#   claude-opus-4-8            — strongest reasoning (decide_replan)
# MODEL_NAME is the default for any call that doesn't override it. Per-task
# routing (A2) passes a specific id per call via hermes_client.complete(model=).
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-6")
# A2 routing seams (env-overridable; default to MODEL_NAME if you skip routing):
MODEL_GENERATION = os.getenv("MODEL_GENERATION", "claude-haiku-4-5-20251001")
MODEL_PLAN = os.getenv("MODEL_PLAN", "claude-sonnet-4-6")
MODEL_REPLAN = os.getenv("MODEL_REPLAN", "claude-opus-4-8")

LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))  # bounded retries for JSON / transport failures

# ---------------------------------------------------------------------------
# Language (Decision D19 — content-only bilingual, two languages, no UI i18n)
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = ["en", "zh"]   # FROZEN at two. Do not extend in the MVP.
DEFAULT_EXPLANATION_LANGUAGE = "en"

# ---------------------------------------------------------------------------
# Deterministic replan triggers
# The Agent is NOT invoked on every event. These thresholds decide when it wakes.
# ---------------------------------------------------------------------------
TRIGGERS = {
    "behind_schedule_pct": 0.25,   # >25% of due tasks incomplete -> consider replan
    "low_mastery_threshold": 0.40, # concept mastery below this after evidence -> consider
    "quiz_fail_threshold": 0.50,   # quiz score below this on a concept -> consider
    "min_evidence_events": 3,      # never replan on a single data point
}

# ---------------------------------------------------------------------------
# Diagnostic / plan generation
# ---------------------------------------------------------------------------
DIAGNOSTIC_NUM_QUESTIONS = 6

# ---------------------------------------------------------------------------
# Retrieval (NOT built in MVP — search_learning_material returns available:false)
# Values kept here so the interface is config-ready without being implemented.
# ---------------------------------------------------------------------------
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 5
EMBEDDING_MODEL = None  # not used in MVP

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
SINGLE_USER_ID = 1     # MVP hardcodes one user (no auth — Decision: no authentication)
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # Vite dev server
