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
from pathlib import Path

# Load a git-ignored backend/.env BEFORE reading any env var below, so a plain
# `uvicorn main:app` picks up MOCK_LLM / the LMU key without the tester manually
# `set`-ing them (C-1: without this the process silently stays mock_llm:true and
# every tester run is invalidated). Idempotent and non-fatal: a real environment
# variable still wins over the file, and a missing python-dotenv just no-ops.
# Load from the backend dir explicitly so it works regardless of the cwd uvicorn
# was launched from.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# MOCK_LLM defaults to True (the safe default stays) — a present .env only now
# actually takes effect.
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
# Model escalation ladder (cost-aware capability ladder)
# ---------------------------------------------------------------------------
# A call starts at its per-task model (the cheapest tier that should handle it)
# and, ONLY if that tier fails to parse / transport-fails after its attempts,
# escalates UP to the next tier for that one call. Because per-task routing is
# independent, the next task automatically starts back at the cheapest tier —
# so we never get "stuck" on an expensive model and blow the bill. Escalation
# is triggered by OBJECTIVE failure (unparseable response / transport error),
# not by the model's self-reported confidence (which isn't trustworthy).
#
# Ordered cheapest -> strongest, each with its own attempt budget (tunable via
# env). The top tier is terminal: if it still fails, we stop and raise an
# explanatory LLMUnavailableError instead of looping forever.
#   Haiku  : 3 attempts (cheap; most calls succeed here)
#   Sonnet : 2 attempts
#   Opus   : 2 attempts (also absorbs a transient API error at the top)
LADDER_ATTEMPTS_GENERATION = int(os.getenv("LADDER_ATTEMPTS_GENERATION", "3"))
LADDER_ATTEMPTS_PLAN = int(os.getenv("LADDER_ATTEMPTS_PLAN", "2"))
LADDER_ATTEMPTS_REPLAN = int(os.getenv("LADDER_ATTEMPTS_REPLAN", "2"))
MODEL_LADDER = [
    (MODEL_GENERATION, LADDER_ATTEMPTS_GENERATION),  # haiku tier
    (MODEL_PLAN, LADDER_ATTEMPTS_PLAN),              # sonnet tier
    (MODEL_REPLAN, LADDER_ATTEMPTS_REPLAN),          # opus tier
]

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
    "ahead_schedule_pct": 0.20,    # >20% of not-yet-due tasks already done -> consider pulling work forward
    "low_mastery_threshold": 0.40, # concept mastery below this after evidence -> consider
    "quiz_fail_threshold": 0.50,   # quiz score below this on a concept -> consider
    "min_evidence_events": 3,      # never replan on a single data point
    # Debounce: after an agent decision lands for a goal, non-explicit triggers
    # are suppressed for this many seconds. Without it, a burst of quick task
    # completions clears min_evidence_events instantly and replans fire on nearly
    # every checkbox (R2-02). An explicit user "replan" always bypasses this.
    "replan_cooldown_seconds": 300,
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
# Logging (local, privacy-safe, persistent — see logging_config.py)
# Operational metadata only (times, endpoints, model ids, durations, errors,
# decision types); NEVER request bodies, goal/document content, or the API key.
# Size-based rotation so the log persists across restarts and is not time-wiped.
# ---------------------------------------------------------------------------
LOG_DIR = os.getenv("LOG_DIR", "./logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")             # DEBUG for verbose local debugging
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # 5 MB per file
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))             # keep 5 rolled-over files

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
SINGLE_USER_ID = 1     # MVP hardcodes one user (no auth — Decision: no authentication)
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # Vite dev server
