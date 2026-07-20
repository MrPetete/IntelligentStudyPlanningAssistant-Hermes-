"""
TraceLearn — single LLM wrapper (Hermes tool-calling), with a MOCK mode.

Why a single wrapper: the model is swappable, and MOCK_LLM lets all three team
members work WITHOUT live API keys until integration. Flip config.MOCK_LLM to
False and implement `_real_*` once a Hermes endpoint is available.

Phase 0: only MOCK responses are implemented. The shapes returned here match
what the orchestrator and generation steps expect, so downstream code is real
even while the model is fake.
"""
from __future__ import annotations

from typing import Any

from config import MOCK_LLM


# ---------------------------------------------------------------------------
# Public interface — the rest of the app only calls these.
# ---------------------------------------------------------------------------
def decide_replan(
    *,
    learner_state: dict[str, Any],
    progress: dict[str, Any],
    evidence: list[dict[str, Any]],
    current_plan: dict[str, Any],
    explanation_language: str,
) -> dict[str, Any]:
    """
    The single LLM DECISION POINT of the agent loop.

    Returns:
      {
        "decision": "new_version" | "no_change",
        "reasoning_text": "<localized explanation>",
        "plan": {...} | None,      # proposed new plan when decision == new_version
      }

    In MOCK mode this returns a deterministic normalization-remediation decision,
    which is exactly the seeded demo scenario.
    """
    if MOCK_LLM:
        return _mock_decide_replan(evidence, explanation_language)
    return _real_decide_replan(
        learner_state=learner_state,
        progress=progress,
        evidence=evidence,
        current_plan=current_plan,
        explanation_language=explanation_language,
    )


def extract_concepts(*, material_text: str, explanation_language: str) -> list[dict[str, Any]]:
    """Concept-map extraction. MOCK returns the seeded databases concept map."""
    if MOCK_LLM:
        return _mock_concepts(explanation_language)
    return _real_extract_concepts(material_text, explanation_language)


def generate_diagnostic(
    *, concepts: list[dict[str, Any]], num_questions: int, explanation_language: str
) -> list[dict[str, Any]]:
    """Diagnostic generation. MOCK returns fixed concept-tagged MCQs."""
    if MOCK_LLM:
        return _mock_diagnostic(concepts, num_questions, explanation_language)
    return _real_generate_diagnostic(concepts, num_questions, explanation_language)


def generate_plan(
    *,
    goal: dict[str, Any],
    concepts: list[dict[str, Any]],
    scores: dict[int, float],
    explanation_language: str,
) -> dict[str, Any]:
    """Roadmap V1 generation. MOCK returns a small valid seeded plan."""
    if MOCK_LLM:
        return _mock_plan(concepts, explanation_language)
    return _real_generate_plan(goal, concepts, scores, explanation_language)


# ---------------------------------------------------------------------------
# MOCK implementations (Phase 0). Bilingual-aware where cheap.
# ---------------------------------------------------------------------------
def _t(lang: str, en: str, zh: str) -> str:
    return zh if lang == "zh" else en


def _mock_concepts(lang: str) -> list[dict[str, Any]]:
    base = [
        ("Normalization", "Database normalization", 1),
        ("Indexing", "Indexing", 2),
        ("Transactions", "Transactions & ACID", 3),
        ("Joins", "SQL Joins", 4),
        ("Query Optimization", "Query optimization", 5),
    ]
    out = []
    for term, name, order in base:
        out.append(
            {
                "canonical_term": term,
                "name": name,
                "explanation": _t(
                    lang,
                    f"Core concept: {name}.",
                    f"核心概念：{name}。",
                ),
                "order_index": order,
                "source": "material",
            }
        )
    return out


def _mock_diagnostic(concepts: list[dict[str, Any]], n: int, lang: str) -> list[dict[str, Any]]:
    qs = []
    for i, c in enumerate(concepts[:n], start=1):
        qs.append(
            {
                "id": i,
                "concept_id": c.get("id", i),
                "prompt": _t(
                    lang,
                    f"Which statement about {c['canonical_term']} is correct?",
                    f"关于 {c['canonical_term']} 的哪种说法是正确的？",
                ),
                "options": ["A", "B", "C", "D"],
                "answer": "A",  # server-side only
            }
        )
    return qs


def _mock_plan(concepts: list[dict[str, Any]], lang: str) -> dict[str, Any]:
    tasks = []
    for i, c in enumerate(concepts, start=1):
        tasks.append(
            {
                "concept_id": c.get("id", i),
                "day": f"2026-07-2{i}",
                "description": _t(
                    lang,
                    f"Study {c['canonical_term']} and do 3 practice questions.",
                    f"学习 {c['canonical_term']} 并完成 3 道练习题。",
                ),
                "est_minutes": 45,
            }
        )
    return {"tasks": tasks}


def _mock_decide_replan(evidence: list[dict[str, Any]], lang: str) -> dict[str, Any]:
    """Deterministic mock: insert normalization remediation, cite the evidence."""
    reasoning = _t(
        lang,
        "Your recent quiz on Normalization scored low and several Normalization "
        "tasks were left incomplete. I've added two remediation tasks for "
        "Normalization before moving on, because it underpins later topics.",
        "你最近关于 Normalization 的测验得分较低，且多个 Normalization 任务未完成。"
        "由于该概念是后续主题的基础，我在继续之前新增了两个 Normalization 巩固任务。",
    )
    plan = {
        "tasks": [
            {
                "concept_id": None,  # orchestrator resolves canonical_term -> concept_id
                "canonical_term": "Normalization",
                "day": "2026-07-21",
                "description": _t(
                    lang,
                    "Remediation: review 1NF-3NF with worked examples.",
                    "巩固：结合例题复习 1NF-3NF。",
                ),
                "est_minutes": 40,
            },
            {
                "concept_id": None,
                "canonical_term": "Normalization",
                "day": "2026-07-22",
                "description": _t(
                    lang,
                    "Remediation: decompose 5 relations to 3NF.",
                    "巩固：将 5 个关系分解到 3NF。",
                ),
                "est_minutes": 40,
            },
        ]
    }
    return {"decision": "new_version", "reasoning_text": reasoning, "plan": plan}


# ---------------------------------------------------------------------------
# REAL implementations — TODO (later phase, once Hermes endpoint is wired).
# Kept as explicit stubs so the swap point is obvious.
# ---------------------------------------------------------------------------
def _real_decide_replan(**kwargs: Any) -> dict[str, Any]:  # pragma: no cover
    raise NotImplementedError("Wire Hermes tool-calling here; set MOCK_LLM=False.")


def _real_extract_concepts(material_text: str, lang: str) -> list[dict[str, Any]]:  # pragma: no cover
    raise NotImplementedError("Wire Hermes concept extraction here.")


def _real_generate_diagnostic(concepts, n, lang):  # pragma: no cover
    raise NotImplementedError("Wire Hermes diagnostic generation here.")


def _real_generate_plan(goal, concepts, scores, lang):  # pragma: no cover
    raise NotImplementedError("Wire Hermes plan generation here.")
