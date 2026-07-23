# V1 Discovery Report

> Copy this file and rename it with your name, e.g. `V1_DISCOVERY_REPORT_memberB.md`.
> Fill it in as you test. Keep entries short and structured — this file is to **compact**
> your findings so the discovery audit is fast, not to write essays. One row/block per issue.
> Attach `backend/logs/tracelearn.log` + screenshots in your zip (see the test guide, Part 4).

## Tester info
- **Name:** Member B
- **Date tested:** 2026-07-22
- **OS / browser:** Windows 10 / Chrome
- **Run mode:** local uvicorn
- **/health showed `mock_llm`:** false
- **Commit tested (`git rev-parse --short HEAD`):** 15bc1fc

---

## 1. Standard procedure checklist
Mark each: ✅ works · ⚠️ works but issue · ❌ broken · ⏭️ skipped. Put details in Section 2/3.

| Step | Result | Note (short) |
|---|---|---|
| A1 Create goal | ✅ works | Goal saved, advanced to next screen |
| A2 Upload real PDF/TXT → concepts from doc | ️⚠️ works but issue | LLM retry escalated 3 times (JSON decode errors) before succeeding with sonnet; ~44s total |
| A3 Edit + confirm concept map | ✅ works | 24 concepts extracted from doc, edits persisted |
| B4 No-file onboarding → goal-topic map | ⏭️ skipped | Tested with file path only |
| B5 Junk/broken file handled cleanly | ⏭️ skipped | |
| C6 Diagnostic questions on-topic | ✅ works | Questions matched confirmed concepts |
| C7 Scores reflect right/wrong answers | ✅ works | Per-concept scores returned correctly |
| D8 Plan dated + realistic | ❌ broken | **PLAN GENERATION FAILS EVERY TIME** — 422 validation error |
| E9 Replan → new version, history intact | ⏭️ skipped | Cannot test — blocked by D8 |
| E10 Decision View reasoning + trace | ⏭️ skipped | Cannot test — blocked by D8 |
| E11 Chinese (zh) text, English terms | ⏭️ skipped | Cannot test — blocked by D8 |
| F12 Errors degrade cleanly | ❌ broken | 422 from plan generate → blank white page (no error shown) |

---

## 2. Bugs / problems found
Duplicate this block per issue. Severity: 🔴 blocker · 🟠 major ·  minor · 🔵 cosmetic.

### Issue #1
- **Severity:** 🔴 blocker
- **Where (screen / endpoint):** Onboarding Step 5 (Roadmap V1 reveal) → `POST /goals/{id}/plan/generate`
- **What I did (steps):** Completed onboarding (goal + material upload + concept confirm + diagnostic), then the app auto-generates the plan. Page goes blank white.
- **What I expected:** Roadmap V1 with tasks displayed.
- **What actually happened:** Blank white page. Backend returns `422` with `planned minutes 515 exceed available 413`.
- **Log lines** (from `backend/logs/tracelearn.log`, paste the relevant few — no need for the whole file):
  ```
  2026-07-22T16:01:35+0800 INFO    tracelearn.llm generate_plan ok (model=claude-sonnet-4-6, tier=1/2, attempt=1/2, 16323ms)
  2026-07-22T16:01:35+0800 INFO    tracelearn.request POST /goals/2/plan/generate -> 422 (16327ms)
  ```
  Reproduced 4 times across 2 goals:
  ```
  POST /goals/1/plan/generate -> 422 (29940ms)
  POST /goals/2/plan/generate -> 422 (16327ms)
  POST /goals/2/plan/generate -> 422 (19498ms)
  POST /goals/2/plan/generate -> 422 (19916ms)
  ```
- **Screenshot filename (in zip):** `blank_roadmap.png`
- **Reproducible?** always
- **Notes:** The LLM generates a plan with 515 minutes but only 413 are available (weekly_hours=6 → 360 min/week, but the tolerance multiplier gives 413). The **validator correctly rejects it** (this is the right behavior), but the LLM doesn't self-correct within its retry budget. This is an LLM prompt / validator alignment issue. The frontend also fails to show the error — it just goes blank.

