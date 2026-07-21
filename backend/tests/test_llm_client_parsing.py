"""
Tests for the response parsers backing the three real-generation prompts
(_real_extract_concepts, _real_generate_diagnostic, _real_generate_plan).

Plain-script style (no pytest) to match test_triggers_validator.py and
test_versioning.py — run with `python tests/test_llm_client_parsing.py`.

These parsers are the actual (non-mock) logic Member C owns; the network
call itself is intentionally not wired (MOCK_LLM stays True — see
llm_client.py). Each test feeds a hand-written string standing in for a raw
model response, including the kind of slop a real model tends to produce
(markdown fences, an invented concept_id, a missing field), and checks the
parser either normalizes it into the exact `_mock_*` shape or rejects it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Run as a plain script (not `python -m`): put backend/ on sys.path so
# `agent.llm_client` resolves the same way the app does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import llm_client as lc


def _assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"expected {exc_type.__name__}, got {type(e).__name__}: {e}")
    raise AssertionError(f"expected {exc_type.__name__}, but no exception was raised")


# ---------------------------------------------------------------------------
# _loads_json_loose
# ---------------------------------------------------------------------------
def test_loads_json_loose_strips_markdown_fence():
    raw = '```json\n{"a": 1}\n```'
    assert lc._loads_json_loose(raw) == {"a": 1}


def test_loads_json_loose_plain_json():
    assert lc._loads_json_loose('{"a": 1}') == {"a": 1}


def test_loads_json_loose_recovers_prose_before_object():
    # A real model sometimes prepends a sentence before the JSON. The strict
    # parse fails; the brace-balanced fallback recovers the object rather than
    # 502-ing the whole call after the retry budget is spent.
    raw = 'Sure! Here is the concept map:\n{"concepts": [{"canonical_term": "X"}]}'
    assert lc._loads_json_loose(raw) == {"concepts": [{"canonical_term": "X"}]}


def test_loads_json_loose_recovers_trailing_note():
    raw = '{"decision": "no_change", "plan": null}\n\nLet me know if you need more.'
    assert lc._loads_json_loose(raw) == {"decision": "no_change", "plan": None}


def test_loads_json_loose_brace_inside_string_value_not_miscounted():
    # A '}' inside a quoted value must not prematurely close the object.
    raw = 'noise {"reasoning_text": "use a set like {a, b}", "decision": "no_change"} tail'
    out = lc._loads_json_loose(raw)
    assert out["reasoning_text"] == "use a set like {a, b}"
    assert out["decision"] == "no_change"


# ---------------------------------------------------------------------------
# concept extraction parser
# ---------------------------------------------------------------------------
def test_parse_concepts_response_happy_path():
    raw = json.dumps({
        "concepts": [
            {"canonical_term": "Normalization", "name": "DB Normalization",
             "explanation": "...", "order_index": 1},
            {"canonical_term": "Indexing", "name": "Indexing",
             "explanation": "...", "order_index": 2},
        ]
    })
    out = lc._parse_concepts_response(raw)
    assert len(out) == 2
    assert out[0]["canonical_term"] == "Normalization"
    assert out[0]["source"] == "material"


def test_parse_concepts_response_drops_items_missing_canonical_term():
    raw = json.dumps({"concepts": [
        {"name": "no term here", "explanation": "..."},
        {"canonical_term": "Joins", "explanation": "..."},
    ]})
    out = lc._parse_concepts_response(raw)
    assert len(out) == 1
    assert out[0]["canonical_term"] == "Joins"


def test_parse_concepts_response_caps_at_max():
    raw = json.dumps({"concepts": [
        {"canonical_term": f"Concept{i}", "explanation": "..."} for i in range(40)
    ]})
    out = lc._parse_concepts_response(raw)
    assert len(out) == lc._CONCEPT_MAP_MAX


def test_parse_concepts_response_rejects_empty_list():
    _assert_raises(ValueError, lc._parse_concepts_response, json.dumps({"concepts": []}))


def test_parse_concepts_response_rejects_missing_key():
    _assert_raises(ValueError, lc._parse_concepts_response, json.dumps({"oops": []}))


def test_parse_concepts_response_no_parent_concept_id_fabricated():
    """C-FIX-3: parser must not invent a parent_concept(_id) field it can't resolve."""
    raw = json.dumps({"concepts": [
        {"canonical_term": "Normalization", "explanation": "...", "parent_concept": "Relational design"},
    ]})
    out = lc._parse_concepts_response(raw)
    assert "parent_concept" not in out[0]
    assert "parent_concept_id" not in out[0]


