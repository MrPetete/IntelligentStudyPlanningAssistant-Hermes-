"""
TraceLearn — deterministic plan validator.

Every plan the Agent proposes is checked here BEFORE it is persisted. The LLM
cannot bypass this. This is the guardrail half of the deterministic/LLM split.

Real (not a stub) and pure: takes a proposed plan + context, returns pass/fail
with structured errors so the orchestrator can ask the LLM to revise, or fall
back to no_change after bounded retries.

The 5 rejection rules (see 02_AGENT_BACKEND_CONTEXT.md):
  1. planned minutes exceed the day-accurate available-time budget (with tolerance)
  2. a task scheduled after the deadline
  3. a task scheduled in the past
  4. a task references a non-existent / unconfirmed concept_id
  5. zero tasks, OR drops all coverage of a still-weak concept

Budget model (V1.1): the learner commits ``hours_per_day``. The available
study budget is day-accurate, NOT week-rounded: the current (partial) day
contributes only the hours actually left until midnight, and every full day
after today through the deadline contributes a full ``hours_per_day``. This
removes the old 1-week floor that let a 3-day deadline claim a whole week of
minutes (root cause of D-01). ``available_minutes_for`` is the single source of
truth for this budget — the plan router imports it so prompt, validator, and
feasibility check all agree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

# minutes tolerance when comparing planned load to available time
WEEKLY_TOLERANCE = 1.15  # allow 15% over the raw budget before rejecting


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def validate_plan(
    *,
    plan: dict,
    hours_per_day: float,
    deadline: str,                       # ISO date
    today: str,                          # ISO date
    valid_concept_ids: set[int],         # confirmed concepts only
    weak_concept_ids: set[int] | None = None,
    now: datetime | None = None,         # wall-clock for partial-first-day budget
) -> ValidationResult:
    """Return ValidationResult(ok, errors). Empty errors == pass.

    ``now`` fixes the partial first day for Rule 1's budget. When omitted it
    defaults to midnight at the start of ``today`` (a full first day) so the
    check stays deterministic in tests; the router passes the real wall-clock
    so a deadline later *today* honestly reflects the hours left.
    """
    errors: list[str] = []
    tasks = plan.get("tasks", []) or []
    weak_concept_ids = weak_concept_ids or set()

    # Rule 5a: zero tasks
    if not tasks:
        errors.append("plan has zero tasks")
        return ValidationResult(False, errors)

    deadline_d = _parse(deadline)
    today_d = _parse(today)
    if now is None and today_d is not None:
        now = datetime.combine(today_d, time.min)

    # Rule 1: planned load vs the day-accurate available-time budget.
    total_minutes = sum(int(t.get("est_minutes") or 0) for t in tasks)
    raw_budget = available_minutes_for(hours_per_day, deadline_d, now)
    budget = raw_budget * WEEKLY_TOLERANCE
    if budget > 0 and total_minutes > budget:
        errors.append(
            f"planned minutes {total_minutes} exceed available {int(budget)}"
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


def available_minutes_for(
    hours_per_day: float,
    deadline: date | None,
    now: datetime | None,
) -> float:
    """Day-accurate study budget in RAW minutes (tolerance applied by callers).

    The current day contributes only the hours actually left until midnight
    (capped at ``hours_per_day`` — you won't study more today than you commit
    to daily), and every full day after today up to and including the deadline
    contributes a full ``hours_per_day``. A deadline earlier today yields just
    the hours left today; a past deadline yields 0.

    This is the single source of truth for the plan budget: the router uses it
    for the model prompt and the feasibility check, and Rule 1 uses it here, so
    all three always agree.
    """
    if not hours_per_day or hours_per_day <= 0 or deadline is None or now is None:
        return 0.0

    today_d = now.date()
    if deadline < today_d:
        return 0.0

    # Hours left in the current (partial) day, capped by the daily commitment.
    midnight = datetime.combine(today_d + timedelta(days=1), time.min)
    hours_left_today = max(0.0, (midnight - now).total_seconds() / 3600.0)
    first_day_hours = min(hours_per_day, hours_left_today)

    # Full days strictly after today, through the deadline day inclusive.
    full_days = (deadline - today_d).days  # 0 when deadline is today
    total_hours = first_day_hours + hours_per_day * full_days
    return total_hours * 60.0
