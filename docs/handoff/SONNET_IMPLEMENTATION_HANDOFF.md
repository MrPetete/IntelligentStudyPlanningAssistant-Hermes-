# TraceLearn — Implementation Handoff (Claude Sonnet 5)

**You are a fresh Claude Sonnet 5 session with no prior conversation history.** This
document is self-contained. Read it fully before writing code. The architecture phase
is complete and **frozen** — your job is implementation, not redesign.

---

## 1. Project summary

**TraceLearn** is a Material-Grounded Personal Learning Path Agent (a university
internship project, optimized for a working demo and defence, not commercial launch).

**Core value:** TraceLearn transforms a learner's goal and learning materials into an
executable roadmap, then continuously improves that roadmap using real learning
evidence while explaining why every change happened.

**It IS:** a learning Agent that creates a grounded learning path and maintains an
**explainable trace** of how that path evolves.

**It is NOT:** a generic AI planner, a chatbot tutor, a translation tool, or a superapp.

**The differentiator — the product value is THE TRACE:**
```
Evidence → Agent decision → New version → Explanation → History
```
Do not describe the product as "adaptive learning" or "AI-generated study plan." The
distinguishing feature is that every plan change is traceable to specific evidence and
specific concepts, with a visible tool trace and written justification.

### The frozen core loop
```
User Goal
  ↓
Learning Material (optional but valuable)
  ↓
Concept Map
  ↓
Human confirmation
  ↓
Diagnostic
  ↓
Roadmap Version 1
  ↓
Learning Evidence
  ↓
Hermes Agent Decision
  ↓
New Plan Version
  ↓
Evidence-linked Explanation
  ↓
Version History + Tool Trace
```

---

## 2. Frozen architecture

| Layer | Choice |
|---|---|
| Frontend | Vue 3 + ECharts |
| Backend | Python + FastAPI |
| Database | SQLite + SQLModel |
| Agent | Hermes tool-calling Agent |

**Agent design: DETERMINISTIC ORCHESTRATION** — NOT free-form autonomous tool looping.
Code calls the read tools in a fixed order; the LLM owns a single decision point.
```
Trigger (deterministic)
  ↓
Read tools (fixed order)
  ↓
Hermes decision point (change / no_change + reasoning + proposed plan)
  ↓
Validator (deterministic; bounded retries; else fall back to no_change)
  ↓
create_plan_version   (write tool, append-only)
  ↓
record_agent_decision (write tool, ALWAYS — including no_change)
```

**The control split (this is the defence story — protect it):**
- Deterministic code controls: *when* the Agent runs (triggers), *what a valid plan is*
  (validator), and *storage/versioning*.
- The LLM decides: *whether* to change, *what* to change, and *why* (the reasoning text).
- One-liner: "The LLM never runs unbounded — deterministic triggers wake it and
  deterministic validators check it before anything is persisted."

---

## 3. Frozen decisions

### Tools — exactly 7 (5 read, 2 write)
Read: `get_learner_state`, `get_current_plan`, `get_progress_summary`,
`get_evidence_since_last_plan`, `search_learning_material`.
Write: `create_plan_version`, `record_agent_decision`.

- **No `record_task_progress` tool.** The *application* records evidence when the user
  acts; the Agent only *reads* evidence and decides. Keep the write surface at 2 tools.
- `search_learning_material` returns `{"available": false}` in the MVP (no RAG).
- `plan_versions` is **append-only**: replanning = new version_no + new task rows + parent
  link. Never mutate an existing version or its tasks.
