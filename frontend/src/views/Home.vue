<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import store, { api, refreshVersions } from '../store.js'
import { pollForNewDecision } from '../replanPoll.js'
import ConceptTag from '../components/ConceptTag.vue'
import OfflineBanner from '../components/OfflineBanner.vue'
import CheckpointQuiz from '../components/CheckpointQuiz.vue'

const { t } = useI18n()

const tasks = ref([])
const busy = ref(false)
const toast = ref('')
const loadError = ref(null)
const updatingPlan = ref(false)   // non-blocking "a replan is queued" indicator

// Which unit's quiz panel is currently open (taking OR viewing a past result).
// A Set so the toggle button per unit is independent of every other unit's.
const expandedQuiz = ref(new Set())
function toggleQuiz(unitKey) {
  if (expandedQuiz.value.has(unitKey)) expandedQuiz.value.delete(unitKey)
  else expandedQuiz.value.add(unitKey)
}

// A finished checkpoint's full result (scores + per-question breakdown),
// keyed by unit — persisted so re-opening the panel re-shows the real result
// instead of re-generating a fresh quiz or losing it on navigation/refresh.
function resultsStorageKey() { return `tl_checkpoint_results_${store.goalId}` }
function loadCheckpointResults() {
  try { return JSON.parse(localStorage.getItem(resultsStorageKey()) || '{}') }
  catch { return {} }
}
function saveCheckpointResult(unitKey, result) {
  const all = loadCheckpointResults()
  all[unitKey] = result
  localStorage.setItem(resultsStorageKey(), JSON.stringify(all))
  checkpointResults.value = all
}
const checkpointResults = ref({})

const versionNo = computed(() => store.currentPlan?.version_no ?? 1)

// Days already cleared by a checkpoint (pass or fail — either way the day is
// "done" and evidence has been recorded; a fail feeds the trigger gate rather
// than blocking forward progress forever). Persisted per-goal so a refresh
// doesn't re-lock a day the learner already cleared.
function checkpointStorageKey() { return `tl_checkpoint_days_${store.goalId}` }
function loadClearedDays() {
  try { return new Set(JSON.parse(localStorage.getItem(checkpointStorageKey()) || '[]')) }
  catch { return new Set() }
}
function markDayCleared(day) {
  const s = loadClearedDays(); s.add(day)
  localStorage.setItem(checkpointStorageKey(), JSON.stringify([...s]))
}
const clearedDays = ref(new Set())

// Which plan-version diff introduced each task, so replanned work can render
// in its own "Remediation #N" block instead of blending into a done day
// (B-V2-2). Full-merge replanning carries every parent task forward as a
// brand-new row under the new version, matched only by (description, day) —
// so a task's *current* id never matches the id in an older version's diff.
// We resolve identity by (description, day) against the live task list
// instead (see TraceLearn_Package/Member A_Progress/A-V2-5_VERSION_TAGGING_DESIGN_NOTE.md).
const remediationSources = ref([]) // [{ versionNo, keys: Set<"description__day"> }]

function taskKey(t) { return `${t.description}__${t.day}` }

async function loadRemediationBlocks() {
  const agentVersions = store.versions
    .filter((v) => v.created_by === 'agent')
    .sort((a, b) => a.version_no - b.version_no)
  const blocks = []
  for (const v of agentVersions) {
    try {
      const diff = await api.getDiff(store.goalId, v.version_no - 1, v.version_no)
      const keys = new Set((diff.added_tasks || []).map(taskKey))
      if (keys.size) blocks.push({ versionNo: v.version_no, keys })
    } catch {
      // A version whose parent no longer resolves (shouldn't happen under
      // append-only history) just contributes no block rather than breaking load.
    }
  }
  remediationSources.value = blocks
}

async function load() {
  loadError.value = null
  try {
    await refreshVersions(store.goalId)
    tasks.value = store.currentPlan ? [...store.currentPlan.tasks] : []
    clearedDays.value = loadClearedDays()
    checkpointResults.value = loadCheckpointResults()
    await loadRemediationBlocks()
  } catch (e) {
    // B-RC2-3: a failed load must not render as "0 tasks" — keep whatever was
    // on screen and show a retry banner instead of silently zeroing out.
    loadError.value = e
  }
}
onMounted(load)

