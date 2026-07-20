"""
TraceLearn — the 7 Agent tools (5 read, 2 write).

These are the ONLY ways the Agent touches the world. Signatures are FROZEN and
final; Phase 0 bodies contain real DB reads/writes where trivial, and clearly
marked stubs where feature logic is deferred.

Design rules (see 06_DECISION_REGISTER.md):
  - Small, guarded WRITE surface (2 tools). No record_task_progress tool:
    task progress is written by the APP, the Agent only READS evidence.
  - Machine layer stays English: tool names, args, canonical_term, identifiers.
  - search_learning_material returns {"available": false} (no RAG in MVP).
  - create_plan_version is APPEND-ONLY and must pass the validator (enforced by
    the orchestrator, which owns the retry/fallback policy).

Each tool returns JSON-serializable data. The orchestrator records every call
into the tool trace.
"""
from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

import models


# ===========================================================================
# READ TOOLS
# ===========================================================================
def get_learner_state(session: Session, goal_id: int) -> dict[str, Any]:
    """Goal + deadline + weekly hours + per-concept mastery + explanation_language."""
    goal = session.get(models.Goal, goal_id)
    if not goal:
        return {"error": "goal_not_found"}

    concepts = session.exec(
        select(models.Concept).where(models.Concept.goal_id == goal_id)
    ).all()
    mastery = _mastery_by_concept(session, goal_id)

    return {
        "goal_text": goal.goal_text,
        "deadline": goal.deadline,
        "weekly_hours": goal.weekly_hours,
        "explanation_language": goal.explanation_language,
        "concepts": [
            {
                "concept_id": c.id,
                "canonical_term": c.canonical_term,
                "mastery": mastery.get(c.id, 0.5),
                "confirmed": c.confirmed,
            }
            for c in concepts
        ],
    }


def get_current_plan(session: Session, goal_id: int) -> dict[str, Any]:
    """Latest plan version + its tasks."""
    pv = _latest_plan_version(session, goal_id)
    if not pv:
        return {"version_no": 0, "tasks": []}
    tasks = session.exec(
        select(models.Task).where(models.Task.plan_version_id == pv.id)
    ).all()
    return {
        "plan_version_id": pv.id,
        "version_no": pv.version_no,
        "tasks": [
            {"id": t.id, "concept_id": t.concept_id, "day": t.day,
             "description": t.description, "status": t.status}
            for t in tasks
        ],
    }


def get_progress_summary(session: Session, goal_id: int) -> dict[str, Any]:
    """Aggregate progress against the current plan."""
    pv = _latest_plan_version(session, goal_id)
    if not pv:
        return {"tasks_total": 0, "tasks_done": 0, "tasks_due": 0, "tasks_incomplete": 0}
    tasks = session.exec(
        select(models.Task).where(models.Task.plan_version_id == pv.id)
    ).all()
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == "done")
    # For the seed, "due" == all tasks; scheduling-aware "due" is a later refinement.
    due = total
    incomplete = sum(1 for t in tasks if t.status != "done")
    return {
        "tasks_total": total,
        "tasks_done": done,
        "tasks_due": due,
        "tasks_incomplete": incomplete,
    }


def get_evidence_since_last_plan(session: Session, goal_id: int) -> list[dict[str, Any]]:
    """Evidence rows created after the current plan version — the replan input."""
    pv = _latest_plan_version(session, goal_id)
    cutoff = pv.created_at if pv else ""
    rows = session.exec(
        select(models.Evidence)
        .where(models.Evidence.goal_id == goal_id)
        .where(models.Evidence.created_at >= cutoff)
    ).all()
    return [
        {
            "id": e.id,
            "type": e.type,
            "concept_id": e.concept_id,
            "payload": _loads(e.payload_json),
            "created_at": e.created_at,
        }
        for e in rows
    ]


def search_learning_material(session: Session, goal_id: int, query: str, k: int = 5) -> dict[str, Any]:
    """Retrieval over material. NOT built in the MVP (no RAG) — degrades gracefully."""
    return {"available": False, "chunks": [], "note": "retrieval not enabled in MVP"}


# ===========================================================================
# WRITE TOOLS (few, guarded)
# ===========================================================================
def create_plan_version(
    session: Session,
    goal_id: int,
    plan: dict[str, Any],
    created_by: str = "agent",
) -> dict[str, Any]:
    """
    Create a NEW immutable plan version + its tasks, linked to the current version.

    APPEND-ONLY: never mutates an existing version. The orchestrator MUST have
    validated `plan` before calling this. Tasks are expected to carry resolved
    concept_id values (the orchestrator resolves canonical_term -> concept_id).
    """
    prev = _latest_plan_version(session, goal_id)
    next_no = (prev.version_no + 1) if prev else 1

    pv = models.PlanVersion(
        goal_id=goal_id,
        version_no=next_no,
        plan_json=_dumps({"tasks": plan.get("tasks", [])}),
        created_by=created_by,
        parent_version_id=prev.id if prev else None,
    )
    session.add(pv)
    session.commit()
    session.refresh(pv)

    for t in plan.get("tasks", []):
        session.add(
            models.Task(
                plan_version_id=pv.id,
                concept_id=t.get("concept_id"),
                day=t.get("day"),
                description=t.get("description", ""),
                est_minutes=t.get("est_minutes"),
                status="pending",
            )
        )
    session.commit()
    return {"plan_version_id": pv.id, "version_no": pv.version_no}


def record_agent_decision(
    session: Session,
    goal_id: int,
    trigger: str,
    evidence_snapshot: dict[str, Any],
    reasoning_text: str,
    tool_trace: list[dict[str, Any]],
    decision: str,
    resulting_plan_version_id: int | None,
) -> dict[str, Any]:
    """
    Write the agent_decisions row (the defence artifact). Called once at the end
    of EVERY agent invocation, including 'no_change'.
    """
    rec = models.AgentDecision(
        goal_id=goal_id,
        trigger=trigger,
        evidence_snapshot_json=_dumps(evidence_snapshot),
        reasoning_text=reasoning_text,
        tool_trace_json=_dumps(tool_trace),
        decision=decision,
        resulting_plan_version_id=resulting_plan_version_id,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return {"decision_id": rec.id}


# ===========================================================================
# internal helpers (not tools)
# ===========================================================================
def _latest_plan_version(session: Session, goal_id: int) -> models.PlanVersion | None:
    return session.exec(
        select(models.PlanVersion)
        .where(models.PlanVersion.goal_id == goal_id)
        .order_by(models.PlanVersion.version_no.desc())
    ).first()


def _mastery_by_concept(session: Session, goal_id: int) -> dict[int, float]:
    """
    Derive a per-concept mastery signal from evidence.

    Phase 0: simple heuristic — start at 0.5, nudge down on failed quizzes /
    skipped tasks. Documented and explainable (the Agent will cite it). A richer
    weighted update is a later refinement.
    """
    mastery: dict[int, float] = {}
    rows = session.exec(
        select(models.Evidence).where(models.Evidence.goal_id == goal_id)
    ).all()
    for e in rows:
        if e.concept_id is None:
            continue
        cur = mastery.setdefault(e.concept_id, 0.5)
        payload = _loads(e.payload_json)
        if e.type == "quiz_result" and payload.get("score") is not None:
            mastery[e.concept_id] = float(payload["score"])
        elif e.type == "task_skipped":
            mastery[e.concept_id] = max(0.0, cur - 0.15)
        elif e.type == "task_done":
            mastery[e.concept_id] = min(1.0, cur + 0.1)
    return mastery


def _loads(s: str | None) -> dict[str, Any]:
    try:
        return json.loads(s) if s else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
