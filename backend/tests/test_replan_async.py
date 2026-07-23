"""
TraceLearn — Member A V1.1-rc2 regression tests (R2-02 / A-RC2-1, A-RC2-2, A-RC2-4).

Covers the async replan boundary and the pieces that feed it:
  - A-RC2-1: a fired trigger is SCHEDULED on the background task, not run inline
    on the request thread (the checkbox no longer blocks 15-57s on opus).
  - A-RC2-2: cooldown — a recent decision (or an in-flight run) suppresses a
    non-explicit replan; an explicit user request bypasses the cooldown.
  - A-RC2-4: checkpoint submit writes per-concept quiz_result evidence and routes
    the re-test signal through the same trigger gate.
  - uncomplete: flips done->pending and invalidates the task_done evidence.

Plain-script style (no pytest) — run with `python tests/test_replan_async.py`.
DB-tier: needs sqlmodel; auto-skips cleanly if unavailable (run for real in the
python:3.12-slim Docker sandbox).
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _db_available() -> bool:
    try:
        import sqlmodel  # noqa: F401
        return True
    except Exception:
        return False


def _fresh_db(tmp_name: str):
    import importlib
    import config as _config
    _config.DATABASE_URL = f"sqlite:///./_test_{tmp_name}.db"
    import db as _db
    importlib.reload(_db)
    # agent.replan captured session_scope from the PRE-reload db module; reload it
    # too so its session_scope + engine point at this test DB.
    from agent import replan as _replan
    importlib.reload(_replan)
    from sqlmodel import SQLModel
    SQLModel.metadata.drop_all(_db.engine)
    SQLModel.metadata.create_all(_db.engine)
    return _db


class _CapturingBackground:
    """Capture scheduled tasks instead of running them, so a test can assert the
    call returned BEFORE the heavy agent run and then run it deliberately."""
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))

    def run_all(self):
        for fn, args, kwargs in self.tasks:
            fn(*args, **kwargs)


def _seed_goal_with_pending_plan(db, n_skips: int = 3):
    """Goal + confirmed concept + plan v1 (all pending) + `n_skips` task_skipped
    evidence rows. That's enough to fire the trigger gate: >= min_evidence_events
    and behind_schedule (all tasks incomplete) / low_mastery (skips drop it)."""
    from sqlmodel import Session
    import models
    from agent import tools
    with Session(db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="pass databases", deadline="2026-08-10",
                         hours_per_day=6.0, explanation_language="en")
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)
        tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-24", "description": "study", "est_minutes": 45},
            {"concept_id": c.id, "day": "2026-07-25", "description": "practice", "est_minutes": 45},
        ]}, created_by="user")
        for _ in range(n_skips):
            s.add(models.Evidence(goal_id=g.id, concept_id=c.id, type="task_skipped",
                                  payload_json="{}"))
        s.commit()
        return g.id


@contextmanager
def _patched_agent(record: list):
    """Patch orchestrator.run_agent so no LLM is called; record each invocation."""
    from agent import orchestrator
    orig = orchestrator.run_agent

    def _fake(session, goal_id, reason):
        record.append((goal_id, reason))
        return {"decision": "no_change", "decision_id": 999}

    orchestrator.run_agent = _fake
    try:
        yield
    finally:
        orchestrator.run_agent = orig


def _reset_inflight():
    from agent import replan
    with replan._inflight_lock:
        replan._inflight_since.clear()


def test_fired_trigger_is_scheduled_not_run_inline():
    """A-RC2-1: evaluate_and_schedule returns immediately (queued) and the agent
    is handed to the background task — NOT called on the request thread."""
    if not _db_available():
        print("SKIP  test_fired_trigger_is_scheduled_not_run_inline (no sqlmodel)")
        return
    from sqlmodel import Session
    db = _fresh_db("rc2_sched")
    from agent import replan
    _reset_inflight()
    goal_id = _seed_goal_with_pending_plan(db)

    calls: list = []
    bg = _CapturingBackground()
    with _patched_agent(calls), Session(db.engine) as s:
        queued, decision_id = replan.evaluate_and_schedule(s, goal_id, bg)
    # Returned "queued", the agent has NOT run yet, exactly one task scheduled.
    assert queued is True, "trigger should fire on all-pending plan + 3 skips"
    assert decision_id is None, "async path returns None decision_id (poll instead)"
    assert calls == [], "run_agent must NOT be called inline (would block the request)"
    assert len(bg.tasks) == 1, f"exactly one background task, got {len(bg.tasks)}"


def test_cooldown_suppresses_nonexplicit_but_explicit_bypasses():
    """A-RC2-2: a recent agent_decision puts the goal in cooldown -> a
    non-explicit trigger is suppressed; an explicit user request still fires."""
    if not _db_available():
        print("SKIP  test_cooldown_suppresses_nonexplicit_but_explicit_bypasses (no sqlmodel)")
        return
    from sqlmodel import Session
    import models
    db = _fresh_db("rc2_cooldown")
    from agent import replan
    _reset_inflight()
    goal_id = _seed_goal_with_pending_plan(db)

    # A decision landed 10s ago -> well within the 300s cooldown window.
    recent = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with Session(db.engine) as s:
        s.add(models.AgentDecision(goal_id=goal_id, trigger="behind_schedule",
                                   decision="new_version", created_at=recent))
        s.commit()

    calls: list = []
    with _patched_agent(calls), Session(db.engine) as s:
        bg = _CapturingBackground()
        queued, _ = replan.evaluate_and_schedule(s, goal_id, bg)
        assert queued is False, "non-explicit replan must be suppressed by cooldown"
        assert len(bg.tasks) == 0, "nothing scheduled during cooldown"

        bg2 = _CapturingBackground()
        queued_x, _ = replan.evaluate_and_schedule(s, goal_id, bg2, explicit=True)
        assert queued_x is True, "explicit user request must bypass the cooldown"
        assert len(bg2.tasks) == 1, "explicit replan schedules the agent run"


def test_at_most_one_run_while_inflight():
    """A-RC2-2: two rapid trigger-firing events (before the first run writes its
    decision row) collapse to a single scheduled run via the in-flight guard."""
    if not _db_available():
        print("SKIP  test_at_most_one_run_while_inflight (no sqlmodel)")
        return
    from sqlmodel import Session
    db = _fresh_db("rc2_inflight")
    from agent import replan
    _reset_inflight()
    goal_id = _seed_goal_with_pending_plan(db)

    calls: list = []
    with _patched_agent(calls), Session(db.engine) as s:
        bg = _CapturingBackground()
        q1, _ = replan.evaluate_and_schedule(s, goal_id, bg)   # schedules -> in-flight set
        q2, _ = replan.evaluate_and_schedule(s, goal_id, bg)   # in-flight -> suppressed
    assert q1 is True and q2 is False, f"expected (True, False), got ({q1}, {q2})"
    assert len(bg.tasks) == 1, f"burst must collapse to one run, got {len(bg.tasks)}"


def test_checkpoint_submit_writes_quiz_evidence_and_gates_replan():
    """A-RC2-4: checkpoint submit scores answers, writes per-concept quiz_result
    evidence (source 'checkpoint'), and routes the signal through the trigger
    gate (background-scheduled if it fires)."""
    if not _db_available():
        print("SKIP  test_checkpoint_submit_writes_quiz_evidence_and_gates_replan (no sqlmodel)")
        return
    from sqlmodel import Session, select
    import models
    from routers import diagnostic as diag_router
    from schemas import CheckpointGenerate, CheckpointSubmit, DiagnosticAnswer
    db = _fresh_db("rc2_checkpoint")
    from agent import replan
    _reset_inflight()
    goal_id = _seed_goal_with_pending_plan(db)

    calls: list = []
    with _patched_agent(calls), Session(db.engine) as s:
        cid = s.exec(select(models.Concept).where(
            models.Concept.goal_id == goal_id)).first().id
        out = diag_router.generate_checkpoint(
            goal_id, CheckpointGenerate(concept_ids=[cid]), session=s)
        assert out.questions, "checkpoint must produce questions"
        assert cid in out.concept_ids

        # Answer everything WRONG (choose an option we know isn't the key: the
        # mock answer is always "A"/first option, so submit "B").
        answers = [DiagnosticAnswer(question_id=q.id, choice="B") for q in out.questions]
        bg = _CapturingBackground()
        res = diag_router.submit_checkpoint(
            goal_id, CheckpointSubmit(checkpoint_id=out.checkpoint_id, answers=answers),
            bg, session=s)
        # per-concept score recorded, low (all wrong) -> quiz_result evidence written
        assert cid in res.per_concept_score
        assert res.per_concept_score[cid] == 0.0, res.per_concept_score
        evid = s.exec(select(models.Evidence).where(
            models.Evidence.goal_id == goal_id,
            models.Evidence.type == "quiz_result")).all()
        assert evid, "checkpoint submit must write quiz_result evidence"
        import json as _json
        assert any(_json.loads(e.payload_json).get("source") == "checkpoint" for e in evid)


def test_uncomplete_reverts_and_invalidates_evidence():
    """uncheck (B-RC2-1 backend): done->pending, its task_done evidence removed,
    and no replan is scheduled by undoing a misclick."""
    if not _db_available():
        print("SKIP  test_uncomplete_reverts_and_invalidates_evidence (no sqlmodel)")
        return
    from sqlmodel import Session, select
    import models
    from routers import evidence as evidence_router
    db = _fresh_db("rc2_uncomplete")
    _reset_inflight()

    from agent import tools
    with Session(db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", hours_per_day=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)
        tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-24", "description": "study", "est_minutes": 45},
        ]}, created_by="user")
        task = s.exec(select(models.Task)).first()
        goal_id, task_id = g.id, task.id

    calls: list = []
    with _patched_agent(calls), Session(db.engine) as s:
        bg = _CapturingBackground()
        evidence_router.complete_task(task_id, bg, session=s)
    with Session(db.engine) as s:
        assert s.get(models.Task, task_id).status == "done"
        done_ev = s.exec(select(models.Evidence).where(
            models.Evidence.type == "task_done")).all()
        assert len(done_ev) == 1

    with Session(db.engine) as s:
        res = evidence_router.uncomplete_task(task_id, session=s)
        assert res.status == "pending"
        assert res.evidence_removed == 1, f"expected 1 removed, got {res.evidence_removed}"
    with Session(db.engine) as s:
        assert s.get(models.Task, task_id).status == "pending"
        assert s.get(models.Task, task_id).completed_at is None
        remaining = s.exec(select(models.Evidence).where(
            models.Evidence.type == "task_done")).all()
        assert remaining == [], "task_done evidence must be invalidated on uncomplete"


ALL_TESTS = [
    test_fired_trigger_is_scheduled_not_run_inline,
    test_cooldown_suppresses_nonexplicit_but_explicit_bypasses,
    test_at_most_one_run_while_inflight,
    test_checkpoint_submit_writes_quiz_evidence_and_gates_replan,
    test_uncomplete_reverts_and_invalidates_evidence,
]


if __name__ == "__main__":
    passed = failed = 0
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
