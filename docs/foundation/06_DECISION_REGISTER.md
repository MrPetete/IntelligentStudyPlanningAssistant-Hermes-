# 06 — Decision Register

This file records **locked decisions** and **explicitly rejected ideas**, with reasons. It exists to stop the team re-litigating settled questions mid-build. To change any locked decision: raise it with the whole team, update the relevant context file, and edit this register.

---

## Part 1 — Locked decisions

### D1 — Positioning: accountable, not autonomous
The product is positioned as **evidence-driven, material-grounded, explainable** learning path evolution. We do **not** market "autonomous intelligence."
**Why:** "autonomous" is hard to build reliably, risky to demo, and hard to defend when the LLM errs live. "Explainable + accountable" is our real strength and maps to what examiners ask.

### D2 — The trace is the product
The single most important artifact is the chain: evidence → reasoning → new plan version → written explanation → version history. We polish the tool-trace viewer and diff view above all else.
**Why:** it is the true differentiator and the strongest defence beat.

### D3 — Material grounding is core, via the concept map
Material is the grounding source, not a minor feature. The **concept map** extracted from material is a first-class DB entity and the join key across diagnostics, tasks, evidence, and agent decisions.
**Why:** grounding is only meaningful because concepts connect the whole loop; without it, replanning is mere schedule juggling.

### D4 — System must work without material
No upload → fallback to goal-topic concept map. Same pipeline, `source='goal_topic'`.
**Why:** never block first value on an expensive, failure-prone step.

### D5 — Onboarding uses Option C (hybrid), roadmap never precedes concept extraction
Goal → async material processing (with warm-up questions as filler) → concept map → user confirmation → diagnostic → roadmap.
**Why:** grounds the plan (backbone of Option A) while keeping perceived speed (feel of Option B). A roadmap is never generated before the concept map exists.

### D6 — Warm-up questions are context only, not the diagnostic
The self-reflection questions during processing provide soft priors. They are not the diagnostic and are not roadmap input.
**Why:** prevents the flow from silently degrading into "plan first, ground later."

### D7 — Human confirms the concept map
The user reviews/edits concepts before planning. The confirmed map is authoritative.
**Why:** human-in-the-loop grounding improves quality, protects against bad extraction, and is a strong defence moment.

### D8 — Seven tools: 5 read, 2 write
Read: `get_learner_state`, `get_current_plan`, `get_progress_summary`, `get_evidence_since_last_plan`, `search_learning_material`. Write: `create_plan_version`, `record_agent_decision`.
**Why:** a small, guarded write surface is safer and is a mark of mature agent design.

### D9 — Task progress is written by the app, not the Agent
No `record_task_progress` tool. The user checks a task off; the application writes the evidence. The Agent only reads evidence.
**Why:** keeps the write surface at 2 tools and keeps the "Agent reads evidence, proposes plan changes" story clean.

### D10 — Deterministic/LLM control split
Deterministic code controls: when the Agent is invoked (triggers), plan validation, persistence/versioning, guardrails. The LLM decides: whether to change, what to change, and the justification.
**Why:** bounds the LLM, makes behaviour safe and defensible, and answers "is it real / is it safe" in one sentence.

### D11 — Plan versions are immutable and append-only
Replanning creates a new `version_no` + new task rows + parent link. Never mutate an existing version.
**Why:** version history and diffs require immutable snapshots.

### D12 — Every Agent invocation records a decision, including `no_change`
**Why:** "considered and left unchanged" proves the Agent is judging, not blindly rewriting.

### D13 — Planning uses the concept map, not raw material or RAG
Planning and diagnostics read the compact concept map. Retrieval (RAG) is reserved for optional Q&A/concept explanation only.
**Why:** avoids context blow-up and vague plans; this separation is the most common failure point in student RAG projects.

### D14 — V1 material scope: one clean text-based PDF/TXT
No OCR, no scanned images, no PPT/DOCX in V1.
**Why:** protects concept-extraction quality within a short timeline.

### D15 — Terminology: "Learner State Model", not "memory"
**Why:** honest and precise; over one internship there is no longitudinal memory to demonstrate.

### D16 — Honesty guardrails in all output
No claims of perfect knowledge assessment, human-level understanding, or autonomous intelligence. Mastery is an "estimated" heuristic signal.
**Why:** defensible, credible, and avoids overclaiming that examiners will puncture.