// Resolve each remediation source's task identities against the LIVE task
// list (current ids), claiming each task for at most one block.
const remediationUnits = computed(() => {
  const claimed = new Set()
  return remediationSources.value.map((b, i) => {
    const blockTasks = tasks.value.filter((t) => {
      if (claimed.has(t.id) || !b.keys.has(taskKey(t))) return false
      claimed.add(t.id)
      return true
    })
    return {
      kind: 'remediation',
      key: `remediation-${b.versionNo}`,
      label: i + 1,
      tasks: blockTasks,
      conceptIds: [...new Set(blockTasks.map((t) => t.concept_id).filter((c) => c != null))]
    }
  }).filter((u) => u.tasks.length)
})
const remediationTaskIds = computed(() =>
  new Set(remediationUnits.value.flatMap((u) => u.tasks.map((t) => t.id))))

// ---- day grouping + gating (B-RC2-1) --------------------------------------
// Tasks claimed by a remediation block render there instead of under their day.
const byDay = computed(() => {
  const map = {}
  for (const t of tasks.value) {
    if (remediationTaskIds.value.has(t.id)) continue
    const d = t.day || 'unscheduled'
    ;(map[d] ||= []).push(t)
  }
  return Object.entries(map).sort((a, b) => a[0].localeCompare(b[0]))
})

// Unified, ORDERED list of interactive units: original days first (date
// order), then each remediation block in the order its replan happened.
// Gating (B-RC2-1) applies uniformly across this whole sequence — the same
// "earliest incomplete unit is interactive, everything after is locked" rule
// that governed days now also governs remediation blocks (B-V2-2: reuse the
// day-gate/quiz function, don't fork a second gating system).
const units = computed(() => [
  ...byDay.value.map(([day, list]) => ({ kind: 'day', key: day, label: day, tasks: list })),
  ...remediationUnits.value.map((u) => ({ ...u, label: `Remediation #${u.label}` }))
])

// The active (interactive) unit is the earliest one that still has a pending
// task OR whose checkpoint hasn't been cleared yet, even if all its tasks are
// done. Everything strictly after it is locked.
const activeUnit = computed(() => {
  for (const u of units.value) {
    const allDone = u.tasks.length > 0 && u.tasks.every((t) => t.status === 'done')
    if (!allDone || !clearedDays.value.has(u.key)) return u.key
  }
  return null // every unit done + cleared
})
function unitIndex(key) { return units.value.findIndex((u) => u.key === key) }
function isDayLocked(key) { return activeUnit.value !== null && unitIndex(key) > unitIndex(activeUnit.value) }
function isDayActive(key) { return key === activeUnit.value }

// A unit's quiz button unlocks purely on "all of this unit's own tasks are
// done" — independent of the day-locking sequence, so a learner can revisit
// an already-cleared earlier unit's result at any time, and a later unit's
// button unlocks the moment ITS tasks are done even if an earlier unit's
// checkpoint hasn't happened yet (checkpoint completion, not the checkbox
// gate, is what advances activeUnit — see activeUnit above).
function unitAllDone(u) { return u.tasks.length > 0 && u.tasks.every((t) => t.status === 'done') }
function quizLabel(u) {
  if (expandedQuiz.value.has(u.key)) return t('home.hideResult')
  return checkpointResults.value[u.key] ? t('home.viewResult') : t('home.takeQuiz')
}

// A task may live in a day OR a remediation block — resolve which unit key
// gates it so checkOff/undoCheck stay a single code path for both.
function unitKeyForTask(task) {
  if (remediationTaskIds.value.has(task.id)) {
    return remediationUnits.value.find((u) => u.tasks.some((t) => t.id === task.id))?.key
  }
  return task.day || 'unscheduled'
}

