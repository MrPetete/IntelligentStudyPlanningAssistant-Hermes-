# TraceLearn — Phase 0 Code Seed

Material-Grounded Personal Learning Path Agent. This is the **engineering skeleton**
for parallel development, not a finished product. It prioritizes **stable interfaces,
clear contracts, and mock-first development** over feature completeness.

> Read the frozen foundation in the parent package first:
> `01_SHARED_CONTEXT.md` … `06_DECISION_REGISTER.md`.

---

## What this seed gives you

- A running FastAPI backend with **all endpoints wired** (mostly stubs returning valid shapes).
- The **frozen SQLite schema** (SQLModel) for all 8 tables.
- The **API contracts** (Pydantic) — the parallelization contract for the team.
- The **agent layer**: 7 tool interfaces, deterministic triggers (real), plan validator (real), a deterministic orchestrator (real), and an LLM wrapper with **MOCK mode**.
- A **seed + simulate** path that produces the full demo loop end-to-end with no live LLM.

---

## How to run

```bash
cd app/backend
python -m venv .venv && . .venv/Scripts/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1) start the API
uvicorn main:app --reload
#    docs: http://127.0.0.1:8000/docs   health: http://127.0.0.1:8000/health

# 2) in another shell: seed the demo scenario, then simulate a failure
python -m seed.seed              # creates goal + concepts + Roadmap V1 (EN)
python -m seed.simulate 1        # inject normalization failure -> Agent makes V2
```

`MOCK_LLM = True` in `config.py` means **no API keys or network are needed**. Flip it
to `False` only when a real Hermes endpoint is wired (later phase).

---

## Architecture (what each file does)

```
app/backend/
  main.py            FastAPI app, CORS, DB startup, router registration, /health
  config.py          SINGLE SOURCE OF TRUTH: DB url, MOCK_LLM, triggers, language, retries
  db.py              SQLite engine, create_all(), session dependency
  models.py          FROZEN schema: users, goals, documents, concepts, diagnostics,
                     plan_versions, tasks, evidence, agent_decisions
  schemas.py         API contracts (Pydantic). The 3 key shapes: PlanVersionOut,
                     AgentDecisionOut (+ToolCall), ConceptOut
  routers/
    goals.py         goal create/get (REAL), language patch, document upload (PLACEHOLDER)
    concepts.py      extract (MOCK LLM), confirm (REAL, human-in-the-loop)
    diagnostic.py    generate (MOCK LLM), submit -> per-concept scores + evidence
    plan.py          generate V1 (MOCK+validator), current, versions, single, diff
    evidence.py      task complete, generic evidence, replan, SIMULATE (demo control)
    decisions.py     list + full decision incl. tool trace (defence artifact)
  agent/
    tools.py         the 7 tools (5 read, 2 write). Small guarded write surface
    triggers.py      REAL deterministic trigger layer (config-driven, pure, testable)
    validator.py     REAL plan validator (5 rejection rules, pure, testable)
    orchestrator.py  REAL deterministic loop + single LLM decision point
    llm_client.py    single Hermes wrapper; MOCK mode returns canned JSON
  seed/
    sample_db_course.txt   stand-in material
    seed.py                goal + confirmed concepts + Roadmap V1
    simulate.py            inject failure -> trigger -> agent -> V2 (no HTTP needed)
app/frontend/
  README_FRONTEND.md       Vue scaffold notes + endpoint list (Member B)
```

### The agent workflow (frozen)

```
trigger (deterministic)
  -> read tools: get_learner_state, get_progress_summary, get_evidence_since_last_plan, get_current_plan
  -> LLM decision point (change / no_change + reasoning + proposed plan)
  -> validator (bounded retries; else fall back to no_change, recorded)
  -> create_plan_version        [write tool, append-only]
  -> record_agent_decision      [write tool, ALWAYS — incl. no_change]
```

Every tool call is appended to the **tool trace**, stored on the decision, and
served by `GET /goals/{id}/decisions/{id}` for the trace viewer.

---

## What is implemented vs stubbed vs future

### Implemented (real logic)
- Goal creation, language setting, concept confirmation (human-in-the-loop).
- Deterministic **trigger layer** and plan **validator** (both pure + unit-testable).
- Deterministic **orchestrator** with the single LLM decision point.
- The 7 **tools** (real DB reads/writes; `search_learning_material` intentionally returns `available:false`).
- Append-only **versioning**, **decision logging** (incl. `no_change`), **diff**.
- **Seed + simulate** producing the full demo loop under MOCK_LLM.

### Stubbed / placeholder (shape is real, logic deferred)
- **Document upload** records a file but does no extraction.
- **Concept extraction / diagnostic / plan generation** call the LLM wrapper, which
  returns **canned JSON** (MOCK). Swap to real Hermes by implementing the `_real_*`
  functions in `llm_client.py` and setting `MOCK_LLM = False`.
- **Mastery model** is a simple, documented heuristic in `tools._mastery_by_concept`.

### Deliberately NOT built (see 06_DECISION_REGISTER.md)
- Full RAG / vector search, OCR, multiple documents, authentication, calendar,
  mobile, full UI i18n, multi-agent, production deployment.

---

## Team parallelization (why the seed exists)

- **Member A (Agent/Backend):** harden `orchestrator`, `validator`, `triggers`,
  versioning; wire real Hermes in `llm_client._real_*`.
- **Member B (Frontend):** build against `schemas.py` shapes + mocks immediately;
  focus on the diff + tool-trace viewer.
- **Member C (Data/Material/Test):** real extraction + the three generation prompts;
  own `seed/` + the rehearsed demo + recorded fallback; unit-test `triggers`/`validator`.

Freeze the three key JSON shapes (`PlanVersionOut`, `AgentDecisionOut`, `ConceptOut`)
in hour one — they are the entire contract that lets the three of you work in parallel.

---

## Notes / caveats

- **No authentication** by design (MVP): a single user is auto-created (`SINGLE_USER_ID`).
- **SQLite file** `tracelearn.db` is created on first run in `app/backend/`. Delete it to reset.
- Timestamps are ISO-8601 UTC strings; `plan_versions` is append-only — never mutate.
- The machine layer (tool names/args, `canonical_term`, identifiers) stays English;
  only human-facing text (`explanation`, `reasoning_text`, task/diagnostic text) is localized.