### D17 — Stack frozen
Vue or React + ECharts / Python FastAPI / SQLite / Hermes tool-calling Agent.
**Why:** appropriate for the team, timeline, and demo; no time for infrastructure debates.

### D18 — Demo requires a seed + simulate path and a recorded fallback
**Why:** examiners cannot wait for real evidence; the demo must not depend on a live LLM call at the worst moment.

### D19 — Cross-language material grounding is a scoped supporting capability
The system supports a learner whose material is in one language and who wants human-facing output in another. This is a **supporting capability, not the product identity** — the core remains material-grounded, evidence-driven, explainable learning path evolution. The correct feature name is **"cross-language material grounding."**

**Implement now:**
- `explanation_language` field on the learner profile / goal (`'en'` | `'zh'`).
- Language preference passed into all generation and Agent prompts.
- Concept structure = `canonical_term` (technical term preserved verbatim) + localized `explanation`.

**Layer split (frozen):**
- **Machine layer — always English:** Agent reasoning, tool names, tool arguments, database identifiers, `canonical_term`.
- **Human-facing layer — adapts to `explanation_language`:** explanations, notes, diagnostic questions, task descriptions, `reasoning_text`.

**Do NOT implement (Future roadmap):**
- Full UI translation / i18n framework (UI chrome stays monolingual).
- Translation database / parallel-translation tables.
- Source-document translation (extract from the original; localize only the output).
- More than two languages.

**Why:** it sharpens the material-grounded differentiator for the real user base (bilingual students) at near-zero cost — two optional columns and a few prompt directives — while keeping the core identity unblurred and fencing off the scope-creep that is the only real risk. The concept map's `canonical_term` doubles as the language-neutral anchor, so this reinforces the "concepts are the spine" architecture rather than competing with it.

---

## Part 2 — Rejected ideas (do not build in the internship)

| Rejected | Why rejected |
|---|---|
| "AI generates a study plan" as the pitch | Commodity; zero differentiation. |
| Autonomy as the headline | Risky, hard to defend; replaced by accountability (D1). |
| Personalised memory as an intelligence feature | No longitudinal data in one internship; it is a schema, not a feature (D15). |
| Claiming true ability measurement from 5-8 questions | Statistically unreliable; overclaim (D16). |
| RAG for planning | Blows context, produces vague plans; concept map instead (D13). |
| Feeding whole documents / all chunks into the LLM | Context blow-up; top-k only, planning uses concept map. |
| Multiple documents / semester knowledge library | Scope black hole; Future only. |
| OCR, PPT/DOCX | Extraction-quality and time risk; Future only (D14). |
| Calendar integration | Integration tax, no differentiation; Future. |
| Career planning / campus ecosystem | Not this product; Future. |
| Mobile app | Out of scope for the timeline; Future. |
| Multi-agent system | Unnecessary complexity for the MVP; single Agent + tools is enough. |
| Option A (upload → extract → diagnostic → roadmap) as-is | Blocks first value on a slow, failure-prone step; replaced by Option C (D5). |
| Option B (quick diagnostic → upload → refine) | Demotes grounding to an afterthought, contradicting D3; rejected (D5). |
| `record_task_progress` as an Agent tool | Muddies the read-only-evidence story; app writes progress (D9). |
| Mutating plans in place | Kills version history/diffs; append-only instead (D11). |
| Full UI translation / i18n framework | High chore, low value, no differentiation; steals time from the trace. UI chrome stays monolingual (D19). |
| Translation database / parallel-translation tables | Unnecessary complexity; content is generated directly in the target language, one version stored (D19). |
| Translating the source document before extraction | Silently degrades grounding; extract from the original, localize the output only (D19). |
| More than two languages | Scope creep; frozen at Chinese + English (D19). |
| Bilingual as core product identity | Invites judging on translation quality and dilutes the trace/agent story; it is a supporting capability (D19). |
| Display language inside tool arguments / concept IDs | Breaks tool-calling reliability; machine layer stays English (D19). |

---

## Part 3 — Open items (decide before/at Phase 0)

- Frontend: Vue vs React — pick one on day 1 and record it here.
- Embedding model — only if optional retrieval is built; record choice here.
- Exact trigger threshold values — start from the defaults in file 02, tune in Phase 2, record final values here.
- UI chrome language (monolingual per D19) — pick the one language for buttons/labels based on the defence audience; record it here. (Content is separately localizable via `explanation_language`.)

_(Fill these in as they are decided.)_