// ---- async replan (B-RC2-2): poll, never block ----------------------------
async function watchForReplan() {
  const knownIds = store.decisions.map((d) => d.id)
  updatingPlan.value = true
  const fresh = await pollForNewDecision(store.goalId, knownIds)
  updatingPlan.value = false
  if (fresh) {
    await refreshVersions(store.goalId)
    tasks.value = [...store.currentPlan.tasks]
    await loadRemediationBlocks() // a landed replan may introduce a new Remediation #N block
    if (fresh.resulting_plan_version_id) {
      toast.value = t('app.planUpdatedToast', { version: store.currentPlan.version_no })
      setTimeout(() => (toast.value = ''), 5000)
    }
  }
}

async function checkOff(task) {
  if (isDayLocked(unitKeyForTask(task)) || task.status === 'done') return
  busy.value = true
  try {
    const res = await api.completeTask(task.id)
    task.status = 'done'
    if (res.trigger_fired) {
      watchForReplan() // fire-and-poll; does not block the checkbox
    } else {
      toast.value = t('home.progressRecorded')
      setTimeout(() => (toast.value = ''), 2400)
    }
  } catch (e) {
    toast.value = t('home.error', { message: e.message })
    setTimeout(() => (toast.value = ''), 3000)
  } finally { busy.value = false }
}

async function undoCheck(task) {
  // Uncheck is only offered on the CURRENT interactive unit (day OR
  // remediation block — spec: "a misclick on the current day"), not on
  // earlier already-cleared units — those are done history.
  if (!isDayActive(unitKeyForTask(task))) return
  busy.value = true
  try {
    await api.uncompleteTask(task.id)
    task.status = 'pending'
  } catch (e) {
    toast.value = t('home.error', { message: e.message })
    setTimeout(() => (toast.value = ''), 3000)
  } finally { busy.value = false }
}

function onCheckpointDone(unitKey, { passed, result }) {
  saveCheckpointResult(unitKey, result)
  markDayCleared(unitKey)
  clearedDays.value = loadClearedDays()
  toast.value = passed ? t('home.checkpointPassed') : t('home.checkpointFailed')
  setTimeout(() => (toast.value = ''), 4000)
  if (result?.trigger_fired) watchForReplan()
}

async function simulate() {
  busy.value = true
  toast.value = ''
  try {
    const knownIds = store.decisions.map((d) => d.id)
    const res = await api.simulate(store.goalId, 'normalization_failure')
    if (res.trigger_fired) {
      toast.value = t('home.replanQueued')
      watchForReplan(knownIds)
    }
  } catch (e) {
    toast.value = t('home.error', { message: e.message })
    setTimeout(() => (toast.value = ''), 3000)
  } finally { busy.value = false }
}

const pending = computed(() => tasks.value.filter((t) => t.status !== 'done'))
const done = computed(() => tasks.value.filter((t) => t.status === 'done'))
</script>

