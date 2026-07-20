"""
TraceLearn — Agent orchestrator (the spine).

DETERMINISTIC ORCHESTRATION with an LLM DECISION POINT (feasibility audit decision):
code calls the tools in a fixed order; the LLM only decides change/no_change,
writes the reasoning, and proposes the new plan. This removes the flaky part
(free-form tool looping) while remaining genuinely tool-using and agentic.

Workflow (frozen):
    trigger
      -> read tools (get_learner_state, get_progress_summary, get_evidence_since_last_plan)
      -> LLM decision point (llm_client.decide_replan)
      -> validator (bounded retries; else fall back to no_change)
      -> create_plan_version            [write tool]
      -> record_agent_decision          [write tool, ALWAYS]

Every tool call is appended to `tool_trace` — the defence artifact.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlmodel import Session, select

import models
from agent import llm_client, tools
from agent.validator import validate_plan
from config import LLM_MAX_RETRIES, TRIGGERS


def run_agent(session: Session, goal_id: int, trigger_reason: str) -> dict[str, Any]:
    """
    Execute one agent invocation. Returns a summary dict incl. the decision_id.
    Assumes the deterministic trigger already decided this should run.
    """
    trace: list[dict[str, Any]] = []

    # --- read tools, fixed order -------------------------------------------
    learner_state = _traced(trace, "get_learner_state",
                            {"goal_id": goal_id},
                            tools.get_learner_state(session, goal_id))
    progress = _traced(trace, "get_progress_summary",
                       {"goal_id": goal_id},
                       tools.get_progress_summary(session, goal_id))
    evidence = _traced(trace, "get_evidence_since_last_plan",
                      {"goal_id": goal_id},
                      tools.get_evidence_since_last_plan(session, goal_id))
    current_plan = _traced(trace, "get_current_plan",
                          {"goal_id": goal_id},
                          tools.get_current_plan(session, goal_id))

    lang = learner_state.get("explanation_language", "en")
    evidence_snapshot = {"progress": progress, "evidence_count": len(evidence)}

    # --- LLM decision point -------------------------------------------------
    decision = llm_client.decide_replan(
        learner_state=learner_state,
        progress=progress,
        evidence=evidence,
        current_plan=current_plan,
        explanation_language=lang,
    )
    trace.append({
        "tool": "llm.decide_replan",
        "args": {"explanation_language": lang, "evidence_count": len(evidence)},
        "result_summary": f"decision={decision.get('decision')}",
    })

    reasoning = decision.get("reasoning_text", "")

    # --- no change path -----------------------------------------------------
    if decision.get("decision") != "new_version" or not decision.get("plan"):
        rec = tools.record_agent_decision(
            session, goal_id, trigger_reason, evidence_snapshot,
            reasoning or "No change needed based on current evidence.",
            trace, "no_change", None,
        )
        return {"decision": "no_change", "decision_id": rec["decision_id"]}

    # --- resolve canonical_term -> concept_id, then validate (bounded) ------
    plan = _resolve_concepts(session, goal_id, decision["plan"])
    valid_ids = _confirmed_concept_ids(session, goal_id)
    weak_ids = _weak_concept_ids(learner_state)
    today = date.today().isoformat()
    deadline = learner_state.get("deadline", today)
    weekly_hours = learner_state.get("weekly_hours", 0.0)

    result_version_id: int | None = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        vres = validate_plan(
            plan=plan,
            weekly_hours=weekly_hours,
            deadline=deadline,
            today=today,
            valid_concept_ids=valid_ids,
            weak_concept_ids=weak_ids,
        )
        trace.append({
            "tool": "validator.validate_plan",
            "args": {"attempt": attempt},
            "result_summary": "ok" if vres.ok else f"rejected: {vres.errors}",
        })
        if vres.ok:
            created = tools.create_plan_version(session, goal_id, plan, created_by="agent")
            trace.append({
                "tool": "create_plan_version",
                "args": {"task_count": len(plan.get("tasks", []))},
                "result_summary": f"version_no={created['version_no']}",
            })
            result_version_id = created["plan_version_id"]
            break
        # In MOCK mode we don't re-ask the model; a real impl would revise here.
        if attempt >= LLM_MAX_RETRIES:
            # Fall back to no_change, recording WHY (validation failed).
            rec = tools.record_agent_decision(
                session, goal_id, trigger_reason, evidence_snapshot,
                reasoning + f"  [Proposed plan rejected by validator: {vres.errors}]",
                trace, "no_change", None,
            )
            return {"decision": "no_change", "decision_id": rec["decision_id"],
                    "note": "validation_failed"}

    # --- record decision (ALWAYS) ------------------------------------------
    rec = tools.record_agent_decision(
        session, goal_id, trigger_reason, evidence_snapshot,
        reasoning, trace, "new_version", result_version_id,
    )
    return {"decision": "new_version", "decision_id": rec["decision_id"],
            "plan_version_id": result_version_id}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _traced(trace: list[dict[str, Any]], name: str, args: dict, result: Any) -> Any:
    """Append a read-tool call to the trace and return its result unchanged."""
    if isinstance(result, list):
        summary = f"{len(result)} items"
    elif isinstance(result, dict):
        summary = ", ".join(list(result.keys())[:4]) or "ok"
    else:
        summary = str(result)[:60]
    trace.append({"tool": name, "args": args, "result_summary": summary})
    return result


def _resolve_concepts(session: Session, goal_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    """Map canonical_term -> concept_id for any task missing a concept_id."""
    by_term = {
        c.canonical_term: c.id
        for c in session.exec(
            select(models.Concept).where(models.Concept.goal_id == goal_id)
        ).all()
    }
    for t in plan.get("tasks", []):
        if t.get("concept_id") is None and t.get("canonical_term"):
            t["concept_id"] = by_term.get(t["canonical_term"])
    return plan


def _confirmed_concept_ids(session: Session, goal_id: int) -> set[int]:
    return {
        c.id
        for c in session.exec(
            select(models.Concept)
            .where(models.Concept.goal_id == goal_id)
            .where(models.Concept.confirmed == True)  # noqa: E712
        ).all()
        if c.id is not None
    }


def _weak_concept_ids(learner_state: dict[str, Any]) -> set[int]:
    thr = TRIGGERS["low_mastery_threshold"]
    return {
        c["concept_id"]
        for c in learner_state.get("concepts", [])
        if c.get("mastery", 1.0) < thr and c.get("concept_id") is not None
    }
