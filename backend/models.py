"""
TraceLearn — FROZEN database schema (SQLModel).

Design invariants (see 06_DECISION_REGISTER.md):
  - `concepts` is the central join key AND the language-neutral layer.
      canonical_term  = technical term preserved verbatim (never translated) -> the anchor
      explanation     = the ONLY language-varying field (learner's explanation_language)
  - `plan_versions` is APPEND-ONLY. Replanning = new version_no + new tasks + parent link.
      Never UPDATE a plan version or its tasks.
  - `evidence` is written by the APPLICATION when the user acts; the Agent only READS it.
  - `agent_decisions` is written on EVERY agent invocation, including 'no_change'.
      tool_trace_json is the defence artifact.

JSON-shaped payloads are stored as TEXT columns (SQLite) and documented inline.
Phase 0: schema is complete and final; business logic lives elsewhere.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> str:
    """ISO-8601 UTC timestamp as a string (all timestamps are stored this way)."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# users — MVP hardcodes a single user (no auth). Kept for structure/foreign keys.
# ---------------------------------------------------------------------------
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str | None = None


# ---------------------------------------------------------------------------
# goals — one learning goal. Carries explanation_language (Decision D19).
# ---------------------------------------------------------------------------
class Goal(SQLModel, table=True):
    __tablename__ = "goals"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    goal_text: str
    deadline: str                       # ISO date, e.g. "2026-08-10"
    hours_per_day: float                # study hours the learner commits per day
    explanation_language: str = "en"    # 'en' | 'zh' — human-facing output language
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# documents — one uploaded material file. Optional but kept (single document only).
# ---------------------------------------------------------------------------
class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: int | None = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goals.id")
    filename: str | None = None
    storage_path: str | None = None
    # 'none' | 'uploaded' | 'processing' | 'ready' | 'failed'
    status: str = "none"
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# concepts — CENTRAL ENTITY. Join key + language-neutral layer.
# ---------------------------------------------------------------------------
class Concept(SQLModel, table=True):
    __tablename__ = "concepts"

    id: int | None = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goals.id")
    canonical_term: str                 # e.g. "Normalization" — preserved verbatim, the anchor
    name: str                           # display label (may equal canonical_term)
    explanation: str | None = None      # localized; the ONLY language-varying field
    source: str = "material"            # 'material' | 'goal_topic' | 'user_added'
    order_index: int | None = None      # suggested learning order
    parent_concept_id: int | None = None  # optional shallow hierarchy
    confirmed: bool = False             # True after the user confirms/edits


# ---------------------------------------------------------------------------
# diagnostics — the initial concept-targeted quiz + its results.
# ---------------------------------------------------------------------------
class Diagnostic(SQLModel, table=True):
    __tablename__ = "diagnostics"

    id: int | None = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goals.id")
    # [{id, concept_id, prompt, options, answer}] — prompts localized, concept_id language-independent
    questions_json: str = "[]"
    answers_json: str | None = None                 # user answers
    per_concept_score_json: str | None = None       # {concept_id: score 0..1}
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# plan_versions — APPEND-ONLY immutable roadmap snapshots.
# ---------------------------------------------------------------------------
class PlanVersion(SQLModel, table=True):
    __tablename__ = "plan_versions"

    id: int | None = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goals.id")
    version_no: int
    plan_json: str                       # summary of the plan (days, concept coverage)
    created_by: str                      # 'user' | 'agent'
    parent_version_id: int | None = None  # previous version, for diffing
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# tasks — belong to ONE plan version. New version => new task rows.
# ---------------------------------------------------------------------------
class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: int | None = Field(default=None, primary_key=True)
    plan_version_id: int = Field(foreign_key="plan_versions.id")
    concept_id: int | None = Field(default=None, foreign_key="concepts.id")
    day: str | None = None               # ISO date the task is scheduled for
    description: str                     # localized human-facing text
    est_minutes: int | None = None
    status: str = "pending"              # 'pending' | 'done' | 'skipped'
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# evidence — learning events. Written by the APP, read by the Agent.
# ---------------------------------------------------------------------------
class Evidence(SQLModel, table=True):
    __tablename__ = "evidence"

    id: int | None = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goals.id")
    concept_id: int | None = Field(default=None, foreign_key="concepts.id")
    # 'task_done' | 'task_skipped' | 'quiz_result' | 'time_logged' | 'question'
    type: str
    payload_json: str = "{}"
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# agent_decisions — the DEFENCE ARTIFACT. One row per agent invocation.
# ---------------------------------------------------------------------------
class AgentDecision(SQLModel, table=True):
    __tablename__ = "agent_decisions"

    id: int | None = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goals.id")
    trigger: str                         # which deterministic trigger fired
    evidence_snapshot_json: str = "{}"   # what the Agent saw
    reasoning_text: str = ""             # the LLM justification (localized, human-facing)
    tool_trace_json: str = "[]"          # ordered [{tool, args, result_summary}]
    decision: str = "no_change"          # 'no_change' | 'new_version'
    resulting_plan_version_id: int | None = Field(default=None, foreign_key="plan_versions.id")
    created_at: str = Field(default_factory=_utcnow)
