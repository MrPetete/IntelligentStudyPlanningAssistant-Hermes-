# 04 — Data + Learning System Context (Member C)

**Owner:** Member C — Data + Learning System
**Prerequisite reading:** `01_SHARED_CONTEXT.md`, `06_DECISION_REGISTER.md`
**Use with an AI assistant:** paste `01_SHARED_CONTEXT.md` + this file as context before requesting code.

You own the intelligence that grounds the whole product: turning raw material into a concept map, generating concept-targeted diagnostics, shaping evidence, and building the demo scenario. The concept map you produce is the spine of the system.

---

## 1. Your responsibilities

- Document ingestion: PDF/TXT text extraction.
- Concept map generation (the central artifact).
- Diagnostic question generation from concepts.
- Evidence shaping and scoring helpers.
- Optional retrieval store (chunks + embeddings) if Q&A is built.
- Test scenarios and the demo seed/simulate data.

You do **not** own: the Agent loop or endpoints (Member A), the UI (Member B). You produce the pipelines and prompts Member A calls.

---

## 2. The critical design rule: planning does NOT need RAG

Two different jobs, do not confuse them:

- **Planning + diagnostics** need a **compact structured concept map**, generated once at upload. Planning reads this small artifact, never the raw document.
- **Q&A / concept explanation** (Should-Have) needs **retrieval** (top-k over chunks). This is the only place RAG belongs, and it is optional.

Most student projects fail by dumping whole documents into the planning prompt. Do not do this. The concept map is the interface between material and everything else.

## 2a. Cross-language material grounding (frozen rules)

The material may be in one language and the learner may want output in another (Chinese ↔ English only). Your pipeline handles this at the **output** stage, never the input stage.

- **NEVER translate the source document.** Extract concepts from the original text. Translating the source before extraction degrades grounding and is explicitly forbidden (Decision D19).
- Every generation prompt (concept map, diagnostic, task text) receives a `target_language` parameter = the goal's `explanation_language`.
- Prompts instruct: "The material may be in any language. Produce `explanation` / questions / task descriptions in `{target_language}`. Preserve technical terms as `canonical_term` in their original form — do not translate the canonical term."
- `canonical_term` is language-stable across the whole system; only `explanation`, diagnostic prompts, and task descriptions vary by language.
- Two languages only: `'en'`, `'zh'`. No third language. No translation table — you generate directly in the target language, you do not store parallel translations.

---

## 3. Document processing pipeline (V1)

Input: one clean, text-based PDF or TXT. **No OCR, no scanned images, no PPT/DOCX in V1.**

```
1. Save raw file → documents.storage_path, status='uploaded'
2. status='processing'
3. Extract plain text (pdfplumber / PyMuPDF for PDF; direct read for TXT)
4. Generate concept map (Section 4)  → concepts table
5. (Optional) chunk text + embed → document_chunks   (only if Q&A is built)
6. status='ready'   (or 'failed' with a reason)
```

This runs **async** (background task) so onboarding is not blocked (see Option C flow). On failure, set status='failed' and the system falls back to goal-topic concepts.

---

## 4. Concept map generation (the spine)

Goal: from extracted text, produce a **structured, compact** list of concepts. Use map-reduce summarization for longer documents — summarise sections, then consolidate into a concept list. Never rely on stuffing the full text into one prompt.

Target output (stored to `concepts`):
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

Guidelines:
- Keep it to a **teachable number** of concepts (roughly 8-25 for a course document). Not every sentence is a concept.
- `canonical_term` is the technical term **preserved verbatim in its original language** (e.g. "Normalization"). It is the grounding anchor and the join key. Never translate it.
- `name` is a short display label; may equal the canonical term.
- `explanation` is the one-line-plus explanation, written in the learner's `explanation_language`, used for diagnostic + task generation. This is the ONLY language-varying field.
- `order_index` gives a suggested learning sequence; a shallow parent grouping is enough (no deep trees).
- `source` = 'material' when extracted, 'goal_topic' for the fallback, 'user_added' when the user adds one in confirmation.

**Fallback (no material):** generate the concept map from the goal text alone ("pass my databases final") using the LLM's topic knowledge. Same output shape, `source='goal_topic'`.

**Human-in-the-loop:** the user confirms/edits this map before anything is planned. Treat the confirmed map as authoritative.

---

## 5. Diagnostic generation

Input: the **confirmed** concept map. Output: 5-8 questions, each tied to concept(s).

