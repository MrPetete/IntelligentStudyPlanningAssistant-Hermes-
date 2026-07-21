<script setup>
import { onMounted, computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import store, { initGoal } from './store.js'

const route = useRoute()
const ready = ref(false)

const nav = [
  { to: '/home', label: 'Today', ico: '◉' },
  { to: '/roadmap', label: 'Roadmap', ico: '▤' },
  { to: '/history', label: 'Version History', ico: '⟲' },
  { to: '/dashboard', label: 'Dashboard', ico: '📊' }
]

const showShell = computed(() => route.path !== '/onboarding')
const goalText = computed(() => store.goal?.goal_text || '')

// Initialize the seeded goal (id 1) BEFORE any child route mounts, so views
// never read a null goalId. Gate router-view on `ready`.
onMounted(async () => {
  try {
    if (!store.goalId) await initGoal(1)
  } catch (e) {
    // Onboarding path: goal not created yet — allow the wizard to start.
    if (route.path !== '/onboarding') {}
  } finally {
    ready.value = true
  }
})
</script>

<template>
  <div class="app-shell" v-if="ready">
    <aside v-if="showShell" class="sidebar">
      <div class="brand">TraceLearn<small>Material-grounded learning path agent</small></div>
      <router-link v-for="n in nav" :key="n.to" :to="n.to" class="nav-item" active-class="active">
        <span class="ico">{{ n.ico }}</span>{{ n.label }}
      </router-link>
      <div class="spacer"></div>
      <div v-if="goalText" class="card" style="padding:10px;font-size:12px;">
        <div class="label">Goal</div>
        <div class="muted" style="margin-top:4px;">{{ goalText }}</div>
        <div class="faint" style="margin-top:6px;">
          {{ store.goal?.explanation_language === 'zh' ? '解释语言：中文' : 'Explanation: English' }}
        </div>
      </div>
    </aside>

    <main class="content">
      <router-view :key="$route.fullPath" />
    </main>
  </div>
  <div v-else class="page"><div class="empty">Loading TraceLearn…</div></div>
</template>
