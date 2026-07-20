# TraceLearn Frontend (Phase 0 — scaffold notes only)

Member B owns this. Phase 0 delivers a **scaffold + API client + mocks**, not
features. No i18n framework (Decision D19 — monolingual UI chrome).

## Scaffold

```bash
npm create vite@latest tracelearn -- --template vue
cd tracelearn
npm install
npm install echarts
npm run dev        # http://localhost:5173  (matches backend CORS_ORIGINS)
```

## Build order (see 03_FRONTEND_PRODUCT_CONTEXT.md)

1. `src/api.js` — one client mapped 1:1 to the backend contract (below).
2. Mock the responses first (copy shapes from `schemas.py`) so you are never
   blocked by the backend.
3. Onboarding screens 1–5.
4. Tasks + Roadmap + version selector.
5. **Version History + Diff view + Tool-Trace viewer** (the money shot — do not
   leave last).
6. Dashboard (ECharts).

## API endpoints to wrap (base: http://127.0.0.1:8000)

```
POST   /goals
GET    /goals/{id}
PATCH  /goals/{id}/language
POST   /goals/{id}/document
GET    /goals/{id}/document
POST   /goals/{id}/concepts:extract
GET    /goals/{id}/concepts
PUT    /goals/{id}/concepts
POST   /goals/{id}/diagnostic
POST   /goals/{id}/diagnostic/submit
POST   /goals/{id}/plan/generate
GET    /goals/{id}/plan/current
GET    /goals/{id}/plan/versions
GET    /goals/{id}/plan/versions/{version_no}
GET    /goals/{id}/plan/diff?from=1&to=2
POST   /tasks/{task_id}/complete
POST   /goals/{id}/evidence
POST   /goals/{id}/replan
POST   /goals/{id}/simulate         <-- demo control button
GET    /goals/{id}/decisions
GET    /goals/{id}/decisions/{decision_id}   <-- tool trace + reasoning
```

## The two shapes to build the trace UI against

- `AgentDecisionOut` — `{ trigger, evidence_snapshot, reasoning_text, tool_trace[], decision, resulting_plan_version_id }`
  - `tool_trace[]` items are `{ tool, args, result_summary }` — render in order.
- `PlanDiff` — `{ from_version, to_version, added_tasks[], removed_tasks[], concept_summary }`

Render `tool` names/args as-is (machine layer, English) and `reasoning_text` in
whatever language the backend returns (human-facing layer).
