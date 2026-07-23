"""
TraceLearn — replan scheduling boundary (R2-02 fix, A-RC2-1 / A-RC2-2).

Two problems this module solves, both surfaced once the post-onboarding loop
became reachable:

  A-RC2-1  `decide_replan` is a 15-57s `claude-opus-4-8` call. It USED to run
           inline in `POST /tasks/{id}/complete`, so a checkbox click froze the
           UI for up to a minute. Here we split the work: triggers are evaluated
           SYNCHRONOUSLY (cheap, pure, deterministic), and only the agent run is
           handed to a FastAPI BackgroundTask. The request returns in ~tens of ms;
           `trigger_fired` now means "a replan was QUEUED", not "finished". The
           frontend polls `GET /goals/{id}/decisions` for the result.

  A-RC2-2  Replans fired on nearly every completion. A cooldown debounces them:
           after an agent decision lands for a goal, non-explicit triggers are
           suppressed for `TRIGGERS["replan_cooldown_seconds"]`. An explicit user
           request always bypasses the cooldown.

The evaluate step is shared by `routers/evidence.py` (task completion, generic
evidence, simulate) and `routers/diagnostic.py` (checkpoint-quiz submit), so the
whole app schedules replans through ONE guarded path.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlmodel import Session, select

import models
from agent import orchestrator, tools
from agent.triggers import evaluate_triggers
from config import TRIGGERS
from db import session_scope
from logging_config import get_logger

_log = get_logger("agent")


class _BackgroundScheduler(Protocol):
    """Structural type for FastAPI's BackgroundTasks (only add_task is used).
    Kept as a Protocol so tests can pass a capturing double without importing
    Starlette."""

    def add_task(self, func: Any, *args: Any, **kwargs: Any) -> None: ...


# In-process guard against scheduling a second run while the first is still
# in-flight. The DB-based cooldown (below) only sees a decision AFTER the ~15-57s
# opus call writes its row; a burst of completions in that window would otherwise
# each schedule a run. This dict records "a run is queued/executing for goal_id
# since <ts>" so the burst collapses to one. Single-process V1 (no auth, local
# SQLite) — a plain dict + lock is sufficient and deterministic; it is a debounce
# optimisation, not a correctness guarantee, and the DB cooldown remains the
# durable bound across restarts.
_inflight_lock = threading.Lock()
_inflight_since: dict[int, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    # Stored timestamps are UTC ISO strings; tolerate a naive one just in case.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _last_decision_at(session: Session, goal_id: int) -> datetime | None:
    row = session.exec(
        select(models.AgentDecision)
        .where(models.AgentDecision.goal_id == goal_id)
        .order_by(models.AgentDecision.id.desc())
    ).first()
    return _parse_iso(row.created_at) if row else None


def _in_cooldown(session: Session, goal_id: int) -> bool:
    """True if a replan for this goal is within the cooldown window — either a
    decision landed recently (durable, survives restart) or a run is currently
    in-flight (in-process, covers the long opus call before its row exists)."""
    window = TRIGGERS.get("replan_cooldown_seconds", 0) or 0
    if window <= 0:
        return False
    now = _now()

    last = _last_decision_at(session, goal_id)
    if last is not None and (now - last).total_seconds() < window:
        return True

    with _inflight_lock:
        started = _inflight_since.get(goal_id)
    if started is not None and (now.timestamp() - started) < window:
        return True
    return False


def evaluate_and_schedule(
    session: Session,
    goal_id: int,
    background: _BackgroundScheduler | None = None,
    explicit: bool = False,
) -> tuple[bool, int | None]:
    """Evaluate triggers synchronously; if fired, SCHEDULE the agent run in the
    background instead of running it inline.

    Returns (queued, decision_id):
      - queued: a replan was queued (or, in the no-background fallback, run).
      - decision_id: only populated on the synchronous fallback path (no
        BackgroundTasks passed). On the normal async path it is None because the
        decision does not exist yet — the client polls GET /goals/{id}/decisions.

    `explicit=True` (user pressed "replan") bypasses BOTH the min-evidence guard
    (inside evaluate_triggers) and the cooldown.
    """
    # --- cheap, deterministic evaluation (safe on the request thread) --------
    progress = tools.get_progress_summary(session, goal_id)
    learner = tools.get_learner_state(session, goal_id)
    mastery = {c["concept_id"]: c["mastery"] for c in learner.get("concepts", [])}
    recent = tools.get_evidence_since_last_plan(session, goal_id)

    tr = evaluate_triggers(
        progress=progress, concept_mastery=mastery,
        recent_evidence=recent, explicit_request=explicit,
    )
    if not tr.fired:
        return False, None

    # --- cooldown / debounce (A-RC2-2) --------------------------------------
    if not explicit and _in_cooldown(session, goal_id):
        _log.info("replan suppressed by cooldown (goal_id=%s, would-be trigger=%s)",
                  goal_id, tr.reason)
        return False, None

    # --- schedule (A-RC2-1) --------------------------------------------------
    if background is not None:
        with _inflight_lock:
            _inflight_since[goal_id] = _now().timestamp()
        background.add_task(_run_agent_bg, goal_id, tr.reason)
        _log.info("replan queued (goal_id=%s, trigger=%s)", goal_id, tr.reason)
        return True, None

    # Fallback: no background scheduler available (e.g. a direct unit call).
    # Run inline and return the decision_id so behaviour is still correct.
    result = orchestrator.run_agent(session, goal_id, tr.reason)
    return True, result.get("decision_id")


def _run_agent_bg(goal_id: int, reason: str) -> None:
    """Background worker: opens its OWN session (the request's is already closed,
    like goals._process_document) and runs the agent. Never raises — a background
    task has no caller to catch it; every outcome is recorded as an
    agent_decision row by the orchestrator."""
    try:
        with session_scope() as session:
            orchestrator.run_agent(session, goal_id, reason)
    except Exception as exc:  # noqa: BLE001 — background task must not propagate
        _log.error("background replan failed (goal_id=%s, trigger=%s): %s: %s",
                   goal_id, reason, type(exc).__name__, exc)
    finally:
        # Clear the in-flight marker so the NEXT meaningful signal (after the
        # DB cooldown window) can schedule again.
        with _inflight_lock:
            _inflight_since.pop(goal_id, None)
