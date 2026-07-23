# V1.1-RC2 Discovery Report — Member B

**Tester:** Member B
**Date tested:** 2026-07-23
**OS / browser:** Windows 11 / Chrome
**Run mode:** local uvicorn (backend) + local Vite dev server (frontend), no Docker
**`/goals/*` LLM calls confirmed live:** yes — `MOCK_LLM=false`, real key, real `claude-haiku-4-5-20251001` / `claude-sonnet-4-6` / `claude-opus-4-8` traffic seen in `backend/logs/tracelearn.log` (async replan on goal 5 confirmed end to end: queued → `decide_replan ok (model=claude-opus-4-8, 48013ms)` → `agent run -> new_version (goal_id=5, plan_version_id=10, decision_id=22)`)
**Commit tested (`git rev-parse --short HEAD`):** `638a937` (dev — Member B V1.1-rc2: day gating, async replan polling, dashboard fix, i18n, multi-goal)

---

## 1. Summary

All items in `V1_1_RC2_FIXES_MEMBER_B.md` are implemented and manually tested end to end against the real backend (Member A's merged `member-a-v1_1-rc2` contracts, PR #13): daily task gating with real uncheck, non-blocking async replan with polling + toast, offline/failure state, the Dashboard trend/mastery fix, human-readable percentage scores, the collapsible Decision-View trace, multi-goal switching, and full-UI i18n (en/zh) all work as specified.

Testing surfaced a small set of follow-up refinements — none of them regressions of this round's work, all of them scope clarifications for the checkpoint-quiz and remediation UX that weren't fully speced in the RC2 doc. These are listed below as issues/observations for the next round, in priority order.

---

## 2. What I tested and confirmed working

| Step | Result | Note |
|---|---|---|
| Day gating (only earliest incomplete day interactive) | ✅ works | Later days render locked/greyed with a lock hint; checkboxes don't respond |
| Uncheck on current day (`POST /tasks/{id}/uncomplete`) | ✅ works | Only offered on the active day; persists across reload |
| Checkpoint quiz generation + submit | ✅ works | Fires once a day's tasks are all done; scoped to that day's concepts |
| Async replan (task complete / Replan button / Simulate) | ✅ works | `trigger_fired` no longer blocks the request; UI shows "updating plan," toast lands once `GET /goals/{id}/decisions` shows a new id — confirmed with a real 48s `claude-opus-4-8` call on goal 5 (decision id 22) |
| Offline/failure state | ✅ works | Network failure now shows a retry banner instead of rendering as zero tasks |
| Dashboard trend chart | ✅ works | Fetches each plan version's own task list; goal 5's 6 versions now show distinct completion counts instead of a flat line |
| Dashboard / checkpoint scores as percentages | ✅ works | Displayed as `%`, not raw decimals |
| Decision View trace toggle | ✅ works | Trace hidden by default behind "Details"; fetch only fires with `?include_trace=true` on expand |
| Goal switcher / New Goal | ✅ works | `GET /goals` populates the switcher; New Goal clears state and routes to Onboarding |
| Language switch (en/zh) mid-flow | ✅ works | Same `explanation_language` field drives both UI chrome and content immediately |

---

## 3. Issues / follow-ups found

### Issue #1 — 🟠 major — checkpoint quiz result screen doesn't show a usable score breakdown
- **Where:** `frontend/src/components/CheckpointQuiz.vue` (result view, lines 83-93)
- **What I did:** Completed a day's tasks, took the checkpoint quiz, submitted answers.
- **What I expected:** A results screen showing my score, and which specific questions I got right vs. wrong.
- **What actually happened:** The component does receive and display `per_concept_score` as a `%` per concept (`pct(score)}%` — this part isn't literally broken), but there's no question-by-question breakdown at all. The backend's `_score_answers()` (`diagnostic.py:35-56`) discards the correct answer once it's tallied — the response (`CheckpointResult`) only ever returns `per_concept_score`, never a per-question right/wrong list. So even though a percentage score does render, it reads as an unhelpfully thin result screen with no way to show which question was right/wrong or highlight the correct answer, which is the actual ask here.
- **Reproducible?** always
- **Proposed fix:**
  1. Backend: `submit_checkpoint` needs to also return a per-question breakdown — `question_id`, the learner's submitted choice, whether it was correct, and the correct option text (safe to reveal now, since the quiz is over) — e.g. a new `CheckpointResult.per_question: list[{question_id, submitted, correct_choice, is_correct}]`. `_score_answers` already computes `correct` per question internally (`diagnostic.py:52`); it just needs to also return that detail instead of only the aggregated per-concept tally.
  2. Frontend: render each question in the result view with the learner's answer highlighted green if correct / red if wrong, and show the correct option alongside a wrong answer.
- **Notes:** same shape/gap likely applies to the onboarding diagnostic result screen (`DiagnosticResult` has the same "aggregate only" limitation) — worth deciding if that should get the same treatment for consistency, or if it's out of scope since onboarding isn't a graded re-test.

### Issue #2 — 🟠 major — replan should react to *why* the quiz was failed (weakness), not just *that* it failed
- **Where:** `backend/agent/orchestrator.py` (or wherever `decide_replan`'s prompt/context is assembled), `agent/triggers.py`
- **What I checked:** whether a checkpoint failure gives the agent anything to target besides "a trigger fired."
- **What I found:** the trigger layer correctly stays deterministic (Issue #1a from the previous round — confirmed still respected, no regressions), and `quiz_result` evidence rows already carry `concept_id` + `score` (`diagnostic.py:239-243`), so the *signal* the agent needs already exists in evidence. What's not yet confirmed is whether `decide_replan`'s prompt actually surfaces per-concept weakness (which concepts scored low, which are strong) as an explicit instruction to prioritize/remediate — vs. just being told "a trigger fired, evidence attached" and left to infer it from a raw evidence dump.
- **Ask (from product/team lead):** the replanned tasks should visibly target the weak concept(s) from the failed checkpoint, not just be "more of the same." Right now this can't be confirmed as *by design* vs. *by luck* without reading the orchestrator's prompt construction directly — flagging as a review item, not a confirmed bug.
- **Reproducible?** N/A — needs a code read of the prompt-assembly step, not a UI repro.

### Issue #3 — 🔴 blocker (missing feature) — no "ahead of schedule" trigger; agent never adds forward-looking work
- **Where:** `backend/agent/triggers.py` (`evaluate_triggers`), `backend/config.py` (`TRIGGERS`)
- **What I checked:** whether finishing tasks early / being ahead of the day-by-day plan ever causes a replan.
- **What I found:** `evaluate_triggers()` only has three fire conditions today — `behind_schedule`, `low_mastery`, `quiz_fail` (`triggers.py:56-87`). There is no "ahead of schedule" case at all. A learner who finishes every day early, with time to spare before the deadline, gets nothing extra — the plan just sits there with no way to pull forward not-yet-covered concepts.
- **Ask (from product/team lead):** when a learner is meaningfully ahead of schedule, the agent should be able to add new tasks for concepts not yet scheduled, sized to how much slack is actually left before the deadline (don't overload — "the AI already plans the most optimal roadmap for the deadline," so any pulled-forward work should stay proportionate to the remaining time budget, not just dump everything at once).
- **Proposed fix:** add a fourth trigger condition (e.g. `ahead_schedule_pct`, mirroring the existing `behind_schedule_pct` shape) and give `decide_replan` the deadline + remaining slack + not-yet-scheduled concepts as context so it can size new tasks sensibly. This is new trigger-layer + prompt work, not a UI-only fix — flagging as a blocker for the *feature*, not a broken-behavior blocker.

### Issue #4 — 🟠 major — replanned tasks need a distinct "remediation" section, not appended into an already-completed day
- **Where:** `frontend/src/views/Home.vue` (day grouping / `byDay`)
- **What I checked:** where new tasks from a replan (from a quiz fail, or a future ahead-of-schedule trigger) land relative to already-cleared days.
- **What I found:** `Home.vue`'s day-gating already correctly refuses to place new tasks anywhere in the past (confirmed carried over from `planmerge.py` behavior, previous round's Issue #1b — still holds, verified no regression). But visually, `byDay` just groups every task by its `day` string and renders one card per day in date order — there's no separate "this block came from a replan" grouping. If a replan appends tasks onto a day that's *today or later* but was effectively already fully worked through, it can still visually blend into the normal day flow instead of standing out as "here's what you need to fix."
- **Ask (from product/team lead):** replanned tasks should render in their own labeled block (e.g. "Remediation #1"), separate from the normal day-by-day task list — not mixed into a day where all original tasks are already checked. Each subsequent replan gets its own numbered block (`Remediation #2`, `#3`, ...) rather than appending into an existing one, so progress on each round of remediation is trackable independently. Each remediation block needs the same checkbox + end-of-block checkpoint-quiz behavior as a normal day.
- **Proposed fix:** this needs a way to tag which plan-version delta a task came from and whether it's "remediation" vs. original scheduled work — currently `Task` has no such field (checked `models.py`; only `day`, `status`, `concept_id`, etc. exist). Smallest version: derive "remediation block N" client-side from `(day, originating plan_version_no)` since every replan is already a new immutable `PlanVersion` (`planmerge.py`) — group new tasks by which version introduced them rather than only by `day`. Needs a design pass before implementing so plan-version-derived grouping doesn't fight with the existing per-day layout.
- **Reproducible?** confirmed by inspecting `Home.vue`'s current grouping logic + the plan-version/task model; not something that can be demonstrated as a broken screen today since no explicit "remediation" UI exists yet to be broken.

### Issue #5 — 🟡 minor — quiz question accuracy vs. concept just completed
- **Where:** `backend/agent/llm_client.py` (`generate_checkpoint`/prompt), `routers/diagnostic.py` (`_concepts_for_day`)
- **What I checked:** whether checkpoint questions are scoped tightly to the specific task(s) the learner just finished, vs. the whole day's concept set.
- **What I found:** scoping already resolves correctly at the *day* level (`_concepts_for_day()` pulls concepts from that day's tasks in the latest plan version) — this part works as designed. The open question is finer-grained: whether question *content* generated by the LLM stays tightly anchored to what was just studied, or drifts to adjacent/general knowledge about the same concept. Didn't catch a clear drift case in this round's testing, but flagging since it's a prompt-quality concern that's easy to miss without reading many quiz samples.
- **Reproducible?** not reproduced as a concrete bad-question example this round — noted as a watch item, not a confirmed defect.

---

## 4. Backend logs / DB evidence referenced above

- Full log: `backend/logs/tracelearn.log` (attach with this report)
- Async replan confirmed end to end on goal 5:
  ```
  2026-07-23T03:02:09+0800 INFO  tracelearn.agent replan queued (goal_id=5, trigger=quiz_fail)
  2026-07-23T03:02:09+0800 INFO  tracelearn.agent agent run start (goal_id=5, trigger=quiz_fail)
  2026-07-23T03:02:57+0800 INFO  tracelearn.llm decide_replan ok (model=claude-opus-4-8, tier=1/1, attempt=1/2, 48013ms)
  2026-07-23T03:02:57+0800 INFO  tracelearn.agent agent run -> new_version (goal_id=5, plan_version_id=10, decision_id=22)
  ```
  Confirmed via `GET /goals/5/decisions` that decision id 22 (`resulting_plan_version_id: 10`) is visible and would be caught by the frontend's `pollForNewDecision()` (90s timeout, 3s interval — well within the observed 48s).
- Dashboard trend fix verified against goal 5's 6 plan versions (`plan_versions` ids 1-6, `created_at` 2026-07-22T17:34 → 2026-07-23T03:02) — each version's own task list now returns a distinct done-count instead of the flat line from the previous round's Issue #2.

---

## 5. Proposed scope for next round (from this session's discussion)

1. **Checkpoint result breakdown** — return + render per-question right/wrong with the correct answer highlighted (green/red). (Issue #1)
2. **Confirm/strengthen weakness-targeted replanning** — verify (or add, if missing) that `decide_replan`'s prompt explicitly surfaces per-concept weakness from checkpoint evidence, not just "a trigger fired." (Issue #2)
3. **Ahead-of-schedule trigger** — new trigger condition + prompt context so the agent can pull forward not-yet-covered concepts when a learner is ahead, sized to remaining slack before the deadline. (Issue #3)
4. **Remediation block UI** — replanned tasks render in their own numbered "Remediation #N" section (own checkboxes + own end-of-block checkpoint quiz), never appended into an already-completed day. Needs a task/plan-version tagging design pass first. (Issue #4)
5. **(Watch item, not committed)** spot-check checkpoint question specificity against the exact concept/task just completed. (Issue #5)

## 6. Out of scope / already confirmed correct, no action needed

- Replan never touching past days — still correct, re-verified this round (previous round's Issue #1b holds).
- Day gating, uncheck, async polling+toast, offline state, Dashboard trend, percentage scores, trace collapse, goal switcher, New Goal, full-UI i18n — all implemented and working per Section 2, no further action this round.

---

## 7. Files to attach when sharing this report

- [x] this report (`V1_1_RC2_DISCOVERY_REPORT_memberB.md`)
- [x] `backend/logs/tracelearn.log`
- [ ] screenshots (checkpoint result screen, dashboard trend chart) — add before sending if needed
- [x] confirmed **NO** `backend/.env` or API key included
