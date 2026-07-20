# AI Handoff Prompt — Member A (AI Agent + Backend)

Copy the block below into a fresh AI coding session as your first message.

---

You are assisting **Member A** of TraceLearn — a Material-Grounded Personal Learning
Path Agent. Member A owns the Hermes Agent loop and the FastAPI backend, and is the
technical lead for the frozen contracts.

**Read these files first, in order, before writing any code:**
1. `01_SHARED_CONTEXT.md` — product foundation and glossary
2. `02_AGENT_BACKEND_CONTEXT.md` — backend + agent implementation contract
3. `06_DECISION_REGISTER.md` — locked decisions and rejected ideas
4. `app/backend/` — the Phase 0 code seed (esp. `agent/`, `models.py`, `schemas.py`, `routers/`, `seed/`)

**Do NOT change:**
- Frozen product decisions, architecture, or scope.
- The DB schema in `models.py` or the API shapes in `schemas.py` — unless the change is agreed by the team and logged in `06_DECISION_REGISTER.md`.
- The orchestration model: it is **deterministic orchestration** (code calls read tools in a fixed order; the LLM owns a single decision point). Never introduce free-form tool looping.
- The write surface: exactly 2 write tools (`create_plan_version`, `record_agent_decision`). Do not add write tools.

**Responsibilities:** Hermes integration (`llm_client._real_*`), the deterministic orchestrator, the trigger layer, the plan validator (5 rejection rules), append-only versioning, decision logging, and the API contracts.

**First tasks:**
1. Run and verify the seed → simulate loop; confirm a Version 2 plan and an `agent_decision` with an ordered tool trace are produced.
2. Fix any SQLModel session/query wiring if the DB-backed loop fails (this is the only path unverified offline).
3. Freeze the three key shapes (`PlanVersionOut`, `AgentDecisionOut`+`ToolCall`, `ConceptOut`) and treat them as stable.
4. Wire real Hermes one seam at a time (concepts → diagnostic → roadmap → decision), keeping `MOCK_LLM` as a working fallback.

**Success criteria:** the evidence → trigger → decision → new version → explanation loop runs end-to-end; every invocation records a decision including `no_change`; validation rejects impossible plans before persistence; the mock path still works for the recorded demo.

Work in small, verifiable steps. After each change, run the seed/simulate loop to confirm nothing regressed. Ask before altering any frozen contract.
