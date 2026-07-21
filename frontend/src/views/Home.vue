<script setup>
import { ref, onMounted, computed } from 'vue'
import store, { api, refreshVersions } from '../store.js'
import ConceptTag from '../components/ConceptTag.vue'

const tasks = ref([])
const busy = ref(false)
const toast = ref('')
const lastTrigger = ref(null)

const versionNo = computed(() => store.currentPlan?.version_no ?? 1)

async function load() {
  await refreshVersions(store.goalId)
  if (store.currentPlan) tasks.value = [...store.currentPlan.tasks]
}

onMounted(load)

async function checkOff(t) {
  busy.value = true
  try {
    const res = await api.completeTask(t.id)
    t.status = 'done'
    if (res.trigger_fired) {
      lastTrigger.value = res
      toast.value = 'Trigger fired — the agent is reconsidering your plan.'
      await refreshVersions(store.goalId)
      tasks.value = [...store.currentPlan.tasks]
    } else {
      toast.value = 'Progress recorded.'
      setTimeout(() => (toast.value = ''), 2400)
    }
  } catch (e) {
    toast.value = 'Error: ' + e.message
    setTimeout(() => (toast.value = ''), 3000)
  } finally { busy.value = false }
}

async function simulate() {
  busy.value = true
  toast.value = ''
  try {
    const res = await api.simulate(store.goalId, 'normalization_failure')
    if (res.trigger_fired) {
      await refreshVersions(store.goalId)
      tasks.value = [...store.currentPlan.tasks]
      toast.value = 'Simulation: evidence injected → agent created a new plan version. See Version History.'
    }
  } catch (e) {
    toast.value = 'Simulation error: ' + e.message
    setTimeout(() => (toast.value = ''), 3000)
  } finally { busy.value = false }
}

const pending = computed(() => tasks.value.filter((t) => t.status !== 'done'))
const done = computed(() => tasks.value.filter((t) => t.status === 'done'))
</script>

<template>
  <div class="page">
    <div class="eyebrow" style="color:var(--user);">Today</div>
    <h1>Your tasks</h1>
    <p class="muted">Version {{ versionNo }} · checking a task off records evidence and may trigger a replan.</p>

    <div v-if="toast" class="card" style="padding:10px 14px;background:var(--agent-soft);border-color:#f0cfc6;color:var(--agent);margin-bottom:16px;">{{ toast }}</div>

    <div class="row" style="gap:12px;margin-bottom:16px;">
      <div class="card" style="flex:1;padding:14px;">
        <div class="label">Pending</div>
        <div style="font-size:22px;font-weight:700;">{{ pending.length }}</div>
      </div>
      <div class="card" style="flex:1;padding:14px;">
        <div class="label">Done</div>
        <div style="font-size:22px;font-weight:700;color:var(--user);">{{ done.length }}</div>
      </div>
      <div class="card" style="flex:1;padding:14px;">
        <div class="label">Plan version</div>
        <div style="font-size:22px;font-weight:700;">v{{ versionNo }}</div>
      </div>
    </div>

    <div class="card" style="padding:8px 8px 4px;">
      <div v-if="!tasks.length" class="empty">No tasks yet — finish onboarding to generate your roadmap.</div>
      <div v-for="t in tasks" :key="t.id" class="task-row row" :class="{ done: t.status === 'done' }">
        <button v-if="t.status !== 'done'" class="check" @click="checkOff(t)" :disabled="busy" title="Mark done">○</button>
        <span v-else class="check done">✓</span>
        <div class="col" style="gap:3px;min-width:0;">
          <div class="row" style="gap:8px;">
            <ConceptTag :term="t.canonical_term" />
            <span class="faint">{{ t.day }}</span>
          </div>
          <div :style="t.status === 'done' ? 'text-decoration:line-through;color:var(--text-faint)' : ''">{{ t.description }}</div>
        </div>
        <span class="spacer"></span>
        <span class="faint">{{ t.est_minutes }} min</span>
      </div>
    </div>

    <div class="row" style="justify-content:flex-end;margin-top:18px;">
      <button @click="simulate" :disabled="busy">⚡ Simulate evidence (demo)</button>
    </div>
  </div>
</template>

<style scoped>
.task-row { padding: 12px; gap: 12px; border-bottom: 1px solid var(--border); }
.task-row:last-child { border-bottom: 0; }
.check { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
  border: 2px solid var(--border); background: var(--surface); color: var(--text-faint); flex: none; }
.check.done { background: var(--user); border-color: var(--user); color: #fff; }
button.check { cursor: pointer; }
button.check:hover { border-color: var(--user); color: var(--user); }
</style>
