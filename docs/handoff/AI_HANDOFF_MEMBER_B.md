# AI Handoff Prompt — Member B (Frontend + Product)

Copy the block below into a fresh AI coding session as your first message.

---

You are assisting **Member B** of TraceLearn — a Material-Grounded Personal Learning
Path Agent. Member B owns the Vue 3 frontend and the product experience. The product's
value is the **trace** ("why did my plan change?"); the tool-trace viewer and the
version diff page are the most important demo screens.

**Read these files first, in order, before writing any code:**
1. `01_SHARED_CONTEXT.md` — product foundation and glossary
2. `03_FRONTEND_PRODUCT_CONTEXT.md` — frontend + product contract (screens, flow)
3. `06_DECISION_REGISTER.md` — locked decisions and rejected ideas
4. `app/backend/schemas.py` — the API contract (READ-ONLY; do not modify)
5. `mock_api_examples/` — concrete JSON for PlanVersion, AgentDecision, ToolTrace, Concept

**Do NOT change:**
- Frozen product decisions, architecture, or scope.
- Backend contracts. Consume `schemas.py` as given; if a field is missing, ask Member A rather than inventing one.
- The language approach: build **no i18n framework**. UI chrome is monolingual (Decision D19). One control on Screen 1 sets `explanation_language`; render whatever language the API returns.

**Do NOT add** unnecessary pages. There are five screens; polish the diff view and the tool-trace viewer above all else.

**Responsibilities:** Vue 3 + ECharts app; onboarding (Option C hybrid); roadmap + task interface; the version diff view; the tool-trace viewer.

**First tasks (no backend dependency — start immediately against mocks):**
1. Scaffold Vue 3 (Vite) + ECharts; run at `localhost:5173`.
2. Build an API client mapped 1:1 to the endpoints in `app/frontend/README_FRONTEND.md`.
3. Wire the `mock_api_examples/*.json` as fixed responses.
4. Build screens in order: onboarding → tasks/roadmap → version history + diff + tool-trace viewer → dashboard.

**Rendering rules:** render `tool_trace[]` items (`tool`, `args`, `result_summary`) in order; tool names/args are English (machine layer), `reasoning_text` is in the returned language (human-facing layer); concept tags always show the `canonical_term` verbatim. Render `no_change` decisions correctly too.

**Success criteria:** onboarding runs end-to-end incl. no-material fallback; the diff clearly shows what changed grouped by concept; the tool-trace viewer makes "read → reason → act → record" obvious to a non-technical viewer.

Build mock-first so you never wait on the backend. Ask before assuming any contract field.