```json
{
  "questions": [
    {"id": 1, "concept_id": 3, "prompt": "...", "options": ["a","b","c","d"], "answer": "b"}
  ]
}
```

Guidelines:
- Cover the most important / foundational concepts first; you cannot test everything with 5-8 items.
- Multiple-choice keeps scoring deterministic and demo-friendly.
- Produce a **per-concept score** on submission: `{concept_id: score 0..1}`. This seeds each concept's mastery in the Learner State Model.
- **Honesty rule:** this is a heuristic signal, not a measurement. Never label output as a true ability score. The UI reflects this ("estimated").
- **Language:** question prompts/options are generated in the goal's `explanation_language`; canonical terms inside them stay verbatim. Answers/scoring are language-independent (they key on `concept_id`).

---

## 6. Evidence shaping

Evidence rows are written by the application (Member A's endpoints), but you define the payload shapes and any scoring helpers.

| type | payload_json example | concept_id |
|---|---|---|
| `task_done` | `{"task_id": 12, "minutes": 25}` | task's concept |
| `task_skipped` | `{"task_id": 13}` | task's concept |
| `quiz_result` | `{"concept_id": 3, "score": 0.4, "items": 5}` | the concept |
| `time_logged` | `{"minutes": 40}` | optional |
| `question` | `{"text": "why is 3NF needed?"}` | optional |

You provide the helper that maps evidence → updated per-concept mastery signal (a simple weighted update is fine; document the formula). Keep it explainable — the Agent will cite it.

---

## 7. Optional retrieval (Should-Have / Could-Have)

Only if time allows and Q&A / concept-explanation is being built:
- Chunk extracted text (fixed size + small overlap; put chunk size in config).
- Embed with one embedding model (config-driven).
- `search_learning_material` returns top-k (k≈5, config) by cosine similarity.
- Never return more than k chunks. Never feed the whole document.

If not built, `search_learning_material` returns `{"available": false}` and the product still works fully.

---

## 8. Configurable variables (put in shared config)

- chunk_size, chunk_overlap
- top_k
- embedding_model
- concept_map_max_concepts
- summary_depth (map-reduce granularity)
- diagnostic_num_questions
- mastery update weights
- supported_languages = ['en', 'zh']   (frozen at two; do not extend)
- default_explanation_language
- (Agent triggers live in the same config, owned by Member A)

---

## 9. Demo scenario (you own this — it decides the grade)

Examiners cannot wait 3 real days for evidence to accumulate. Build a **seed + simulate** path so a replan can be triggered on demand.

Prepare:
1. A clean sample document (e.g. a databases course PDF) with a known concept map.
2. A seeded goal with a Version 1 roadmap.
3. A "simulate" script/endpoint that injects evidence: fail a quiz on **normalization**, mark several normalization tasks incomplete, advance the clock.
4. Verify this reliably fires the trigger → Agent reads state → creates Version 2 with normalization remediation → records a clear reasoning_text.
5. A **recorded/seeded fallback** so the demo does not depend on a live LLM call at the worst moment.
6. A **bilingual variant** (high value): the same flow with an **English** database PDF and `explanation_language = 'zh'`. Concept map keeps English canonical terms ("Normalization"); explanations, tasks, and the Agent's reasoning appear in Chinese. No extra demo machinery — one field set. Rehearse on the one verified sample so term preservation looks crisp.

The canonical demo story (rehearse it):
> "Here is the plan grounded in the student's own slides. The student struggles with normalization — watch the evidence come in. The trigger fires, the Agent reads the state, reasons over the concept, and creates Version 2 that inserts normalization remediation. Here is the tool trace, and here is exactly why it changed."

---

## 10. Definition of done (data + learning system)

- [ ] PDF/TXT extraction works on the sample document.
- [ ] Concept map generation produces a clean, teachable concept list; map-reduce used for longer docs.
- [ ] No-material fallback produces goal-topic concepts in the same shape.
- [ ] Diagnostic generation produces concept-tagged questions + per-concept scores.
- [ ] Evidence payload shapes + mastery-update helper documented and implemented.
- [ ] (If built) retrieval returns top-k and degrades gracefully when absent.
- [ ] Sample document + seeded goal + simulate script reliably trigger a Version 2 replan.
- [ ] Recorded fallback demo path exists.
- [ ] Concepts carry a preserved `canonical_term` + localized `explanation`; generation prompts take `target_language`; source document is never translated; bilingual demo variant verified on the sample.
