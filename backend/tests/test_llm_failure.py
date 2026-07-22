"""
TraceLearn — Member A A3: real-LLM failure handling.

Plain-script style (no pytest) to match the other suites — run with
`python tests/test_llm_failure.py`.

These tests prove the guardrails around a LIVE model WITHOUT needing one:
every test monkeypatches `hermes_client.complete` (or `llm_client.decide_replan`)
to raise / return garbage, and asserts the loop degrades safely:
  - bounded retries fire up to LLM_MAX_RETRIES, then LLMUnavailableError;
  - a transient failure that then succeeds is recovered;
  - the replan orchestrator falls back to a recorded no_change (never crashes,
    never corrupts the plan);
  - an onboarding generation endpoint surfaces a clean 502 (not a 500).

They force the REAL path by calling `_real_*` / `_complete_and_parse` directly,
so config.MOCK_LLM is irrelevant here (it stays at its safe default True).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run as a plain script: put backend/ on sys.path so top-level modules resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agent import hermes_client, llm_client
from agent.hermes_client import HermesError
from agent.llm_client import LLMUnavailableError


def _assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"expected {exc_type.__name__}, got {type(e).__name__}: {e}")
    raise AssertionError(f"expected {exc_type.__name__}, but no exception was raised")


# Speed the tests up: no real backoff sleeps.
llm_client._RETRY_BACKOFF_SECONDS = 0


# ---------------------------------------------------------------------------
# _complete_and_parse — the shared bounded-retry core.
# ---------------------------------------------------------------------------
def test_transport_error_retries_to_cap_then_raises():
    calls = {"n": 0}

    def _always_fail(**kwargs):
        calls["n"] += 1
        raise HermesError("simulated transport failure")

    orig = hermes_client.complete
    hermes_client.complete = _always_fail
    try:
        _assert_raises(
            LLMUnavailableError,
            llm_client._complete_and_parse,
            system_prompt="s", user_prompt="u", parse=lambda raw: raw, what="unit",
        )
        # 1 initial + LLM_MAX_RETRIES retries
        assert calls["n"] == config.LLM_MAX_RETRIES + 1, (
            f"expected {config.LLM_MAX_RETRIES + 1} attempts, got {calls['n']}"
        )
    finally:
        hermes_client.complete = orig


def test_malformed_json_retries_then_raises():
    """A parser ValueError (prose instead of JSON) is retried like a transport
    error, then gives up with LLMUnavailableError."""
    calls = {"n": 0}

    def _returns_prose(**kwargs):
        calls["n"] += 1
        return "I'm sorry, I cannot help with that."  # not JSON

    orig = hermes_client.complete
    hermes_client.complete = _returns_prose
    try:
        _assert_raises(
            LLMUnavailableError,
            llm_client._complete_and_parse,
            system_prompt="s", user_prompt="u",
            parse=llm_client._parse_concepts_response, what="extract_concepts",
        )
        assert calls["n"] == config.LLM_MAX_RETRIES + 1
    finally:
        hermes_client.complete = orig


def test_transient_failure_then_success_recovers():
    """Fails once, succeeds on retry -> returns the parsed result, no error."""
    calls = {"n": 0}
    good = '{"concepts": [{"canonical_term": "Normalization", "name": "N", "explanation": "x", "order_index": 1}]}'

    def _fail_once(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HermesError("transient")
        return good

    orig = hermes_client.complete
    hermes_client.complete = _fail_once
    try:
        out = llm_client._complete_and_parse(
            system_prompt="s", user_prompt="u",
            parse=llm_client._parse_concepts_response, what="extract_concepts",
        )
        assert isinstance(out, list) and out[0]["canonical_term"] == "Normalization"
        assert calls["n"] == 2, "should have retried exactly once"
    finally:
        hermes_client.complete = orig


# ---------------------------------------------------------------------------
# Model escalation ladder — start cheap, escalate on failure, top tier terminal.
# ---------------------------------------------------------------------------
def test_ladder_from_starts_at_tier_and_only_goes_up():
    """A call starting at the Sonnet tier can escalate to Opus but never back
    down to Haiku; an unknown/None model falls back to the legacy single tier."""
    full = llm_client._ladder_from(config.MODEL_GENERATION)  # haiku
    assert [m for m, _ in full] == [config.MODEL_GENERATION, config.MODEL_PLAN, config.MODEL_REPLAN]
    from_sonnet = llm_client._ladder_from(config.MODEL_PLAN)
    assert [m for m, _ in from_sonnet] == [config.MODEL_PLAN, config.MODEL_REPLAN]
    # None / custom id -> legacy single-tier ladder with LLM_MAX_RETRIES budget.
    legacy = llm_client._ladder_from(None)
    assert len(legacy) == 1 and legacy[0][1] == config.LLM_MAX_RETRIES + 1


def test_ladder_escalates_through_all_tiers_then_raises():
    """Every tier fails -> LLMUnavailableError, and each tier was tried its full
    budget in order (haiku x3, sonnet x2, opus x2 by default)."""
    seen: list[str] = []

    def _always_fail(**kwargs):
        seen.append(kwargs.get("model"))
        raise HermesError("simulated failure")

    orig = hermes_client.complete
    hermes_client.complete = _always_fail
    try:
        _assert_raises(
            LLMUnavailableError,
            llm_client._complete_and_parse,
            system_prompt="s", user_prompt="u", parse=lambda raw: raw,
            model=config.MODEL_GENERATION, what="extract_concepts",
        )
        expected = (
            [config.MODEL_GENERATION] * config.LADDER_ATTEMPTS_GENERATION
            + [config.MODEL_PLAN] * config.LADDER_ATTEMPTS_PLAN
            + [config.MODEL_REPLAN] * config.LADDER_ATTEMPTS_REPLAN
        )
        assert seen == expected, f"escalation order wrong: {seen}"
    finally:
        hermes_client.complete = orig


def test_ladder_escalates_and_succeeds_at_higher_tier():
    """Haiku fails its whole budget, Sonnet succeeds on its first attempt ->
    returns the parsed result and does NOT touch Opus."""
    seen: list[str] = []
    good = '{"concepts": [{"canonical_term": "Normalization", "name": "N", "explanation": "x", "order_index": 1}]}'

    def _fail_haiku_then_ok(**kwargs):
        model = kwargs.get("model")
        seen.append(model)
        if model == config.MODEL_GENERATION:
            raise HermesError("haiku slop")
        return good  # sonnet answers cleanly

    orig = hermes_client.complete
    hermes_client.complete = _fail_haiku_then_ok
    try:
        out = llm_client._complete_and_parse(
            system_prompt="s", user_prompt="u",
            parse=llm_client._parse_concepts_response,
            model=config.MODEL_GENERATION, what="extract_concepts",
        )
        assert isinstance(out, list) and out[0]["canonical_term"] == "Normalization"
        assert seen.count(config.MODEL_GENERATION) == config.LADDER_ATTEMPTS_GENERATION
        assert seen.count(config.MODEL_PLAN) == 1, "should stop at first sonnet success"
        assert config.MODEL_REPLAN not in seen, "must not reach opus once sonnet succeeds"
    finally:
        hermes_client.complete = orig


# ---------------------------------------------------------------------------
# Orchestrator fallback — a replan must NEVER crash or corrupt the plan.
# ---------------------------------------------------------------------------
def _db_available() -> bool:
    try:
        import sqlmodel  # noqa: F401
        return True
    except Exception:
        return False


def _fresh_db(tmp_name: str):
    """Isolated SQLite for one test (mirrors test_versioning._fresh_db)."""
    import importlib
    import config as _config
    _config.DATABASE_URL = f"sqlite:///./_test_{tmp_name}.db"
    import db as _db
    importlib.reload(_db)
    from sqlmodel import SQLModel
    SQLModel.metadata.drop_all(_db.engine)
    SQLModel.metadata.create_all(_db.engine)
    return _db


def test_replan_llm_unavailable_falls_back_to_recorded_no_change():
    """If decide_replan raises LLMUnavailableError, run_agent must record a
    no_change decision (D-A3) — never raise, never touch the plan."""
    if not _db_available():
        print("SKIP  test_replan_llm_unavailable_falls_back_to_recorded_no_change (no sqlmodel)")
        return
    from sqlmodel import Session, select
    import models
    from agent import orchestrator, tools

    _db = _fresh_db("a3fallback")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", weekly_hours=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit(); s.refresh(c)
        tools.create_plan_version(s, g.id, {"tasks": [
            {"concept_id": c.id, "day": "2026-07-21", "description": "base", "est_minutes": 40},
        ]}, created_by="user")

        versions_before = s.exec(select(models.PlanVersion).where(
            models.PlanVersion.goal_id == g.id)).all()

        orig = llm_client.decide_replan

        def _raise_unavailable(**kw):
            raise LLMUnavailableError("model down after retries")

        llm_client.decide_replan = _raise_unavailable
        try:
            res = orchestrator.run_agent(s, g.id, "low_mastery")
        finally:
            llm_client.decide_replan = orig

        assert res["decision"] == "no_change", res
        assert res.get("note") == "llm_unavailable", res
        dec = s.get(models.AgentDecision, res["decision_id"])
        assert dec is not None and dec.decision == "no_change"
        assert dec.reasoning_text, "a fallback decision must still carry reasoning_text"
        # plan untouched: no new version created
        versions_after = s.exec(select(models.PlanVersion).where(
            models.PlanVersion.goal_id == g.id)).all()
        assert len(versions_after) == len(versions_before), "no version should be created on LLM failure"


# ---------------------------------------------------------------------------
# Onboarding generation endpoints surface a clean 502, not a 500.
# ---------------------------------------------------------------------------
def test_diagnostic_generation_unavailable_returns_502():
    if not _db_available():
        print("SKIP  test_diagnostic_generation_unavailable_returns_502 (no sqlmodel)")
        return
    from fastapi import HTTPException
    from sqlmodel import Session
    import models
    from routers import diagnostic as diag_router

    _db = _fresh_db("a3_502")
    with Session(_db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="g", deadline="2026-08-10", weekly_hours=6.0)
        s.add(g); s.commit(); s.refresh(g)
        c = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N", confirmed=True)
        s.add(c); s.commit()

        orig = llm_client.generate_diagnostic

        def _raise_unavailable(**kw):
            raise LLMUnavailableError("model down after retries")

        llm_client.generate_diagnostic = _raise_unavailable
        try:
            try:
                diag_router.generate_diagnostic(g.id, session=s)
            except HTTPException as exc:
                assert exc.status_code == 502, f"expected 502, got {exc.status_code}"
                return
            raise AssertionError("expected an HTTPException(502), none raised")
        finally:
            llm_client.generate_diagnostic = orig


ALL_TESTS = [
    test_transport_error_retries_to_cap_then_raises,
    test_malformed_json_retries_then_raises,
    test_transient_failure_then_success_recovers,
    test_ladder_from_starts_at_tier_and_only_goes_up,
    test_ladder_escalates_through_all_tiers_then_raises,
    test_ladder_escalates_and_succeeds_at_higher_tier,
    test_replan_llm_unavailable_falls_back_to_recorded_no_change,
    test_diagnostic_generation_unavailable_returns_502,
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
