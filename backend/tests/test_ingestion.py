"""
Tests for storage.py (C1) and ingestion.py (C2/C3).

Plain-script style (no pytest) to match test_triggers_validator.py,
test_versioning.py, and test_llm_client_parsing.py — run with
`python tests/test_ingestion.py`.

Runs entirely under MOCK_LLM (config default) so it needs no live Hermes
endpoint: C3's wiring/fallback logic is exercised against `_mock_concepts`,
which is enough to prove the plumbing (empty text -> fallback, model error
-> fallback, real text -> pass-through). Prompt-quality tuning against a
real model (C4/C5) is a separate, manual step — see MEMBER_C_PHASE2_TASKLIST.md.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

# Run as a plain script: put backend/ on sys.path so top-level modules
# (storage, ingestion, agent.llm_client) resolve the same way the app does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import storage
import ingestion
from agent import llm_client


def _assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"expected {exc_type.__name__}, got {type(e).__name__}: {e}")
    raise AssertionError(f"expected {exc_type.__name__}, but no exception was raised")


# ---------------------------------------------------------------------------
# storage.save_upload (C1)
# ---------------------------------------------------------------------------
def test_save_upload_writes_bytes_and_returns_existing_path():
    tmp = tempfile.mkdtemp()
    try:
        storage.UPLOAD_DIR = tmp
        path = storage.save_upload(42, "notes.pdf", b"%PDF-1.4 fake bytes")
        assert Path(path).exists(), "save_upload must write the file to disk"
        assert Path(path).read_bytes() == b"%PDF-1.4 fake bytes"
        assert path.endswith(str(Path("42") / "notes.pdf"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_save_upload_sanitizes_path_traversal_filename():
    tmp = tempfile.mkdtemp()
    try:
        storage.UPLOAD_DIR = tmp
        path = storage.save_upload(1, "../../etc/passwd", b"x")
        resolved = Path(path).resolve()
        assert str(resolved).startswith(str(Path(tmp).resolve())), (
            "a hostile filename must not escape UPLOAD_DIR"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_save_upload_overwrites_same_filename():
    tmp = tempfile.mkdtemp()
    try:
        storage.UPLOAD_DIR = tmp
        p1 = storage.save_upload(7, "doc.txt", b"first")
        p2 = storage.save_upload(7, "doc.txt", b"second")
        assert p1 == p2
        assert Path(p2).read_bytes() == b"second"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# ingestion.extract_text (C2)
# ---------------------------------------------------------------------------
def test_extract_text_txt_utf8():
    tmp = tempfile.mkdtemp()
    try:
        p = Path(tmp) / "sample.txt"
        p.write_text("Normalization: 1NF, 2NF, 3NF.\n\nIndexing speeds up reads.", encoding="utf-8")
        text = ingestion.extract_text(str(p))
        assert "Normalization" in text
        assert "Indexing" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_extract_text_on_real_demo_sample():
    sample = Path(__file__).resolve().parent.parent / "seed" / "sample_db_course.txt"
    assert sample.exists(), "demo sample doc should exist at backend/seed/sample_db_course.txt"
    text = ingestion.extract_text(str(sample))
    assert len(text.strip()) > 200, "demo sample should extract substantial text"


def test_extract_text_rejects_unsupported_extension():
    tmp = tempfile.mkdtemp()
    try:
        p = Path(tmp) / "slides.pptx"
        p.write_bytes(b"not really a pptx")
        _assert_raises(ingestion.UnsupportedDocumentError, ingestion.extract_text, str(p))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_is_usable_material():
    assert ingestion.is_usable_material("A" * 41) is True
    assert ingestion.is_usable_material("") is False
    assert ingestion.is_usable_material("   ") is False
    assert ingestion.is_usable_material("short") is False


# ---------------------------------------------------------------------------
# ingestion.build_concept_map / build_goal_topic_map (C3)
# ---------------------------------------------------------------------------
def test_build_concept_map_passes_through_real_text():
    concepts = ingestion.build_concept_map(
        "Normalization removes redundancy. Indexing speeds up lookups. " * 3,
        "en",
    )
    assert isinstance(concepts, list) and concepts
    assert all(c["source"] == "material" for c in concepts)


def test_build_concept_map_falls_back_on_empty_text_with_goal():
    concepts = ingestion.build_concept_map("", "en", goal_text="pass my databases final")
    assert isinstance(concepts, list) and concepts
    assert all(c["source"] == "goal_topic" for c in concepts)


def test_build_concept_map_raises_on_empty_text_without_goal():
    _assert_raises(ValueError, ingestion.build_concept_map, "", "en")


def test_build_concept_map_falls_back_on_model_error_with_goal():
    original = llm_client.extract_concepts
    calls = {"n": 0}

    def _fails_once_then_mocks(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated model failure")
        return original(**kwargs)

    llm_client.extract_concepts = _fails_once_then_mocks
    try:
        concepts = ingestion.build_concept_map(
            "plenty of real material text here " * 5,
            "en",
            goal_text="learn databases",
        )
        assert all(c["source"] == "goal_topic" for c in concepts)
    finally:
        llm_client.extract_concepts = original


def test_build_goal_topic_map_shape_matches_mock_shape():
    concepts = ingestion.build_goal_topic_map("pass my databases final", "zh")
    assert isinstance(concepts, list) and concepts
    for c in concepts:
        assert set(c.keys()) >= {"canonical_term", "name", "explanation", "order_index", "source"}
        assert c["source"] == "goal_topic"


ALL_TESTS = [
    test_save_upload_writes_bytes_and_returns_existing_path,
    test_save_upload_sanitizes_path_traversal_filename,
    test_save_upload_overwrites_same_filename,
    test_extract_text_txt_utf8,
    test_extract_text_on_real_demo_sample,
    test_extract_text_rejects_unsupported_extension,
    test_is_usable_material,
    test_build_concept_map_passes_through_real_text,
    test_build_concept_map_falls_back_on_empty_text_with_goal,
    test_build_concept_map_raises_on_empty_text_without_goal,
    test_build_concept_map_falls_back_on_model_error_with_goal,
    test_build_goal_topic_map_shape_matches_mock_shape,
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
