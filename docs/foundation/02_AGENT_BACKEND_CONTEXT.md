# 02 — Agent + Backend Context (Member A)

**Owner:** Member A — AI Agent + Backend
**Prerequisite reading:** `01_SHARED_CONTEXT.md`, `06_DECISION_REGISTER.md`
**Use with an AI assistant:** paste `01_SHARED_CONTEXT.md` + this file as context before requesting code.

This file is the implementation contract for the backend and the Hermes Agent. It is deliberately concrete so an AI assistant produces code aligned with the frozen architecture.

---

## 1. Your responsibilities

- Hermes tool-calling Agent integration and the replanning loop.
- FastAPI backend and all REST endpoints.
- SQLite database schema and access.
- Implementation of the 7 tools (5 read, 2 write).
- Deterministic trigger layer and plan validators.
- Versioning + decision logging.

You do **not** own: document text extraction and concept-map generation prompts (Member C), UI (Member B). You expose the endpoints they consume.

---

## 2. Stack and conventions

- Python 3.11+, FastAPI, Uvicorn.
- SQLite via `sqlite3` or SQLModel/SQLAlchemy (team choice; keep it simple — SQLModel recommended for typed models).
- Pydantic models for all request/response bodies.
- LLM access through a single `llm_client` module so the model is swappable. Hermes is the tool-calling model.
- All timestamps stored as ISO-8601 UTC strings.
- All plan/concept payloads stored as JSON columns.
- One config file `config.py` (or `config.yaml`) holds all tunable thresholds. Nothing tunable is hardcoded in logic.

---

## 3. Database schema (frozen for MVP)

Concepts are the join key. `plan_versions` is append-only. Evidence is written by the app, read by the Agent.

```sql
-- A single user for the MVP is fine; keep the table for structure.
users(
  id INTEGER PRIMARY KEY,
  name TEXT
);

goals(
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  goal_text TEXT NOT NULL,
  deadline TEXT NOT NULL,             -- ISO date
  weekly_hours REAL NOT NULL,
  explanation_language TEXT NOT NULL DEFAULT 'en',  -- 'en' | 'zh' : human-facing output language
  created_at TEXT NOT NULL
);

documents(
  id INTEGER PRIMARY KEY,
  goal_id INTEGER REFERENCES goals(id),
  filename TEXT,
  storage_path TEXT,
  status TEXT NOT NULL,               -- 'uploaded' | 'processing' | 'ready' | 'failed' | 'none'
  created_at TEXT NOT NULL
);

-- CENTRAL ENTITY. One row per concept. This is the join key AND the language-neutral layer.
concepts(
  id INTEGER PRIMARY KEY,
  goal_id INTEGER REFERENCES goals(id),
  canonical_term TEXT NOT NULL,       -- technical term preserved verbatim, e.g. "Normalization". Grounding anchor. Never translated.
  name TEXT NOT NULL,                 -- display label (may equal canonical_term)
  explanation TEXT,                   -- localized explanation in the learner's explanation_language
  source TEXT NOT NULL,               -- 'material' | 'goal_topic' | 'user_added'
  order_index INTEGER,                -- suggested learning order
  parent_concept_id INTEGER,          -- optional shallow hierarchy
  confirmed INTEGER DEFAULT 0         -- 1 after user confirms/edits
);
-- Language note: canonical_term is the stable identifier used in reasoning and joins.
-- explanation is the ONLY language-varying field on a concept. There is NO per-language
-- translation table (see Decision Register D19) — one explanation, in the chosen language.

-- Optional retrieval store, only if Q&A / concept-explanation is built.
document_chunks(
  id INTEGER PRIMARY KEY,
  document_id INTEGER REFERENCES documents(id),
  idx INTEGER,
  text TEXT,
  embedding BLOB                      -- nullable; only if retrieval is enabled
);

diagnostics(
  id INTEGER PRIMARY KEY,
  goal_id INTEGER REFERENCES goals(id),
  questions_json TEXT NOT NULL,       -- [{id, concept_id, prompt, options, answer}]
  answers_json TEXT,                  -- user answers
  per_concept_score_json TEXT,        -- {concept_id: score 0..1}
  created_at TEXT NOT NULL
);

-- APPEND-ONLY. Never UPDATE a plan; always INSERT a new version.
plan_versions(
  id INTEGER PRIMARY KEY,
  goal_id INTEGER REFERENCES goals(id),
  version_no INTEGER NOT NULL,
  plan_json TEXT NOT NULL,            -- summary of the plan (days, concept coverage)
  created_by TEXT NOT NULL,           -- 'user' | 'agent'
  parent_version_id INTEGER,          -- previous version, for diffing
  created_at TEXT NOT NULL
);

tasks(
  id INTEGER PRIMARY KEY,
  plan_version_id INTEGER REFERENCES plan_versions(id),
  concept_id INTEGER REFERENCES concepts(id),
  day TEXT,                           -- ISO date the task is scheduled for
  description TEXT NOT NULL,
  est_minutes INTEGER,
  status TEXT NOT NULL,               -- 'pending' | 'done' | 'skipped'
  completed_at TEXT
);

-- Written by the APPLICATION when the user acts. Read by the Agent.
evidence(
  id INTEGER PRIMARY KEY,
  goal_id INTEGER REFERENCES goals(id),
  concept_id INTEGER,                 -- nullable
  type TEXT NOT NULL,                 -- 'task_done' | 'task_skipped' | 'quiz_result' | 'time_logged' | 'question'
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- The DEFENCE ARTIFACT. One row per replan reasoning event.
agent_decisions(
  id INTEGER PRIMARY KEY,
  goal_id INTEGER REFERENCES goals(id),
  trigger TEXT NOT NULL,              -- which deterministic trigger fired
  evidence_snapshot_json TEXT NOT NULL,
  reasoning_text TEXT NOT NULL,       -- the LLM justification
  tool_trace_json TEXT NOT NULL,      -- ordered [{tool, args, result_summary}]
  decision TEXT NOT NULL,             -- 'no_change' | 'new_version'
  resulting_plan_version_id INTEGER,  -- nullable if no_change
  created_at TEXT NOT NULL
);
```

