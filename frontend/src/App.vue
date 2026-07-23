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
      <div class="brand">
        <svg class="brand-logo" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <circle cx="16" cy="17" r="13" fill="var(--brand)"/>
          <circle cx="16" cy="17" r="13" fill="url(#tangerine-shine)"/>
          <path d="M16 4c1.6 0 2.6 1.7 2.6 3.4" stroke="var(--brand-soft)" stroke-width="1.6" stroke-linecap="round"/>
          <g stroke="var(--brand-dark)" stroke-width="1" opacity=".55" stroke-linecap="round">
            <line x1="16" y1="6" x2="16" y2="28"/>
            <line x1="6" y1="17" x2="26" y2="17"/>
            <line x1="8.7" y1="9.7" x2="23.3" y2="24.3"/>
            <line x1="23.3" y1="9.7" x2="8.7" y2="24.3"/>
          </g>
          <defs>
            <radialGradient id="tangerine-shine" cx="35%" cy="30%" r="65%">
              <stop offset="0%" stop-color="#ffb347" stop-opacity=".9"/>
              <stop offset="100%" stop-color="var(--brand)" stop-opacity="0"/>
            </radialGradient>
          </defs>
        </svg>
        <div class="brand-text">{{ $t('app.brand') }}<small>{{ $t('app.tagline') }}</small></div>
      </div>
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
          <div class="switch" @click="onLanguageChange(store.goal?.explanation_language === 'en' ? 'zh' : 'en')">
            <span class="switch-thumb" :style="{ transform: store.goal?.explanation_language === 'zh' ? 'translateX(100%)' : 'translateX(0)' }"></span>
            <span class="switch-option" :class="{ active: store.goal?.explanation_language !== 'zh' }">EN</span>
            <span class="switch-option" :class="{ active: store.goal?.explanation_language === 'zh' }">中文</span>
          </div>
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
