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


#
# Member C (2026-07-21): the three prompts below are DRAFTED and their
# response parsers are REAL and unit-testable. What is NOT done — by design,
# per the V1 task list — is the network call itself: MOCK_LLM stays True, and
# `_real_*` still raises NotImplementedError so nobody accidentally flips the
# switch before a live Hermes endpoint exists. Wiring a real endpoint is a
# one-line change at the marked `# >>> WIRE HERE` spot in each function: call
# the client with (system_prompt, user_prompt), then feed the raw text into
# the matching `_parse_*_response` — the parser already produces the exact
# `_mock_*` shape, so the swap is drop-in.
#
_CONCEPT_MAP_MIN = 8
_CONCEPT_MAP_MAX = 25
_MAP_REDUCE_CHAR_THRESHOLD = 6000  # above this, summarize in sections first


def _lang_name(lang: str) -> str:
    return "Chinese (Simplified)" if lang == "zh" else "English"


# ---------------------------------------------------------------------------
# 1. Concept-map extraction
# ---------------------------------------------------------------------------
def _extract_concepts_system_prompt(lang: str) -> str:
    return (
        "You are an expert curriculum analyst. You read course material and "
        "produce a compact, teachable CONCEPT MAP that will drive a study "
        "planner. You do not plan study tasks yourself.\n\n"
        "Rules (do not break these):\n"
        "- NEVER translate the source material. Read it in its original "
        "language exactly as written.\n"
        f"- `canonical_term` must be the technical term PRESERVED VERBATIM in "
        "its original language from the source text (e.g. \"Normalization\"). "
        "It is a machine join key — never translate or paraphrase it.\n"
        f"- `explanation` is the only field that varies by language: write it "
        f"in {_lang_name(lang)}.\n"
        f"- Produce a TEACHABLE number of concepts: between {_CONCEPT_MAP_MIN} "
        f"and {_CONCEPT_MAP_MAX}. Not every sentence is a concept — merge "
        "minor sub-points into their parent concept.\n"
        "- If the material is long, you have been given section summaries "
        "instead of the raw text (map-reduce). Consolidate them into ONE "
        "concept list; do not just list each section's concepts separately.\n"
        "- `order_index` is a suggested learning sequence (1..N). "
        "`parent_concept` is an optional shallow grouping — no deep trees.\n"
        "- Output ONLY a JSON object, no prose, no markdown fences, matching:\n"
        "  {\"concepts\": [{\"canonical_term\": str, \"name\": str, "
        "\"explanation\": str, \"order_index\": int, "
        "\"parent_concept\": str | null}]}"
    )


def _extract_concepts_user_prompt(material_text: str) -> str:
    if len(material_text) > _MAP_REDUCE_CHAR_THRESHOLD:
        sections = _split_into_sections(material_text)
        body = "\n\n".join(
            f"[Section {i+1}/{len(sections)}]\n{s}" for i, s in enumerate(sections)
        )
        return (
            "The material below was long, so it is split into sections. "
            "Read all sections, then produce ONE consolidated concept map "
            "(do not treat each section independently):\n\n" + body
        )
    return f"Course material:\n\n{material_text}"


