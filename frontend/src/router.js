import { createRouter, createWebHashHistory } from 'vue-router'
import store from './store.js'

import Onboarding from './views/Onboarding.vue'
import Home from './views/Home.vue'
import Roadmap from './views/Roadmap.vue'
import VersionHistory from './views/VersionHistory.vue'
import DecisionView from './views/DecisionView.vue'
import Dashboard from './views/Dashboard.vue'

const routes = [
  { path: '/', redirect: '/onboarding' },
  { path: '/onboarding', name: 'onboarding', component: Onboarding },
  { path: '/home', name: 'home', component: Home },
  { path: '/roadmap', name: 'roadmap', component: Roadmap },
  { path: '/history', name: 'history', component: VersionHistory },
  { path: '/decision/:id', name: 'decision', component: DecisionView },
  { path: '/dashboard', name: 'dashboard', component: Dashboard }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// After onboarding completes for goal 1, route to home.
export function goAfterOnboarding() {
  router.push('/home')
}

export default router
