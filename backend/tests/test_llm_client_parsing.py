"""
Tests for the response parsers backing the three real-generation prompts
(_real_extract_concepts, _real_generate_diagnostic, _real_generate_plan).

These parsers are the actual (non-mock) logic Member C owns; the network
call itself is intentionally not wired (MOCK_LLM stays True — see
llm_client.py). Each test feeds a hand-written string standing in for a raw
model response, including the kind of slop a real model tends to produce
(markdown fences, an invented concept_id, a missing field), and checks the
parser either normalizes it into the exact `_mock_*` shape or rejects it.
"""
from __future__ import annotations

import json

import pytest

from agent import llm_client as lc


# ---------------------------------------------------------------------------
# _loads_json_loose
# ---------------------------------------------------------------------------
def test_loads_json_loose_strips_markdown_fence():
    raw = '```json\n{"a": 1}\n```'
    assert lc._loads_json_loose(raw) == {"a": 1}


def test_loads_json_loose_plain_json():
    assert lc._loads_json_loose('{"a": 1}') == {"a": 1}


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
    with pytest.raises(ValueError):
        lc._parse_concepts_response(json.dumps({"concepts": []}))


def test_parse_concepts_response_rejects_missing_key():
    with pytest.raises(ValueError):
        lc._parse_concepts_response(json.dumps({"oops": []}))


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
    with pytest.raises(ValueError):
        lc._parse_diagnostic_response(raw, valid_concept_ids={1}, n=6)


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
    with pytest.raises(ValueError):
        lc._parse_plan_response(
            json.dumps({"tasks": [{"concept_id": 999, "day": "2026-08-01", "description": "x"}]}),
            valid_concept_ids={1},
        )
