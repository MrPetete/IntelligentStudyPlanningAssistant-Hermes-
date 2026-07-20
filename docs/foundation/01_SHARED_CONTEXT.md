# 01 — Shared Context (Read First)

This is the complete product foundation for TraceLearn. Every team member reads this file in full before writing any code. It is the shared vocabulary and the frozen truth.

---

## 1. Project identity

- **Name:** TraceLearn
- **Subtitle:** Material-Grounded Personal Learning Path Agent
- **Type:** University production internship project. Not a commercial launch. Optimised for: working demo, explainability, technical correctness, defence quality, portfolio value.
- **Team size:** 3
- **Timeline:** short internship period (~2–3 weeks active build).

### Core value proposition

> TraceLearn transforms a learner's goal and learning materials into an executable roadmap, then continuously improves that roadmap using real learning evidence while explaining every change.

---

## 2. The core product insight

TraceLearn is **NOT** "AI generates a study plan." That is already common and worth nothing as a differentiator.

TraceLearn **IS** a material-grounded learning Agent that creates, tracks, and explains the *evolution* of a learner's path.

The differentiation is:

> **Evidence-driven, material-grounded, explainable learning path evolution.**

The system is designed to answer the question most tools ignore:

> **"Why did my learning plan change?"**

not only:

> "What should I study?"

The product **is the trace**. If we polish one thing, it is the visible chain from evidence to reasoning to a new plan version to a written explanation.

---

## 3. The final core loop

```
Goal
  ↓
Learning Material            (optional but highly valuable)
  ↓
Concept Map Extraction
  ↓
Human confirmation / editing
  ↓
Initial Diagnostic
  ↓
Learning Roadmap  (Version 1)
  ↓
Daily Learning Tasks
  ↓
Learning Evidence            (task completion, quiz results, time, questions)
  ↓
Hermes Agent Analysis
  ↓
New Plan Version
  ↓
Evidence-linked Explanation
  ↓
Version History
```

Everything we build serves this loop. If a feature is not on this loop, it is Should-Have at best and probably Future.

---

## 4. Material design decision (frozen)

Material upload is **not** a minor optional feature. It is the **grounding source** of the system.

**Without material:** Goal + deadline + ability produces a *general* topic-based roadmap. (Graceful fallback — the product still works.)

**With material:** the system understands actual course coverage, teacher emphasis, syllabus structure, and required concepts. It then produces targeted diagnosis, concept-linked tasks, a focused roadmap, and meaningful replanning.

**Hard rule:** the system MUST work without uploaded material. No material → fallback to topic-based planning. Material is where the product becomes special, but its absence must never break the flow.

### 4a. Cross-language material grounding (supporting capability)

Real learners often study material in a language they are still mastering: a Chinese student with an English textbook, or an international student with Chinese course material. For them, the language gap *is part of* the grounding problem. TraceLearn addresses this with **cross-language material grounding**:

> The system understands material in one language and produces its explanations, tasks, and diagnostic questions in the learner's preferred language — while preserving technical terms in their original form.

This is a **supporting capability, not the product identity.** It *sharpens* the material-grounded differentiator (it grounds a plan even when the material is in a second language); it does not replace it. The core product remains **material-grounded, evidence-driven, explainable learning path evolution.**

**The layer split (frozen):**

| Machine layer — always English | Human-facing layer — adapts to `explanation_language` |
|---|---|
| Agent internal reasoning | Explanations |
| Tool names | Notes |
| Tool arguments | Diagnostic questions |
| Database identifiers | Task descriptions |

**Scope fence (frozen — do NOT cross):** two languages only (Chinese, English); content localization only; the **source document is never translated** (extract from the original, localize the output); there is **no UI translation / i18n framework** and **no translation database**. See `06_DECISION_REGISTER.md` D19.

**Positioning line for the demo:** *"The concept map is language-neutral — technical terms are preserved as grounding anchors — while explanations adapt to the learner's language. One concept drives the diagnostic, tasks, evidence, and the agent's reasoning, whatever language you read in."*

---

## 5. Concept map as system foundation

The extracted **concept map** is the central connection layer of the entire system. It is a **first-class database entity**, not a byproduct.

It connects everything:

```
Material
  ↓
Concepts          ← the shared join key
  ↓
Diagnostic questions   (each question targets concept(s))
  ↓
Learning tasks         (each task targets concept(s))
  ↓
Evidence               (attaches to concept(s))
  ↓
Agent decisions        (reason over concept(s), cite them by name)
```

### Worked example (this is the whole product in one example)

| Stage | What happens |
|---|---|
| Concept | Database normalization |
| Diagnostic | Student fails the normalization question |
| Task | Add normalization practice |
| Evidence | Quiz score on normalization remains low |
| Agent decision | Create additional normalization remediation tasks, explain why |

Because concepts are the shared key across diagnostics, tasks, evidence, and agent decisions, every plan change can be traced to a named concept. This is what makes replanning *pedagogically meaningful* instead of mere schedule juggling.

**Protect the concept map.** If concept extraction is weak, the differentiator wobbles. Mitigations: V1 uses one clean text-based PDF/TXT (no OCR); the user confirms/edits the concept map before planning (human-in-the-loop grounding); generic fallback when no material exists.

**The concept map is also the language-neutral layer.** Each concept carries a **canonical term** (the technical term preserved in its original form, e.g. "Normalization") plus a **localized explanation** in the learner's language. The canonical term is the stable grounding anchor and the join key; the explanation adapts. This is what makes cross-language grounding (Section 4a) an *architectural* feature rather than a translation bolt-on.

---

## 6. Final onboarding flow (Option C hybrid — frozen)

The guiding rule: **never generate a roadmap before concept extraction, but never make the user stare at a blocking spinner either.**

