# 03 — Frontend + Product Context (Member B)

**Owner:** Member B — Frontend + Product
**Prerequisite reading:** `01_SHARED_CONTEXT.md`, `06_DECISION_REGISTER.md`
**Use with an AI assistant:** paste `01_SHARED_CONTEXT.md` + this file as context before requesting code.

You own the experience. The product's differentiator — "why did my plan change?" — lives or dies in the UI. If we polish one thing, it is the trace: the tool-call view and the version diff. Build for the demo moment.

---

## 1. Your responsibilities

- The onboarding flow (Option C hybrid).
- All screens and navigation.
- The dashboard and concept-weakness visualization (ECharts).
- The version comparison / diff view.
- The Agent decision / tool-trace viewer (the money shot).
- Consuming the backend API contract (Section 9 of `02_AGENT_BACKEND_CONTEXT.md`).

You do **not** own: the Agent logic, document processing, or diagnostic generation. You render what the API returns.

---

## 2. Stack and conventions

- Vue 3 (or React — pick one on day 1 and freeze it) + ECharts.
- A single API client module mapped 1:1 to the backend contract. Mock it first so you are never blocked by backend.
- Keep state simple (Pinia / Zustand / plain composables). This is a demo app, not an enterprise SPA.
- Prioritise clarity over visual flourish. Clean, calm, readable.

---

## 3. The onboarding flow (Option C — frozen)

The rule: **never show a roadmap before concept extraction, never show a blocking spinner.**

```
Screen 1  Goal setup
  Fields: goal (free text), deadline (date), weekly hours (number),
          explanation language (Chinese / English — one control).
  Optional: drag-drop one PDF/TXT.
  CTA: "Start".  Upload begins async in the background.

Screen 2  Warm-up (shown while material processes)
  2-3 lightweight self-reflection questions
    ("Have you studied this before?", "Starting from scratch?").
  Label clearly: this is context, NOT a test.
  A subtle background indicator shows material analysis progressing.
  If no material was uploaded: still show 1-2 warm-up questions, then skip to Screen 4 fallback.

Screen 3  Concept map confirmation   (human-in-the-loop grounding)
  Show extracted concepts as editable chips/list.
  User can: rename, remove, add, reorder.
  CTA: "Confirm concepts".  -> PUT /goals/{id}/concepts
  This screen is a defence highlight. Make it feel intentional.

Screen 4  Diagnostic
  Concept-targeted questions (from confirmed concepts, or goal topic if no material).
  Short (5-8 questions). Submit -> per-concept scores.

Screen 5  Roadmap V1 reveal
  Show the generated roadmap + first days of tasks.
  Highlight flagged weak concepts.
  This is the aha moment. It must land within ~3 minutes of Screen 1.
```

**Trap to avoid:** the warm-up answers (Screen 2) are soft context only. Do not present them as the diagnostic and do not let them look like they generate the plan.

---

## 4. Core screens after onboarding

### A. Today / Tasks
- Daily task list with concept tags.
- Check-off marks a task done → `POST /tasks/{id}/complete` (this may silently fire the Agent trigger).
- Optional: log study time, submit a quick quiz.

### B. Roadmap
- Full plan for the current version, grouped by day/week.
- Each task shows its concept tag.
- Version selector: "Version 1 · Version 2 · Version 3…".

### C. Version History (the differentiator)
- Timeline of plan versions with created_by ('you' vs 'TraceLearn agent') and timestamp.
- Click a version pair → **Diff view**.

### D. Diff view
- Side-by-side or inline diff between two plan versions.
- Show: tasks added, removed, reordered, reschedule changes.
- Group changes by concept where possible ("2 tasks added for normalization").
- Directly above/beside the diff: the **evidence-linked explanation** (`reasoning_text`).