**Key invariants:**
- Never mutate a `plan_versions` row or its `tasks`. Replanning = new version_no + new task rows + parent link.
- `tasks.concept_id` and `evidence.concept_id` connect to `concepts`. This is what makes the trace concept-grounded.
- `agent_decisions` is written on every Agent invocation, even when the decision is `no_change`. "Considered and left unchanged" is a valid, valuable trace.

---

## 4. The 7 tools (frozen)

Tools are plain Python functions registered to Hermes as callable tools. Each returns JSON. Keep read tools cheap and write tools guarded.

### Read tools (safe, callable freely)

**`get_learner_state(goal_id)`**
Returns the Learner State Model: goal_text, deadline, weekly_hours, days_remaining, and per-concept mastery signals (from diagnostic + evidence). This is the Agent's primary situational read.
```json
{
  "goal_text": "...", "deadline": "2026-08-10", "weekly_hours": 6,
  "days_remaining": 18,
  "explanation_language": "zh",
  "concepts": [
    {"concept_id": 3, "canonical_term": "Normalization", "mastery": 0.3, "confirmed": true}
  ]
}
```

**`get_current_plan(goal_id)`**
Returns the latest plan version: version_no, tasks with status, per-concept coverage.

**`get_progress_summary(goal_id)`**
Returns aggregate progress: tasks_total, tasks_done, tasks_overdue, percent_on_schedule, hours_logged_vs_expected.

**`get_evidence_since_last_plan(goal_id)`**
Returns evidence rows created after the current plan version's `created_at`. This is scoped exactly to "what changed since we last planned" — the natural input to a replan decision.

**`search_learning_material(goal_id, query, k=5)`**
Top-k retrieval over `document_chunks` for a concept/question. Returns up to `k` chunks. **Only implement if the retrieval store exists.** If not built, return an empty result with `"available": false`. Never dump more than `k` chunks.

### Write tools (few, guarded)

