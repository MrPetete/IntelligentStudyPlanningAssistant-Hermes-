# Data Contracts — Concepts, Diagnostic, Plan, Evidence, Mastery

**Owner:** Member C (Data + Material + Testing)
**Purpose:** one source of truth for the shapes Member A's endpoints/orchestrator
write and Member B's frontend renders, and for the mastery formula the Agent
cites in its `reasoning_text`. Copied from `docs/foundation/04_DATA_MATERIAL_CONTEXT.md`
§4–§6 and verified against the actual code in this repo on 2026-07-21 — if this
doc and the code ever disagree, the code is Member A's/Member C's to fix and
this doc gets corrected, not the other way around.

---

## 1. Concept map (`agent.llm_client.extract_concepts`)

```json
{
  "concepts": [
    {
      "canonical_term": "Normalization",
      "name": "Database normalization",
      "explanation": "把关系分解为 1NF-3NF，消除冗余，基于函数依赖……",
      "order_index": 4,
      "parent_concept": "Relational design",
      "source": "material"
    }
  ]
}
```

- `canonical_term` — the technical term, **preserved verbatim in its original
  language**. This is the machine-layer join key everything else keys off.
  Never translated, never paraphrased.
- `name` — short display label; may equal `canonical_term`.
- `explanation` — the only language-varying field; written in the goal's
  `explanation_language`.
- `order_index` — suggested learning sequence.
- `source` — `"material"` (extracted), `"goal_topic"` (no-material fallback),
  or `"user_added"` (added during confirmation).
- Teachable range: **8–25 concepts** per course document (enforced by the real
  parser, `_parse_concepts_response` in `agent/llm_client.py`).

---

## 2. Diagnostic (`agent.llm_client.generate_diagnostic`)

```json
{
  "questions": [
    {"id": 1, "concept_id": 3, "prompt": "...", "options": ["a","b","c","d"], "answer": "b"}
  ]
}
```

- Input is the **confirmed** concept map only.
- 5–8 questions (config: `DIAGNOSTIC_NUM_QUESTIONS`, Member A's `config.py`).
- Every question ties to exactly one `concept_id` — never an invented one.
- `answer` is server-side only, never sent to the client.
- Submission produces a per-concept score `{concept_id: score 0..1}`, which
  seeds mastery (§4).
- **Honesty rule (D16):** this is a heuristic signal, never described as a
  true ability measurement.
- `prompt`/`options` localized to `explanation_language`; scoring is
  language-independent (keyed on `concept_id`).

---

## 3. Plan / roadmap tasks (`agent.llm_client.generate_plan`, `decide_replan`)

```json
{
  "tasks": [
    {"concept_id": 3, "day": "2026-08-01", "description": "...", "est_minutes": 40}
  ]
}
```

- `concept_id` must be one of the confirmed concepts' real ids for the
  initial roadmap (`generate_plan`).
- For a **replan** (`decide_replan`), the mock/prompt instead returns
  `canonical_term` per task with `concept_id: null` — the **orchestrator**
  (Member A) resolves `canonical_term -> concept_id` before validation. Do not
  change this — it is how the LLM proposes a concept it may not have the id
  for handy.
- Validated by `agent/validator.py`'s 5 rules before it is ever persisted
  (weekly-minutes budget, no past dates, no dates after deadline, valid
  concept references, must cover every still-weak concept). See that file for
  the authoritative rule text — this doc does not duplicate it.
- **Known current limitation (report to Member A, do not fix here):** replan
  versions currently *replace* the whole task list rather than merging with
  the current plan's untouched tasks. The team decision (see
  `MEMBER_C_V1_TASKLIST.md` §3) is **full merge** — plan version 2 should be
  plan version 1's tasks carried forward + the new remediation tasks. That
  merge is deterministic orchestrator logic (Member A's lane), not yet
  implemented as of this writing.

---

## 4. Evidence payloads

Evidence rows are written by the **application** (Member A's endpoints); this
table is the contract Member A and Member B key off.

| `type` | `payload_json` example | `concept_id` |
|---|---|---|
| `task_done` | `{"task_id": 12, "minutes": 25}` | the task's concept |
| `task_skipped` | `{"task_id": 13}` | the task's concept |
| `quiz_result` | `{"concept_id": 3, "score": 0.4, "items": 5}` | the concept |
| `time_logged` | `{"minutes": 40}` | optional |
| `question` | `{"text": "why is 3NF needed?"}` | optional |

---

## 5. Mastery-update formula (as actually implemented)

Implemented in `agent/tools.py::_mastery_by_concept` — **read it, do not
change it** (Member A's file). Documented here so the Agent's `reasoning_text`
and any UI copy describe it accurately.

- Every concept starts at **mastery = 0.5** the first time evidence touches it.
- `quiz_result` with a `score` **sets** mastery to that score directly
  (does not average with the prior value).
- `task_skipped` **subtracts 0.15** from current mastery (floor 0.0).
- `task_done` **adds 0.1** to current mastery (ceiling 1.0).
- Evidence rows are processed in creation order; only the running value
  matters, there is no windowing/decay.
- This is a **heuristic, not a measurement** (Decision D16) — never describe
  it to the learner as a true ability score. The UI's word for it is
  "estimated."

**Thresholds that read this signal** (`config.py TRIGGERS`, Member A's file,
tuned in Phase 2 — do not change without sign-off):
- `low_mastery_threshold = 0.40` — any concept's mastery below this is a
  "weak concept" and can fire the `low_mastery` trigger.
- `quiz_fail_threshold = 0.50` — a single quiz score below this on a concept
  can fire the `quiz_fail` trigger.
- `behind_schedule_pct = 0.25` — more than 25% of "due" tasks incomplete can
  fire `behind_schedule`. **Caveat:** `get_progress_summary()` currently
  treats *all* pending tasks as "due" regardless of date (a documented
  Phase-0 simplification) — see `seed/seed.py`'s comment for why the seed
  script marks non-Normalization tasks `done` to avoid this trigger firing
  on a false signal.
- `min_evidence_events = 3` — the agent is never invoked on a single data
  point.

---

## 6. Language rule, restated once more because it is easy to get backwards

- Extract concepts from the material **in its original language, never
  translated**.
- Every generation prompt takes a `target_language` and produces
  `explanation` / question text / task `description` / `reasoning_text` in
  that language.
- `canonical_term` is the one field that is **never** translated, in any
  prompt, at any layer.
- Two languages only: `en`, `zh` (`config.SUPPORTED_LANGUAGES`, frozen).