- Every Agent invocation records a decision — including `no_change` ("considered, left
  unchanged" is a valuable trace).

### Material — grounding is core, but MVP scope is tight
Implement: one clean PDF/TXT, simple text extraction, one concept-map generation call.
Do NOT implement: full RAG, vector database, OCR, multiple documents, knowledge library.

The **concept map is the spine.** Concepts are the join key connecting:
```
Material → Diagnostic → Tasks → Evidence → Agent decisions
```
Each concept has a `canonical_term` (technical term, preserved verbatim — the anchor and
join key) and a localized `explanation` (the only language-varying field).

### Language — cross-language material grounding only (NOT UI translation)
Implement: `explanation_language` (on the goal; `'en'` | `'zh'`) and `canonical_term`.
- **Machine layer stays English:** tool names, IDs, arguments, DB identifiers, `canonical_term`.
- **Human layer may be localized:** explanations, notes, diagnostic questions, task descriptions, `reasoning_text`.
- Do NOT build: a full i18n framework, a translation database, or source-document
  translation (extract from the original; localize only the output). Two languages only.

---

## 4. Repository structure

The Phase 0 code seed already exists under `app/`:

```
app/
  README.md                    how to run, architecture, implemented vs future
  backend/
    main.py                    FastAPI app, CORS, DB startup, router registration, /health
    config.py                  SINGLE SOURCE OF TRUTH: DB url, MOCK_LLM, triggers, languages, retries
    db.py                      SQLite engine, create_all(), session dependency
    models.py                  FROZEN schema (8 tables) — see below
    schemas.py                 API contracts (Pydantic). Key shapes: PlanVersionOut, AgentDecisionOut(+ToolCall), ConceptOut
    requirements.txt           fastapi, uvicorn, sqlmodel, python-multipart
    routers/
      goals.py                 goal create/get (REAL), language patch, document upload (PLACEHOLDER)
      concepts.py              extract (MOCK LLM), confirm (REAL, human-in-the-loop)
      diagnostic.py            generate (MOCK LLM), submit -> per-concept scores + evidence
      plan.py                  generate V1 (MOCK+validator), current, versions, single, diff
      evidence.py              task complete, generic evidence, replan, SIMULATE (demo control)
      decisions.py             list + full decision incl. tool trace
    agent/
      tools.py                 the 7 tools (5 read, 2 write) — real DB reads/writes
      triggers.py              REAL deterministic trigger layer (pure, config-driven, tested)
      validator.py             REAL plan validator (5 rejection rules, pure, tested)
      orchestrator.py          REAL deterministic loop + single LLM decision point
      llm_client.py            single Hermes wrapper; MOCK_LLM returns canned bilingual JSON
    seed/
      sample_db_course.txt     stand-in material
      seed.py                  goal + confirmed concepts + Roadmap V1
      simulate.py              inject failure -> trigger -> agent -> V2 (no HTTP needed)
    tests/
      test_triggers_validator.py   passing starter unit tests (pure functions)
  frontend/
    README_FRONTEND.md         Vue scaffold notes + endpoint list (Member B)
```

### Frozen database schema (8 tables, SQLModel)
`users` (single hardcoded user, no auth), `goals` (+ `explanation_language`),
`documents` (single), `concepts` (`canonical_term` + localized `explanation` — the spine),
`diagnostics`, `plan_versions` (append-only, `parent_version_id`), `tasks`
(belong to one plan version), `evidence` (written by app, read by agent),
`agent_decisions` (trigger, evidence_snapshot, reasoning_text, `tool_trace_json`,
decision, resulting_plan_version_id — the defence artifact).

---

## 5. Current code seed status

**Implemented (real logic):** goal creation, language setting, concept confirmation,
the deterministic trigger layer, the plan validator, the deterministic orchestrator,
the 7 tools, append-only versioning, decision logging (incl. `no_change`), the diff,
and the seed + simulate path. Starter unit tests pass.

**Stubbed / placeholder (shape is real, logic deferred to real Hermes):** document
upload (records file, no extraction), concept extraction / diagnostic / plan generation
(call `llm_client`, which returns canned JSON under `MOCK_LLM = True`).

**Verified offline:** all files compile; triggers, validator, and the MOCK LLM
(including canonical-term stability across `en`/`zh`) work; the starter tests pass.

**NOT yet verified at runtime (do this first):** the DB-backed loop
(`seed.py` → `simulate.py` → endpoints). `sqlmodel` was not installable in the
authoring environment (no PyPI access), so the SQLModel session/query path is unexercised.
This is the single most important thing to verify before building on top.

---

## 6. First implementation tasks (in order)

1. **Verify the runtime loop** (Section 7). Fix any SQLModel session/query wiring until
   `seed.simulate 1` produces a Version 2 plan **and** an `agent_decision` with an ordered
   tool trace.
2. **Freeze the 3 contracts** in `schemas.py`: `PlanVersionOut`, `AgentDecisionOut` (+`ToolCall`),
   `ConceptOut`. Treat as stable; frontend and data build against them.
3. **Wire real Hermes one seam at a time** in `llm_client._real_*`: concepts → diagnostic →
   roadmap → decision. Keep `MOCK_LLM` working as the fallback for the recorded demo.
4. **Harden the agent loop:** validator retry/fallback, evidence scoping, versioning correctness.
5. **Support the demo:** ensure the normalization-failure simulate reliably yields a
   remediation V2 with a clear `reasoning_text`, and keep a recorded/seeded fallback.

Work in small, verifiable steps. After each change, run the seed/simulate loop to confirm
no regression.

---

## 7. Runtime verification steps

```bash
cd app/backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# 1) API up
uvicorn main:app --reload           # check http://127.0.0.1:8000/health and /docs

# 2) pure logic (no DB, no LLM) — should already pass
python tests/test_triggers_validator.py

# 3) the full loop (this is the unverified path)
python -m seed.seed                 # creates goal + concepts + Roadmap V1
python -m seed.simulate 1           # inject normalization failure -> Agent makes V2
```
Success = `simulate` prints a fired trigger and an agent result with a new `plan_version_id`,
and `GET /goals/1/decisions/{id}` returns a decision with a populated `tool_trace`.
`MOCK_LLM = True` means no API keys are needed for any of this.

---

## 8. What must NEVER be changed without discussion

Changing any of these requires team agreement **and** an update to `06_DECISION_REGISTER.md`:

1. The 7-tool set and the 2-write-tool limit (no `record_task_progress`).
2. Deterministic orchestration (never introduce free-form tool looping).
3. The append-only `plan_versions` invariant.
4. The DB schema in `models.py` and the frozen shapes in `schemas.py`.
5. The concept-map-as-spine design and `canonical_term` as the language-neutral join key.
6. The machine-layer-English / human-layer-localized split; no full i18n, no source translation.
7. The MVP scope fence: no RAG, OCR, multi-document, auth, calendar, mobile, multi-agent.
8. Recording a decision on every invocation (including `no_change`).

If in doubt, preserve the frozen design and ask. The goal is a working, defensible demo of
the trace — not a bigger system.

