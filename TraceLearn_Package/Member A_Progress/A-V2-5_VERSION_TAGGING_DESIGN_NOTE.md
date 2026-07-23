# A-V2-5 — task read shape for "Remediation #N" blocks (design finding)

**Status:** design pass done, **no schema change recommended.** Needs B's sign-off
on the grouping approach before B builds the UI.

## The ask (from B-f4)
Render replanned tasks in their own "Remediation #N" block instead of blended
into a done day. B needs the task read shape to let a consumer tell which
plan-version *introduced* each task.

## Key finding — `plan_version_id` on the CURRENT plan can't do it
Replanning is **full-merge** (`agent/planmerge.py::merge_tasks`): version N+1 =
every parent task carried forward as **brand-new rows** under the new
`plan_version_id` + the delta appended. So on the latest plan, **every** task —
original *and* remediation — carries the **same** `plan_version_id` (the latest
version's). Exposing `plan_version_id` on `TaskOut` would therefore NOT
distinguish remediation from original work. It's a real dead-end, not an
oversight.

## Recommended approach — derive it from the existing version read surface
The append-only version history already encodes origin, and the read endpoints
already expose it. No new field, no migration:

- `GET /goals/{id}/plan/versions` → ordered `[{version_no, created_by, created_at}]`.
  `created_by == "agent"` marks a replan; its `version_no` is the remediation
  block number source.
- `GET /goals/{id}/plan/diff?from={N-1}&to={N}` → `added_tasks` is exactly the
  tasks version N introduced (carried-forward tasks match on `(description, day)`
  and read as unchanged, so they never show up as added). `removed_tasks` is
  always empty under full-merge.

So "Remediation block for version N" = `plan_diff(from=N-1, to=N).added_tasks`.
Walk the agent-created versions from the versions list; each yields one block.

**Verified:** `backend/tests/test_v1_2_fixes.py::test_diff_distinguishes_v2_remediation_from_v1_tasks`
builds a v1 (user) + v2 (agent delta) goal and asserts the diff surfaces only the
v2-introduced task, with `removed_tasks == []`.

## When a schema change WOULD be justified (fallback, not now)
If the version-derived grouping fights the per-day layout in practice (e.g. B
needs an origin tag inline on every task in the *current* plan view without an
extra diff call per version), add a dedicated `origin_version_no` column on
`Task` that `merge_tasks` **preserves on carry-forward** and stamps to the new
`version_no` for delta tasks — then expose it on `TaskOut`. That touches
`models.py`, `agent/planmerge.py`, `agent/tools.py::create_plan_version`, the
startup migration (idempotent `ADD COLUMN`, like R2-01's `hours_per_day`), and
`TaskOut`. Prefer the derived approach above unless B's design review shows it's
insufficient.

## Decision needed from B
1. Is the versions+diff derivation enough to build the "Remediation #N" blocks?
2. If not, confirm the `origin_version_no` column shape above and we land it as a
   coordinated schema + migration change (mirrors the RC2 endpoint contract work).
