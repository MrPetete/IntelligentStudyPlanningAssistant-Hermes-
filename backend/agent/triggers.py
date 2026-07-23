"""
TraceLearn — deterministic trigger layer.

The Agent is NOT invoked on every event. Deterministic code decides WHEN it
wakes up, reading thresholds from config.TRIGGERS. This is the boundary that
lets us say, in defence: "the LLM never runs unbounded."

This module is REAL (not a stub) and pure — it takes plain data and returns a
decision, so it is unit-testable with fake evidence before any LLM exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import TRIGGERS


@dataclass
class TriggerResult:
    fired: bool
    reason: str          # machine-layer label, e.g. "behind_schedule" (English)
    detail: dict[str, Any]


def evaluate_triggers(
    *,
    progress: dict[str, Any],
    concept_mastery: dict[int, float],
    recent_evidence: list[dict[str, Any]],
    explicit_request: bool = False,
) -> TriggerResult:
    """
    Decide whether to invoke the Agent.

    Args:
      progress: {"tasks_due": int, "tasks_incomplete": int, ...}
      concept_mastery: {concept_id: 0..1}
      recent_evidence: evidence rows since the last plan (list of dicts)
      explicit_request: user pressed "replan"

    Returns TriggerResult(fired, reason, detail).
    """
    # An explicit user request always fires, bypassing the min-evidence guard.
    if explicit_request:
        return TriggerResult(True, "explicit_user_request", {})

    # Guard: never replan on too little signal.
    if len(recent_evidence) < TRIGGERS["min_evidence_events"]:
        return TriggerResult(
            False,
            "insufficient_evidence",
            {"events": len(recent_evidence), "required": TRIGGERS["min_evidence_events"]},
        )

    # 1) Behind schedule? Prefer the schedule-aware OVERDUE signal (tasks that
    # should be done BY TODAY but aren't) when the caller supplies it; fall back
    # to the legacy total-incomplete ratio for pure/older callers that don't.
    #
    # This refinement is what makes ahead_schedule (below) reachable at all: with
    # the old total-based ratio, any not-yet-due future task counts as "behind",
    # so a learner who is genuinely ahead (pending work is all in the future)
    # would perpetually trip behind_schedule. Basing "behind" on overdue-only
    # work also stops a brand-new, future-loaded plan from reading as behind on
    # day one — a reduction in firing, consistent with the R2-02 cooldown intent.
    if "tasks_due_by_today" in progress:
        due_ref = progress.get("tasks_due_by_today", 0) or 0
        incomplete_ref = progress.get("tasks_incomplete_due", 0) or 0
    else:
        due_ref = progress.get("tasks_due", 0) or 0
        incomplete_ref = progress.get("tasks_incomplete", 0) or 0
    if due_ref > 0:
        behind_pct = incomplete_ref / due_ref
        if behind_pct > TRIGGERS["behind_schedule_pct"]:
            return TriggerResult(
                True,
                "behind_schedule",
                {"behind_pct": round(behind_pct, 3), "threshold": TRIGGERS["behind_schedule_pct"]},
            )

    # 2) Low mastery on any concept?
    weak = {cid: m for cid, m in concept_mastery.items() if m < TRIGGERS["low_mastery_threshold"]}
    if weak:
        return TriggerResult(
            True,
            "low_mastery",
            {"weak_concepts": weak, "threshold": TRIGGERS["low_mastery_threshold"]},
        )

    # 3) A failing quiz result in recent evidence?
    for ev in recent_evidence:
        if ev.get("type") == "quiz_result":
            score = (ev.get("payload") or {}).get("score")
            if score is not None and score < TRIGGERS["quiz_fail_threshold"]:
                return TriggerResult(
                    True,
                    "quiz_fail",
                    {"score": score, "threshold": TRIGGERS["quiz_fail_threshold"],
                     "concept_id": ev.get("concept_id")},
                )

    # 4) Ahead of schedule? (B-f3 — the trigger half of parked F-1)
    # Fires when the learner has pulled a meaningful share of NOT-YET-DUE tasks
    # forward AND is not behind on anything already due — i.e. finishing early
    # with slack before the deadline, so the agent can consider pulling work
    # forward proportionately. The schedule-aware keys are additive: a progress
    # dict without them (older callers, or pure unit inputs) simply can't trip
    # this, so no existing behaviour changes. The min-evidence guard above and
    # the replan cooldown (in agent/replan.py) bound how often it can fire.
    tasks_future = progress.get("tasks_future", 0) or 0
    tasks_done_ahead = progress.get("tasks_done_ahead", 0) or 0
    tasks_incomplete_due = progress.get("tasks_incomplete_due", 0) or 0
    if tasks_future > 0 and tasks_incomplete_due == 0 and tasks_done_ahead > 0:
        ahead_pct = tasks_done_ahead / tasks_future
        if ahead_pct > TRIGGERS["ahead_schedule_pct"]:
            return TriggerResult(
                True,
                "ahead_schedule",
                {"ahead_pct": round(ahead_pct, 3),
                 "threshold": TRIGGERS["ahead_schedule_pct"],
                 "tasks_done_ahead": tasks_done_ahead, "tasks_future": tasks_future},
            )

    return TriggerResult(False, "no_trigger", {})