**`create_plan_version(goal_id, plan, rationale_summary)`**
Creates a NEW immutable plan version + its tasks, linked to the current version as parent.
- MUST pass the deterministic validator (Section 6) before persisting. If validation fails, the tool returns an error and no version is created; the Agent must revise and retry.
- `plan` references `concept_id`s. Tasks without a valid concept are rejected.

**`record_agent_decision(goal_id, trigger, evidence_snapshot, reasoning_text, tool_trace, decision, resulting_plan_version_id)`**
Writes the `agent_decisions` row. Called once at the end of every Agent invocation (including `no_change`).

### Tools deliberately NOT included
- No `record_task_progress` tool. **Task progress is written by the application when the user checks a task off, not by the Agent.** The Agent only *reads* evidence. This keeps the write surface at 2 tools and keeps the "Agent reads evidence, proposes plan changes" story clean. (See `06_DECISION_REGISTER.md`.)

---

## 5. Deterministic trigger layer

The Agent is NOT invoked on every event. Deterministic code decides when to wake it. Triggers live in `config.py`.

```python
TRIGGERS = {
    "behind_schedule_pct": 0.25,     # >25% of due tasks incomplete → consider replan
    "low_mastery_threshold": 0.4,    # concept mastery below this after evidence → consider replan
    "quiz_fail_threshold": 0.5,      # quiz score below this on a concept → consider replan
    "min_evidence_events": 3,        # don't replan on a single data point
    "explicit_user_request": True,   # user can always request a replan
}
```

Flow:
```
event arrives (task check-off, quiz result, time tick, user request)
  → app writes evidence row
  → evaluate_triggers(goal_id) using deterministic rules above
      → no trigger fired → stop (no Agent call)
      → trigger fired → invoke Agent (Section 7)
```

The trigger that fired is passed to the Agent and recorded in `agent_decisions.trigger`. This is how you show "the LLM does not run unbounded."

---

## 6. Deterministic plan validator

Every plan the Agent proposes via `create_plan_version` is validated by deterministic code BEFORE it is persisted. The LLM cannot bypass this.

Validator rejects a plan if any of:
- Total scheduled minutes per week exceed `weekly_hours` (with a small tolerance).
- Any task is scheduled after the deadline.
- Any task is scheduled in the past.
- A task references a non-existent or unconfirmed `concept_id`.
- The plan has zero tasks or drops all coverage of a concept that still has low mastery.

On rejection: return a structured error to the Agent describing what failed, so it can revise and retry (bounded retries, e.g. 2). If still failing, fall back to keeping the current version and record a `no_change` decision noting the validation failure.

---

## 7. The Agent replanning loop

```
invoke_agent(goal_id, trigger):
    tool_trace = []
    # Hermes runs a tool-calling loop. Typical (not hardcoded) sequence:
    #   get_learner_state → get_progress_summary → get_evidence_since_last_plan
    #   → (optionally search_learning_material) → decide
    # The model chooses tools and args itself; we record every call into tool_trace.

    decision = model_decides()   # 'no_change' or a proposed new plan

    if decision == new plan:
        validated = validator(proposed_plan)
        if validated ok:
            version = create_plan_version(...)   # write tool
        else:
            retry up to N; else fall back to no_change

    record_agent_decision(
        goal_id, trigger,
        evidence_snapshot, reasoning_text, tool_trace,
        decision, resulting_plan_version_id
    )
    return decision
```

**What the LLM decides:** whether a change is needed, what specifically to change, and the natural-language justification.
**What deterministic code controls:** when the loop starts, what a valid plan is, persistence/versioning, and guardrails.

**Every tool call is appended to `tool_trace`.** This trace is the single most important artifact for the defence and for the UI. Log tool name, arguments, and a short result summary in order.

---

## 8. System prompt guidance for the Agent

The Agent's system prompt should:
- State its role: a learning-path planning assistant that revises a roadmap based on evidence, grounded in the learner's confirmed concept map.
- Instruct it to gather state via read tools before deciding.
- Instruct it to reason over concepts by their **canonical term**, and to cite specific concepts and specific evidence in its justification.
- Instruct it that changes are proposed via `create_plan_version` and may be rejected by validation, in which case it revises.
- Forbid claims of certainty about the learner's true ability. Mastery values are heuristic signals.
- Require a concise, honest `reasoning_text` that a student could read and understand ("Why did my plan change?").

