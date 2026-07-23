"""
TraceLearn — starter unit tests for the deterministic trigger layer and the
plan validator. Both modules are pure (no DB, no LLM), so these run standalone.

Run:
    cd app/backend
    python tests/test_triggers_validator.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run as a plain script (not `python -m`): put backend/ on sys.path so
# `agent.triggers` / `agent.validator` resolve the same way the app does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.triggers import evaluate_triggers
from agent.validator import validate_plan


# ---------------------------------------------------------------------------
# triggers.evaluate_triggers
# ---------------------------------------------------------------------------
def test_explicit_request_always_fires():
    result = evaluate_triggers(
        progress={"tasks_due": 0, "tasks_incomplete": 0},
        concept_mastery={},
        recent_evidence=[],
        explicit_request=True,
    )
    assert result.fired is True
    assert result.reason == "explicit_user_request"


def test_insufficient_evidence_blocks_all_other_triggers():
    result = evaluate_triggers(
        progress={"tasks_due": 10, "tasks_incomplete": 10},  # would trip behind_schedule
        concept_mastery={1: 0.1},                             # would trip low_mastery
        recent_evidence=[{"type": "task_done"}],               # below min_evidence_events (3)
    )
    assert result.fired is False
    assert result.reason == "insufficient_evidence"


def test_behind_schedule_fires_above_threshold():
    result = evaluate_triggers(
        progress={"tasks_due": 4, "tasks_incomplete": 2},  # 50% > 25% threshold
        concept_mastery={},
        recent_evidence=[{"type": "task_done"}] * 3,
    )
    assert result.fired is True
    assert result.reason == "behind_schedule"


def test_low_mastery_fires_below_threshold():
    result = evaluate_triggers(
        progress={"tasks_due": 4, "tasks_incomplete": 0},
        concept_mastery={7: 0.2},  # below 0.40 threshold
        recent_evidence=[{"type": "task_done"}] * 3,
    )
    assert result.fired is True
    assert result.reason == "low_mastery"
    assert 7 in result.detail["weak_concepts"]


def test_quiz_fail_fires_below_threshold():
    result = evaluate_triggers(
        progress={"tasks_due": 4, "tasks_incomplete": 0},
        concept_mastery={},
        recent_evidence=[
            {"type": "task_done"},
            {"type": "task_done"},
            {"type": "quiz_result", "concept_id": 3, "payload": {"score": 0.3}},
        ],
    )
    assert result.fired is True
    assert result.reason == "quiz_fail"


def test_no_trigger_when_all_signals_healthy():
    result = evaluate_triggers(
        progress={"tasks_due": 4, "tasks_incomplete": 0},
        concept_mastery={1: 0.9},
        recent_evidence=[
            {"type": "task_done"},
            {"type": "task_done"},
            {"type": "quiz_result", "concept_id": 1, "payload": {"score": 0.9}},
        ],
    )
    assert result.fired is False
    assert result.reason == "no_trigger"


# ---------------------------------------------------------------------------
# ahead_schedule trigger (A-V2-4 / B-f3)
# ---------------------------------------------------------------------------
def _healthy_evidence():
    """>= min_evidence_events with nothing that would trip an earlier trigger."""
    return [{"type": "task_done"}] * 3


def test_ahead_schedule_fires_when_learner_is_ahead():
    """Done 2 of 5 future tasks early (40% > 20%), nothing overdue -> ahead."""
    result = evaluate_triggers(
        progress={"tasks_due_by_today": 3, "tasks_incomplete_due": 0,
                  "tasks_future": 5, "tasks_done_ahead": 2},
        concept_mastery={1: 0.9},
        recent_evidence=_healthy_evidence(),
    )
    assert result.fired is True
    assert result.reason == "ahead_schedule"
    assert result.detail["tasks_done_ahead"] == 2


def test_ahead_schedule_does_not_fire_on_pace():
    """No future work pulled forward -> on pace, no ahead trigger."""
    result = evaluate_triggers(
        progress={"tasks_due_by_today": 3, "tasks_incomplete_due": 0,
                  "tasks_future": 5, "tasks_done_ahead": 0},
        concept_mastery={1: 0.9},
        recent_evidence=_healthy_evidence(),
    )
    assert result.fired is False
    assert result.reason == "no_trigger"


def test_ahead_schedule_does_not_fire_below_threshold():
    """1 of 10 future done early = 10% <= 20% threshold -> not enough to fire."""
    result = evaluate_triggers(
        progress={"tasks_due_by_today": 5, "tasks_incomplete_due": 0,
                  "tasks_future": 10, "tasks_done_ahead": 1},
        concept_mastery={1: 0.9},
        recent_evidence=_healthy_evidence(),
    )
    assert result.fired is False


def test_ahead_schedule_suppressed_when_behind_on_due_work():
    """Ahead on future work but with OVERDUE tasks -> behind wins, never ahead."""
    result = evaluate_triggers(
        progress={"tasks_due_by_today": 6, "tasks_incomplete_due": 4,  # 0.667 > 0.25 -> behind
                  "tasks_future": 5, "tasks_done_ahead": 3},
        concept_mastery={1: 0.9},
        recent_evidence=_healthy_evidence(),
    )
    assert result.fired is True
    assert result.reason == "behind_schedule"


def test_ahead_schedule_respects_min_evidence_guard():
    """Even clearly ahead, too little evidence blocks the trigger."""
    result = evaluate_triggers(
        progress={"tasks_due_by_today": 3, "tasks_incomplete_due": 0,
                  "tasks_future": 5, "tasks_done_ahead": 4},
        concept_mastery={1: 0.9},
        recent_evidence=[{"type": "task_done"}],  # below min_evidence_events (3)
    )
    assert result.fired is False
    assert result.reason == "insufficient_evidence"


# ---------------------------------------------------------------------------
# validator.validate_plan — the 5 rejection rules
# ---------------------------------------------------------------------------
def _valid_task(concept_id=1, day="2026-08-01", minutes=60):
    return {"concept_id": concept_id, "day": day, "description": "study", "est_minutes": minutes}


def test_validator_accepts_a_reasonable_plan():
    plan = {"tasks": [_valid_task(day="2026-08-01"), _valid_task(day="2026-08-03")]}
    result = validate_plan(
        plan=plan, hours_per_day=6, deadline="2026-08-10", today="2026-07-25",
        valid_concept_ids={1}, weak_concept_ids=set(),
    )
    assert result.ok is True
    assert result.errors == []


def test_validator_rejects_zero_tasks():
    result = validate_plan(
        plan={"tasks": []}, hours_per_day=6, deadline="2026-08-10", today="2026-07-25",
        valid_concept_ids={1},
    )
    assert result.ok is False
    assert any("zero tasks" in e for e in result.errors)


def test_validator_rejects_overloaded_week():
    # 10 tasks * 600 min = 6000 min, ~7-day window at 6h/day -> over the budget
    plan = {"tasks": [_valid_task(day="2026-07-26", minutes=600) for _ in range(10)]}
    result = validate_plan(
        plan=plan, hours_per_day=6, deadline="2026-08-01", today="2026-07-25",
        valid_concept_ids={1},
    )
    assert result.ok is False
    assert any("exceed available" in e for e in result.errors)


def test_validator_rejects_task_after_deadline():
    plan = {"tasks": [_valid_task(day="2026-09-01")]}
    result = validate_plan(
        plan=plan, hours_per_day=6, deadline="2026-08-10", today="2026-07-25",
        valid_concept_ids={1},
    )
    assert result.ok is False
    assert any("after deadline" in e for e in result.errors)


def test_validator_rejects_task_in_the_past():
    plan = {"tasks": [_valid_task(day="2026-07-01")]}
    result = validate_plan(
        plan=plan, hours_per_day=6, deadline="2026-08-10", today="2026-07-25",
        valid_concept_ids={1},
    )
    assert result.ok is False
    assert any("in the past" in e for e in result.errors)


def test_validator_rejects_unconfirmed_concept():
    plan = {"tasks": [_valid_task(concept_id=99, day="2026-08-01")]}
    result = validate_plan(
        plan=plan, hours_per_day=6, deadline="2026-08-10", today="2026-07-25",
        valid_concept_ids={1},  # 99 is not in the confirmed set
    )
    assert result.ok is False
    assert any("invalid/unconfirmed concept_id" in e for e in result.errors)


def test_validator_rejects_dropped_weak_concept_coverage():
    plan = {"tasks": [_valid_task(concept_id=1, day="2026-08-01")]}
    result = validate_plan(
        plan=plan, hours_per_day=6, deadline="2026-08-10", today="2026-07-25",
        valid_concept_ids={1, 2}, weak_concept_ids={2},  # concept 2 is weak but never covered
    )
    assert result.ok is False
    assert any("drops all coverage" in e for e in result.errors)


def test_validator_near_deadline_budget_is_day_accurate():
    """A 3-day deadline yields a small day-accurate budget (no 1-week floor).

    now is pinned to midnight so the first day counts full: 3 days x 2h/day =
    6h = 360 raw min, x1.15 tolerance = 414. A plan summing 300 min fits; one
    summing 600 min overshoots Rule 1. (This is the gap that let D-01 ship —
    previously a 3-day deadline got a whole week's minutes.)"""
    from datetime import datetime
    fit = {"tasks": [_valid_task(day="2026-07-26", minutes=150),
                     _valid_task(day="2026-07-27", minutes=150)]}
    over = {"tasks": [_valid_task(day="2026-07-26", minutes=300),
                      _valid_task(day="2026-07-27", minutes=300)]}
    common = dict(hours_per_day=2, deadline="2026-07-28", today="2026-07-25",
                  valid_concept_ids={1}, now=datetime(2026, 7, 25, 0, 0))
    assert validate_plan(plan=fit, **common).ok is True
    res_over = validate_plan(plan=over, **common)
    assert res_over.ok is False
    assert any("exceed available" in e for e in res_over.errors)


def test_validator_trimmed_plan_passes():
    """A plan covering only a subset of concepts, within budget, validates OK
    (proves trimming to fit the budget doesn't trip any rule)."""
    plan = {"tasks": [_valid_task(concept_id=1, day="2026-08-01", minutes=60)]}
    result = validate_plan(
        plan=plan, hours_per_day=6, deadline="2026-08-10", today="2026-07-25",
        valid_concept_ids={1, 2, 3, 4, 5},  # 5 confirmed, only 1 covered -> trimmed
        weak_concept_ids=set(),
    )
    assert result.ok is True, result.errors


ALL_TESTS = [
    test_explicit_request_always_fires,
    test_insufficient_evidence_blocks_all_other_triggers,
    test_behind_schedule_fires_above_threshold,
    test_low_mastery_fires_below_threshold,
    test_quiz_fail_fires_below_threshold,
    test_no_trigger_when_all_signals_healthy,
    test_ahead_schedule_fires_when_learner_is_ahead,
    test_ahead_schedule_does_not_fire_on_pace,
    test_ahead_schedule_does_not_fire_below_threshold,
    test_ahead_schedule_suppressed_when_behind_on_due_work,
    test_ahead_schedule_respects_min_evidence_guard,
    test_validator_accepts_a_reasonable_plan,
    test_validator_rejects_zero_tasks,
    test_validator_rejects_overloaded_week,
    test_validator_rejects_task_after_deadline,
    test_validator_rejects_task_in_the_past,
    test_validator_rejects_unconfirmed_concept,
    test_validator_rejects_dropped_weak_concept_coverage,
    test_validator_near_deadline_budget_is_day_accurate,
    test_validator_trimmed_plan_passes,
]


if __name__ == "__main__":
    passed = 0
    failed = 0
    for test in ALL_TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)
