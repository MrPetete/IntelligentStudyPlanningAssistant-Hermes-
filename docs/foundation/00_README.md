# TraceLearn — Team Context Package

**Project:** TraceLearn
**Subtitle:** Material-Grounded Personal Learning Path Agent
**Status:** Foundation FROZEN (Phase 0 reference package)
**Package version:** 1.0

---

## What this package is

This folder is the single source of truth for the TraceLearn internship project. It exists so that:

1. All three team members share the same understanding of what we are building and why.
2. Each member can paste their role-specific file into an AI coding assistant as project context.
3. Nobody re-opens settled decisions mid-build. Scope is frozen.

If a question is answered in these files, the answer is final unless the whole team agrees to change it and updates `06_DECISION_REGISTER.md`.

---

## Files in this package

| File | Audience | Purpose |
|---|---|---|
| `00_README.md` | Everyone | This file. Explains the package and how to use it. |
| `01_SHARED_CONTEXT.md` | Everyone | The complete product foundation. Read this first. Identity, value, core loop, MVP scope, glossary. |
| `02_AGENT_BACKEND_CONTEXT.md` | Member A | Backend + Hermes Agent AI context. FastAPI, database, tools, triggers, replanning logic, API contracts. |
| `03_FRONTEND_PRODUCT_CONTEXT.md` | Member B | Frontend + product AI context. Onboarding flow, screens, version comparison, dashboard, visualization. |
| `04_DATA_MATERIAL_CONTEXT.md` | Member C | Data + learning system AI context. Document processing, concept map, diagnostic generation, evidence, demo scenarios. |
| `05_DEVELOPMENT_ROADMAP.md` | Everyone | Phases, milestones, task ownership, acceptance criteria, risks. |
| `06_DECISION_REGISTER.md` | Everyone | Locked decisions and explicitly rejected ideas, with reasons. |
| `TraceLearn_Team_Roadmap.html` | Everyone (incl. non-technical) | Visual team-sharing document. Open in any browser. |

---

## How to use this package

**On day one, everyone reads:** `01_SHARED_CONTEXT.md` in full, then `06_DECISION_REGISTER.md`.

**Then each member reads their own file:**
- Member A (AI Agent + Backend) → `02_AGENT_BACKEND_CONTEXT.md`
- Member B (Frontend + Product) → `03_FRONTEND_PRODUCT_CONTEXT.md`
- Member C (Data + Learning System) → `04_DATA_MATERIAL_CONTEXT.md`

**When working with an AI assistant:** paste `01_SHARED_CONTEXT.md` + your own role file as context before asking for code. This keeps the AI aligned with the frozen architecture instead of inventing its own.

**For sharing with supervisors / non-technical viewers:** open `TraceLearn_Team_Roadmap.html`.

---

## Team at a glance

| Member | Role | Owns |
|---|---|---|
| **A** | AI Agent + Backend | Hermes integration, FastAPI, database, tools, replanning logic |
| **B** | Frontend + Product | User flow, UI, dashboard, version comparison, visualization |
| **C** | Data + Learning System | Document processing, concept extraction, diagnostics, testing, demo scenarios |

---

## The one-sentence project

> TraceLearn transforms a learner's goal and learning materials into an executable roadmap, then continuously improves that roadmap using real learning evidence while explaining every change.

---

## The five non-negotiable principles

1. A small complete system beats a large unfinished system.
2. The Agent must visibly: read state → reason → use tools → change state → record decision.
3. We never claim perfect knowledge assessment, human-level understanding, or autonomous intelligence.
4. We say **Learner State Model**, never vague "memory."
5. Material grounding + evidence trace is the core product identity.

---

## Change control

The foundation is frozen. To change anything in this package:
1. Raise it with the whole team.
2. If agreed, update the relevant file **and** log the change in `06_DECISION_REGISTER.md`.
3. Bump the package version in this README.

Do not silently drift from these documents.
