"""
TraceLearn — Member A tests for full-merge replanning + append-only / no_change
invariants (D11, D12). This is Member A's OWN test file — it deliberately does
NOT touch tests/test_triggers_validator.py (Member C's suite).

Two tiers:
  1. PURE tests of agent.planmerge.merge_tasks — no DB, no LLM, always run.
  2. DB-backed invariant tests — need sqlmodel; auto-skipped with a clear note
     if it isn't installed (sandbox), run for real in a full environment.

Run:
    cd backend
    python tests/test_versioning.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run as a plain script: put backend/ on sys.path so `agent.*` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.planmerge import merge_tasks


# ---------------------------------------------------------------------------
# Tier 1 — PURE merge tests (the heart of A2). Always runnable.
# ---------------------------------------------------------------------------
def _parent_seed_tasks():
    """Mirror the seed: 4 done tasks + 1 pending Normalization task (plan v1)."""
    return [
        {"concept_id": 1, "day": "2026-07-21",
         "description": "Study Normalization and do 3 practice questions.",
         "est_minutes": 45, "status": "pending", "completed_at": None},
        {"concept_id": 2, "day": "2026-07-22", "description": "Study Indexing...",
         "est_minutes": 45, "status": "done", "completed_at": "2026-07-22T10:00:00+00:00"},
        {"concept_id": 3, "day": "2026-07-23", "description": "Study Transactions...",
         "est_minutes": 45, "status": "done", "completed_at": "2026-07-23T10:00:00+00:00"},
        {"concept_id": 4, "day": "2026-07-24", "description": "Study Joins...",
         "est_minutes": 45, "status": "done", "completed_at": "2026-07-24T10:00:00+00:00"},
        {"concept_id": 5, "day": "2026-07-25", "description": "Study Query Optimization...",
         "est_minutes": 45, "status": "done", "completed_at": "2026-07-25T10:00:00+00:00"},
    ]


def _delta_remediation():
    """The delta the mock LLM proposes: 2 new Normalization remediation tasks."""
    return [
        {"concept_id": 1, "day": "2026-07-21",
         "description": "Remediation: review 1NF-3NF with worked examples.", "est_minutes": 40},
        {"concept_id": 1, "day": "2026-07-22",
         "description": "Remediation: decompose 5 relations to 3NF.", "est_minutes": 40},
    ]


def test_merge_appends_delta_after_parent():
    merged = merge_tasks(_parent_seed_tasks(), _delta_remediation())
    assert len(merged) == 7, f"expected 5 carried + 2 delta = 7, got {len(merged)}"
    # parent order preserved, delta last
    assert merged[0]["description"].startswith("Study Normalization")
    assert merged[5]["description"].startswith("Remediation: review 1NF-3NF")
    assert merged[6]["description"].startswith("Remediation: decompose")


def test_merge_carries_completion_state_forward():
    """The A2 headline guarantee: done/skipped are NOT reset to pending."""
    merged = merge_tasks(_parent_seed_tasks(), _delta_remediation())
    done = [t for t in merged if t["status"] == "done"]
    assert len(done) == 4, f"expected 4 carried-forward done tasks, got {len(done)}"
    # completed_at preserved verbatim on carried tasks
    idx_task = next(t for t in merged if t["concept_id"] == 2)
    assert idx_task["status"] == "done"
    assert idx_task["completed_at"] == "2026-07-22T10:00:00+00:00"
    # the still-weak Normalization v1 task stays pending (not lost, not completed)
    norm_v1 = merged[0]
    assert norm_v1["status"] == "pending" and norm_v1["completed_at"] is None


def test_merge_delta_tasks_are_fresh_pending():
    """Delta tasks are always new pending work, even if they carried stray fields."""
    delta = [{"concept_id": 1, "day": "2026-07-21", "description": "x",
              "status": "done", "completed_at": "should-be-dropped"}]
    merged = merge_tasks([], delta)
    assert merged[0]["status"] == "pending"
    assert merged[0]["completed_at"] is None


def test_merge_no_parent_is_delta_only():
    """Plan version 1 (seed / user generate): no parent -> version == delta."""
    delta = _delta_remediation()
    merged = merge_tasks([], delta)
    assert len(merged) == 2
    assert all(t["status"] == "pending" for t in merged)


def test_merge_diff_shows_added_only_nothing_removed():
    """
    Simulate the plan_diff key logic ((description, day)) over the merge:
    carried tasks match parent keys, so nothing reads as removed; only the
    delta reads as added. This is the "2 added, nothing removed" guarantee.
    """
    parent = _parent_seed_tasks()
    merged = merge_tasks(parent, _delta_remediation())
    a_keys = {(t["description"], t["day"]) for t in parent}
    b_keys = {(t["description"], t["day"]) for t in merged}
    added = [t for t in merged if (t["description"], t["day"]) not in a_keys]
    removed = [t for t in parent if (t["description"], t["day"]) not in b_keys]
    assert len(added) == 2, f"expected 2 added, got {len(added)}"
    assert len(removed) == 0, f"expected nothing removed, got {len(removed)}"


def test_dedupe_delta_drops_present_keeps_new():
    """A-FIX-1: dedupe_delta removes delta tasks already in the current plan."""
    from agent.planmerge import dedupe_delta
    current = [
        {"concept_id": 1, "description": "Remediation: review 1NF-3NF with worked examples."},
        {"concept_id": 1, "description": "Remediation: decompose 5 relations to 3NF."},
    ]
    # identical delta -> everything dropped (the runaway-replan case)
    assert dedupe_delta([dict(t) for t in current], current) == []
    # a genuinely new task survives
    new = [{"concept_id": 1, "description": "Remediation: brand new task."}]
    assert len(dedupe_delta(new, current)) == 1
    # same description but different concept is NOT a dupe (keyed on both)
    other = [{"concept_id": 2, "description": "Remediation: decompose 5 relations to 3NF."}]
    assert len(dedupe_delta(other, current)) == 1
    # empty current -> nothing dropped
    assert len(dedupe_delta(new, [])) == 1


PURE_TESTS = [
    test_merge_appends_delta_after_parent,
    test_merge_carries_completion_state_forward,
    test_merge_delta_tasks_are_fresh_pending,
    test_merge_no_parent_is_delta_only,
    test_merge_diff_shows_added_only_nothing_removed,
    test_dedupe_delta_drops_present_keeps_new,
]


# ---------------------------------------------------------------------------
# Tier 2 — DB-backed invariants (append-only, carry-forward, no_change fallback).
# Requires sqlmodel; skipped cleanly if unavailable.
# ---------------------------------------------------------------------------
def _db_available() -> bool:
    try:
        import sqlmodel  # noqa: F401
        return True
    except Exception:
        return False


def _fresh_db(tmp_name: str):
    """Build an isolated in-memory-ish SQLite for one test and seed plan v1."""
    import importlib
    import config as _config
    _config.DATABASE_URL = f"sqlite:///./_test_{tmp_name}.db"
    # reimport db + models against the patched URL
    import db as _db
    importlib.reload(_db)
    from sqlmodel import SQLModel
    SQLModel.metadata.drop_all(_db.engine)
    SQLModel.metadata.create_all(_db.engine)
    return _db


def test_db_replan_appends_new_version_and_preserves_parent():
    """Replan creates a new version_no + parent link and NEVER mutates v1 rows."""
    from sqlmodel import Session, select
    import models
    from agent import tools

    _db = _fresh_db("append")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", hours_per_day=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)

        # plan v1: 1 done + 1 pending
        v1 = tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-21", "description": "done task", "est_minutes": 40},
            {"concept_id": c.id, "day": "2026-07-22", "description": "pending task", "est_minutes": 40},
        ]}, created_by="user")
        v1_tasks = s.exec(select(models.Task).where(
            models.Task.plan_version_id == v1["plan_version_id"])).all()
        v1_task_ids = {t.id for t in v1_tasks}
        # mark one done directly (app-written progress)
        done_t = v1_tasks[0]; done_t.status = "done"; done_t.completed_at = "2026-07-21T12:00:00+00:00"
        s.add(done_t); s.commit()

        # replan: delta of 1 remediation task
        v2 = tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-23", "description": "remediation", "est_minutes": 40},
        ]}, created_by="agent")

        # append-only: new version_no, parent link, v1 rows untouched
        pv2 = s.get(models.PlanVersion, v2["plan_version_id"])
        assert pv2.version_no == 2
        assert pv2.parent_version_id == v1["plan_version_id"]
        v1_tasks_after = s.exec(select(models.Task).where(
            models.Task.plan_version_id == v1["plan_version_id"])).all()
        assert {t.id for t in v1_tasks_after} == v1_task_ids, "v1 task rows must be unchanged"
        # v2 is a full merge: 2 carried + 1 delta = 3, distinct rows from v1
        v2_tasks = s.exec(select(models.Task).where(
            models.Task.plan_version_id == v2["plan_version_id"])).all()
        assert len(v2_tasks) == 3
        assert v1_task_ids.isdisjoint({t.id for t in v2_tasks}), "carried tasks must be NEW rows"


def test_db_full_merge_carries_completion_state():
    """A done task in v1 is still done in v2 after the merge."""
    from sqlmodel import Session, select
    import models
    from agent import tools

    _db = _fresh_db("carry")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", hours_per_day=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)

        v1 = tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-21", "description": "finished", "est_minutes": 40},
        ]}, created_by="user")
        t = s.exec(select(models.Task).where(
            models.Task.plan_version_id == v1["plan_version_id"])).first()
        t.status = "done"; t.completed_at = "2026-07-21T09:00:00+00:00"; s.add(t); s.commit()

        v2 = tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-23", "description": "new remediation", "est_minutes": 40},
        ]}, created_by="agent")
        v2_tasks = s.exec(select(models.Task).where(
            models.Task.plan_version_id == v2["plan_version_id"])).all()
        carried = [x for x in v2_tasks if x.description == "finished"]
        assert len(carried) == 1
        assert carried[0].status == "done", "completion state must carry forward"
        assert carried[0].completed_at == "2026-07-21T09:00:00+00:00"


def test_db_validation_failure_records_no_change():
    """
    If the proposed delta fails validation on every retry, the orchestrator must
    still record a no_change decision noting the failure (D12).
    """
    from sqlmodel import Session, select
    import models
    from agent import orchestrator, tools
    from agent import llm_client

    _db = _fresh_db("nochange")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", hours_per_day=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)
        tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-21", "description": "base", "est_minutes": 40},
        ]}, created_by="user")

        # Force a delta that fails validation: task scheduled after the deadline.
        orig = llm_client.decide_replan
        llm_client.decide_replan = lambda **kw: {
            "decision": "new_version", "reasoning_text": "bad plan",
            "plan": {"tasks": [{"concept_id": c.id, "canonical_term": "Normalization",
                                "day": "2027-01-01", "description": "too late", "est_minutes": 40}]},
        }
        try:
            res = orchestrator.run_agent(s, g.id, "low_mastery")
        finally:
            llm_client.decide_replan = orig

        assert res["decision"] == "no_change"
        dec = s.get(models.AgentDecision, res["decision_id"])
        assert dec is not None and dec.decision == "no_change"
        assert "reject" in dec.reasoning_text.lower() or "valid" in dec.reasoning_text.lower()


def test_db_repeated_trigger_records_no_change_not_duplicate():
    """
    A-FIX-1: with the mock returning the same delta every time, a SECOND agent
    run must dedupe to nothing and record no_change — NOT create a V3 with
    duplicate remediation tasks.
    """
    from sqlmodel import Session, select
    import models
    from agent import orchestrator, tools

    _db = _fresh_db("dedup")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", hours_per_day=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)
        tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-21", "description": "base", "est_minutes": 40},
        ]}, created_by="user")

        # First run: mock proposes 2 remediation tasks -> new_version (V2).
        r1 = orchestrator.run_agent(s, g.id, "low_mastery")
        assert r1["decision"] == "new_version", r1
        # Second run with the identical mock delta: must dedupe -> no_change, no V3.
        r2 = orchestrator.run_agent(s, g.id, "low_mastery")
        assert r2["decision"] == "no_change", r2
        versions = s.exec(select(models.PlanVersion).where(
            models.PlanVersion.goal_id == g.id)).all()
        assert max(v.version_no for v in versions) == 2, "no V3 should be created on a duplicate delta"


def test_db_replan_weak_concept_covered_by_parent_not_falsely_rejected():
    """
    Audit finding: full-merge validation must judge the MERGED plan for weak-
    concept coverage, not the delta alone. A weak concept covered by a carried-
    forward parent task is NOT dropped just because the remediation delta only
    touches a different concept. Before the fix, the orchestrator validated the
    delta in isolation and Rule 5b falsely rejected it ("drops all coverage of
    still-weak concepts"), forcing a no_change on every live replan.
    """
    from sqlmodel import Session, select
    import models
    from agent import orchestrator, tools
    from agent import llm_client

    _db = _fresh_db("weakcover")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-09-30", hours_per_day=8.0)
        s.add(g); s.commit(); s.refresh(g)
        # Two confirmed concepts; make BOTH weak via low quiz scores.
        ca = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        cb = models.Concept(goal_id=g.id, canonical_term="ACID", name="A", confirmed=True)
        s.add(ca); s.add(cb); s.commit(); s.refresh(ca); s.refresh(cb)
        for cid in (ca.id, cb.id):
            s.add(models.Evidence(goal_id=g.id, concept_id=cid, type="quiz_result",
                                  payload_json='{"score": 0.2}'))
        s.commit()
        # Parent plan v1 covers BOTH weak concepts.
        tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": ca.id, "day": "2026-07-25", "description": "norm base", "est_minutes": 40},
            {"concept_id": cb.id, "day": "2026-07-26", "description": "acid base", "est_minutes": 40},
        ]}, created_by="user")

        # Delta touches ONLY Normalization (ca). ACID (cb) is weak but covered by
        # the carried-forward parent task, so the merged plan still covers it.
        orig = llm_client.decide_replan
        llm_client.decide_replan = lambda **kw: {
            "decision": "new_version", "reasoning_text": "focus normalization",
            "plan": {"tasks": [{"concept_id": ca.id, "canonical_term": "Normalization",
                                "day": "2026-07-28", "description": "norm remediation",
                                "est_minutes": 40}]},
        }
        try:
            res = orchestrator.run_agent(s, g.id, "low_mastery")
        finally:
            llm_client.decide_replan = orig

        assert res["decision"] == "new_version", res
        versions = s.exec(select(models.PlanVersion).where(
            models.PlanVersion.goal_id == g.id)).all()
        assert max(v.version_no for v in versions) == 2, "a valid remediation delta must create V2"


def test_db_complete_task_on_superseded_version_rejected():
    """A-FIX-2: completing a task on an old version returns 409 and mutates nothing."""
    from fastapi import HTTPException
    from sqlmodel import Session, select
    import models
    from agent import tools
    from routers.evidence import complete_task

    _db = _fresh_db("stale")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", hours_per_day=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)
        v1 = tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-21", "description": "old task", "est_minutes": 40},
        ]}, created_by="user")
        v1_task = s.exec(select(models.Task).where(
            models.Task.plan_version_id == v1["plan_version_id"])).first()
        # replan to V2 so V1 is now superseded
        tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-23", "description": "new", "est_minutes": 40},
        ]}, created_by="agent")

        raised = False
        try:
            complete_task(v1_task.id, session=s)
        except HTTPException as e:
            raised = True
            assert e.status_code == 409
        assert raised, "completing a superseded-version task must raise 409"
        # V1 row untouched
        s.refresh(v1_task)
        assert v1_task.status != "done", "superseded task must not be mutated"


def test_db_complete_task_sets_completed_at():
    """A-FIX-4: completing a current-version task stamps completed_at."""
    from sqlmodel import Session, select
    import models
    from agent import tools
    from routers.evidence import complete_task

    _db = _fresh_db("compat")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", hours_per_day=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)
        v1 = tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-21", "description": "t", "est_minutes": 40},
        ]}, created_by="user")
        task = s.exec(select(models.Task).where(
            models.Task.plan_version_id == v1["plan_version_id"])).first()
        complete_task(task.id, session=s)
        s.refresh(task)
        assert task.status == "done"
        assert task.completed_at, "completed_at must be stamped on completion"


DB_TESTS = [
    test_db_replan_appends_new_version_and_preserves_parent,
    test_db_full_merge_carries_completion_state,
    test_db_validation_failure_records_no_change,
    test_db_repeated_trigger_records_no_change_not_duplicate,
    test_db_replan_weak_concept_covered_by_parent_not_falsely_rejected,
    test_db_complete_task_on_superseded_version_rejected,
    test_db_complete_task_sets_completed_at,
]


if __name__ == "__main__":
    passed = failed = skipped = 0
    for test in PURE_TESTS:
        try:
            test(); print(f"PASS  {test.__name__}"); passed += 1
        except AssertionError as e:
            print(f"FAIL  {test.__name__}: {e}"); failed += 1

    if _db_available():
        for test in DB_TESTS:
            try:
                test(); print(f"PASS  {test.__name__}"); passed += 1
            except AssertionError as e:
                print(f"FAIL  {test.__name__}: {e}"); failed += 1
    else:
        skipped = len(DB_TESTS)
        print(f"\nSKIP  {skipped} DB-backed tests (sqlmodel not installed in this env)")
        for test in DB_TESTS:
            print(f"SKIP  {test.__name__}")

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    if failed:
        raise SystemExit(1)
