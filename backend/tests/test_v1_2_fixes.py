"""
TraceLearn — Member A V1.2 regression tests.

Covers the DB-tier halves of the V1.2 backend batch:
  - A-V2-2: checkpoint + onboarding submit return a per-question right/wrong
    breakdown ({question_id, submitted, correct_choice, is_correct}).
  - A-V2-4: get_progress_summary exposes schedule-aware keys and the
    ahead_schedule trigger fires end-to-end when a learner pulls future work
    forward with no overdue tasks.
  - A-V2-5: version-derived remediation blocks — the existing /plan/versions +
    /plan/diff read surface already lets a consumer distinguish v1 tasks from
    v2-introduced (remediation) tasks WITHOUT a schema change (full-merge makes
    every current task's plan_version_id point at the latest version, so the
    diff between adjacent versions is the correct grouping key).

Plain-script style (no pytest) — run with `python tests/test_v1_2_fixes.py`.
DB-tier: needs sqlmodel; auto-skips cleanly if unavailable (run for real in the
python:3.12-slim Docker sandbox).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Pin MOCK mode BEFORE any app import reads config: these tests assert against
# the deterministic mock LLM (fixed question/answer key). A real env var wins
# over load_dotenv, so this holds even when a live backend/.env (MOCK_LLM=false)
# is mounted into the sandbox. The 4 live-only tests live elsewhere.
os.environ.setdefault("MOCK_LLM", "true")

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
    from agent import replan as _replan
    importlib.reload(_replan)
    from sqlmodel import SQLModel
    SQLModel.metadata.drop_all(_db.engine)
    SQLModel.metadata.create_all(_db.engine)
    return _db


class _CapturingBackground:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


def _seed_goal_two_concepts(db):
    """Goal + 2 confirmed concepts, no plan yet. Returns (goal_id, [c1, c2])."""
    from sqlmodel import Session
    import models
    with Session(db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="pass databases", deadline="2026-08-10",
                         hours_per_day=6.0, explanation_language="en")
        s.add(g); s.commit(); s.refresh(g)
        c1 = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        c2 = models.Concept(goal_id=g.id, canonical_term="Indexing", name="I", confirmed=True)
        s.add(c1); s.add(c2); s.commit(); s.refresh(c1); s.refresh(c2)
        return g.id, c1.id, c2.id


# ---------------------------------------------------------------------------
# A-V2-2: per-question breakdown
# ---------------------------------------------------------------------------
def test_checkpoint_submit_returns_per_question_breakdown():
    if not _db_available():
        print("SKIP  test_checkpoint_submit_returns_per_question_breakdown (no sqlmodel)")
        return
    from sqlmodel import Session
    from routers import diagnostic as diag_router
    from schemas import CheckpointGenerate, CheckpointSubmit, DiagnosticAnswer
    db = _fresh_db("v12_pq_checkpoint")
    from agent import replan  # noqa: F401  (reloaded to point at this DB)
    goal_id, c1, c2 = _seed_goal_two_concepts(db)

    with Session(db.engine) as s:
        out = diag_router.generate_checkpoint(
            goal_id, CheckpointGenerate(concept_ids=[c1, c2]), session=s)
        assert len(out.questions) >= 2, "need >=2 questions to test a right + a wrong"

        # Mock answer key is always "A" (== first option). Answer q1 correctly
        # ("A") and q2 incorrectly ("B").
        q1, q2 = out.questions[0], out.questions[1]
        answers = [DiagnosticAnswer(question_id=q1.id, choice="A"),
                   DiagnosticAnswer(question_id=q2.id, choice="B")]
        bg = _CapturingBackground()
        res = diag_router.submit_checkpoint(
            goal_id, CheckpointSubmit(checkpoint_id=out.checkpoint_id, answers=answers),
            bg, session=s)

    by_qid = {pq.question_id: pq for pq in res.per_question}
    assert len(by_qid) == len(out.questions), "one per-question row per question"
    assert by_qid[q1.id].is_correct is True, by_qid[q1.id]
    assert by_qid[q1.id].submitted == "A"
    assert by_qid[q2.id].is_correct is False, by_qid[q2.id]
    assert by_qid[q2.id].submitted == "B"
    # Correct option is revealed now the quiz is over (letter "A" -> option text).
    assert by_qid[q1.id].correct_choice is not None
    assert by_qid[q2.id].correct_choice is not None


def test_diagnostic_submit_returns_per_question_breakdown():
    if not _db_available():
        print("SKIP  test_diagnostic_submit_returns_per_question_breakdown (no sqlmodel)")
        return
    from sqlmodel import Session
    from routers import diagnostic as diag_router
    from schemas import DiagnosticAnswer, DiagnosticSubmit
    db = _fresh_db("v12_pq_diag")
    from agent import replan  # noqa: F401
    goal_id, c1, c2 = _seed_goal_two_concepts(db)

    with Session(db.engine) as s:
        out = diag_router.generate_diagnostic(goal_id, session=s)
        assert out.questions
        q1 = out.questions[0]
        answers = [DiagnosticAnswer(question_id=q1.id, choice="B")]  # wrong
        res = diag_router.submit_diagnostic(
            goal_id, DiagnosticSubmit(answers=answers), session=s)

    assert res.per_question, "onboarding result also carries per-question detail"
    by_qid = {pq.question_id: pq for pq in res.per_question}
    assert by_qid[q1.id].is_correct is False
    assert by_qid[q1.id].submitted == "B"


# ---------------------------------------------------------------------------
# A-V2-4: schedule-aware progress + ahead_schedule trigger end-to-end
# ---------------------------------------------------------------------------
def test_progress_summary_exposes_schedule_aware_keys_and_ahead_fires():
    if not _db_available():
        print("SKIP  test_progress_summary_exposes_schedule_aware_keys_and_ahead_fires (no sqlmodel)")
        return
    from sqlmodel import Session, select
    import models
    from agent import tools
    from agent.triggers import evaluate_triggers
    db = _fresh_db("v12_ahead")
    from agent import replan  # noqa: F401
    goal_id, c1, c2 = _seed_goal_two_concepts(db)

    today = date.today()
    past = (today - timedelta(days=1)).isoformat()
    future1 = (today + timedelta(days=3)).isoformat()
    future2 = (today + timedelta(days=4)).isoformat()

    with Session(db.engine) as s:
        # A due (past) task already done + two FUTURE tasks, one done early.
        tools.create_plan_version(s, goal_id, {"tasks": [
            {"concept_id": c1, "day": past, "description": "due task", "est_minutes": 45},
            {"concept_id": c1, "day": future1, "description": "future A", "est_minutes": 45},
            {"concept_id": c2, "day": future2, "description": "future B", "est_minutes": 45},
        ]}, created_by="user")
        # Mark the past task and the first future task as done (pulled forward).
        tasks = s.exec(select(models.Task)).all()
        for t in tasks:
            if t.day in (past, future1):
                t.status = "done"
                s.add(t)
        s.commit()

        progress = tools.get_progress_summary(s, goal_id)
        assert progress["tasks_future"] == 2, progress
        assert progress["tasks_done_ahead"] == 1, progress
        assert progress["tasks_incomplete_due"] == 0, progress

        # 1 of 2 future done early = 50% > 20% threshold, nothing overdue -> ahead.
        tr = evaluate_triggers(
            progress=progress,
            concept_mastery={c1: 0.9, c2: 0.9},
            recent_evidence=[{"type": "task_done"}] * 3,
        )
    assert tr.fired is True
    assert tr.reason == "ahead_schedule", tr


# ---------------------------------------------------------------------------
# A-V2-5: version-derived remediation blocks via /plan/versions + /plan/diff
# ---------------------------------------------------------------------------
def test_diff_distinguishes_v2_remediation_from_v1_tasks():
    """B groups remediation into "Remediation #N" blocks by the PlanVersion that
    introduced each task. Under full-merge every current task's plan_version_id
    points to the LATEST version, so plan_version_id alone can't distinguish
    origin — but the diff between adjacent versions can, with no schema change."""
    if not _db_available():
        print("SKIP  test_diff_distinguishes_v2_remediation_from_v1_tasks (no sqlmodel)")
        return
    from sqlmodel import Session
    from agent import tools
    from routers import plan as plan_router
    db = _fresh_db("v12_diff")
    from agent import replan  # noqa: F401
    goal_id, c1, c2 = _seed_goal_two_concepts(db)

    with Session(db.engine) as s:
        # v1: one Normalization task.
        tools.create_plan_version(s, goal_id, {"tasks": [
            {"concept_id": c1, "day": "2026-08-01", "description": "v1 study Normalization",
             "est_minutes": 45},
        ]}, created_by="user")
        # v2 (agent replan): delta adds an Indexing remediation task. Full-merge
        # carries v1's task forward + appends the delta.
        tools.create_plan_version(s, goal_id, {"tasks": [
            {"concept_id": c2, "day": "2026-08-02", "description": "v2 remediation Indexing",
             "est_minutes": 40},
        ]}, created_by="agent")

        versions = plan_router.list_versions(goal_id, session=s)
        assert [v.version_no for v in versions] == [1, 2], versions
        assert versions[1].created_by == "agent"

        # The diff v1 -> v2 surfaces exactly the v2-introduced remediation task,
        # and NOT the carried-forward v1 task (matches on description+day).
        diff = plan_router.plan_diff(goal_id, from_=1, to=2, session=s)
        added_desc = [t.description for t in diff.added_tasks]
        assert added_desc == ["v2 remediation Indexing"], added_desc
        assert diff.removed_tasks == [], "full-merge never drops parent tasks"
        assert "Indexing" in diff.concept_summary, diff.concept_summary


ALL_TESTS = [
    test_checkpoint_submit_returns_per_question_breakdown,
    test_diagnostic_submit_returns_per_question_breakdown,
    test_progress_summary_exposes_schedule_aware_keys_and_ahead_fires,
    test_diff_distinguishes_v2_remediation_from_v1_tasks,
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
