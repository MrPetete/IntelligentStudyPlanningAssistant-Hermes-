<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import store, { api, refreshVersions } from '../store.js'
import ConceptTag from '../components/ConceptTag.vue'
import OfflineBanner from '../components/OfflineBanner.vue'

const router = useRouter()
const selectedVersion = ref(null)
const plan = ref(null)
const loading = ref(false)
const loadError = ref(null)

async function load() {
  loadError.value = null
  try {
    await refreshVersions(store.goalId)
    selectedVersion.value = store.currentPlan?.version_no ?? (store.versions.at(-1)?.version_no || 1)
    await loadVersion(selectedVersion.value)
  } catch (e) {
    loadError.value = e
  }
}
async function loadVersion(no) {
  loading.value = true
  try {
    plan.value = await api.getVersion(store.goalId, no)
  } catch (e) {
    loadError.value = e
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
    <div class="eyebrow">{{ $t('roadmap.eyebrow') }}</div>
    <h1>{{ $t('roadmap.title') }}</h1>

    <OfflineBanner :error="loadError" @retry="load" />

    <div class="row" style="gap:8px;margin-bottom:18px;flex-wrap:wrap;">
      <span class="label" style="align-self:center;">{{ $t('roadmap.version') }}</span>
      <button v-for="v in store.versions" :key="v.version_no"
              :class="['ghost', { primary: v.version_no === selectedVersion }]"
              style="border:1px solid var(--border);"
              @click="selectVersion(v.version_no)">
        v{{ v.version_no }}
        <span class="badge" :class="v.created_by === 'agent' ? 'agent' : 'user'" style="margin-left:6px;">{{ v.created_by === 'agent' ? $t('roadmap.agent') : $t('roadmap.you') }}</span>
      </button>
    </div>

    <div v-if="loading" class="empty">{{ $t('roadmap.loading') }}</div>
    <div v-else-if="!plan && !loadError" class="empty">{{ $t('roadmap.noPlan') }}</div>
    <div v-else-if="plan" class="stack">
      <div v-for="[day, list] in byDay" :key="day" class="card" style="padding:14px 16px;">
        <div class="row">
          <h3 style="margin:0;">{{ day }}</h3>
          <span class="spacer"></span>
          <span class="faint">{{ $t('roadmap.tasksCount', { n: list.length }) }}</span>
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
      <button @click="router.push('/history')">{{ $t('roadmap.viewHistory') }}</button>
    </div>
  </div>
</template>
