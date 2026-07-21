"""
TraceLearn — pure full-merge helper for plan versioning.

Kept in its own module (no DB / ORM / LLM imports) so the merge that powers
full-merge replanning is unit-testable offline, independent of SQLModel.

Team decision (06 D11 / MEMBER_A_V1_TASKLIST §3): on replan, plan version N+1 =
the parent version's tasks CARRIED FORWARD (status / completed_at preserved) +
the agent's DELTA tasks appended as new `pending` work. The LLM output stays
delta-only; the merge is deterministic code here, not a model decision (D10).
"""
from __future__ import annotations

from typing import Any


def merge_tasks(
    parent_tasks: list[dict[str, Any]],
    delta_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return parent tasks CARRIED FORWARD (status / completed_at preserved exactly)
    followed by delta tasks appended as NEW pending work.

    Rules:
      - A parent task keeps its original `status` and `completed_at` — a task that
        was 'done'/'skipped' in the parent stays that way (never reset to pending).
      - A delta task is normalized to a fresh pending task (no carried completion).
      - Order is stable: all carried-forward tasks first (parent order), then the
        delta (agent order). This keeps the version-to-version diff clean —
        carried tasks match on (description, day) so nothing reads as "removed".
      - This function does NOT dedupe: the delta is remediation *added on top*, so
        the caller (orchestrator) is responsible for not proposing exact dupes.

    Validation interaction (Rule 1 weekly load): only the DELTA is validated by
    the orchestrator before persistence. Carried-forward tasks are immutable,
    already-validated history, so completed & past tasks never count against
    future weekly capacity and never trip the past-date / after-deadline rules.
    """
    merged: list[dict[str, Any]] = []
    for t in parent_tasks:
        merged.append({
            "concept_id": t.get("concept_id"),
            "day": t.get("day"),
            "description": t.get("description", ""),
            "est_minutes": t.get("est_minutes"),
            "status": t.get("status", "pending"),
            "completed_at": t.get("completed_at"),
        })
    for t in delta_tasks:
        merged.append({
            "concept_id": t.get("concept_id"),
            "day": t.get("day"),
            "description": t.get("description", ""),
            "est_minutes": t.get("est_minutes"),
            "status": "pending",
            "completed_at": None,
        })
    return merged
