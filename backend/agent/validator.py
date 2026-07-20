"""
TraceLearn — deterministic plan validator.

Every plan the Agent proposes is checked here BEFORE it is persisted. The LLM
cannot bypass this. This is the guardrail half of the deterministic/LLM split.

Real (not a stub) and pure: takes a proposed plan + context, returns pass/fail
with structured errors so the orchestrator can ask the LLM to revise, or fall
back to no_change after bounded retries.

The 5 rejection rules (see 02_AGENT_BACKEND_CONTEXT.md):
  1. weekly minutes exceed weekly_hours (with tolerance)
  2. a task scheduled after the deadline
  3. a task scheduled in the past
  4. a task references a non-existent / unconfirmed concept_id
  5. zero tasks, OR drops all coverage of a still-weak concept
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# minutes tolerance when comparing planned load to available time
WEEKLY_TOLERANCE = 1.15  # allow 15% over before rejecting


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def validate_plan(
    *,
    plan: dict,
    weekly_hours: float,
    deadline: str,                       # ISO date
    today: str,                          # ISO date
    valid_concept_ids: set[int],         # confirmed concepts only
    weak_concept_ids: set[int] | None = None,
) -> ValidationResult:
    """Return ValidationResult(ok, errors). Empty errors == pass."""
    errors: list[str] = []
    tasks = plan.get("tasks", []) or []
    weak_concept_ids = weak_concept_ids or set()

    # Rule 5a: zero tasks
    if not tasks:
        errors.append("plan has zero tasks")
        return ValidationResult(False, errors)

    deadline_d = _parse(deadline)
    today_d = _parse(today)

    # Rule 1: weekly load vs available time
    total_minutes = sum(int(t.get("est_minutes") or 0) for t in tasks)
    available_minutes = weekly_hours * 60 * WEEKLY_TOLERANCE
    # NOTE: simple total-vs-week check for the seed; per-week bucketing is a later refinement.
    if available_minutes > 0 and total_minutes > available_minutes * _num_weeks(today_d, deadline_d):
        errors.append(
            f"planned minutes {total_minutes} exceed available "
            f"{int(available_minutes * _num_weeks(today_d, deadline_d))}"
        )

    covered_concepts: set[int] = set()
    for t in tasks:
        cid = t.get("concept_id")
        day = t.get("day")

        # Rule 4: valid concept reference
        if cid is None or cid not in valid_concept_ids:
            errors.append(f"task references invalid/unconfirmed concept_id={cid!r}")
        else:
            covered_concepts.add(cid)

        # Rules 2 & 3: date bounds
        if day:
            d = _parse(day)
            if d and deadline_d and d > deadline_d:
                errors.append(f"task scheduled after deadline: {day}")
            if d and today_d and d < today_d:
                errors.append(f"task scheduled in the past: {day}")

    # Rule 5b: dropped all coverage of a still-weak concept
    dropped_weak = weak_concept_ids - covered_concepts
    if dropped_weak:
        errors.append(f"plan drops all coverage of still-weak concepts: {sorted(dropped_weak)}")

    return ValidationResult(len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _parse(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        return date.fromisoformat(iso[:10])
    except ValueError:
        return None


def _num_weeks(start: date | None, end: date | None) -> float:
    if not start or not end or end <= start:
        return 1.0
    return max(1.0, (end - start).days / 7.0)
