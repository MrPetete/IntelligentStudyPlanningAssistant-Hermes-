import { reactive } from 'vue'
import api from './api.js'
import i18n from './i18n.js'

/**
 * App-wide reactive store. Keeps state simple (composables + reactive) per the
 * frontend contract — no Pinia needed for a demo app.
 */
export const store = reactive({
  goalId: null,          // current goal id
  goal: null,            // GoalOut
  goals: [],             // GoalListItem[] — multi-goal switcher (B-RC2-7)
  concepts: [],          // ConceptOut[]
  diagnostic: null,      // DiagnosticOut
  diagnosticResult: null,// DiagnosticResult
  currentPlan: null,     // PlanVersionOut (current version)
  versions: [],          // PlanVersionSummary[]
  decisions: [],         // AgentDecisionSummary[]
  // onboarding progress flags
  onboarded: false,
  // last known-good load, so a transient offline blip doesn't have to nuke state
  lastError: null
})

// Single field drives BOTH the LLM content language and the UI chrome
// (B-RC2-8) — there is no separate UI-language setting. Every place that
// changes explanation_language (goal load, goal switch, language toggle)
// must call this so the interface follows without a page reload.
function syncLocale(lang) {
  if (lang === 'en' || lang === 'zh') i18n.global.locale.value = lang
}

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
  syncLocale(goal.explanation_language)
  if (versions.length) {
    store.currentPlan = await api.getCurrentPlan(goalId)
    store.onboarded = true
  } else {
    store.currentPlan = null
    store.onboarded = false
  }
}

export async function initGoal(goalId) {
  store.lastError = null
  try {
    await loadCore(goalId)
  } catch (e) {
    store.lastError = e
    throw e
  }
}

/** Switch the active goal (B-RC2-7) — every view keys off store.goalId, so
 * reloading core state here is enough for the whole app to follow. */
export async function switchGoal(goalId) {
  await initGoal(goalId)
}

export async function refreshGoalList() {
  store.goals = await api.getGoals()
  return store.goals
}

export async function refreshVersions(goalId) {
  store.versions = await api.getVersions(goalId)
  store.currentPlan = await api.getCurrentPlan(goalId)
  store.decisions = await api.getDecisions(goalId)
}

export async function setLanguage(goalId, lang) {
  const updated = await api.setLanguage(goalId, lang)
  store.goal = updated
  syncLocale(updated.explanation_language)
  return updated
}

export { api, syncLocale }
export default store
