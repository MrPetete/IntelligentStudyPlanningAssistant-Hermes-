"""
TraceLearn — Member C V1.2 regression tests.

Covers:
  - C-V2-2: checkpoint quiz generation (and the onboarding diagnostic, same
    root cause) must pass each concept's `explanation` and `order_index`
    into `llm_client.generate_diagnostic`, not just `id`/`canonical_term`.
    Before this fix, `_diagnostic_user_prompt` had nothing but the bare term
    to anchor a question to, since it reads `c.get("explanation", "")` and
    the router never supplied that key — the LLM had no signal for what was
    actually studied, only the term name, which is the likely source of the
    "drifts to adjacent general knowledge" watch item (B-f5).

Plain-script style (no pytest) — run with `python tests/test_c_v2_fixes.py`.
DB-tier: needs sqlmodel; auto-skips cleanly if unavailable (run for real in
the python:3.12-slim Docker sandbox).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

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


def _seed_goal_two_explained_concepts(db):
    """Goal + 2 confirmed concepts, each with a distinct explanation and
    order_index, so we can assert both flow through to the LLM call."""
    from sqlmodel import Session
    import models
    with Session(db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="pass databases", deadline="2026-08-10",
                         hours_per_day=6.0, explanation_language="en")
        s.add(g); s.commit(); s.refresh(g)
        c1 = models.Concept(goal_id=g.id, canonical_term="Normalization", name="N",
                             explanation="Splitting tables to remove redundant data (3NF).",
                             order_index=0, confirmed=True)
        c2 = models.Concept(goal_id=g.id, canonical_term="Indexing", name="I",
                             explanation="B-tree indexes speed up WHERE/JOIN lookups.",
                             order_index=1, confirmed=True)
        s.add(c1); s.add(c2); s.commit(); s.refresh(c1); s.refresh(c2)
        return g.id, c1.id, c2.id


# ---------------------------------------------------------------------------
# C-V2-2: checkpoint / diagnostic concept dicts carry explanation context
# ---------------------------------------------------------------------------
def test_checkpoint_concept_dicts_include_explanation_and_order():
    if not _db_available():
        print("SKIP  test_checkpoint_concept_dicts_include_explanation_and_order (no sqlmodel)")
        return
    from sqlmodel import Session
    from routers import diagnostic as diag_router
    from schemas import CheckpointGenerate
    db = _fresh_db("c_v2_checkpoint_explain")
    from agent import replan  # noqa: F401  (reloaded to point at this DB)
    goal_id, c1, c2 = _seed_goal_two_explained_concepts(db)

    captured = {}
    real_generate = diag_router.llm_client.generate_diagnostic

    def _spy(*, concepts, num_questions, explanation_language):
        captured["concepts"] = concepts
        return real_generate(concepts=concepts, num_questions=num_questions,
                              explanation_language=explanation_language)

    diag_router.llm_client.generate_diagnostic = _spy
    try:
        with Session(db.engine) as s:
            diag_router.generate_checkpoint(
                goal_id, CheckpointGenerate(concept_ids=[c1, c2]), session=s)
    finally:
        diag_router.llm_client.generate_diagnostic = real_generate

    by_id = {c["id"]: c for c in captured["concepts"]}
    assert by_id[c1]["explanation"].startswith("Splitting tables"), by_id[c1]
    assert by_id[c2]["explanation"].startswith("B-tree indexes"), by_id[c2]
    assert by_id[c1]["order_index"] == 0
    assert by_id[c2]["order_index"] == 1


def test_onboarding_diagnostic_concept_dicts_include_explanation_and_order():
    if not _db_available():
        print("SKIP  test_onboarding_diagnostic_concept_dicts_include_explanation_and_order (no sqlmodel)")
        return
    from sqlmodel import Session
    from routers import diagnostic as diag_router
    db = _fresh_db("c_v2_onboarding_explain")
    from agent import replan  # noqa: F401
    goal_id, c1, c2 = _seed_goal_two_explained_concepts(db)

    captured = {}
    real_generate = diag_router.llm_client.generate_diagnostic

    def _spy(*, concepts, num_questions, explanation_language):
        captured["concepts"] = concepts
        return real_generate(concepts=concepts, num_questions=num_questions,
                              explanation_language=explanation_language)

    diag_router.llm_client.generate_diagnostic = _spy
    try:
        with Session(db.engine) as s:
            diag_router.generate_diagnostic(goal_id, session=s)
    finally:
        diag_router.llm_client.generate_diagnostic = real_generate

    by_id = {c["id"]: c for c in captured["concepts"]}
    assert by_id[c1]["explanation"].startswith("Splitting tables"), by_id[c1]
    assert by_id[c2]["explanation"].startswith("B-tree indexes"), by_id[c2]


ALL_TESTS = [
    test_checkpoint_concept_dicts_include_explanation_and_order,
    test_onboarding_diagnostic_concept_dicts_include_explanation_and_order,
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
