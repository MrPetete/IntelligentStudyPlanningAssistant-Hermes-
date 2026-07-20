# 05 — Development Roadmap

**Prerequisite reading:** `01_SHARED_CONTEXT.md`

**Timeline (FROZEN): a 48-hour MVP implementation sprint.** Phase 0 (the code seed) is already delivered.
Hour bands below are guides, not gates — keep the phase structure and acceptance criteria. The single-page
hour-by-hour execution plan and failure plan live in `TraceLearn_Team_Roadmap.html` (Section 10). This file is
the detailed companion. There is no 2-week plan; anything longer is Future roadmap only (Phase 3, documented not built).

Roles: **A** = AI Agent + Backend · **B** = Frontend + Product · **C** = Data + Material + Testing.

---

## Guiding rules for the roadmap

1. A small complete loop beats a large broken system.
2. Freeze the API contract in sprint hour 1 so B and C are never blocked by A.
3. Build stubs/mocks first; integrate real logic behind them.
4. The trace viewer + version diff are NOT last-minute — they are the product.
5. Reserve buffer for "the LLM flakes on defence day."

---

## Phase 0 — Foundation (DELIVERED — code seed; sprint hours 0–2 to verify + freeze)

**Goal:** everyone can run the stack; all contracts frozen; nobody blocks anyone.

| Task | Owner | 
|---|---|
| Repo + FastAPI skeleton + SQLite schema | A |
| Freeze API contract JSON (Section 9 of file 02) with B & C | A + B + C |
| Frontend scaffold (Vue/React) + API client + mocks + empty screens | B |
| Document text extraction + concept-map pipeline skeleton | C |
| Pick frontend framework, embedding model (if any), config file layout | All |

**Deliverables:** running empty end-to-end app; frozen schema; frozen API contract; mock data flowing into the UI.

**Acceptance gate:** B can render all screens from mocks; A's endpoints return stubbed shapes matching the contract; C can extract text from the sample PDF.

**Risks:** API drift between A and B (mitigate: contract frozen + mocked in hour 1). Over-engineering the schema (mitigate: use the frozen schema in file 02, no additions).

---

## Phase 1 — MVP (the bulk, sprint hours 2–32)

**Goal:** the full core loop works on the happy path.

| Task | Owner |
|---|---|
| Implement 7 tools; trigger layer; validator; versioning; decision logging | A |
| Hermes tool-calling loop end-to-end | A |
| Onboarding Option C (screens 1-5) against real API + no-material fallback | B |
| Tasks, roadmap, version selector; version history + diff + tool-trace viewer | B |
| Concept-map generation (real); diagnostic generation; evidence shaping | C |
| Sample document + seeded goal + simulate script | C |

**Deliverables:** goal → material → concept map → confirm → diagnostic → roadmap V1 → evidence → agent decision → V2 → explanation → version history, working.

**Acceptance gate (the MVP definition of done):**
- [ ] Onboarding completes with and without material.
- [ ] Concept confirmation persists.
- [ ] Diagnostic produces per-concept scores.
- [ ] Roadmap V1 generated, concept-tagged tasks.
- [ ] Task check-off writes evidence.
- [ ] Simulated evidence fires a trigger → Agent runs → V2 created → decision + tool trace recorded.
- [ ] `no_change` path also records a decision.
- [ ] Tool-trace viewer + diff view render the change and its reason.

**Risks:** Agent loop consumes all time (mitigate: A ships a stub tool layer first so B/C aren't blocked; harden real loop after). Concept extraction quality (mitigate: one clean PDF, human confirmation step, fallback).

---

## Phase 2 — Polish (sprint hours 32–48)

**Goal:** demoable, defensible, stable.

| Task | Owner |
|---|---|
| Dashboard + concept-weakness visualization (ECharts); trace viewer polish | B |
| Prompt hardening; validator edge cases; config-driven thresholds | A |
| Test scenarios; robustness on bad/empty uploads; recorded fallback demo | C |
| Rehearse the demo script together | All |

**Deliverables:** rehearsed demo, edge cases handled, config exposed, dashboard live.

**Acceptance gate:** the full demo path runs smoothly twice in a row; a recorded/seeded fallback exists; empty/failure states handled.

**Risks:** live LLM flakiness on defence day (mitigate: seeded fallback path that does not depend on a live call). Scope creep into Should/Could items (mitigate: Decision Register + MoSCoW).

---

## Phase 3 — Future (document only, do NOT build)

Put these on a single "roadmap" slide. Building any of them in the internship window is out of scope by decision.

- Multiple documents / full semester knowledge library
- Better RAG (hybrid search, re-rankers, graph)
- OCR, PPT/DOCX processing
- Calendar integration
- Career skill roadmap
- Learning analytics at scale
- Mobile application
- Campus ecosystem integration
- Multi-agent system

---

## Milestone summary

| Milestone | When | Signal |
|---|---|---|
| M0 Foundation frozen | end of Phase 0 | contracts frozen, mocks flowing |
| M1 Loop closed | end of Phase 1 | simulate → V2 → trace + diff works |
| M2 Demo-ready | end of Phase 2 | rehearsed, stable, fallback ready |
| Defence | after M2 | show reasoning changing a plan in <5 min |

---

## Cross-cutting acceptance criteria (must all be true at M2)

1. The Agent visibly reads state → reasons → uses tools → changes state → records a decision.
2. Every plan change shows its evidence-linked explanation.
3. The concept map connects material → diagnostic → tasks → evidence → decisions (concept tags visible throughout).
4. The product works with and without uploaded material.
5. No claims of perfect assessment, human-level understanding, or autonomous intelligence anywhere in UI or slides.
6. A non-technical viewer can look at the tool-trace viewer and understand what the Agent did.
