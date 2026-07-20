"""
TraceLearn — standalone simulate (CLI equivalent of POST /goals/{id}/simulate).

Injects a canned failure pattern and runs the trigger -> agent loop directly,
so the full evidence -> decision -> version -> explanation chain can be produced
without the HTTP layer (useful for the recorded fallback demo).

Run:
    cd app/backend
    python -m seed.simulate <goal_id> [normalization_failure|missed_tasks]
"""
from __future__ import annotations

import json
import sys

from sqlmodel import Session, select

import models
from agent import orchestrator, tools
from agent.triggers import evaluate_triggers
from db import engine


def simulate(goal_id: int, scenario: str = "normalization_failure") -> None:
    with Session(engine) as session:
        norm = session.exec(
            select(models.Concept).where(models.Concept.goal_id == goal_id)
            .where(models.Concept.canonical_term == "Normalization")
        ).first()

        if scenario == "normalization_failure":
            session.add(models.Evidence(
                goal_id=goal_id, concept_id=(norm.id if norm else None), type="quiz_result",
                payload_json=json.dumps({"score": 0.3, "source": "sim"}),
            ))
            for _ in range(3):
                session.add(models.Evidence(
                    goal_id=goal_id, concept_id=(norm.id if norm else None), type="task_skipped",
                    payload_json=json.dumps({"source": "sim"}),
                ))
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
                    payload_json=json.dumps({"task_id": t.id, "source": "sim"}),
                ))
        session.commit()

        # trigger -> agent
        progress = tools.get_progress_summary(session, goal_id)
        learner = tools.get_learner_state(session, goal_id)
        mastery = {c["concept_id"]: c["mastery"] for c in learner.get("concepts", [])}
        recent = tools.get_evidence_since_last_plan(session, goal_id)
        tr = evaluate_triggers(progress=progress, concept_mastery=mastery, recent_evidence=recent)

        print(f"Trigger fired={tr.fired} reason={tr.reason} detail={tr.detail}")
        if tr.fired:
            result = orchestrator.run_agent(session, goal_id, tr.reason)
            print(f"Agent result: {result}")
        else:
            print("No replan (trigger did not fire).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m seed.simulate <goal_id> [scenario]")
        raise SystemExit(1)
    gid = int(sys.argv[1])
    scen = sys.argv[2] if len(sys.argv) > 2 else "normalization_failure"
    simulate(gid, scen)
