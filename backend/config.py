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
# LLM / Agent
# ---------------------------------------------------------------------------
# MOCK_LLM = True  ->  no network calls; llm_client returns canned JSON.
# Flip to False only once a real Hermes endpoint is wired (later phase).
MOCK_LLM = True

MODEL_NAME = "hermes-tool-calling"   # placeholder id; real endpoint wired later
LLM_MAX_RETRIES = 2                  # bounded retries for JSON / validation failures

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
