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
const showCheckpoint = ref(false)
const checkpointResult = ref(null)

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

async function load() {
  loadError.value = null
  try {
    await refreshVersions(store.goalId)
    tasks.value = store.currentPlan ? [...store.currentPlan.tasks] : []
    clearedDays.value = loadClearedDays()
  } catch (e) {
    // B-RC2-3: a failed load must not render as "0 tasks" — keep whatever was
    // on screen and show a retry banner instead of silently zeroing out.
    loadError.value = e
  }
}
onMounted(load)

// ---- day grouping + gating (B-RC2-1) --------------------------------------
const byDay = computed(() => {
  const map = {}
  for (const t of tasks.value) {
    const d = t.day || 'unscheduled'
    ;(map[d] ||= []).push(t)
  }
  return Object.entries(map).sort((a, b) => a[0].localeCompare(b[0]))
})

// The active (interactive) day is the earliest day that still has a pending
// task OR whose checkpoint hasn't been cleared yet, even if all its tasks are
// done. Every day strictly after it is locked. Days before it (fully done +
// checkpoint-cleared) render normally but are no longer clickable either —
// there is nothing left to check off there.
const activeDay = computed(() => {
  for (const [day, list] of byDay.value) {
    const allDone = list.every((t) => t.status === 'done')
    if (!allDone || !clearedDays.value.has(day)) return day
  }
  return null // every day done + cleared
})
function isDayLocked(day) { return activeDay.value !== null && day > activeDay.value }
function isDayActive(day) { return day === activeDay.value }

const activeDayTasks = computed(() =>
  byDay.value.find(([d]) => d === activeDay.value)?.[1] || [])
const activeDayAllDone = computed(() =>
  activeDayTasks.value.length > 0 && activeDayTasks.value.every((t) => t.status === 'done'))
const activeDayNeedsCheckpoint = computed(() =>
  activeDayAllDone.value && activeDay.value && !clearedDays.value.has(activeDay.value))

// ---- async replan (B-RC2-2): poll, never block ----------------------------
async function watchForReplan() {
  const knownIds = store.decisions.map((d) => d.id)
  updatingPlan.value = true
  const fresh = await pollForNewDecision(store.goalId, knownIds)
  updatingPlan.value = false
  if (fresh) {
    await refreshVersions(store.goalId)
    tasks.value = [...store.currentPlan.tasks]
    if (fresh.resulting_plan_version_id) {
      toast.value = t('app.planUpdatedToast', { version: store.currentPlan.version_no })
      setTimeout(() => (toast.value = ''), 5000)
    }
  }
}

async function checkOff(task) {
  if (isDayLocked(task.day) || task.status === 'done') return
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
  // Uncheck is only offered on the CURRENT interactive day (spec: "a misclick
  // on the current day"), not on earlier already-cleared days — those are
  // done history, same as a plan version's carried-forward tasks.
  if (!isDayActive(task.day)) return
  busy.value = true
  try {
    await api.uncompleteTask(task.id)
    task.status = 'pending'
  } catch (e) {
    toast.value = t('home.error', { message: e.message })
    setTimeout(() => (toast.value = ''), 3000)
  } finally { busy.value = false }
}

function onCheckpointDone({ passed, trigger_fired }) {
  markDayCleared(activeDay.value)
  clearedDays.value = loadClearedDays()
  checkpointResult.value = passed
  showCheckpoint.value = false
  toast.value = passed ? t('home.checkpointPassed') : t('home.checkpointFailed')
  setTimeout(() => (toast.value = ''), 4000)
  if (trigger_fired) watchForReplan()
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

    <div v-if="toast" class="card" style="padding:10px 14px;background:var(--agent-soft);border-color:#f0cfc6;color:var(--agent);margin-bottom:16px;">{{ toast }}</div>
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

    <div v-for="[day, list] in byDay" :key="day" class="card day-card"
         :class="{ locked: isDayLocked(day) }" style="padding:8px 8px 4px;margin-bottom:12px;">
      <div class="row day-head">
        <strong>{{ day }}</strong>
        <span v-if="isDayLocked(day)" class="faint" style="font-size:12px;">🔒 {{ $t('home.lockedHint') }}</span>
        <span class="spacer"></span>
      </div>
      <div v-for="t in list" :key="t.id" class="task-row row" :class="{ done: t.status === 'done', locked: isDayLocked(day) }">
        <button v-if="t.status !== 'done'" class="check" @click="checkOff(t)"
                :disabled="busy || isDayLocked(day)" :title="$t('home.markDone')">○</button>
        <button v-else-if="day === activeDay" class="check done" @click="undoCheck(t)"
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
    </div>

    <div v-if="activeDayNeedsCheckpoint && !showCheckpoint" class="card" style="padding:16px;background:var(--user-soft);border-color:#cfe9dd;margin-bottom:16px;">
      <div class="row">
        <span>✅ {{ $t('home.dayComplete') }}</span>
        <span class="spacer"></span>
        <button class="primary" @click="showCheckpoint = true">{{ $t('home.startCheckpoint') }}</button>
      </div>
    </div>

    <CheckpointQuiz v-if="showCheckpoint" :goal-id="store.goalId" :day="activeDay" @done="onCheckpointDone" />

    <div class="row" style="justify-content:flex-end;margin-top:18px;">
      <button @click="simulate" :disabled="busy">{{ $t('home.simulate') }}</button>
    </div>
  </div>
</template>

<style scoped>
.day-card.locked { opacity: .55; }
.day-head { padding: 8px 6px 4px; }
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