### 8a. Language layer split (frozen)

The Agent works across two layers with different language rules:

| Machine layer — ALWAYS English | Human-facing layer — in `explanation_language` |
|---|---|
| Internal reasoning / chain-of-thought | `reasoning_text` shown to the user |
| Tool names | Task descriptions it generates |
| Tool arguments | Any explanation text |
| Database identifiers, `canonical_term` | Diagnostic prompts it produces |

Rules for the system prompt:
- Reason internally in English and call tools with English names and English/identifier arguments. This keeps tool-calling reliable — **display language must never leak into tool arguments or concept identifiers.**
- Reference concepts by `canonical_term` (preserved, e.g. "Normalization") in reasoning and tool args.
- Emit user-facing output (`reasoning_text`, generated task descriptions) in the goal's `explanation_language`, preserving canonical terms verbatim inside that text.
- `explanation_language` is read from `get_learner_state` and passed into the Agent context.

Two languages only: `'en'` and `'zh'`. No source-document translation. (See D19.)

---

## 9. API contract (FastAPI endpoints)

Freeze these shapes with Member B on day 1. Members B and C build against these; stub them early.

```
POST /goals                     -> create goal {goal_text, deadline, weekly_hours, explanation_language}
GET  /goals/{id}                -> goal + status (incl. explanation_language)
PATCH /goals/{id}/language      -> set explanation_language ('en'|'zh')

POST /goals/{id}/document       -> upload PDF/TXT (multipart); kicks off async processing
GET  /goals/{id}/document       -> {status: uploaded|processing|ready|failed|none}

GET  /goals/{id}/concepts       -> concept map
PUT  /goals/{id}/concepts       -> user-confirmed/edited concept map (sets confirmed=1)

POST /goals/{id}/diagnostic     -> generate diagnostic (from confirmed concepts)
GET  /goals/{id}/diagnostic     -> questions
POST /goals/{id}/diagnostic/submit -> answers {answers} ; returns per-concept scores

POST /goals/{id}/plan/generate  -> generate roadmap Version 1
GET  /goals/{id}/plan/current   -> current plan version + tasks
GET  /goals/{id}/plan/versions  -> list of versions
GET  /goals/{id}/plan/versions/{v} -> a specific version
GET  /goals/{id}/plan/diff?from=&to= -> structured diff between two versions

POST /tasks/{id}/complete       -> mark task done (APP writes evidence, may fire trigger)
POST /goals/{id}/evidence       -> record generic evidence (quiz_result, time_logged, question)

POST /goals/{id}/replan         -> explicit user-requested replan (invokes Agent)
GET  /goals/{id}/decisions      -> list agent_decisions (trigger, reasoning, tool_trace, result)
GET  /goals/{id}/decisions/{id} -> full decision incl. tool_trace
```

**Endpoints that can fire the Agent trigger check:** `/tasks/{id}/complete`, `/goals/{id}/evidence`, `/goals/{id}/replan` (always fires).

---

## 10. Definition of done (backend)

- [ ] Schema created; append-only versioning enforced in code.
- [ ] All 7 tools implemented; `search_learning_material` degrades gracefully if retrieval not built.
- [ ] Trigger layer reads thresholds from config; unit-tested with fake evidence.
- [ ] Validator rejects the 5 invalid-plan cases; unit-tested.
- [ ] Full loop works: seed evidence → trigger fires → Agent reads state → proposes plan → validated → new version + decision recorded.
- [ ] `no_change` path also records a decision.
- [ ] `GET /decisions/{id}` returns a complete, human-readable tool trace + reasoning.
- [ ] A "simulate / fast-forward" seeding endpoint or script exists for the demo (coordinate with Member C).
- [ ] `explanation_language` flows from goal → `get_learner_state` → Agent; `reasoning_text` and generated task text come back in that language with canonical terms preserved; tool names/args stay English.

