"""
Plan endpoints: generate V1 (placeholder), current, versions list, single version, diff.

Generation uses MOCK LLM + the real validator, then create_plan_version (append-only).
Diff is computed by comparing task sets between two versions, grouped by concept.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

import models
from agent import llm_client, tools
from agent.llm_client import LLMUnavailableError
from agent.validator import available_minutes_for, validate_plan
from db import get_session
from schemas import PlanDiff, PlanVersionOut, PlanVersionSummary, TaskOut

router = APIRouter(prefix="/goals", tags=["plan"])

# Bounded revise attempts before we accept a budget failure as "too tight".
_MAX_PLAN_ATTEMPTS = 2
# Below this many raw study minutes a deadline is too tight to attempt at all:
# not enough time to cover even one core concept well, so we return a clear,
# actionable error instead of a near-useless one-task stub.
_TOO_TIGHT_MIN_MINUTES = 30


def _tasks_for(session: Session, plan_version_id: int) -> list[models.Task]:
    return session.exec(
        select(models.Task).where(models.Task.plan_version_id == plan_version_id)
    ).all()


def _term_map(session: Session, goal_id: int) -> dict[int, str]:
    return {
        c.id: c.canonical_term
        for c in session.exec(select(models.Concept).where(models.Concept.goal_id == goal_id)).all()
    }


def _coverage_note(plan: dict, concepts: list[models.Concept], lang: str) -> str | None:
    """Honest note when a tight deadline trimmed the plan to a core subset.

    Compares distinct concept_ids in the persisted plan against the total
    confirmed concepts. Returns None when every concept is covered. Localized
    to the goal's explanation_language (en/zh) to match the plan prompt.
    """
    confirmed = [c for c in concepts if c.confirmed] or list(concepts)
    total = len(confirmed)
    covered = len({t.get("concept_id") for t in plan.get("tasks", [])
                   if t.get("concept_id") is not None})
    if total == 0 or covered >= total:
        return None
    if lang == "zh":
        return f"截止日期较紧：已覆盖 {total} 个概念中最核心的 {covered} 个，其余暂缓。"
    return (f"Tight deadline: core {covered} of {total} concepts covered; "
            "rest deferred.")


def _task_out(t: models.Task, terms: dict[int, str]) -> TaskOut:
    return TaskOut(
        id=t.id, concept_id=t.concept_id,
        canonical_term=terms.get(t.concept_id) if t.concept_id else None,
        day=t.day, description=t.description, est_minutes=t.est_minutes, status=t.status,
    )


@router.post("/{goal_id}/plan/generate", response_model=PlanVersionOut)
def generate_plan(goal_id: int, session: Session = Depends(get_session)) -> PlanVersionOut:
    """V1.1 generation: budget -> bounded revise loop -> validate -> persist.

    The day-accurate budget lets a tight deadline produce an honest, fitting
    plan (core concepts covered, rest deferred with a coverage_note) instead of
    dead-ending at a 422. A genuinely impossible deadline returns a structured
    ``deadline_too_tight`` error the frontend can render as a friendly retry.
    """
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")
    concepts = session.exec(select(models.Concept).where(models.Concept.goal_id == goal_id)).all()
    if not concepts:
        raise HTTPException(400, "confirm a concept map first")

    # Day-accurate budget: same helper the validator uses, so prompt + gate agree.
    now = datetime.now()
    deadline_d = date.fromisoformat(goal.deadline[:10])
    available_minutes = int(available_minutes_for(goal.hours_per_day, deadline_d, now))
    days_left = max(0, (deadline_d - now.date()).days)
    num_days = available_minutes / (goal.hours_per_day * 60.0) if goal.hours_per_day else 0.0

    # Impossible before we even ask the model: not enough time for a core plan.
    if available_minutes < _TOO_TIGHT_MIN_MINUTES:
        raise HTTPException(422, {"error": "deadline_too_tight", "detail": (
            f"This deadline (~{days_left} day(s) left) is too short to cover this "
            f"material at {goal.hours_per_day}h/day. Extend the deadline or raise "
            "your daily hours.")})

    concept_dicts = [{"id": c.id, "canonical_term": c.canonical_term} for c in concepts]
    valid_ids = {c.id for c in concepts if c.confirmed} or {c.id for c in concepts}

    # Bounded revise loop: feed each validation failure back to the model so a
    # fixable overage self-corrects without the user ever seeing an error.
    plan: dict | None = None
    vres = None
    errors: list[str] | None = None
    for _ in range(_MAX_PLAN_ATTEMPTS):
        try:
            plan = llm_client.generate_plan(
                goal={"deadline": goal.deadline, "hours_per_day": goal.hours_per_day},
                concepts=concept_dicts, scores={},
                explanation_language=goal.explanation_language,
                available_minutes=available_minutes, num_days=num_days,
                revise_errors=errors,
            )
        except LLMUnavailableError as exc:
            # A3: live model unavailable -> clean, retryable error (never a 500).
            raise HTTPException(502, {"error": "plan generation unavailable, please retry",
                                      "detail": str(exc)}) from exc
        vres = validate_plan(
            plan=plan, hours_per_day=goal.hours_per_day, deadline=goal.deadline,
            today=now.date().isoformat(), valid_concept_ids=valid_ids, now=now,
        )
        if vres.ok:
            break
        errors = vres.errors

    if not vres.ok:
        # Loop exhausted. A budget-only failure on a tiny budget means the
        # deadline is genuinely too tight; anything else is a real defect.
        only_budget = all("exceed available" in e for e in vres.errors)
        if only_budget:
            raise HTTPException(422, {"error": "deadline_too_tight", "detail": (
                f"This deadline (~{days_left} day(s) left) is too short to cover this "
                f"material at {goal.hours_per_day}h/day. Extend the deadline or raise "
                "your daily hours.")})
        raise HTTPException(422, {"error": "generated plan failed validation",
                                  "detail": vres.errors})

    created = tools.create_plan_version(session, goal_id, plan, created_by="user")
    out = get_plan_version(goal_id, created["version_no"], session)
    out.coverage_note = _coverage_note(plan, concepts, goal.explanation_language)
    return out


@router.get("/{goal_id}/plan/current", response_model=PlanVersionOut)
def get_current_plan(goal_id: int, session: Session = Depends(get_session)) -> PlanVersionOut:
    pv = session.exec(
        select(models.PlanVersion).where(models.PlanVersion.goal_id == goal_id)
        .order_by(models.PlanVersion.version_no.desc())
    ).first()
    if not pv:
        raise HTTPException(404, "no plan yet")
    terms = _term_map(session, goal_id)
    return PlanVersionOut(
        id=pv.id, version_no=pv.version_no, created_by=pv.created_by,
        parent_version_id=pv.parent_version_id, created_at=pv.created_at,
        tasks=[_task_out(t, terms) for t in _tasks_for(session, pv.id)],
    )


@router.get("/{goal_id}/plan/versions", response_model=list[PlanVersionSummary])
def list_versions(goal_id: int, session: Session = Depends(get_session)) -> list[PlanVersionSummary]:
    rows = session.exec(
        select(models.PlanVersion).where(models.PlanVersion.goal_id == goal_id)
        .order_by(models.PlanVersion.version_no)
    ).all()
    return [
        PlanVersionSummary(id=p.id, version_no=p.version_no, created_by=p.created_by,
                           parent_version_id=p.parent_version_id, created_at=p.created_at)
        for p in rows
    ]


@router.get("/{goal_id}/plan/versions/{version_no}", response_model=PlanVersionOut)
def get_plan_version(goal_id: int, version_no: int,
                     session: Session = Depends(get_session)) -> PlanVersionOut:
    pv = session.exec(
        select(models.PlanVersion).where(models.PlanVersion.goal_id == goal_id)
        .where(models.PlanVersion.version_no == version_no)
    ).first()
    if not pv:
        raise HTTPException(404, "version not found")
    terms = _term_map(session, goal_id)
    return PlanVersionOut(
        id=pv.id, version_no=pv.version_no, created_by=pv.created_by,
        parent_version_id=pv.parent_version_id, created_at=pv.created_at,
        tasks=[_task_out(t, terms) for t in _tasks_for(session, pv.id)],
    )


@router.get("/{goal_id}/plan/diff", response_model=PlanDiff)
def plan_diff(goal_id: int, from_: int = Query(..., alias="from"), to: int = Query(...),
              session: Session = Depends(get_session)) -> PlanDiff:
    """Structured diff between two versions, grouped by canonical_term."""
    terms = _term_map(session, goal_id)

    def tasks_of(vno: int) -> list[models.Task]:
        pv = session.exec(
            select(models.PlanVersion).where(models.PlanVersion.goal_id == goal_id)
            .where(models.PlanVersion.version_no == vno)
        ).first()
        if not pv:
            raise HTTPException(404, f"version {vno} not found")
        return _tasks_for(session, pv.id)

    a, b = tasks_of(from_), tasks_of(to)
    a_keys = {(t.description, t.day) for t in a}
    b_keys = {(t.description, t.day) for t in b}

    added = [t for t in b if (t.description, t.day) not in a_keys]
    removed = [t for t in a if (t.description, t.day) not in b_keys]
    unchanged = len(b) - len(added)

    added_counts: dict[str, int] = {}
    for t in added:
        term = terms.get(t.concept_id, "general") if t.concept_id else "general"
        added_counts[term] = added_counts.get(term, 0) + 1
    removed_counts: dict[str, int] = {}
    for t in removed:
        term = terms.get(t.concept_id, "general") if t.concept_id else "general"
        removed_counts[term] = removed_counts.get(term, 0) + 1

    concept_summary: dict[str, str] = {}
    for term in set(added_counts) | set(removed_counts):
        parts = []
        if added_counts.get(term):
            parts.append(f"{added_counts[term]} added")
        if removed_counts.get(term):
            parts.append(f"{removed_counts[term]} removed")
        concept_summary[term] = "; ".join(parts)

    return PlanDiff(
        from_version=from_, to_version=to,
        added_tasks=[_task_out(t, terms) for t in added],
        removed_tasks=[_task_out(t, terms) for t in removed],
        unchanged_count=max(0, unchanged), concept_summary=concept_summary,
    )