<template>
  <div class="page">
    <div class="eyebrow" style="color:var(--user);">{{ $t('home.eyebrow') }}</div>
    <h1>{{ $t('home.title') }}</h1>
    <p class="muted">{{ $t('home.subtitle', { version: versionNo }) }}</p>

    <OfflineBanner :error="loadError" @retry="load" />

    <div v-if="toast" class="card" style="padding:10px 14px;background:var(--agent-soft);border-color:var(--agent);color:var(--agent);margin-bottom:16px;">{{ toast }}</div>
    <div v-if="updatingPlan" class="card" style="padding:10px 14px;background:var(--surface-2);margin-bottom:16px;">
      <span class="faint">⏳ {{ $t('home.updatingPlan') }}</span>
    </div>

    <div class="row" style="gap:12px;margin-bottom:16px;">
      <div class="card" style="flex:1;padding:14px;">
        <div class="label">{{ $t('home.pending') }}</div>
        <div style="font-size:22px;font-weight:700;">{{ pending.length }}</div>
      </div>
      <div class="card" style="flex:1;padding:14px;">
        <div class="label">{{ $t('home.done') }}</div>
        <div style="font-size:22px;font-weight:700;color:var(--user);">{{ done.length }}</div>
      </div>
      <div class="card" style="flex:1;padding:14px;">
        <div class="label">{{ $t('home.planVersion') }}</div>
        <div style="font-size:22px;font-weight:700;">v{{ versionNo }}</div>
      </div>
    </div>

    <div v-if="!tasks.length && !loadError" class="card" style="padding:8px 8px 4px;">
      <div class="empty">{{ $t('home.noTasks') }}</div>
    </div>

    <div v-for="u in units" :key="u.key" class="card day-card"
         :class="{ locked: isDayLocked(u.key), remediation: u.kind === 'remediation' }" style="padding:8px 8px 4px;margin-bottom:12px;">
      <div class="row day-head">
        <strong>{{ u.kind === 'remediation' ? u.label : u.label }}</strong>
        <span v-if="u.kind === 'remediation'" class="badge agent" style="font-size:11px;">{{ $t('home.remediationBadge') }}</span>
        <span v-if="isDayLocked(u.key)" class="faint" style="font-size:12px;">🔒 {{ $t('home.lockedHint') }}</span>
        <span class="spacer"></span>
      </div>
      <div v-for="t in u.tasks" :key="t.id" class="task-row row" :class="{ done: t.status === 'done', locked: isDayLocked(u.key) }">
        <button v-if="t.status !== 'done'" class="check" @click="checkOff(t)"
                :disabled="busy || isDayLocked(u.key)" :title="$t('home.markDone')">○</button>
        <button v-else-if="u.key === activeUnit" class="check done" @click="undoCheck(t)"
                :disabled="busy" :title="$t('home.undo')">✓</button>
        <span v-else class="check done">✓</span>
        <div class="col" style="gap:3px;min-width:0;">
          <div class="row" style="gap:8px;">
            <ConceptTag :term="t.canonical_term" />
          </div>
          <div :style="t.status === 'done' ? 'text-decoration:line-through;color:var(--text-faint)' : ''">{{ t.description }}</div>
        </div>
        <span class="spacer"></span>
        <span class="faint">{{ t.est_minutes }} min</span>
      </div>

      <div class="row quiz-toggle-row">
        <span class="spacer"></span>
        <span v-if="!unitAllDone(u)" class="faint" style="font-size:12px;">{{ $t('home.quizLockedHint') }}</span>
        <button class="primary" :disabled="!unitAllDone(u)" @click="toggleQuiz(u.key)">
          {{ quizLabel(u) }}
        </button>
      </div>

      <CheckpointQuiz v-if="expandedQuiz.has(u.key)" :goal-id="store.goalId"
                      :day="u.kind === 'remediation' ? null : u.key"
                      :concept-ids="u.kind === 'remediation' ? u.conceptIds : null"
                      :initial-result="checkpointResults[u.key]"
                      @done="(payload) => onCheckpointDone(u.key, payload)" />
    </div>

    <div class="row" style="justify-content:flex-end;margin-top:18px;">
      <button @click="simulate" :disabled="busy">{{ $t('home.simulate') }}</button>
    </div>
  </div>
</template>

<style scoped>
.day-card.locked { opacity: .55; }
.day-card.remediation { border-color: var(--agent); }
.day-head { padding: 8px 6px 4px; }
.quiz-toggle-row { padding: 10px 12px; gap: 10px; align-items: center; border-top: 1px solid var(--border); }
.task-row { padding: 12px; gap: 12px; border-bottom: 1px solid var(--border); }
.task-row:last-child { border-bottom: 0; }
.task-row.locked { pointer-events: none; }
.check { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
  border: 2px solid var(--border); background: var(--surface); color: var(--text-faint); flex: none; }
.check.done { background: var(--user); border-color: var(--user); color: #fff; }
button.check { cursor: pointer; }
button.check:hover:not(:disabled) { border-color: var(--user); color: var(--user); }
button.check:disabled { cursor: default; opacity: .6; }
</style>
