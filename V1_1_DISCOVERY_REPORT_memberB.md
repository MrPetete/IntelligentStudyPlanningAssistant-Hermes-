# V1.1 Discovery Report — Member B

**Tester:** Member B
**Date tested:** 2026-07-23
**OS / browser:** Windows 11 / Chrome
**Run mode:** local uvicorn (backend) + local Vite dev server (frontend), no Docker
**`/goals/*` LLM calls confirmed live:** yes — `MOCK_LLM=false`, real key, real `claude-haiku-4-5-20251001` / `claude-sonnet-4-6` / `claude-opus-4-8` traffic seen in `backend/logs/tracelearn.log`
**Commit tested (`git rev-parse --short HEAD`):** `30c1597` (dev, PR #12 merged — hours_per_day pivot + blank-page fix)

---

## 1. Summary

The V1.1 fixes landed correctly: `hours_per_day` works end to end, the roadmap screen no longer goes blank on a plan-generation failure, and the retry/error-mapping flow behaves as designed. Goal creation, document upload, concept extraction, diagnostic, plan generation, and agent replanning are all live against the real model (not mock) — confirmed via `backend/logs/tracelearn.log`.

The blocker from the previous round (D-01, 422 on every plan generation) is gone. What's left is a **product-behavior gap**, not a bug: task completion has no daily gating and no comprehension check, so the app currently lets a learner check off every day's tasks in one sitting with zero verification of what they actually learned. That defeats the point of a day-by-day study plan. This report also flags a real replan cost problem this gap causes, and a dashboard issue found during testing.

---

## 2. What I tested and confirmed working

| Step | Result | Note |
|---|---|---|
| Goal creation (`hours_per_day`, not `weekly_hours`) | ✅ works | Field renamed correctly end to end; payload key is `hours_per_day` |
| Hours/day cap on the goal form | ✅ works | Selector caps to hours left before deadline as designed |
| Document upload → concept extraction (real LLM) | ⚠️ works, slow | See Issue #3 (JSON parse retries) |
| Diagnostic generation + scoring | ✅ works | Per-concept scores recorded as evidence |
| Plan generation (real LLM, day-accurate budget) | ✅ works | No more 422 on every attempt — the V1.1 budget fix holds |
| Plan-generation failure → Retry state | ✅ works | Confirmed the blank-white-page bug (D-02) is fixed; failure now shows a card with Retry |
| Task completion (`POST /tasks/{id}/complete`) | ⚠️ works, but see Issue #1 | No gating, no undo, and can trigger slow synchronous replans |
| Agent replan (`decide_replan`, real `claude-opus-4-8`) | ✅ works | Confirmed `new_version` and `no_change` decisions recorded correctly with reasoning + tool trace |
| Version history / diff | ✅ works | Carried-forward tasks preserved correctly across versions |
| Dashboard | ❌ broken | See Issue #2 |

---

## 3. Issues found

### Issue #1 — 🔴 blocker (product gap) — no daily gating, no comprehension check, tasks can't be unchecked
- **Where:** `frontend/src/views/Home.vue` (`checkOff()`), `backend/routers/evidence.py` (`complete_task`)
- **What I did:** Opened "Your tasks" and checked off tasks from multiple future days in a row, with no obstacle.
- **What I expected:** Only today's tasks should be checkable. Future days should be locked (greyed out) until today's are done. After finishing today's tasks, a short quiz on today's concepts should appear before tomorrow unlocks.
- **What actually happened:**
  - Every task in every day of the current plan version is checkable from the moment the plan is generated — `Home.vue` renders `tasks.value` flat, with no day-based lock. `t.day` is only shown as a label (`Home.vue:91`), never used to gate the checkbox.
  - There is no server-side gate either: `complete_task` in `evidence.py` accepts any `task_id` belonging to the current plan version, in any order, regardless of `day` (`evidence.py:47-79`).
  - Once checked, a task cannot be unchecked. `Home.vue` only renders a checkbox when `t.status !== 'done'` (`Home.vue:86`); the done state has no click handler. There is no `PATCH`/uncheck endpoint on the backend at all — I confirmed by grep that `POST /tasks/{id}/complete` is the only task-mutating route.
  - There is no comprehension check anywhere in the day loop. The only quiz in the app is the one-time onboarding diagnostic (`routers/diagnostic.py`) — nothing quizzes the user again after a day's tasks are done.
- **Reproducible?** always
- **Notes / proposed fix (matches what we agreed on for this round):**
  1. Frontend: group `Home.vue` tasks by `t.day`; only the earliest day with any `pending` task is interactive, every later day is rendered greyed out / disabled.
  2. Backend: `complete_task` should 409 if the task's `day` is after the earliest day that still has incomplete tasks (mirrors the existing 409 append-only guard pattern already used for superseded plan versions — see `evidence.py:56-66`).
  3. Add a small end-of-day quiz, gated on: all of that day's tasks are `done`. Store it like the onboarding diagnostic (reuse `Diagnostic`/scoring shape) but scoped to that day's concepts, and reuse the existing `quiz_result` evidence type + `quiz_fail_threshold` trigger (`config.py` `TRIGGERS`) — this plumbing already exists, it's just never invoked mid-plan today.
  4. Passing the day's quiz unlocks the next day. Failing should not silently unlock — see Issue #1a below for why that has to stay a *deterministic* decision, not "every wrong answer replans."

### Issue #1a — 🟠 major (design correction, but important) — don't replan on every single quiz failure
- **Context:** this is the "keep it logical" note attached to Issue #1 — worth calling out separately since it changes the plan for #1.
- **What I want to avoid:** wiring "user got a question wrong" directly to "call the agent." The trigger layer (`backend/agent/triggers.py`) already exists specifically to prevent this — `evaluate_triggers()` requires `min_evidence_events` (currently 3, `config.py TRIGGERS`) before it will even consider firing, and a single `quiz_result` below `quiz_fail_threshold` (0.50) is already one of its three fire conditions (`triggers.py:78-87`).
- **What actually happens today (confirmed in logs) if this isn't respected:** every `POST /tasks/{id}/complete` calls `_evaluate_and_maybe_run()` (`evidence.py:78`), which calls the agent's `decide_replan` synchronously if a trigger fires, and `decide_replan` is a real `claude-opus-4-8` call. In `tracelearn.log` these ranged from **9.4s to 57.3s** per call (lines around `01:36:41`–`01:43:28`), and the whole HTTP response is blocked on it — e.g. `POST /tasks/66/complete -> 200 (57270ms)`. If every day-end quiz failure calls the agent directly instead of going through the trigger gate, the user would eat a ~10-60s freeze after nearly every quiz, and the agent would be invoked far more often than the "the LLM never runs unbounded" guarantee the trigger layer exists to protect (see `triggers.py` docstring).
- **Recommendation:** keep the quiz result as evidence only. Let it flow through the same `_evaluate_and_maybe_run` path task completion already uses, so the existing `min_evidence_events` guard and `quiz_fail_threshold` decide whether a replan is warranted — not a hardcoded "1 wrong quiz = replan" rule in the day-gate logic. This is already 90% built; it just needs the day-quiz to write a `quiz_result` evidence row per concept (same as `diagnostic.py:112-116` does) instead of being a dead-end UI popup.
- **Also flag while we're here:** because that agent call is synchronous and can take up to ~57s, whichever endpoint ends up calling it after a day-quiz should not block the quiz-result screen for a minute. Worth a quick discussion on whether that's in scope for V1.1 or a fast-follow.

### Issue #1b — 🟠 major — replan must only touch future days, never rewrite the past
- **Where:** `backend/agent/planmerge.py` (`merge_tasks`), `backend/agent/orchestrator.py`
- **What I checked:** whether a replan can alter/duplicate tasks on days already completed.
- **What I found:** this part is actually already correct and worth confirming in writing so nobody "fixes" it by accident. `merge_tasks()` carries every parent task forward with its original `status`/`completed_at` untouched (`planmerge.py:26-27`, `41-49`) and only appends new delta tasks as fresh `pending` work (`planmerge.py:50-58`). The validator's Rule 3 independently rejects any proposed task dated before `today` (`validator.py:98-99`). I confirmed this in the live DB: goal 5's remediation tasks (e.g. task ids 55/56/72-76/97 in `tasks` table) were all inserted on **today-or-later** days relative to when they were generated, never on an already-`done` day.
- **Action needed:** none for this specific behavior — just keep it as a hard requirement when building the day-quiz-triggered replan in Issue #1, since it's exactly the constraint from that request ("only put tasks in the future, not in the past like the demo").

### Issue #2 — 🟠 major — Dashboard needs fixing (mastery + trend numbers are not meaningful)
- **Where:** `frontend/src/views/Dashboard.vue`
- **What I did:** Completed several tasks across two different plan versions on the same goal, then opened the Dashboard.
- **What I expected:** per-concept mastery reflecting real progress, and a trend chart showing task completion changing over versions.
- **What actually happened:**
  - **Mastery bars are wrong once no diagnostic score exists for a concept.** The fallback heuristic (`Dashboard.vue:29-36`) computes mastery per concept as `done / tasks.length` using **only the current version's task list**. Since replans carry old tasks forward and append new ones (Issue #1b), a concept that was fully mastered in v1 but gets a new remediation task appended in v2 will show its mastery *drop*, because the denominator grew — this reads as "you got worse" when the opposite happened.
  - **The trend chart is not a trend.** `donePerVersion` (`Dashboard.vue:88-92`) recomputes `plan.value.tasks.filter(done)` — which is always the **current** version's task list — for every point on the x-axis. Every version tag (`v6`, `v7`, `v8`, `v9`...) plots the identical current "done count," so the line is always flat. I confirmed this against goal 5 in the DB, which has 9 plan versions (`plan_versions` table) with different task/done counts per version, but the chart cannot show that difference because it never fetches each version's own task list — only `store.currentPlan`.
  - **No empty/loading distinction.** If `load()` throws (I triggered this by switching goals mid-request), the catch block only `console.error`s (`Dashboard.vue:41`) — the user sees stale or blank charts with no on-screen indication anything went wrong.
- **Reproducible?** always, on any goal with ≥2 plan versions
- **Notes:** fixing the trend chart needs one more read per version (`api.getVersion(goalId, v.version_no)` for each entry in `store.versions`, same call `Roadmap.vue:20` already uses) instead of reusing `store.currentPlan` for every point. The mastery heuristic should probably prefer the latest diagnostic/quiz evidence per concept over the raw done-ratio, especially once Issue #1's day-quizzes start producing real per-concept scores mid-plan — that data will make this heuristic mostly unnecessary.

### Issue #3 — 🟡 minor — concept extraction still retries on malformed JSON (carried over from last round, not fixed, not worse)
- **Where:** `backend/agent/hermes_client.py` / `backend/agent/llm_client.py`, model `claude-haiku-4-5-20251001`
- **What happened:** Same as the prior discovery report — `claude-haiku-4-5-20251001` fails the JSON-prefill continuation 3/3 times on most concept-extraction calls, escalating to `claude-sonnet-4-6`, which then succeeds. Reproduced twice this round.
- **Log evidence:**
  ```
  2026-07-23T01:27:45+0800 WARNING tracelearn.llm extract_concepts attempt 1/3 failed (model=claude-haiku-4-5-20251001, tier=1/3, 4376ms): JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
  2026-07-23T01:27:49+0800 WARNING tracelearn.llm extract_concepts attempt 2/3 failed (model=claude-haiku-4-5-20251001, tier=1/3, 3654ms): JSONDecodeError: ...
  2026-07-23T01:27:54+0800 WARNING tracelearn.llm extract_concepts attempt 3/3 failed (model=claude-haiku-4-5-20251001, tier=1/3, 3797ms): JSONDecodeError: ...
  2026-07-23T01:27:54+0800 WARNING tracelearn.llm extract_concepts escalating claude-haiku-4-5-20251001 -> claude-sonnet-4-6 after 3 failed attempts
  2026-07-23T01:28:22+0800 INFO    tracelearn.llm extract_concepts ok (model=claude-sonnet-4-6, tier=2/3, attempt=1/2, 27636ms)
  ```
  Second occurrence at `01:32:25`–`01:32:42`, same signature.
- **Reproducible?** frequently, not always (self-heals via the escalation ladder both times)
- **Notes:** not a blocker — the ladder is doing its job — but it costs ~15-45s per extraction. Might be worth revisiting whether haiku's prefill handling on this endpoint is fixable with a prompt tweak, independent of this round's scope.

---

## 4. Backend logs / DB evidence referenced above
- Full log: `backend/logs/tracelearn.log` (attach with this report)
- DB counts at time of testing: `goals=5`, `plan_versions=9`, `tasks=123`, `evidence=80`, `concepts=46`, `diagnostics=3`, `agent_decisions=21`
- Replan latency samples pulled from the log (`decide_replan ok` lines, all real `claude-opus-4-8` calls): 9.4s, 9.8s, 10.9s, 14.4s, 21.6s, 26.4s, 27.5s, 27.7s, 34.4s, 36.8s, 41.3s, 57.3s — median well above what a UI should block a task-checkbox click on.

---

## 5. Proposed scope for this round (what we agreed)
1. **Day gating on tasks** — only the earliest incomplete day is checkable; later days render locked/greyed out. (Issue #1)
2. **Uncheck support** — a task should be revertible, at least on the current day, so a misclick doesn't require a full replan cycle to fix. (Issue #1 — not in the code at all today)
3. **End-of-day comprehension quiz** — triggered once all of a day's tasks are checked; scoped to that day's concepts; reuses the existing diagnostic scoring shape and `quiz_result` evidence type. (Issue #1)
4. **Replan stays trigger-gated, not quiz-gated** — a day-quiz result is evidence, not a direct replan call; the existing `min_evidence_events` / `quiz_fail_threshold` trigger logic decides if/when the agent runs, so we don't fire an expensive `claude-opus-4-8` call on every single wrong answer. (Issue #1a)
5. **Replan only edits future days** — already true today (Issue #1b); keep it that way when building #3/#4.
6. **Fix the Dashboard trend + mastery charts** so they reflect real per-version history instead of re-plotting the current version's numbers at every x-axis point. (Issue #2)

## 6. Out of scope for this round
- Fixing the haiku JSON-prefill retry rate (Issue #3) — tracked, not blocking.
- Making the replan call asynchronous/non-blocking — flagged in Issue #1a as worth a follow-up discussion, not committed to this round.

---

## 7. Files to attach when sharing this report
- [x] this report (`V1_1_DISCOVERY_REPORT_memberB.md`)
- [x] `backend/logs/tracelearn.log`
- [ ] screenshots (dashboard flat-trend, task list with no day gating) — add before sending if needed
- [x] confirmed **NO** `backend/.env` or API key included