### E. Agent Decision / Tool-Trace viewer (MONEY SHOT)
- For a selected decision, render, in order:
  1. The **trigger** that fired ("25% of tasks overdue").
  2. The **evidence snapshot** the Agent saw.
  3. The **tool trace**: each tool call as a card — tool name, arguments, short result. In sequence.
  4. The **reasoning text** (the answer to "why did my plan change?").
  5. The **resulting version** link → jumps to the diff.
- Also render `no_change` decisions ("considered, no change needed") — this shows the Agent is judging, not just always rewriting.

### F. Dashboard (Should-Have)
- ECharts: per-concept mastery (bar/radar), progress vs schedule (line/gauge), tasks done over time.
- Concept-weakness visualization: highlight low-mastery concepts.

### G. Knowledge Notebook + Concept Explanation (Should-Have)
- Simple list of concepts with saved notes.
- "Explain this concept" → calls concept-explanation endpoint (uses retrieval if available). Skip if behind schedule.

---

## 5. What to build first (order)

1. API client + mocks matching the contract.
2. Onboarding Screens 1-5 against mocks.
3. Tasks + Roadmap + Version selector.
4. **Version History + Diff view + Tool-Trace viewer** (do not leave these last — they are the point).
5. Dashboard + visualization.
6. Notebook / concept explanation (only if time remains).

---

## 6. Cross-language material grounding (frozen scope for frontend)

TraceLearn supports a learner whose material is in one language and who wants explanations in another. **This is a content feature, not a UI feature.** Your responsibility is narrow and cheap:

- **The UI chrome is monolingual.** Buttons, menus, and labels stay in ONE language. **Do NOT add an i18n framework (vue-i18n / react-i18next), locale routing, or a language switcher on every screen.** (Decision D19.)
- Add **one** language control on Screen 1 (goal setup): the learner's `explanation_language` (Chinese / English). It sets a field on the goal via `POST /goals` / `PATCH /goals/{id}/language`. It does **not** re-translate the interface.
- **Render whatever language the API returns.** Concept explanations, task descriptions, diagnostic questions, and the Agent's `reasoning_text` arrive already localized from the backend. You display them as-is.
- **Concept tags show the canonical term** (e.g. "Normalization") verbatim, regardless of explanation language. The canonical term is the stable anchor across every screen; the explanation next to it may be localized.
- The tool-trace viewer shows tool names/arguments in English (machine layer) and the `reasoning_text` in the learner's language (human-facing layer). This split is itself a good thing to show.

You are never translating anything in the frontend. You are choosing a language on Screen 1 and rendering localized content elsewhere. Two languages only: Chinese, English.

## 7. Design principles for this product

- Make the **trace legible to a non-technical person**. A supervisor should look at the Tool-Trace viewer and immediately see "read → reason → act → record."
- Every plan change must show its **reason** next to it. Never show a new version without the explanation.
- Concept tags everywhere, using the **canonical term**. The user should always see *which concept* a task, question, or change relates to.
- Honest language in the UI: "estimated mastery", "based on your evidence so far" — never "your knowledge level is X%" as if measured.
- Graceful empty/failure states: no material, processing failed, Agent made no change.

---

## 8. Definition of done (frontend)

- [ ] Onboarding Option C works end-to-end against real API, including the no-material fallback.
- [ ] Screen 1 has a single Chinese/English explanation-language control that sets the goal field; no i18n framework added; UI chrome stays monolingual.
- [ ] Localized content (explanations, tasks, diagnostic, reasoning_text) renders as returned; concept tags show canonical terms verbatim.
- [ ] Concept confirmation screen edits persist via `PUT /concepts`.
- [ ] Task check-off records progress and reflects trigger outcomes.
- [ ] Version history timeline lists all versions with author + time.
- [ ] Diff view clearly shows what changed between two versions, grouped by concept.
- [ ] Tool-trace viewer renders trigger → evidence → ordered tool calls → reasoning → resulting version.
- [ ] `no_change` decisions render correctly.
- [ ] Dashboard shows per-concept mastery + progress (Should-Have).
- [ ] The full demo path (onboard → study → simulate evidence → replan → view trace + diff) is smooth and rehearsable.
