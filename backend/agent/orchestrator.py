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
from agent import llm_client, planmerge, tools
from agent.llm_client import LLMUnavailableError
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
    # A3: if the live model is unavailable (transport failure or unparseable
    # after bounded retries), we must NEVER crash a replan. Fall back to a
    # recorded no_change so the plan is never corrupted by a bad/absent
    # response, and the decision row still documents that we considered it.
    try:
        decision = llm_client.decide_replan(
            learner_state=learner_state,
            progress=progress,
            evidence=evidence,
            current_plan=current_plan,
            explanation_language=lang,
        )
    except LLMUnavailableError as exc:
        trace.append({
            "tool": "llm.decide_replan",
            "args": {"explanation_language": lang, "evidence_count": len(evidence)},
            "result_summary": f"unavailable: {exc}",
        })
        rec = tools.record_agent_decision(
            session, goal_id, trigger_reason, evidence_snapshot,
            _model_unavailable_reasoning(lang),
            trace, "no_change", None,
        )
        return {"decision": "no_change", "decision_id": rec["decision_id"],
                "note": "llm_unavailable"}
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

    # --- resolve canonical_term -> concept_id ------------------------------
    plan = _resolve_concepts(session, goal_id, decision["plan"])

    # Dedup the delta against the CURRENT plan (planmerge is a pure appender and
    # deliberately does not dedupe — the orchestrator owns that policy). Without
    # this, a repeated low_mastery trigger re-proposes the identical remediation
    # every event, stacking duplicate tasks across V3, V4, ... Here we drop delta
    # tasks that already exist, and if nothing new remains we honestly record a
    # no_change decision ("considered, current plan already covers it" — D12).
    plan = {**plan, "tasks": planmerge.dedupe_delta(
        plan.get("tasks", []), current_plan.get("tasks", []))}
    if not plan.get("tasks"):
        trace.append({
            "tool": "orchestrator.dedup_delta",
            "args": {"proposed": len(decision["plan"].get("tasks", []))},
            "result_summary": "0 new tasks after dedup; current plan already covers this",
        })
        rec = tools.record_agent_decision(
            session, goal_id, trigger_reason, evidence_snapshot,
            reasoning or "No change: the current plan already covers this remediation.",
            trace, "no_change", None,
        )
        return {"decision": "no_change", "decision_id": rec["decision_id"],
                "note": "delta_already_present"}

    # --- validate (bounded) ------------------------------------------------
    valid_ids = _confirmed_concept_ids(session, goal_id)
    weak_ids = _weak_concept_ids(learner_state)
    # Full-merge model: create_plan_version carries EVERY parent task forward and
    # appends this delta (planmerge.merge_tasks). We validate only the delta for
    # the per-task rules (schedule/budget) because carried-forward tasks are
    # immutable, already-validated history. But Rule 5b (weak-concept coverage)
    # is a GLOBAL property of the persisted plan: a weak concept already covered
    # by a carried-forward parent task is NOT dropped, even though it's absent
    # from the delta. So only require the delta to cover weak concepts the parent
    # plan does not already cover — otherwise a valid remediation-only delta is
    # falsely rejected for "dropping" concepts it never touched. (Parent tasks are
    # never dropped in full-merge, so parent-covered weak concepts are always safe.)
    parent_covered = {
        t.get("concept_id") for t in current_plan.get("tasks", [])
        if t.get("concept_id") is not None
    }
    weak_ids = weak_ids - parent_covered
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
            # `plan` is the delta the LLM proposed; create_plan_version carries the
            # parent's tasks forward and appends this delta (full merge). Label the
            # trace as the ADDED count so the artifact isn't misread as the total.
            trace.append({
                "tool": "create_plan_version",
                "args": {"added_task_count": len(plan.get("tasks", []))},
                "result_summary": f"version_no={created['version_no']} (delta merged onto parent)",
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
def _model_unavailable_reasoning(lang: str) -> str:
    """Localized reasoning_text for a no_change forced by an unavailable model
    (A3). Honest about why nothing changed, so the decision row still reads well."""
    if lang == "zh":
        return (
            "规划助手暂时不可用，本次未能生成新的计划建议。"
            "为避免损坏当前计划，本次保持不变；稍后可再次尝试重新规划。"
        )
    return (
        "The planning assistant was temporarily unavailable, so no new plan was "
        "generated this time. To avoid corrupting the current plan it was left "
        "unchanged; you can trigger a replan again later."
    )


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
