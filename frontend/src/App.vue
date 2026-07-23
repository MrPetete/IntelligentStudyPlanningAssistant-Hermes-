<script setup>
import { onMounted, computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import store, { initGoal, switchGoal, refreshGoalList, setLanguage } from './store.js'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const ready = ref(false)
const showSwitcher = ref(false)

const nav = computed(() => [
  { to: '/home', label: t('app.nav.today'), ico: '◉' },
  { to: '/roadmap', label: t('app.nav.roadmap'), ico: '▤' },
  { to: '/history', label: t('app.nav.history'), ico: '⟲' },
  { to: '/dashboard', label: t('app.nav.dashboard'), ico: '📊' }
])

const showShell = computed(() => route.path !== '/onboarding')
const goalText = computed(() => store.goal?.goal_text || '')

// Try to restore the most recently used goal; if none exists yet, let the
// onboarding wizard start fresh rather than assuming "goal 1" (B-RC2-7).
onMounted(async () => {
  try {
    await refreshGoalList()
    if (!store.goalId && store.goals.length) await initGoal(store.goals[store.goals.length - 1].id)
  } catch (e) {
    if (route.path !== '/onboarding') {}
  } finally {
    ready.value = true
  }
})

async function onSelectGoal(id) {
  showSwitcher.value = false
  await switchGoal(id)
  router.push('/home')
}
function onNewGoal() {
  showSwitcher.value = false
  store.goalId = null
  store.goal = null
  store.currentPlan = null
  store.onboarded = false
  router.push('/onboarding')
}
async function toggleSwitcher() {
  showSwitcher.value = !showSwitcher.value
  if (showSwitcher.value) await refreshGoalList()
}

async function onLanguageChange(lang) {
  if (!store.goalId || lang === store.goal?.explanation_language) return
  await setLanguage(store.goalId, lang)
}
</script>

<template>
  <div class="app-shell" v-if="ready">
    <aside v-if="showShell" class="sidebar">
      <div class="brand">{{ $t('app.brand') }}<small>{{ $t('app.tagline') }}</small></div>
      <router-link v-for="n in nav" :key="n.to" :to="n.to" class="nav-item" active-class="active">
        <span class="ico">{{ n.ico }}</span>{{ n.label }}
      </router-link>

      <button class="ghost nav-item" style="margin-top:8px;" @click="onNewGoal">{{ $t('app.newGoal') }}</button>
      <button class="ghost nav-item" @click="toggleSwitcher">{{ $t('app.switchGoal') }}</button>

      <div v-if="showSwitcher" class="card goal-switcher">
        <div class="label" style="margin-bottom:6px;">{{ $t('goalSwitcher.title') }}</div>
        <div v-if="!store.goals.length" class="faint">{{ $t('app.noGoals') }}</div>
        <div v-for="g in store.goals" :key="g.id" class="row goal-row" @click="onSelectGoal(g.id)">
          <div class="col" style="min-width:0;">
            <span style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ g.goal_text }}</span>
            <span class="faint" style="font-size:11px;">{{ $t('goalSwitcher.deadline') }}: {{ g.deadline }}</span>
          </div>
          <span class="spacer"></span>
          <span v-if="g.id === store.goalId" class="badge ok">•</span>
        </div>
      </div>

      <div class="spacer"></div>
      <div v-if="goalText" class="card" style="padding:10px;font-size:12px;">
        <div class="label">{{ $t('app.goalLabel') }}</div>
        <div class="muted" style="margin-top:4px;">{{ goalText }}</div>
        <div class="row" style="margin-top:8px;gap:8px;align-items:center;">
          <span class="faint">{{ $t('app.language') }}:</span>
          <button class="ghost lang-btn" :class="{ primary: store.goal?.explanation_language === 'en' }"
                  @click="onLanguageChange('en')">EN</button>
          <button class="ghost lang-btn" :class="{ primary: store.goal?.explanation_language === 'zh' }"
                  @click="onLanguageChange('zh')">中文</button>
        </div>
      </div>
    </aside>

    <main class="content">
      <router-view :key="$route.fullPath" />
    </main>
  </div>
  <div v-else class="page"><div class="empty">{{ $t('app.loading') }}</div></div>
</template>

<style scoped>
.goal-switcher { margin-top: 6px; padding: 10px; max-height: 240px; overflow-y: auto; }
.goal-row { padding: 6px 4px; border-radius: 6px; cursor: pointer; gap: 6px; }
.goal-row:hover { background: var(--surface-2); }
.lang-btn { padding: 2px 8px; font-size: 12px; }
</style>