### Issue #2
- **Severity:** 🟠 major
- **Where:** `Onboarding.vue` Step 5 (roadmap reveal screen)
- **What I did:** Completed the full onboarding flow; when plan generation returned 422, the page went blank white with no error message.
- **What I expected:** An error message explaining why plan generation failed, with a "Retry" button.
- **What happened:** Completely blank white page. The `error` banner in the template would show it, but the component state doesn't recover properly.
- **Log lines:** (same as Issue #1 — the 422 response)
  ```
  POST /goals/2/plan/generate -> 422 (16327ms)
  ```
- **Screenshot:** `blank_roadmap.png`
- **Reproducible?** always
- **Notes:** `Onboarding.vue` line ~190-201 (`generatePlan()`) does have `error.value = e.message` in the catch block, but the blank page suggests the error display is either not rendering or the component crashed before reaching the error state.

### Issue #3
- **Severity:** 🟡 minor
- **Where:** Concept extraction (`POST /goals/{id}/concepts:extract`)
- **What I did:** Uploaded a real PDF; watched the "Analyzing material…" stage.
- **What I expected:** Concepts extracted on the first attempt.
- **What happened:** The LLM returned malformed JSON 3 times (`JSONDecodeError`), triggering escalation from `claude-haiku-4-5-20251001` to `claude-sonnet-4-6`. Total time ~44s for concept extraction. Eventually succeeded with 24 concepts.
- **Log lines:**
  ```
  2026-07-22T16:00:26+0800 WARNING tracelearn.llm extract_concepts attempt 1/3 failed ... JSONDecodeError
  2026-07-22T16:00:30+0800 WARNING tracelearn.llm extract_concepts attempt 2/3 failed ... JSONDecodeError
  2026-07-22T16:00:34+0800 WARNING tracelearn.llm extract_concepts attempt 3/3 failed ... JSONDecodeError
  2026-07-22T16:00:34+0800 WARNING tracelearn.llm extract_concepts escalating claude-haiku -> claude-sonnet after 3 failed attempts
  2026-07-22T16:00:51+0800 INFO    tracelearn.llm extract_concepts ok (model=claude-sonnet-4-6, attempt=1/2, 16792ms)
  ```
- **Screenshot:** `concept_extraction_retry.png` (if available)
- **Reproducible?** always (on this document) — happened on both goals tested
- **Notes:** This is the "known soft spot" from the test guide. The retry+escalation mechanism works, but adds ~44s of wait time. The JSON parse failures are likely from the LLM returning markdown code fences or extra text around the JSON.

---

## 3. Free-exploration observations
Things that aren't clean bugs but are worth noting — confusing UX, unclear copy, slow/frozen-looking waits, layout issues, ideas. Bullet points are fine.

- The blank page is the worst UX issue — a user with no technical knowledge would think the app crashed.
- The concept extraction takes ~44s with retries. The "Analyzing material…" progress bar helps, but 44s feels long.
- The `generatePlan()` LLM call takes ~16-30s (sonnet model). Combined with the 422 failure, the user waits 30s for nothing.

---

## 4. The known soft spots — did you hit them?
- **Onboarding malformed-JSON retry:** saw it? y/n — how many times / did retry fix it?
  - Yes — 3 JSONDecodeErrors during concept extraction, escalated to sonnet, then succeeded.
- **Docker data reset on rebuild** (if you used Docker): N/A — tested with local uvicorn.
- **Long-operation UI feedback** (does it look frozen?): Spinners work during loading, but after 422 failure the UI goes blank — no feedback at all.
- **Language toggle mid-flow:** Not tested — blocked by plan generation failure.

---

## 5. Overall impression
- Did the full loop (onboard → diagnostic → plan → replan) feel usable as a real student? **2/5** — The onboarding flow (goal → concepts → diagnostic) works well with real LLM. But the plan generation failure is a complete blocker. The user cannot get past the roadmap reveal.
- Single biggest thing to fix before showing this to anyone: The LLM plan generation prompt needs to respect the `weekly_hours` constraint so the validator passes. And the frontend must show a clear error + retry when plan generation fails.

---

## 6. Files I'm sending (zip contents)
- [x] this report (`V1_DISCOVERY_REPORT_memberB.md`)
- [x] `backend/logs/tracelearn.log` (+ rotated backups if any)
- [x] screenshots (`blank_roadmap.png`)
- [ ] (optional) `backend/tracelearn.db` if a data/state bug is involved
- [x] confirmed **NO** `backend/.env` in the zip
