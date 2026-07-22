"""
Evidence + simulation endpoints.

Task completion and generic evidence are written by the APP (not the Agent).
After writing evidence, deterministic triggers are evaluated SYNCHRONOUSLY; if
one fires (and no cooldown is active), the Agent run is SCHEDULED on a background
task — never run inline, so a checkbox click no longer blocks 15-57s on the opus
call (R2-02 / A-RC2-1). `trigger_fired` therefore means "a replan was QUEUED",
and the frontend polls GET /goals/{id}/decisions for the result.
`/simulate` injects a canned failure pattern so a replan can be demonstrated on
demand (examiners can't wait real days).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

import models
from agent import tools
from agent.replan import evaluate_and_schedule
from db import get_session
from schemas import (
    EvidenceCreate,
    SimulateOut,
    SimulateRequest,
    TaskCompleteOut,
    TaskUncompleteOut,
)

router = APIRouter(tags=["evidence"])


@router.post("/tasks/{task_id}/complete", response_model=TaskCompleteOut)
def complete_task(task_id: int, background: BackgroundTasks,
                  session: Session = Depends(get_session)) -> TaskCompleteOut:
    task = session.get(models.Task, task_id)
    if not task:
        raise HTTPException(404, "task not found")

    pv = session.get(models.PlanVersion, task.plan_version_id)
    goal_id = pv.goal_id

    # Append-only guard (D11): only the CURRENT plan version's tasks may be
    # completed. Completing a task on a superseded version would both mutate
    # immutable history and never reach the current version's carried copy,
    # leaving the two versions divergent. Reject as a conflict instead.
    latest = tools._latest_plan_version(session, goal_id)
    if latest and task.plan_version_id != latest.id:
        raise HTTPException(
            409,
            "cannot complete a task on a superseded plan version; "
            "complete the matching task on the current version",
        )

    task.status = "done"
    task.completed_at = models._utcnow()
    session.add(task)

    session.add(models.Evidence(
        goal_id=goal_id, concept_id=task.concept_id, type="task_done",
        payload_json=json.dumps({"task_id": task_id, "minutes": task.est_minutes}, ensure_ascii=False),
    ))
    session.commit()

    # Evaluate synchronously; schedule the agent in the background if it fired.
    fired, _ = evaluate_and_schedule(session, goal_id, background)
    return TaskCompleteOut(task_id=task_id, status="done", trigger_fired=fired)


@router.post("/tasks/{task_id}/uncomplete", response_model=TaskUncompleteOut)
def uncomplete_task(task_id: int, session: Session = Depends(get_session)) -> TaskUncompleteOut:
    """Revert a mistaken completion on the CURRENT plan version: flip done->pending
    and invalidate the matching task_done evidence so mastery/triggers stop
    counting it (B-RC2-1 uncheck). No replan is scheduled — undoing a misclick
    should never itself trigger the agent.

    Guarded like complete_task: only the current version's tasks are mutable
    (append-only history, D11). A task that isn't `done` is returned unchanged so
    the endpoint is idempotent for the frontend."""
    task = session.get(models.Task, task_id)
    if not task:
        raise HTTPException(404, "task not found")

    pv = session.get(models.PlanVersion, task.plan_version_id)
    goal_id = pv.goal_id

    latest = tools._latest_plan_version(session, goal_id)
    if latest and task.plan_version_id != latest.id:
        raise HTTPException(
            409,
            "cannot uncomplete a task on a superseded plan version; "
            "act on the matching task on the current version",
        )

    if task.status != "done":
        return TaskUncompleteOut(task_id=task_id, status=task.status, evidence_removed=0)

    task.status = "pending"
    task.completed_at = None
    session.add(task)

    # Invalidate the task_done evidence this completion wrote. Match by the
    # task_id recorded in the payload so we only remove THIS task's rows, not
    # another task on the same concept. (Evidence has no task FK by design —
    # it's an append log keyed by goal/concept — so we filter in-Python.)
    removed = 0
    rows = session.exec(
        select(models.Evidence)
        .where(models.Evidence.goal_id == goal_id)
        .where(models.Evidence.type == "task_done")
    ).all()
    for e in rows:
        try:
            payload = json.loads(e.payload_json) if e.payload_json else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if payload.get("task_id") == task_id:
            session.delete(e)
            removed += 1
    session.commit()
    return TaskUncompleteOut(task_id=task_id, status="pending", evidence_removed=removed)


@router.post("/goals/{goal_id}/evidence")
def record_evidence(goal_id: int, body: EvidenceCreate, background: BackgroundTasks,
                    session: Session = Depends(get_session)) -> dict:
    if not session.get(models.Goal, goal_id):
        raise HTTPException(404, "goal not found")
    session.add(models.Evidence(
        goal_id=goal_id, concept_id=body.concept_id, type=body.type,
        payload_json=json.dumps(body.payload, ensure_ascii=False),
    ))
    session.commit()
    fired, decision_id = evaluate_and_schedule(session, goal_id, background)
    return {"ok": True, "trigger_fired": fired, "decision_id": decision_id}


@router.post("/goals/{goal_id}/replan")
def explicit_replan(goal_id: int, background: BackgroundTasks,
                    session: Session = Depends(get_session)) -> dict:
    """User-requested replan: always fires (bypasses the min-evidence guard AND
    the cooldown). DECIDED (lead): background + poll — return immediately with
    "queued"; the frontend polls GET /goals/{id}/decisions and toasts when the
    new version lands. Never hold the request open for the 15-57s opus call."""
    if not session.get(models.Goal, goal_id):
        raise HTTPException(404, "goal not found")
    fired, decision_id = evaluate_and_schedule(session, goal_id, background, explicit=True)
    return {"ok": True, "trigger_fired": fired, "decision_id": decision_id}


@router.post("/goals/{goal_id}/simulate", response_model=SimulateOut)
def simulate(goal_id: int, body: SimulateRequest, background: BackgroundTasks,
             session: Session = Depends(get_session)) -> SimulateOut:
    """
    DEMO CONTROL. Inject a canned failure pattern, then evaluate triggers.
      - normalization_failure: low quiz score on Normalization + skipped tasks
      - missed_tasks: mark several current tasks skipped
    """
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")

    created = 0
    norm = session.exec(
        select(models.Concept).where(models.Concept.goal_id == goal_id)
        .where(models.Concept.canonical_term == "Normalization")
    ).first()

    if body.scenario == "normalization_failure":
        session.add(models.Evidence(
            goal_id=goal_id, concept_id=(norm.id if norm else None), type="quiz_result",
            payload_json=json.dumps({"score": 0.3, "source": "sim"}, ensure_ascii=False),
        ))
        created += 1
        for _ in range(3):
            session.add(models.Evidence(
                goal_id=goal_id, concept_id=(norm.id if norm else None), type="task_skipped",
                payload_json=json.dumps({"source": "sim"}, ensure_ascii=False),
            ))
            created += 1
    else:  # missed_tasks
        pv = session.exec(
            select(models.PlanVersion).where(models.PlanVersion.goal_id == goal_id)
            .order_by(models.PlanVersion.version_no.desc())
        ).first()
        tasks = session.exec(
            select(models.Task).where(models.Task.plan_version_id == pv.id)
        ).all() if pv else []
        for t in tasks[:3]:
            t.status = "skipped"
            session.add(t)
            session.add(models.Evidence(
                goal_id=goal_id, concept_id=t.concept_id, type="task_skipped",
                payload_json=json.dumps({"task_id": t.id, "source": "sim"}, ensure_ascii=False),
            ))
            created += 1
    session.commit()

    # Demo control still schedules in the background like the real path, so the
    # examiner sees the same "queued -> poll -> new version" flow. decision_id is
    # None on the async path (poll decisions); populated only on the direct
    # no-background fallback.
    fired, decision_id = evaluate_and_schedule(session, goal_id, background)
    return SimulateOut(scenario=body.scenario, evidence_created=created,
                       trigger_fired=fired, decision_id=decision_id)
