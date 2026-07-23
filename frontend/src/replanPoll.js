import { api } from './store.js'

/**
 * Poll GET /goals/{id}/decisions for a NEW decision after a `trigger_fired`
 * response (B-RC2-2 / A-RC2-1). The backend now schedules `decide_replan` as a
 * background task — `trigger_fired: true` only means "queued", the decision
 * row doesn't exist yet on that response (decision_id is null on the async
 * path). We diff against the decision count/ids we held BEFORE the triggering
 * call, so a same-length response some ms later doesn't get misread as "done".
 *
 * Works identically for automatic replans (task complete/checkpoint submit)
 * and the explicit "Replan" button — both go background + poll per the
 * lead's decision, so neither should ever block the UI for the 15-57s an
 * opus call can take.
 *
 * @param {number} goalId
 * @param {number[]} knownIds - decision ids already visible before the trigger
 * @param {object} opts
 * @param {number} [opts.intervalMs=3000]
 * @param {number} [opts.timeoutMs=90000] - give up after this long (opus can
 *   take up to ~60s; leave headroom rather than spin forever if something's wrong)
 * @returns {Promise<object|null>} the new AgentDecisionSummary, or null on timeout
 */
export async function pollForNewDecision(goalId, knownIds, opts = {}) {
  const intervalMs = opts.intervalMs ?? 3000
  const timeoutMs = opts.timeoutMs ?? 90000
  const known = new Set(knownIds)
  const deadline = Date.now() + timeoutMs

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs))
    let decisions
    try {
      decisions = await api.getDecisions(goalId)
    } catch {
      continue // transient failure mid-poll — keep trying until the deadline
    }
    const fresh = decisions.find((d) => !known.has(d.id))
    if (fresh) return fresh
  }
  return null
}