def _split_into_sections(text: str, target_chars: int = 4000) -> list[str]:
    """Cheap map-reduce split: paragraph-aware chunking to ~target_chars each."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    sections: list[str] = []
    current = ""
    for p in paragraphs:
        if current and len(current) + len(p) > target_chars:
            sections.append(current.strip())
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current.strip():
        sections.append(current.strip())
    return sections or [text]


def _parse_concepts_response(raw: str) -> list[dict[str, Any]]:
    """
    Parse + validate a model response into the exact `_mock_concepts` shape.
    Real, unit-tested (see tests/test_llm_client_parsing.py). Tolerant of
    minor model slop (markdown fences, missing order_index) but rejects a
    structurally broken response rather than silently guessing content.
    """
    data = _loads_json_loose(raw)
    items = data.get("concepts") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("concept extraction response missing a non-empty 'concepts' list")

    out: list[dict[str, Any]] = []
    for i, item in enumerate(items[:_CONCEPT_MAP_MAX], start=1):
        term = (item.get("canonical_term") or "").strip()
        if not term:
            continue  # a concept without a canonical_term is not usable as a join key
        out.append({
            "canonical_term": term,
            "name": (item.get("name") or term).strip(),
            "explanation": (item.get("explanation") or "").strip(),
            "order_index": int(item.get("order_index") or i),
            "parent_concept": item.get("parent_concept") or None,
            "source": "material",
        })
    if not out:
        raise ValueError("no usable concepts (all missing canonical_term)")
    return out


def _real_extract_concepts(material_text: str, lang: str) -> list[dict[str, Any]]:  # pragma: no cover
    system_prompt = _extract_concepts_system_prompt(lang)
    user_prompt = _extract_concepts_user_prompt(material_text)
    # >>> WIRE HERE: raw = hermes_client.complete(system=system_prompt, user=user_prompt, json_mode=True)
    # >>> then:      return _parse_concepts_response(raw)
    raise NotImplementedError(
        "Prompt drafted in _extract_concepts_system_prompt/_extract_concepts_user_prompt; "
        "parser ready in _parse_concepts_response. Wire the Hermes call here; "
        "set MOCK_LLM=False only once it is live."
    )


# ---------------------------------------------------------------------------
# 2. Diagnostic generation
# ---------------------------------------------------------------------------
def _diagnostic_system_prompt(lang: str, n: int) -> str:
    return (
        "You write a short diagnostic quiz from a CONFIRMED concept map for a "
        "study-planning agent. This is a heuristic signal, not a true ability "
        "measurement — word questions plainly, no trick questions.\n\n"
        "Rules:\n"
        f"- Produce exactly {n} multiple-choice questions (4 options each), "
        "covering the most important/foundational concepts first if you "
        "cannot cover all of them.\n"
        "- Every question must reference exactly one concept_id from the "
        "list you are given — never invent a concept.\n"
        f"- Write `prompt` and `options` in {_lang_name(lang)}. Keep any "
        "canonical_term mentioned inside a question verbatim, unstranslated.\n"
        "- `answer` is the correct option's letter (\"A\"-\"D\") and is used "
        "server-side only — it is never shown to the learner.\n"
        "- Output ONLY a JSON object, no prose, matching:\n"
        "  {\"questions\": [{\"concept_id\": int, \"prompt\": str, "
        "\"options\": [str, str, str, str], \"answer\": str}]}"
    )


def _diagnostic_user_prompt(concepts: list[dict[str, Any]], n: int) -> str:
    ordered = sorted(concepts, key=lambda c: c.get("order_index", 0))
    listing = "\n".join(
        f"- concept_id={c.get('id')}: {c.get('canonical_term')} — {c.get('explanation', '')}"
        for c in ordered
    )
    return f"Confirmed concepts (foundational first):\n{listing}\n\nWrite {n} questions."


def _parse_diagnostic_response(raw: str, valid_concept_ids: set[int], n: int) -> list[dict[str, Any]]:
    """Parse + validate into the exact `_mock_diagnostic` shape."""
    data = _loads_json_loose(raw)
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("diagnostic response missing a non-empty 'questions' list")

    out: list[dict[str, Any]] = []
    for item in items:
        cid = item.get("concept_id")
        options = item.get("options")
        prompt = (item.get("prompt") or "").strip()
        answer = (item.get("answer") or "").strip()
        if cid not in valid_concept_ids:
            continue  # never accept a question about a concept we didn't give it
        if not prompt or not isinstance(options, list) or len(options) < 2:
            continue
        if answer not in ("A", "B", "C", "D"):
            answer = "A"  # last-resort default; server never leaks this to the learner anyway
        out.append({
            "id": len(out) + 1,
            "concept_id": cid,
            "prompt": prompt,
            "options": list(options[:4]),
            "answer": answer,
        })
        if len(out) >= n:
            break
    if not out:
        raise ValueError("no usable questions (all referenced invalid concepts or malformed)")
    return out


def _real_generate_diagnostic(concepts, n, lang):  # pragma: no cover
    system_prompt = _diagnostic_system_prompt(lang, n)
    user_prompt = _diagnostic_user_prompt(concepts, n)
    valid_ids = {c.get("id") for c in concepts}
    # >>> WIRE HERE: raw = hermes_client.complete(system=system_prompt, user=user_prompt, json_mode=True)
    # >>> then:      return _parse_diagnostic_response(raw, valid_ids, n)
    raise NotImplementedError(
        "Prompt drafted in _diagnostic_system_prompt/_diagnostic_user_prompt; "
        "parser ready in _parse_diagnostic_response. Wire the Hermes call here; "
        "set MOCK_LLM=False only once it is live."
    )


# ---------------------------------------------------------------------------
# 3. Roadmap (plan) generation
# ---------------------------------------------------------------------------
def _plan_system_prompt(lang: str) -> str:
    return (
        "You generate a study ROADMAP (a list of dated tasks) from a "
        "confirmed concept map and diagnostic scores, for a real student "
        "against a real deadline. A deterministic validator will reject this "
        "plan if you break its rules, so follow them exactly:\n\n"
        "- Every task's concept_id MUST be one of the concept_id values you "
        "were given — never invent one.\n"
        "- Every task's day must be an ISO date (YYYY-MM-DD) on or after "
        "today and on or before the deadline you were given.\n"
        "- Total planned minutes across all tasks must fit inside the "
        "learner's weekly_hours budget for the number of weeks until the "
        "deadline (small overage tolerance exists, but do not rely on it).\n"
        "- Every concept must be covered by at least one task, and concepts "
        "with a LOW diagnostic score need more/earlier tasks than concepts "
        "with a high score.\n"
        f"- Write `description` in {_lang_name(lang)}. Keep canonical_term "
        "mentions verbatim, untranslated.\n"
        "- Output ONLY a JSON object, no prose, matching:\n"
        "  {\"tasks\": [{\"concept_id\": int, \"day\": \"YYYY-MM-DD\", "
        "\"description\": str, \"est_minutes\": int}]}"
    )


def _plan_user_prompt(
    goal: dict[str, Any], concepts: list[dict[str, Any]], scores: dict[int, float]
) -> str:
    ordered = sorted(concepts, key=lambda c: c.get("order_index", 0))
    listing = "\n".join(
        f"- concept_id={c.get('id')}: {c.get('canonical_term')} "
        f"(diagnostic score: {scores.get(c.get('id'), 'not yet taken')})"
        for c in ordered
    )
    return (
        f"Deadline: {goal.get('deadline')}\n"
        f"Weekly hours available: {goal.get('weekly_hours')}\n\n"
        f"Concepts:\n{listing}\n\n"
        "Produce the roadmap now."
    )


def _parse_plan_response(raw: str, valid_concept_ids: set[int]) -> dict[str, Any]:
    """Parse + validate into the exact `_mock_plan` shape (validator does the rest)."""
    data = _loads_json_loose(raw)
    items = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("plan response missing a non-empty 'tasks' list")

    tasks: list[dict[str, Any]] = []
    for item in items:
        cid = item.get("concept_id")
        day = (item.get("day") or "")[:10]
        description = (item.get("description") or "").strip()
        if cid not in valid_concept_ids or not description:
            continue
        try:
            est_minutes = int(item.get("est_minutes") or 0)
        except (TypeError, ValueError):
            est_minutes = 0
        tasks.append({
            "concept_id": cid,
            "day": day,
            "description": description,
            "est_minutes": max(est_minutes, 0),
        })
    if not tasks:
        raise ValueError("no usable tasks (all referenced invalid concepts or malformed)")
    return {"tasks": tasks}


def _real_generate_plan(goal, concepts, scores, lang):  # pragma: no cover
    system_prompt = _plan_system_prompt(lang)
    user_prompt = _plan_user_prompt(goal, concepts, scores)
    valid_ids = {c.get("id") for c in concepts}
    # >>> WIRE HERE: raw = hermes_client.complete(system=system_prompt, user=user_prompt, json_mode=True)
    # >>> then:      return _parse_plan_response(raw, valid_ids)
    raise NotImplementedError(
        "Prompt drafted in _plan_system_prompt/_plan_user_prompt; parser ready "
        "in _parse_plan_response. Wire the Hermes call here (note: the "
        "orchestrator/validator, not this function, enforces the 5 plan "
        "rules — this parser only guards structural sanity); set MOCK_LLM=False "
        "only once it is live."
    )


# ---------------------------------------------------------------------------
# shared parsing helper
# ---------------------------------------------------------------------------
def _loads_json_loose(raw: str) -> dict[str, Any]:
    """Strip markdown code fences a model might add, then json.loads."""
    import json

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
