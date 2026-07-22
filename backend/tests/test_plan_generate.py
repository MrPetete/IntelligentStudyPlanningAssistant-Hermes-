"""
TraceLearn — Member A V1.1 tests for the plan/generate endpoint (A-FIX-3):
the bounded revise loop and the structured deadline_too_tight error.

Two tiers (mirrors test_versioning.py):
  1. DB-backed endpoint tests via FastAPI TestClient — need sqlmodel + fastapi;
     auto-skipped with a clear note if unavailable (sandbox), run for real in a
     full environment / Docker.

Run:
    cd backend
    python tests/test_plan_generate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run as a plain script: put backend/ on sys.path so `agent.*` / `models` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _skip(reason: str) -> bool:
    print(f"SKIP  {reason}")
    return True


def _deps_available() -> bool:
    try:
        import fastapi  # noqa: F401
        import sqlmodel  # noqa: F401
        return True
    except Exception:
        return False


def _fresh_client(tmp_name: str):
    """Isolated SQLite + a TestClient whose get_session uses that DB.

    Returns (client, engine, teardown). Seeds one goal + 5 confirmed concepts.
    """
    import importlib
    import config as _config
    _config.MOCK_LLM = True  # deterministic; live path is the integration suite
    _config.DATABASE_URL = f"sqlite:///./_test_{tmp_name}.db"

    import db as _db
    importlib.reload(_db)
    import models  # import BEFORE create_all so tables register on the metadata
    from sqlmodel import SQLModel, Session
    SQLModel.metadata.drop_all(_db.engine)
    SQLModel.metadata.create_all(_db.engine)

    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="Pass DB final",
                         deadline="2026-08-10", hours_per_day=2.0,
                         explanation_language="en")
        s.add(g); s.commit(); s.refresh(g)
        for i in range(1, 6):
            s.add(models.Concept(goal_id=g.id, canonical_term=f"C{i}",
                                  name=f"C{i}", order_index=i, confirmed=True))
        s.commit()
        goal_id = g.id

    from fastapi.testclient import TestClient
    from sqlmodel import Session as _Session
    import main
    from db import get_session as _orig_get_session

    def _override():
        with _Session(_db.engine) as s:
            yield s

    main.app.dependency_overrides[_orig_get_session] = _override

    client = TestClient(main.app)

    def teardown():
        main.app.dependency_overrides.clear()
        import os
        try:
            os.remove(f"./_test_{tmp_name}.db")
        except OSError:
            pass

    return client, goal_id, teardown

def test_revise_loop_recovers_first_attempt_overage():
    """Attempt 1 returns an over-budget plan, attempt 2 fits -> endpoint 200s
    and persists the SECOND plan (the revise loop self-corrects, no user error)."""
    if not _deps_available():
        return _skip("test_revise_loop_recovers_first_attempt_overage (fastapi/sqlmodel missing)")
    client, goal_id, teardown = _fresh_client("revise")
    try:
        from agent import llm_client
        orig = llm_client.generate_plan
        calls = {"n": 0}

        over = {"tasks": [{"concept_id": 1, "day": "2026-08-01",
                           "description": "too big", "est_minutes": 999999}]}
        fit = {"tasks": [{"concept_id": 1, "day": "2026-08-01",
                          "description": "fits", "est_minutes": 30}]}

        def fake_generate_plan(**kwargs):
            calls["n"] += 1
            return over if calls["n"] == 1 else fit

        llm_client.generate_plan = fake_generate_plan
        try:
            r = client.post(f"/goals/{goal_id}/plan/generate")
        finally:
            llm_client.generate_plan = orig

        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        assert calls["n"] == 2, f"expected 2 attempts, got {calls['n']}"
        body = r.json()
        descs = [t["description"] for t in body["tasks"]]
        assert descs == ["fits"], f"expected the second (fitting) plan, got {descs}"
        print("PASS  test_revise_loop_recovers_first_attempt_overage")
    finally:
        teardown()


def test_too_tight_deadline_returns_structured_error():
    """An impossible (past) deadline returns the structured deadline_too_tight
    422 — never a generic reject or an unhandled 500."""
    if not _deps_available():
        return _skip("test_too_tight_deadline_returns_structured_error (fastapi/sqlmodel missing)")
    client, goal_id, teardown = _fresh_client("tootight")
    try:
        import models
        import db as _db
        from sqlmodel import Session
        # Force an impossible deadline: already in the past -> 0 available minutes.
        with Session(_db.engine) as s:
            g = s.get(models.Goal, goal_id)
            g.deadline = "2020-01-01"
            s.add(g); s.commit()

        r = client.post(f"/goals/{goal_id}/plan/generate")
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert detail["error"] == "deadline_too_tight", f"got {detail}"
        print("PASS  test_too_tight_deadline_returns_structured_error")
    finally:
        teardown()


ALL_TESTS = [
    test_revise_loop_recovers_first_attempt_overage,
    test_too_tight_deadline_returns_structured_error,
]


if __name__ == "__main__":
    passed = failed = 0
    for test in ALL_TESTS:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed/skipped, {failed} failed")
    if failed:
        raise SystemExit(1)

