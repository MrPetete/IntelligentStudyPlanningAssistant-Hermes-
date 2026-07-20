# AI Handoff Prompt — Member C (Data + Material + Testing)

Copy the block below into a fresh AI coding session as your first message.

---

You are assisting **Member C** of TraceLearn — a Material-Grounded Personal Learning
Path Agent. Member C owns material processing, concept-map generation, diagnostic and
roadmap prompts, evidence design, the seed scenario, and testing. The concept map
Member C produces is the knowledge spine of the whole system.

**Read these files first, in order, before writing any code:**
1. `01_SHARED_CONTEXT.md` — product foundation and glossary
2. `04_DATA_MATERIAL_CONTEXT.md` — data + material + learning-system contract
3. `06_DECISION_REGISTER.md` — locked decisions and rejected ideas
4. `app/backend/agent/llm_client.py` (mock shapes to match) and `app/backend/seed/`

**Do NOT change:**
- Frozen product decisions, architecture, or scope.
- The orchestrator control flow, the endpoints, or the DB schema. You produce pipelines/prompts that Member A calls.
- These language rules: never translate the source material; extract the original first; localize only generated output (pass `target_language`); preserve `canonical_term` verbatim; two languages only (`en`, `zh`).

**Do NOT** use RAG for planning (the concept map is the planning input); `search_learning_material` stays `available: false` in the MVP. No OCR, PPT/DOCX, or multi-document.

**Responsibilities:** text extraction (one clean PDF/TXT); the three generation prompts (`_real_extract_concepts`, `_real_generate_diagnostic`, `_real_generate_plan`); evidence payloads + mastery-update helper; seed + simulate + recorded fallback; unit tests for `triggers.py` and `validator.py`.

**First tasks (no backend dependency — start immediately):**
1. Write unit tests for `agent/triggers.py` and `agent/validator.py` (pure functions; cover fire/no-fire and all 5 plan-rejection rules).
2. Draft the three generation prompts against `MOCK_LLM`, matching the mock JSON shapes exactly so the swap to real Hermes is drop-in.
3. Prepare/confirm the sample material (keep it clean and text-based).
4. Confirm the normalization-failure scenario in `seed/simulate.py` reliably drives a Version 2 with remediation.

**Success criteria:** passing tests for triggers + validator; prompts return JSON matching the mock shapes with canonical terms preserved and explanations localized; seed + simulate reproduce the normalization-remediation V2; a recorded/seeded fallback demo exists.

Work in small steps and verify prompt output against the mock shapes before integration. Ask before touching anything owned by Member A.
