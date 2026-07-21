# Fallback Demo — reproduces the core loop with zero network dependency

**Owner:** Member C
**Purpose (D18):** the graded demo must survive a live-LLM outage, a dead
Wi-Fi, or just running out of real days for evidence to accumulate.
Examiners cannot wait 3 days — this reproduces the exact same result on
demand, entirely offline.

**Guarantee:** every step below runs with `config.MOCK_LLM = True` (the
project default — do not change it). No network call, no API key, no
external dependency of any kind. If the live Hermes integration is down
during a defense, run this instead; nothing in the demo story changes.

---

## What this demonstrates

> "Here is the plan grounded in the student's own slides. The student
> struggles with Normalization — watch the evidence come in. The trigger
> fires, the Agent reads the state, reasons over the concept, and creates
> plan version 2 that inserts Normalization remediation. Here is the tool
> trace, and here is exactly why it changed."

---

## Step-by-step (cold start, reproducible by anyone)

```
cd backend
rm -f tracelearn.db        # start from a clean slate every time
python -m seed.seed        # seeds goal 1, 5 concepts, Roadmap plan version 1
python -m seed.simulate 1 normalization_failure
```

Expected output (verbatim, verified 2026-07-21):

```
$ python -m seed.seed
Seeded goal_id=1 (language=en), 5 concepts, Roadmap V1 created.
Next: POST /goals/1/simulate  {'scenario':'normalization_failure'}

$ python -m seed.simulate 1 normalization_failure
Trigger fired=True reason=low_mastery detail={'weak_concepts': {1: 0.0}, 'threshold': 0.4}
Agent result: {'decision': 'new_version', 'decision_id': 1, 'plan_version_id': 2}
```

- `reason=low_mastery` is the expected trigger — **not** `behind_schedule`.
  If you ever see `behind_schedule` here, `seed/seed.py`'s "mark everything
  but Normalization done" step has regressed — check that file, it's yours.
- `decision_id=1`, `plan_version_id=2` are deterministic on a clean DB; if
  you ran this before without clearing `tracelearn.db`, delete it first.

## Step 2 — show the defence artifacts (via the running API)

```
python -m uvicorn main:app --reload   # separate terminal, still MOCK_LLM
curl -s http://127.0.0.1:8000/goals/1/decisions/1 | python3 -m json.tool
curl -s "http://127.0.0.1:8000/goals/1/plan/diff?from=1&to=2" | python3 -m json.tool
```

Expected `decisions/1` (verbatim, verified 2026-07-21):

```json
{
    "id": 1,
    "trigger": "low_mastery",
    "evidence_snapshot": {
        "progress": {"tasks_total": 5, "tasks_done": 4, "tasks_due": 5, "tasks_incomplete": 1},
        "evidence_count": 8
    },
    "reasoning_text": "Your recent quiz on Normalization scored low and several Normalization tasks were left incomplete. I've added two remediation tasks for Normalization before moving on, because it underpins later topics.",
    "tool_trace": [
        {"tool": "get_learner_state", "args": {"goal_id": 1}, "result_summary": "goal_text, deadline, weekly_hours, explanation_language"},
        {"tool": "get_progress_summary", "args": {"goal_id": 1}, "result_summary": "tasks_total, tasks_done, tasks_due, tasks_incomplete"},
        {"tool": "get_evidence_since_last_plan", "args": {"goal_id": 1}, "result_summary": "8 items"},
        {"tool": "get_current_plan", "args": {"goal_id": 1}, "result_summary": "plan_version_id, version_no, tasks"},
        {"tool": "llm.decide_replan", "args": {"explanation_language": "en", "evidence_count": 8}, "result_summary": "decision=new_version"},
        {"tool": "validator.validate_plan", "args": {"attempt": 0}, "result_summary": "ok"},
        {"tool": "create_plan_version", "args": {"task_count": 2}, "result_summary": "version_no=2"}
    ],
    "decision": "new_version",
    "resulting_plan_version_id": 2
}
```

`plan/diff?from=1&to=2` shows 2 Normalization tasks added. **Known caveat to
narrate honestly if asked:** it currently also shows the 4 already-completed
tasks on other concepts as "removed" — this is because full-merge replanning
(team decision, see `MEMBER_C_V1_TASKLIST.md` §3) is not implemented yet on
Member A's side. If asked, say exactly that: the merge decision is made and
documented, the orchestrator change is pending, and the delta the LLM
proposes (2 new Normalization tasks) is already correct either way.

## Step 3 — bilingual variant (optional, high value, D19)

```
rm -f tracelearn.db
python -m seed.seed zh
python -m seed.simulate 1 normalization_failure
```

Confirm: `canonical_term` values (Normalization, Indexing, ...) stay English
in every table; `explanation`, task `description`, and `reasoning_text` are
Chinese. Verified 2026-07-21 — see `seed/DATA_CONTRACTS.md` §6 for the rule
this demonstrates.

## Step 4 — record it (optional but recommended)

Capture a terminal recording (`asciinema`, `script`, or a screen capture) of
Steps 1–2 once, ahead of time, as the literal worst-case fallback — something
to play back if live systems fail entirely during the defense slot. Nothing
in this file depends on that recording existing; it's an extra layer of
safety on top of "just rerun these four commands."

---

## Why this is safe to run repeatedly

- `MOCK_LLM = True` the whole way through — no API key, no network call, no
  rate limit, no latency variance.
- `rm -f tracelearn.db` before each run guarantees identical, deterministic
  output every time (verified twice in a row above).
- Nothing here touches `agent/orchestrator.py`, `routers/*.py`, `models.py`,
  or `config.py` — if the demo fails, the bug is either in `seed/seed.py` or
  `seed/simulate.py` (yours to fix) or needs reporting to Member A.
