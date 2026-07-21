import { reactive } from 'vue'
import api from './api.js'

/**
 * App-wide reactive store. Keeps state simple (composables + reactive) per the
 * frontend contract — no Pinia needed for a demo app.
 */
export const store = reactive({
  goalId: null,          // current goal id
  goal: null,            // GoalOut
  concepts: [],          // ConceptOut[]
  diagnostic: null,      // DiagnosticOut
  diagnosticResult: null,// DiagnosticResult
  currentPlan: null,     // PlanVersionOut (current version)
  versions: [],          // PlanVersionSummary[]
  decisions: [],         // AgentDecisionSummary[]
  // onboarding progress flags
  onboarded: false
})

async function loadCore(goalId) {
  const [goal, concepts, versions, decisions] = await Promise.all([
    api.getGoal(goalId),
    api.getConcepts(goalId),
    api.getVersions(goalId),
    api.getDecisions(goalId)
  ])
  store.goalId = goalId
  store.goal = goal
  store.concepts = concepts
  store.versions = versions
  store.decisions = decisions
  if (versions.length) {
    store.currentPlan = await api.getCurrentPlan(goalId)
    store.onboarded = true
  }
}

export async function initGoal(goalId) {
  await loadCore(goalId)
}
export async function refreshVersions(goalId) {
  store.versions = await api.getVersions(goalId)
  store.currentPlan = await api.getCurrentPlan(goalId)
  store.decisions = await api.getDecisions(goalId)
}

export { api }
export default store