```
1. User enters: goal, deadline, available study time     (~10s, required)
        ↓
2. Optional material upload → analysis runs ASYNC in background
        ↓
3. While processing: ask lightweight self-reflection questions
   (NOT the diagnostic; they only provide soft context/priors)
        ↓
4. AI creates concept map
        ↓
5. User confirms or edits concept map                    (human-in-the-loop grounding)
        ↓
6. AI generates diagnostic questions based on concepts
        ↓
7. AI generates roadmap (Version 1)
```

**No-material path:** step 2 is skipped, concept map is derived from the goal topic, everything else is identical.

**The trap to avoid:** the self-reflection questions in step 3 are engagement filler + soft priors only. They are NOT the diagnostic and NOT roadmap input. If they become the basis of a plan, the flow silently degrades into "plan first, ground later," which contradicts principle 5.

---

## 7. MVP scope (frozen)

### Must Have
- Goal input
- Deadline
- Optional PDF/TXT upload
- Material extraction
- Concept map generation
- Concept confirmation (human-in-the-loop)
- Initial diagnostic
- Roadmap generation
- Task tracking
- Evidence recording
- Hermes Agent reasoning
- Plan version creation
- Evidence-linked explanation
- Version history

### Should Have
- Basic dashboard
- Concept weakness visualization
- Simple knowledge notebook
- Concept explanation mode

### Future Only (document, do not build)
- Multiple documents
- Full semester library
- OCR
- PPT / DOCX processing
- Calendar
- Career planning
- Campus integration
- Mobile app
- Multi-agent system

**Rule:** if a Must-Have is at risk, cut a Should-Have. Never cut a Must-Have to add a Should-Have.

---

## 8. Technical foundation (frozen)

| Layer | Choice |
|---|---|
| Frontend | Vue or React + ECharts |
| Backend | Python + FastAPI |
| Database | SQLite (initially) |
| Agent | Hermes tool-calling Agent |

### Agent tools (frozen set)

**Read tools (safe, used freely):**
- `get_learner_state`
- `get_current_plan`
- `get_progress_summary`
- `get_evidence_since_last_plan`
- `search_learning_material`

**Write tools (few, guarded):**
- `create_plan_version`
- `record_agent_decision`

The small write surface (2 tools) is intentional and is a defence point: the Agent's ability to change the world is tightly bounded and validated.

---

## 9. What makes this a real Agent (not "ChatGPT + form + DB")

A wrapper does: one prompt in → one text out. TraceLearn is an Agent because:

1. It **reads external state** through tools rather than being handed everything in the prompt.
2. It makes a **conditional decision** — whether to replan — not fixed by the prompt.
3. It **acts on persistent state** via write tools (new plan version, recorded decision).
4. It runs a **loop with a trigger**, not a single turn.
5. The **tool sequence is not hardcoded**; the model chooses tools and arguments from state.

### The control split (memorise this for defence)

| Deterministic code controls | The LLM decides |
|---|---|
| **When** the Agent is invoked (trigger thresholds) | **Whether** the plan needs to change given the evidence |
| **Validation** of any proposed plan (dates, total hours, no past tasks) | **What specifically** to change |
| **Persistence, versioning, parent linkage** | The **natural-language justification** |
| **Guardrails** (reject impossible schedules) | Interpretation of ambiguous evidence |

One-line defence answer: *"We never let the LLM run unbounded. Deterministic triggers decide when it wakes up, and deterministic validators check everything it proposes before it is persisted."*

---

## 10. Final principles (non-negotiable)

1. A small complete system beats a large unfinished system.
2. The Agent must demonstrate: read state → reason → use tools → change state → record decision.
3. Do not claim: perfect knowledge assessment, human-level understanding, or autonomous intelligence.
4. Use the term **Learner State Model**, never vague "memory."
5. Material grounding + evidence trace is the core product identity.

---

## 11. Glossary (shared vocabulary — use these exact terms)

- **Concept Map** — the structured set of concepts extracted from material (or derived from the goal topic). The system's central join key and language-neutral layer.
- **Concept** — a single named knowledge unit (e.g. "database normalization"). First-class entity. Carries a `canonical_term` + a localized `explanation`.
- **Canonical term** — the technical term for a concept, preserved verbatim in its original language (e.g. "Normalization"). The stable grounding anchor; never translated.
- **Explanation language** — the learner's preferred language (Chinese or English) for human-facing output. Stored on the learner profile as `explanation_language`.
- **Cross-language material grounding** — understanding material in one language and producing human-facing output in the learner's language while preserving canonical terms. A supporting capability, not the product identity.
- **Machine layer / human-facing layer** — the machine layer (Agent reasoning, tool names, tool arguments, DB identifiers) is always English; the human-facing layer (explanations, notes, diagnostic questions, task descriptions) adapts to `explanation_language`.
- **Learner State Model** — the current structured picture of the learner: goal, deadline, available time, per-concept mastery signals, progress. Replaces the word "memory."
- **Diagnostic** — the initial concept-targeted quiz that produces the first ability signal. A heuristic signal, not a measurement.
- **Roadmap / Plan** — an ordered set of daily tasks toward the goal. Exists as immutable **Plan Versions**.
- **Plan Version** — one immutable snapshot of the roadmap. New versions are created, never mutated in place.
- **Evidence** — a recorded learning event: task completion, quiz result, study time, or user question. Written by the application, read by the Agent.
- **Trigger** — a deterministic condition that decides when the Agent is invoked.
- **Agent Decision** — a logged record of a replan reasoning event: trigger, evidence snapshot, reasoning text, tool trace, resulting plan version.
- **Tool Trace** — the ordered list of tool calls (name, args, result) the Agent made. The key defence artifact.
