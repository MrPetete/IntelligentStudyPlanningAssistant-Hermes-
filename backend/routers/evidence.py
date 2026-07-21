"""
Evidence + simulation endpoints.

Task completion and generic evidence are written by the APP (not the Agent).
After writing evidence, deterministic triggers are evaluated; if one fires, the
orchestrator runs the Agent. `/simulate` injects a canned failure pattern so a
replan can be demonstrated on demand (examiners can't wait real days).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import models
from agent import orchestrator, tools
from agent.triggers import evaluate_triggers
from db import get_session
from schemas import (
    EvidenceCreate,
    SimulateOut,
    SimulateRequest,
    TaskCompleteOut,
)

router = APIRouter(tags=["evidence"])


def _evaluate_and_maybe_run(session: Session, goal_id: int, explicit: bool = False):
    """Shared: build trigger inputs, evaluate, and run the Agent if fired."""
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
    result = orchestrator.run_agent(session, goal_id, tr.reason)
    return True, result.get("decision_id")


@router.post("/tasks/{task_id}/complete", response_model=TaskCompleteOut)
def complete_task(task_id: int, session: Session = Depends(get_session)) -> TaskCompleteOut:
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

    fired, _ = _evaluate_and_maybe_run(session, goal_id)
    return TaskCompleteOut(task_id=task_id, status="done", trigger_fired=fired)


@router.post("/goals/{goal_id}/evidence")
def record_evidence(goal_id: int, body: EvidenceCreate,
                    session: Session = Depends(get_session)) -> dict:
    if not session.get(models.Goal, goal_id):
        raise HTTPException(404, "goal not found")
    session.add(models.Evidence(
        goal_id=goal_id, concept_id=body.concept_id, type=body.type,
        payload_json=json.dumps(body.payload, ensure_ascii=False),
    ))
    session.commit()
    fired, decision_id = _evaluate_and_maybe_run(session, goal_id)
    return {"ok": True, "trigger_fired": fired, "decision_id": decision_id}


@router.post("/goals/{goal_id}/replan")
def explicit_replan(goal_id: int, session: Session = Depends(get_session)) -> dict:
    """User-requested replan: always invokes the Agent (bypasses min-evidence guard)."""
    if not session.get(models.Goal, goal_id):
        raise HTTPException(404, "goal not found")
    fired, decision_id = _evaluate_and_maybe_run(session, goal_id, explicit=True)
    return {"ok": True, "trigger_fired": fired, "decision_id": decision_id}


@router.post("/goals/{goal_id}/simulate", response_model=SimulateOut)
def simulate(goal_id: int, body: SimulateRequest,
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

    fired, decision_id = _evaluate_and_maybe_run(session, goal_id)
    return SimulateOut(scenario=body.scenario, evidence_created=created,
                       trigger_fired=fired, decision_id=decision_id)
