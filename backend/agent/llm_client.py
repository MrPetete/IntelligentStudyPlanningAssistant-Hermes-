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

import time
from datetime import date, timedelta
from typing import Any, Callable

from config import (
    LLM_MAX_RETRIES,
    MOCK_LLM,
    MODEL_GENERATION,
    MODEL_PLAN,
    MODEL_REPLAN,
)
from logging_config import get_logger

_log = get_logger("llm")


class LLMUnavailableError(RuntimeError):
    """Raised when a `_real_*` call exhausts its bounded retries (transport
    failure, empty response, or unparseable JSON every attempt). Callers
    handle it: onboarding surfaces a retryable error; the replan orchestrator
    falls back to a recorded `no_change`. This is the ONE error type the rest
    of the app catches from this module — `HermesError` and parser
    `ValueError` are internal to the retry loop below (A3)."""


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
                "day": (date.today() + timedelta(days=i - 1)).isoformat(),
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
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    plan = {
        "tasks": [
            {
                "concept_id": None,  # orchestrator resolves canonical_term -> concept_id
                "canonical_term": "Normalization",
                "day": today,
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
                "day": tomorrow,
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
# REAL implementations — live LMU (Anthropic Messages) calls.
#
# A2 wires each seam: build prompts (already drafted) -> hermes_client.complete
# -> feed raw text into the matching real parser -> return the exact _mock_*
# shape. A3 wraps the network+parse in `_complete_and_parse` so a transient
# transport hiccup or a one-off malformed response is retried (bounded) before
# giving up with LLMUnavailableError.
# ---------------------------------------------------------------------------
_RETRY_BACKOFF_SECONDS = 0.5  # short, linear backoff between bounded retries


def _complete_and_parse(
    *,
    system_prompt: str,
    user_prompt: str,
    parse: Callable[[str], Any],
    model: str | None = None,
    what: str,
) -> Any:
    """Call the live model and parse its response, with bounded retries.

    Retries on BOTH transport failure (`HermesError`) and a structurally
    broken response (the parser's `ValueError`) — a live model occasionally
    returns prose or truncated JSON, and a fresh attempt usually fixes it.
    Retries are capped at `LLM_MAX_RETRIES` (config, default 2). On final
    failure raises `LLMUnavailableError` for the caller to handle.

    Imported here (not at module top) so mock-mode never imports httpx and
    tests that monkeypatch `hermes_client.complete` patch the same object we call.
    """
    from agent.hermes_client import HermesError, complete

    # Operational logging only: task name, model id, attempt, duration, outcome.
    # We NEVER log system_prompt / user_prompt / raw response — those carry the
    # user's goal text, document content, and the model's reasoning.
    last_error: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        start = time.perf_counter()
        try:
            raw = complete(system=system_prompt, user=user_prompt, json_mode=True, model=model)
            result = parse(raw)
            elapsed_ms = (time.perf_counter() - start) * 1000
            _log.info("%s ok (model=%s, attempt=%d/%d, %.0fms)",
                      what, model or "default", attempt + 1, LLM_MAX_RETRIES + 1, elapsed_ms)
            return result
        except (HermesError, ValueError) as exc:
            last_error = exc
            elapsed_ms = (time.perf_counter() - start) * 1000
            _log.warning("%s attempt %d/%d failed (model=%s, %.0fms): %s: %s",
                         what, attempt + 1, LLM_MAX_RETRIES + 1, model or "default",
                         elapsed_ms, type(exc).__name__, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
    _log.error("%s UNAVAILABLE after %d attempts (model=%s): %s",
               what, LLM_MAX_RETRIES + 1, model or "default", last_error)
    raise LLMUnavailableError(
        f"{what} failed after {LLM_MAX_RETRIES + 1} attempts: {last_error}"
    ) from last_error


def _real_decide_replan(
    *,
    learner_state: dict[str, Any],
    progress: dict[str, Any],
    evidence: list[dict[str, Any]],
    current_plan: dict[str, Any],
    explanation_language: str,
) -> dict[str, Any]:
    system_prompt = _decide_replan_system_prompt(explanation_language)
    user_prompt = _decide_replan_user_prompt(learner_state, progress, evidence, current_plan)
    # decide_replan is the one call that truly reasons over evidence -> strongest model.
    return _complete_and_parse(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        parse=_parse_decide_replan_response,
        model=MODEL_REPLAN,
        what="decide_replan",
    )


# ---------------------------------------------------------------------------
# 4. Replan decision (Member A's own prompt + parser — the tool-calling point)
# ---------------------------------------------------------------------------
def _decide_replan_system_prompt(lang: str) -> str:
    return (
        "You are a learning-path planning assistant. You revise a student's "
        "study roadmap based on EVIDENCE of how their learning is going, "
        "grounded in their confirmed concept map. A deterministic trigger has "
        "already decided this is worth reviewing — your job is to judge whether "
        "the plan should change, and if so, propose the delta.\n\n"
        "Reason internally in English. Reference concepts by their "
        "`canonical_term` (preserved verbatim, e.g. \"Normalization\"), and "
        "cite the SPECIFIC evidence (low quiz score, skipped/overdue tasks) that "
        "drives your decision. Do not claim certainty about the learner's true "
        "ability — mastery values are heuristic signals.\n\n"
        "Rules:\n"
        "- Decide `\"no_change\"` if the evidence does not justify altering the "
        "plan (a valid, valuable outcome), or `\"new_version\"` if it does.\n"
        "- On `\"new_version\"`, propose ONLY the DELTA tasks to add (remediation "
        "/ reordering) — not the whole plan. The system merges your delta onto "
        "the current plan and a deterministic validator enforces schedule/"
        "deadline/concept rules, so keep tasks realistic.\n"
        "- Every delta task must name a `canonical_term` from the learner's "
        "confirmed concepts. `day` is an ISO date (YYYY-MM-DD) on or after today.\n"
        f"- Write `reasoning_text` in {_lang_name(lang)} — concise and honest, so "
        "a student reading \"why did my plan change?\" understands it. Keep "
        "canonical terms verbatim inside that text.\n"
        "- Output ONLY a JSON object, no prose, no markdown fences, matching:\n"
        "  {\"decision\": \"new_version\"|\"no_change\", \"reasoning_text\": str, "
        "\"plan\": {\"tasks\": [{\"canonical_term\": str, \"day\": \"YYYY-MM-DD\", "
        "\"description\": str, \"est_minutes\": int}]} | null}\n"
        "  On \"no_change\", set \"plan\" to null."
    )


def _decide_replan_user_prompt(
    learner_state: dict[str, Any],
    progress: dict[str, Any],
    evidence: list[dict[str, Any]],
    current_plan: dict[str, Any],
) -> str:
    import json

    concepts = learner_state.get("concepts", [])
    concept_lines = "\n".join(
        f"- {c.get('canonical_term')}: mastery="
        f"{c.get('mastery', 'unknown')}, confirmed={c.get('confirmed')}"
        for c in concepts
    ) or "(no concepts on record)"

    current_tasks = current_plan.get("tasks", [])
    plan_lines = "\n".join(
        f"- {t.get('canonical_term') or ('concept_id=' + str(t.get('concept_id')))}"
        f" on {t.get('day')}: {t.get('description', '')} [{t.get('status', 'pending')}]"
        for t in current_tasks
    ) or "(current plan has no tasks)"

    return (
        f"Today's date is {date.today().isoformat()}. Any delta task's `day` must "
        "be on or after today's date and use the correct current year — do not "
        "date tasks in a past year.\n"
        f"Goal: {learner_state.get('goal_text')}\n"
        f"Deadline: {learner_state.get('deadline')} "
        f"({learner_state.get('days_remaining')} days remaining)\n"
        f"Weekly hours available: {learner_state.get('weekly_hours')}\n\n"
        f"Concept mastery signals:\n{concept_lines}\n\n"
        f"Progress summary:\n{json.dumps(progress, ensure_ascii=False)}\n\n"
        f"Current plan (version {current_plan.get('version_no')}):\n{plan_lines}\n\n"
        f"Evidence since the last plan ({len(evidence)} events):\n"
        f"{json.dumps(evidence, ensure_ascii=False)}\n\n"
        "Decide whether to replan. If yes, propose the delta tasks."
    )


def _parse_decide_replan_response(raw: str) -> dict[str, Any]:
    """Parse + validate a model response into the exact `_mock_decide_replan`
    shape: {"decision", "reasoning_text", "plan": {...}|None}.

    Structural sanity only — the orchestrator resolves canonical_term ->
    concept_id, dedupes the delta, and the validator enforces the 5 plan rules.
    A decision the model can't express cleanly is rejected with ValueError so
    the retry loop can re-ask; a bad-but-parseable decision degrades to
    no_change rather than corrupting the plan."""
    data = _loads_json_loose(raw)
    if not isinstance(data, dict):
        raise ValueError("decide_replan response is not a JSON object")

    decision = (data.get("decision") or "").strip()
    reasoning = (data.get("reasoning_text") or "").strip()
    if decision not in ("new_version", "no_change"):
        raise ValueError(f"decide_replan: invalid decision {decision!r}")
    if not reasoning:
        raise ValueError("decide_replan: missing reasoning_text")

    if decision == "no_change":
        return {"decision": "no_change", "reasoning_text": reasoning, "plan": None}

    raw_plan = data.get("plan") or {}
    raw_tasks = raw_plan.get("tasks") if isinstance(raw_plan, dict) else None
    if not isinstance(raw_tasks, list) or not raw_tasks:
        # new_version with no usable delta -> honestly a no_change (the
        # orchestrator would dedupe it to nothing anyway).
        return {"decision": "no_change", "reasoning_text": reasoning, "plan": None}

    tasks: list[dict[str, Any]] = []
    for item in raw_tasks:
        term = (item.get("canonical_term") or "").strip()
        description = (item.get("description") or "").strip()
        if not term or not description:
            continue  # a delta task the orchestrator can't ground is useless
        try:
            est_minutes = int(item.get("est_minutes") or 0)
        except (TypeError, ValueError):
            est_minutes = 0
        tasks.append({
            "concept_id": None,  # orchestrator resolves canonical_term -> concept_id
            "canonical_term": term,
            "day": (item.get("day") or "")[:10],
            "description": description,
            "est_minutes": max(est_minutes, 0),
        })
    if not tasks:
        return {"decision": "no_change", "reasoning_text": reasoning, "plan": None}
    return {"decision": "new_version", "reasoning_text": reasoning, "plan": {"tasks": tasks}}


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
            # parent linking deferred — see V1_AUDIT_FIXES_MEMBER_C.md C-FIX-3
            # (models.Concept.parent_concept_id is an int FK; the model only
            # gives us a name string here, so we don't fabricate a mismatched
            # field until the real path resolves name -> parent_concept_id).
            "source": "material",
        })
    if not out:
        raise ValueError("no usable concepts (all missing canonical_term)")
    return out


def _real_extract_concepts(material_text: str, lang: str) -> list[dict[str, Any]]:
    system_prompt = _extract_concepts_system_prompt(lang)
    user_prompt = _extract_concepts_user_prompt(material_text)
    # Mechanical generation -> cheap/fast model (MODEL_GENERATION).
    return _complete_and_parse(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        parse=_parse_concepts_response,
        model=MODEL_GENERATION,
        what="extract_concepts",
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


def _real_generate_diagnostic(concepts, n, lang):
    system_prompt = _diagnostic_system_prompt(lang, n)
    user_prompt = _diagnostic_user_prompt(concepts, n)
    valid_ids = {c.get("id") for c in concepts}
    # Mechanical generation -> cheap/fast model (MODEL_GENERATION).
    return _complete_and_parse(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        parse=lambda raw: _parse_diagnostic_response(raw, valid_ids, n),
        model=MODEL_GENERATION,
        what="generate_diagnostic",
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
        f"Today's date is {date.today().isoformat()}. Every task's `day` must be "
        "on or after today's date and use the correct current year — do not date "
        "tasks in a past year.\n"
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


def _real_generate_plan(goal, concepts, scores, lang):
    system_prompt = _plan_system_prompt(lang)
    user_prompt = _plan_user_prompt(goal, concepts, scores)
    valid_ids = {c.get("id") for c in concepts}
    # Plan generation is balanced work -> MODEL_PLAN (default sonnet tier).
    return _complete_and_parse(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        parse=lambda raw: _parse_plan_response(raw, valid_ids),
        model=MODEL_PLAN,
        what="generate_plan",
    )


# ---------------------------------------------------------------------------
# shared parsing helper
# ---------------------------------------------------------------------------
def _loads_json_loose(raw: str) -> dict[str, Any]:
    """Strip markdown code fences a model might add, then json.loads.

    Defensive fallback: if the strict parse fails (e.g. the model prepended a
    sentence of prose before the JSON, or appended a trailing note), retry on
    the outermost brace-balanced ``{...}`` substring. This only runs after the
    strict parse has already raised, so a well-formed response is never altered
    — it just recovers the intermittent slop that would otherwise 502 the whole
    call after the retry budget is spent.
    """
    import json

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        obj = _extract_json_object(text)
        if obj is None:
            raise
        return json.loads(obj)


def _extract_json_object(text: str) -> str | None:
    """Return the first brace-balanced ``{...}`` object in ``text``, or None.

    Brace counting is string-literal aware so a ``{`` or ``}`` inside a quoted
    value doesn't throw off the balance.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
