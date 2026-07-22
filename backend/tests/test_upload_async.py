"""
TraceLearn — Member A A4: async document upload + background concept pipeline.

Plain-script style (no pytest) — run with `python tests/test_upload_async.py`.

Runs under MOCK_LLM (config default) so it needs no live endpoint: the real
concept extraction is mocked, but the ASYNC PLUMBING + STATUS LIFECYCLE
(processing -> ready/failed, real concepts written, no-file + broken-file
fallbacks) is what these tests exercise — that's Member A's lane.

The background task normally runs after the HTTP response via FastAPI's
BackgroundTasks. Here we call `_process_document` directly (it's the unit under
test) after checking the endpoint set status='processing' and scheduled it.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
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
    from sqlmodel import SQLModel
    SQLModel.metadata.drop_all(_db.engine)
    SQLModel.metadata.create_all(_db.engine)
    return _db


class _FakeUpload:
    """Minimal stand-in for Starlette's UploadFile (only .filename + async read)."""
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


class _CapturingBackground:
    """Capture the scheduled task instead of running it, so the test can assert
    the endpoint returned BEFORE the heavy work and then run it deliberately."""
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))

    def run_all(self):
        for fn, args, kwargs in self.tasks:
            fn(*args, **kwargs)


def _seed_goal(db):
    from sqlmodel import Session
    import models
    with Session(db.engine) as s:
        s.add(models.User(id=1, name="t")); s.commit()
        g = models.Goal(user_id=1, goal_text="pass my databases final",
                        deadline="2026-08-10", weekly_hours=6.0,
                        explanation_language="en")
        s.add(g); s.commit(); s.refresh(g)
        return g.id


def _seed_processing_doc(db, goal_id, storage_path=None):
    """Mirror what the upload endpoint does before scheduling the background
    task: create the Document row in 'processing'. The direct-call tests below
    invoke _process_document without the endpoint, so they seed this first."""
    from sqlmodel import Session
    import models
    with Session(db.engine) as s:
        s.add(models.Document(goal_id=goal_id, filename="x",
                              storage_path=storage_path, status="processing"))
        s.commit()


def _doc_status(db, goal_id):
    from sqlmodel import Session, select
    import models
    with Session(db.engine) as s:
        doc = s.exec(select(models.Document).where(
            models.Document.goal_id == goal_id)).first()
        return doc.status if doc else None


def _concepts(db, goal_id):
    from sqlmodel import Session, select
    import models
    with Session(db.engine) as s:
        return s.exec(select(models.Concept).where(
            models.Concept.goal_id == goal_id)).all()


def test_upload_with_file_returns_processing_then_ready_with_concepts():
    if not _db_available():
        print("SKIP  test_upload_with_file_returns_processing_then_ready_with_concepts (no sqlmodel)")
        return
    from sqlmodel import Session
    from routers import goals as goals_router
    import storage

    db = _fresh_db("a4_ready")
    goal_id = _seed_goal(db)
    tmp = tempfile.mkdtemp()
    try:
        storage.UPLOAD_DIR = tmp
        upload = _FakeUpload("notes.txt", b"Databases: normalization, indexing, transactions. " * 5)
        bg = _CapturingBackground()
        with Session(db.engine) as s:
            out = asyncio.run(goals_router.upload_document(
                goal_id, bg, file=upload, session=s))
        # 1) returns immediately with processing, and the work was scheduled (not run yet)
        assert out.status == "processing", out.status
        assert len(bg.tasks) == 1, "exactly one background task should be scheduled"
        assert _doc_status(db, goal_id) == "processing"
        # 2) run the background task -> ready + real (mock) concepts written
        bg.run_all()
        assert _doc_status(db, goal_id) == "ready", _doc_status(db, goal_id)
        cs = _concepts(db, goal_id)
        assert cs, "concepts must be written after processing"
        assert all(not c.confirmed for c in cs), "extracted concepts start unconfirmed"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_upload_no_file_falls_back_to_goal_topic_ready():
    """The no-file path (placeholder endpoint supported it) must still work:
    processing -> ready with goal-topic concepts, no crash."""
    if not _db_available():
        print("SKIP  test_upload_no_file_falls_back_to_goal_topic_ready (no sqlmodel)")
        return
    from sqlmodel import Session
    from routers import goals as goals_router

    db = _fresh_db("a4_nofile")
    goal_id = _seed_goal(db)
    bg = _CapturingBackground()
    with Session(db.engine) as s:
        out = asyncio.run(goals_router.upload_document(
            goal_id, bg, file=None, session=s))
    assert out.status == "processing", out.status
    assert out.filename is None
    bg.run_all()
    assert _doc_status(db, goal_id) == "ready", _doc_status(db, goal_id)
    cs = _concepts(db, goal_id)
    assert cs, "goal-topic fallback must still yield concepts with no file"
    assert all(c.source == "goal_topic" for c in cs), \
        "no-file concepts must be tagged goal_topic"


def test_broken_file_extraction_error_marks_failed():
    """If extraction AND the goal-topic fallback both fail (model error with no
    fallback possible), the document lands on 'failed' — never stuck processing."""
    if not _db_available():
        print("SKIP  test_broken_file_extraction_error_marks_failed (no sqlmodel)")
        return
    from routers import goals as goals_router
    import ingestion

    db = _fresh_db("a4_failed")
    goal_id = _seed_goal(db)
    _seed_processing_doc(db, goal_id)

    # Force build_concept_map to raise (simulates model down with no fallback).
    orig = ingestion.build_concept_map

    def _boom(*a, **k):
        raise RuntimeError("simulated total extraction failure")

    ingestion.build_concept_map = _boom
    try:
        goals_router._process_document(goal_id, None, "en", "learn databases")
    finally:
        ingestion.build_concept_map = orig

    assert _doc_status(db, goal_id) == "failed", _doc_status(db, goal_id)


def test_unsupported_file_type_falls_back_not_crashes():
    """An out-of-scope file type (e.g. .docx) -> UnsupportedDocumentError is
    swallowed and the goal-topic fallback still makes the doc 'ready'."""
    if not _db_available():
        print("SKIP  test_unsupported_file_type_falls_back_not_crashes (no sqlmodel)")
        return
    from routers import goals as goals_router
    import storage

    db = _fresh_db("a4_unsupported")
    goal_id = _seed_goal(db)
    tmp = tempfile.mkdtemp()
    try:
        storage.UPLOAD_DIR = tmp
        path = storage.save_upload(goal_id, "slides.docx", b"not really a docx")
        _seed_processing_doc(db, goal_id, storage_path=path)
        goals_router._process_document(goal_id, path, "en", "learn databases")
        # extract_text raises UnsupportedDocumentError -> caught -> goal-topic map -> ready
        assert _doc_status(db, goal_id) == "ready", _doc_status(db, goal_id)
        cs = _concepts(db, goal_id)
        assert cs and all(c.source == "goal_topic" for c in cs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


ALL_TESTS = [
    test_upload_with_file_returns_processing_then_ready_with_concepts,
    test_upload_no_file_falls_back_to_goal_topic_ready,
    test_broken_file_extraction_error_marks_failed,
    test_unsupported_file_type_falls_back_not_crashes,
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
