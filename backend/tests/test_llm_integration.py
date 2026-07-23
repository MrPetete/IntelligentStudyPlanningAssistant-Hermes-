"""
TraceLearn — Member A A2: LIVE-LLM integration tests (guarded).

Plain-script style — run with `python tests/test_llm_integration.py`.

These call the REAL model through the four `_real_*` seams and assert the
returned shapes match the `_mock_*` twins. They are the ONLY tests that need a
live endpoint, so they SKIP cleanly unless BOTH:
  - config.MOCK_LLM is False, and
  - config.ANTHROPIC_API_KEY is set
This is the plain-script equivalent of `@pytest.mark.skipif(MOCK_LLM)`: in
normal (mock) CI every test prints SKIP and the suite stays green; the user
runs it live with `--env-file .env` (MOCK_LLM=false) during the audit.

Live run (Docker, key from .env — never baked into the image):
    docker run --rm --env-file .env -v "$(pwd -W)":/app -w /app python:3.12-slim \
      bash -c "pip install -q -r requirements.txt && python tests/test_llm_integration.py"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agent import llm_client

_LIVE = (not config.MOCK_LLM) and bool(config.ANTHROPIC_API_KEY)
_SKIP_MSG = "(MOCK_LLM is true or ANTHROPIC_API_KEY unset — live test skipped)"


def test_live_extract_concepts_shape():
    if not _LIVE:
        print(f"SKIP  test_live_extract_concepts_shape {_SKIP_MSG}")
        return
    material = (
        "Database normalization organizes tables to reduce redundancy: 1NF, 2NF, "
        "3NF. Indexing speeds lookups. Transactions provide ACID guarantees. "
        "Joins combine rows across tables. Query optimization plans execution."
    )
    out = llm_client.extract_concepts(material_text=material, explanation_language="en")
    assert isinstance(out, list) and out, "expected a non-empty concept list"
    for c in out:
        assert {"canonical_term", "name", "explanation", "order_index", "source"} <= set(c)
        assert c["canonical_term"], "canonical_term must be non-empty (the join key)"


def test_live_generate_diagnostic_shape():
    if not _LIVE:
        print(f"SKIP  test_live_generate_diagnostic_shape {_SKIP_MSG}")
        return
    concepts = [
        {"id": 1, "canonical_term": "Normalization", "explanation": "reduce redundancy", "order_index": 1},
        {"id": 2, "canonical_term": "Indexing", "explanation": "speed lookups", "order_index": 2},
    ]
    out = llm_client.generate_diagnostic(concepts=concepts, num_questions=3, explanation_language="en")
    assert isinstance(out, list) and out, "expected non-empty questions"
    valid_ids = {1, 2}
    for q in out:
        assert q["concept_id"] in valid_ids, "questions must reference given concepts only"
        assert isinstance(q["options"], list) and len(q["options"]) >= 2
        assert q["answer"] in ("A", "B", "C", "D")


def test_live_generate_plan_shape():
    if not _LIVE:
        print(f"SKIP  test_live_generate_plan_shape {_SKIP_MSG}")
        return
    concepts = [
        {"id": 1, "canonical_term": "Normalization", "order_index": 1},
        {"id": 2, "canonical_term": "Indexing", "order_index": 2},
    ]
    out = llm_client.generate_plan(
        goal={"deadline": "2026-08-10", "hours_per_day": 6},
        concepts=concepts, scores={1: 0.3, 2: 0.8}, explanation_language="en",
    )
    assert isinstance(out, dict) and out.get("tasks"), "expected a plan with tasks"
    for t in out["tasks"]:
        assert t["concept_id"] in {1, 2}, "tasks must reference given concepts only"
        assert t["description"], "task needs a description"
        assert isinstance(t["est_minutes"], int)


def test_live_decide_replan_shape():
    if not _LIVE:
        print(f"SKIP  test_live_decide_replan_shape {_SKIP_MSG}")
        return
    learner_state = {
        "goal_text": "pass databases final", "deadline": "2026-08-10",
        "days_remaining": 20, "hours_per_day": 6, "explanation_language": "en",
        "concepts": [
            {"concept_id": 1, "canonical_term": "Normalization", "mastery": 0.2, "confirmed": True},
            {"concept_id": 2, "canonical_term": "Indexing", "mastery": 0.9, "confirmed": True},
        ],
    }
    progress = {"tasks_total": 5, "tasks_done": 2, "tasks_overdue": 2}
    evidence = [
        {"type": "quiz_result", "concept_id": 1, "payload": {"score": 0.2}},
        {"type": "task_skipped", "concept_id": 1, "payload": {}},
        {"type": "task_skipped", "concept_id": 1, "payload": {}},
    ]
    current_plan = {"version_no": 1, "tasks": [
        {"concept_id": 1, "canonical_term": "Normalization", "day": "2026-07-21",
         "description": "study normalization", "status": "skipped"},
    ]}
    out = llm_client.decide_replan(
        learner_state=learner_state, progress=progress, evidence=evidence,
        current_plan=current_plan, explanation_language="en",
    )
    assert out["decision"] in ("new_version", "no_change")
    assert isinstance(out["reasoning_text"], str) and out["reasoning_text"].strip()
    if out["decision"] == "new_version":
        assert out["plan"] and isinstance(out["plan"]["tasks"], list) and out["plan"]["tasks"]
        for t in out["plan"]["tasks"]:
            assert t.get("canonical_term"), "delta tasks must name a canonical_term"
    else:
        assert out["plan"] is None


ALL_TESTS = [
    test_live_extract_concepts_shape,
    test_live_generate_diagnostic_shape,
    test_live_generate_plan_shape,
    test_live_decide_replan_shape,
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