def test_split_into_sections_handles_short_and_long_text():
    assert lc._split_into_sections("short") == ["short"]
    long_text = "\n\n".join(f"paragraph {i} " * 50 for i in range(20))
    sections = lc._split_into_sections(long_text, target_chars=500)
    assert len(sections) > 1
    # nothing lost: every paragraph marker still appears somewhere
    assert "paragraph 0 " in sections[0]


# ---------------------------------------------------------------------------
# diagnostic parser
# ---------------------------------------------------------------------------
def test_parse_diagnostic_response_happy_path():
    raw = json.dumps({"questions": [
        {"concept_id": 1, "prompt": "What is 3NF?",
         "options": ["a", "b", "c", "d"], "answer": "B"},
        {"concept_id": 2, "prompt": "What is an index?",
         "options": ["a", "b", "c", "d"], "answer": "A"},
    ]})
    out = lc._parse_diagnostic_response(raw, valid_concept_ids={1, 2}, n=6)
    assert len(out) == 2
    assert out[0]["id"] == 1
    assert out[0]["answer"] == "B"


def test_parse_diagnostic_response_drops_invalid_concept_id():
    raw = json.dumps({"questions": [
        {"concept_id": 999, "prompt": "invented concept",
         "options": ["a", "b", "c", "d"], "answer": "A"},
        {"concept_id": 1, "prompt": "real one",
         "options": ["a", "b", "c", "d"], "answer": "A"},
    ]})
    out = lc._parse_diagnostic_response(raw, valid_concept_ids={1}, n=6)
    assert len(out) == 1
    assert out[0]["concept_id"] == 1


def test_parse_diagnostic_response_truncates_to_n():
    raw = json.dumps({"questions": [
        {"concept_id": 1, "prompt": f"q{i}", "options": ["a", "b", "c", "d"], "answer": "A"}
        for i in range(10)
    ]})
    out = lc._parse_diagnostic_response(raw, valid_concept_ids={1}, n=3)
    assert len(out) == 3


def test_parse_diagnostic_response_defaults_bad_answer_letter():
    raw = json.dumps({"questions": [
        {"concept_id": 1, "prompt": "q", "options": ["a", "b", "c", "d"], "answer": "banana"},
    ]})
    out = lc._parse_diagnostic_response(raw, valid_concept_ids={1}, n=6)
    assert out[0]["answer"] == "A"


def test_parse_diagnostic_response_rejects_all_invalid():
    raw = json.dumps({"questions": [
        {"concept_id": 999, "prompt": "q", "options": ["a", "b"], "answer": "A"},
    ]})
    _assert_raises(ValueError, lc._parse_diagnostic_response, raw, valid_concept_ids={1}, n=6)


# ---------------------------------------------------------------------------
# plan parser
# ---------------------------------------------------------------------------
def test_parse_plan_response_happy_path():
    raw = json.dumps({"tasks": [
        {"concept_id": 1, "day": "2026-08-01", "description": "Study X", "est_minutes": 30},
    ]})
    out = lc._parse_plan_response(raw, valid_concept_ids={1})
    assert out["tasks"][0]["concept_id"] == 1
    assert out["tasks"][0]["est_minutes"] == 30


