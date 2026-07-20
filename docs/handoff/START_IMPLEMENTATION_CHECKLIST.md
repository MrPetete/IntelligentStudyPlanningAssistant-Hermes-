# TraceLearn — Start Implementation Checklist

The 48-hour MVP sprint. Work top to bottom. Do not start "First 2 hours" until the
"Before coding" gate is green.

---

## Before coding (setup gate)

- [ ] **Foundation package shared** — all members have `00`–`06` docs + the HTML roadmap.
- [ ] **Role packages distributed** — A, B, C each have their ZIP and their `MEMBER_*_START.md`.
- [ ] **Git repository initialized** — `git init` at `app/`, seed committed, `.gitignore` for `.venv/`, `node_modules/`, `tracelearn.db`, `__pycache__/`.
- [ ] **Python environment ready** — Python 3.11+, `pip install -r app/backend/requirements.txt` succeeds (needs network for PyPI).
- [ ] **Node environment ready** — Node 18+, `npm` available for the Vue scaffold.
- [ ] **Phase 0 code seed tested** — `uvicorn main:app --reload` serves `/health` and `/docs`.
- [ ] **Seed → simulate loop works** — `python -m seed.seed` then `python -m seed.simulate 1` produces a Version 2 plan **and** an `agent_decision` with an ordered tool trace. *(This is the one path unverified offline — verify it first.)*

---

## First 2 hours (parallel — nobody waits)

### Member A (backend / agent lead)
- [ ] Verify backend runtime (the seed → simulate loop above).
- [ ] Fix any SQLModel session/query wiring if the loop fails.
- [ ] **Freeze the 3 contracts** (`PlanVersionOut`, `AgentDecisionOut`+`ToolCall`, `ConceptOut`) and publish to B and C.
- [ ] Confirm `MOCK_LLM = True` fallback works; plan the real-Hermes wiring order.

### Member B (frontend / product)
- [ ] Scaffold Vue 3 (Vite) + ECharts; run at `localhost:5173`.
- [ ] Build the API client from `app/frontend/README_FRONTEND.md`.
- [ ] Wire `mock_api_examples/*.json` as fixed responses; render a first pass of the tool-trace + diff screens against them.

### Member C (data / material / testing)
- [ ] Write unit tests for `triggers.py` and `validator.py` (pure — no DB/LLM).
- [ ] Draft the three generation prompts against `MOCK_LLM`, matching the mock shapes.
- [ ] Prepare/confirm the sample material and the normalization-failure demo scenario.

---

## Shared decisions to record in hour 1 (log in `06_DECISION_REGISTER.md`)

- [ ] Frontend framework confirmed (Vue 3).
- [ ] UI-chrome language chosen (monolingual per D19).
- [ ] Final trigger threshold values (or keep config defaults for now).

---

## Integration order (after hour 2)

1. Concepts (real extraction) → 2. Diagnostic → 3. Roadmap V1 → 4. **The agent loop** (simulate → decision → V2) → 5. Diff + trace against real decision JSON → 6. Dashboard → 7. Seed hardening + recorded fallback → 8. Rehearse twice.

If behind: apply the failure plan in the HTML roadmap (−25% / −50% / irreducible floor). Cut from the front of the pipeline (seed the generation steps); protect the evidence → decision → version → explanation → trace tail.
