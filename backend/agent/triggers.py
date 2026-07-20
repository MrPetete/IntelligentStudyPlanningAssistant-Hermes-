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

    # 1) Behind schedule?
    tasks_due = progress.get("tasks_due", 0) or 0
    tasks_incomplete = progress.get("tasks_incomplete", 0) or 0
    if tasks_due > 0:
        behind_pct = tasks_incomplete / tasks_due
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

    return TriggerResult(False, "no_trigger", {})