def test_parse_plan_response_drops_invalid_concept_and_empty_description():
    raw = json.dumps({"tasks": [
        {"concept_id": 999, "day": "2026-08-01", "description": "bad ref", "est_minutes": 30},
        {"concept_id": 1, "day": "2026-08-01", "description": "", "est_minutes": 30},
        {"concept_id": 1, "day": "2026-08-01", "description": "good", "est_minutes": 30},
    ]})
    out = lc._parse_plan_response(raw, valid_concept_ids={1})
    assert len(out["tasks"]) == 1
    assert out["tasks"][0]["description"] == "good"


def test_parse_plan_response_coerces_bad_minutes_to_zero():
    raw = json.dumps({"tasks": [
        {"concept_id": 1, "day": "2026-08-01", "description": "x", "est_minutes": "not-a-number"},
    ]})
    out = lc._parse_plan_response(raw, valid_concept_ids={1})
    assert out["tasks"][0]["est_minutes"] == 0


def test_parse_plan_response_rejects_all_invalid():
    raw = json.dumps({"tasks": [{"concept_id": 999, "day": "2026-08-01", "description": "x"}]})
    _assert_raises(ValueError, lc._parse_plan_response, raw, valid_concept_ids={1})


# ---------------------------------------------------------------------------
# C-FIX-1 / C-FIX-2 regression: mock dates must never be hardcoded/broken
# ---------------------------------------------------------------------------
def test_mock_decide_replan_dates_are_relative_and_valid_today():
    from agent.validator import validate_plan
    from datetime import date

    plan = lc._mock_decide_replan([], "en")["plan"]
    for t in plan["tasks"]:
        t["concept_id"] = 1  # normally resolved by the orchestrator
    result = validate_plan(
        plan=plan, weekly_hours=6.0, deadline="2026-08-10",
        today=date.today().isoformat(), valid_concept_ids={1}, weak_concept_ids={1},
    )
    assert result.ok, f"mock replan dates rejected by validator: {result.errors}"


def test_mock_plan_dates_valid_for_more_than_nine_concepts():
    """C-FIX-2 regression: string-template dates broke past concept #9."""
    concepts = [{"id": i, "canonical_term": f"Concept{i}"} for i in range(1, 12)]
    plan = lc._mock_plan(concepts, "en")
    days = [t["day"] for t in plan["tasks"]]
    assert len(days) == 11
    for d in days:
        assert len(d) == 10 and d[4] == "-" and d[7] == "-", f"malformed date: {d}"


ALL_TESTS = [
    test_loads_json_loose_strips_markdown_fence,
    test_loads_json_loose_plain_json,
    test_parse_concepts_response_happy_path,
    test_parse_concepts_response_drops_items_missing_canonical_term,
    test_parse_concepts_response_caps_at_max,
    test_parse_concepts_response_rejects_empty_list,
    test_parse_concepts_response_rejects_missing_key,
    test_parse_concepts_response_no_parent_concept_id_fabricated,
    test_loads_json_loose_recovers_prose_before_object,
    test_loads_json_loose_recovers_trailing_note,
    test_loads_json_loose_brace_inside_string_value_not_miscounted,
    test_split_into_sections_handles_short_and_long_text,
    test_parse_diagnostic_response_happy_path,
    test_parse_diagnostic_response_drops_invalid_concept_id,
    test_parse_diagnostic_response_truncates_to_n,
    test_parse_diagnostic_response_defaults_bad_answer_letter,
    test_parse_diagnostic_response_rejects_all_invalid,
    test_parse_plan_response_happy_path,
    test_parse_plan_response_drops_invalid_concept_and_empty_description,
    test_parse_plan_response_coerces_bad_minutes_to_zero,
    test_parse_plan_response_rejects_all_invalid,
    test_mock_decide_replan_dates_are_relative_and_valid_today,
    test_mock_plan_dates_valid_for_more_than_nine_concepts,
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
