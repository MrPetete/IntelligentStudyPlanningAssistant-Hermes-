<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import store, { api, refreshVersions } from '../store.js'
import ConceptTag from '../components/ConceptTag.vue'

const router = useRouter()
const selectedVersion = ref(null)
const plan = ref(null)
const loading = ref(false)

async function load() {
  await refreshVersions(store.goalId)
  selectedVersion.value = store.currentPlan?.version_no ?? (store.versions.at(-1)?.version_no || 1)
  await loadVersion(selectedVersion.value)
}
async function loadVersion(no) {
  loading.value = true
  try {
    plan.value = await api.getVersion(store.goalId, no)
  } finally { loading.value = false }
}
onMounted(load)

const byDay = computed(() => {
  if (!plan.value) return []
  const map = {}
  plan.value.tasks.forEach((t) => {
    const d = t.day || 'Unscheduled'
    ;(map[d] ||= []).push(t)
  })
  return Object.entries(map).sort((a, b) => a[0].localeCompare(b[0]))
})

function selectVersion(no) { selectedVersion.value = no; loadVersion(no) }
</script>

<template>
  <div class="page">
    <div class="eyebrow">Roadmap</div>
    <h1>Learning plan</h1>

    <div class="row" style="gap:8px;margin-bottom:18px;flex-wrap:wrap;">
      <span class="label" style="align-self:center;">Version</span>
      <button v-for="v in store.versions" :key="v.version_no"
              :class="['ghost', { primary: v.version_no === selectedVersion }]"
              style="border:1px solid var(--border);"
              @click="selectVersion(v.version_no)">
        v{{ v.version_no }}
        <span class="badge" :class="v.created_by === 'agent' ? 'agent' : 'user'" style="margin-left:6px;">{{ v.created_by === 'agent' ? 'agent' : 'you' }}</span>
      </button>
    </div>

    <div v-if="loading" class="empty">Loading plan…</div>
    <div v-else-if="!plan" class="empty">No plan yet.</div>
    <div v-else class="stack">
      <div v-for="[day, list] in byDay" :key="day" class="card" style="padding:14px 16px;">
        <div class="row">
          <h3 style="margin:0;">{{ day }}</h3>
          <span class="spacer"></span>
          <span class="faint">{{ list.length }} tasks</span>
        </div>
        <hr class="divider" style="margin:10px 0;" />
        <div class="stack" style="margin-top:0;">
          <div v-for="t in list" :key="t.id" class="row" style="gap:10px;">
            <span v-if="t.status === 'done'" class="badge ok">✓</span>
            <span v-else class="badge muted">·</span>
            <ConceptTag :term="t.canonical_term" />
            <span :style="t.status === 'done' ? 'text-decoration:line-through;color:var(--text-faint)' : ''">{{ t.description }}</span>
            <span class="spacer"></span>
            <span class="faint">{{ t.est_minutes }} min</span>
          </div>
        </div>
      </div>
    </div>

    <div class="row" style="justify-content:flex-end;margin-top:20px;">
      <button @click="router.push('/history')">View version history →</button>
    </div>
  </div>
</template>
