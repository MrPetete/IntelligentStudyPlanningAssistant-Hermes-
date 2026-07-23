<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import store, { api } from '../store.js'
import ConceptTag from '../components/ConceptTag.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const decision = ref(null)
const loading = ref(false)
const err = ref('')
const traceExpanded = ref(false)
const traceLoading = ref(false)

// Classify each tool call into the four-phase story (read → reason → act → record)
// so a non-technical viewer immediately sees the agent loop.
function phaseOf(tool) {
  if (tool.startsWith('get_') || tool === 'search_learning_material') return 'read'
  if (tool.startsWith('llm.')) return 'reason'
  // RECORD phase: record_agent_decision (check BEFORE generic create_/record_ → act rule)
  if (tool.startsWith('record_agent_decision')) return 'record'
  if (tool.startsWith('create_') || tool.startsWith('validator')) return 'act'
  return 'reason'
}
const PHASE_META = {
  read:   { label: 'READ',     color: 'var(--brand)',     soft: 'var(--brand-soft)',     icon: '📥' },
  reason: { label: 'REASON',   color: 'var(--accent)',    soft: 'var(--brand-soft)',     icon: '🧠' },
  act:    { label: 'ACT',      color: 'var(--agent)',     soft: 'var(--agent-soft)',     icon: '✏️' },
  record: { label: 'RECORD',   color: 'var(--user)',      soft: 'var(--user-soft)',      icon: '📝' }
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    // Default fetch (no ?include_trace): the backend now omits tool_trace by
    // default (B-RC2-6 / A-RC2-5) — the student view leads with reasoning_text
    // only. The trace is fetched separately, on demand, when expanded below.
    decision.value = await api.getDecision(store.goalId, Number(route.params.id))
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}
onMounted(load)

async function toggleTrace() {
  traceExpanded.value = !traceExpanded.value
  if (traceExpanded.value && (!decision.value.tool_trace || !decision.value.tool_trace.length)) {
    traceLoading.value = true
    try {
      decision.value = await api.getDecision(store.goalId, Number(route.params.id), true)
    } catch (e) { err.value = e.message }
    finally { traceLoading.value = false }
  }
}

const grouped = computed(() => {
  if (!decision.value) return []
  const order = ['read', 'reason', 'act', 'record']
  const g = { read: [], reason: [], act: [], record: [] }
  ;(decision.value.tool_trace || []).forEach((t) => { g[phaseOf(t.tool)].push(t) })
  return order.map((k) => ({ key: k, meta: PHASE_META[k], calls: g[k] })).filter((g) => g.calls.length)
})
function fmtDate(s) { try { return new Date(s).toLocaleString() } catch { return s } }
</script>

<template>
  <div class="page page-wide">
    <button class="ghost" style="margin-bottom:8px;" @click="router.push('/history')">{{ $t('decision.back') }}</button>

    <div v-if="loading" class="empty">{{ $t('decision.loading') }}</div>
    <div v-else-if="err" class="card" style="padding:14px;color:var(--danger);">{{ err }}</div>
    <div v-else-if="decision">
      <!-- Header -->
      <div class="row">
        <div>
          <div class="eyebrow" :style="decision.decision === 'no_change' ? 'color:var(--text-muted)' : 'color:var(--agent)'">
            Agent decision #{{ decision.id }}
          </div>
          <h1 style="margin:4px 0 0;">{{ $t('decision.title') }}</h1>
        </div>
        <span class="spacer"></span>
        <span class="badge" :class="decision.decision === 'new_version' ? 'agent' : 'muted'">
          {{ decision.decision === 'new_version' ? $t('decision.changedPlan') : $t('decision.noChangeNeeded') }}
        </span>
      </div>

      <!-- no_change banner -->
      <div v-if="decision.decision === 'no_change'" class="card" style="margin:16px 0;padding:14px 16px;background:var(--surface-2);border-color:var(--border);">
        <strong>{{ $t('decision.consideredBanner') }}</strong>
        <span class="muted"> {{ $t('decision.consideredNote') }}</span>
      </div>

      <div class="stack" style="margin-top:14px;">

        <!-- 1. Trigger -->
        <div class="card block">
          <div class="row">
            <span class="step-ico" style="background:var(--warn-soft);color:var(--warn)">⚡</span>
            <div>
              <div class="label">{{ $t('decision.triggerLabel') }}</div>
              <div style="font-weight:650;">{{ decision.trigger }}</div>
              <div class="faint" style="font-size:12px;">{{ $t('decision.triggerNote') }}</div>
            </div>
          </div>
        </div>

        <!-- 2. Evidence snapshot -->
        <div class="card block">
          <div class="label">{{ $t('decision.evidenceLabel') }}</div>
          <pre class="evidence mono">{{ JSON.stringify(decision.evidence_snapshot, null, 2) }}</pre>
          <div class="faint" style="font-size:12px;margin-top:6px;">{{ $t('decision.evidenceNote') }}</div>
        </div>

        <!-- 3. Reasoning — prominent, always shown -->
        <div class="card block" :style="decision.decision === 'new_version' ? 'background:var(--agent-soft);border-color:var(--agent)' : ''">
          <div class="row">
            <span class="step-ico" style="background:var(--brand-soft);color:var(--accent)">🧠</span>
            <div>
              <div class="label">{{ $t('decision.reasoningLabel') }}</div>
              <div class="reasoning" style="font-size:15px;line-height:1.7;margin-top:4px;">{{ decision.reasoning_text }}</div>
            </div>
          </div>
        </div>

        <!-- 4. Tool trace — collapsed by default (B-RC2-6): the raw tool-call
             list is the defence artifact, not something a student needs to see
             up front. Fetched with ?include_trace=true only when expanded. -->
        <div class="card block">
          <button class="ghost trace-toggle" @click="toggleTrace" style="width:100%;text-align:left;">
            <span class="row">
              <span class="step-ico" style="background:var(--brand-soft);color:var(--brand)">🔗</span>
              <span>{{ traceExpanded ? $t('decision.hideDetails') : $t('decision.showDetails') }}</span>
              <span class="spacer"></span>
              <span class="chevron" :class="{ open: traceExpanded }">▾</span>
            </span>
          </button>

          <div v-if="traceExpanded" style="margin-top:12px;">
            <div class="muted" style="font-size:13px;margin-bottom:8px;">{{ $t('decision.traceNote') }}</div>
            <div v-if="traceLoading" class="empty">{{ $t('decision.loading') }}</div>
            <div v-for="g in grouped" :key="g.key" class="phase">
              <div class="phase-head">
                <span class="phase-chip" :style="{ background: g.meta.soft, color: g.meta.color }">{{ g.meta.icon }} {{ g.meta.label }}</span>
                <span class="phase-line"></span>
              </div>
              <div v-for="(t, i) in g.calls" :key="i" class="tool-card card">
                <div class="row">
                  <code class="tool-name mono">{{ t.tool }}</code>
                  <span class="spacer"></span>
                  <span class="badge ok">{{ t.result_summary }}</span>
                </div>
                <div class="args" v-if="Object.keys(t.args).length">
                  <span class="faint">{{ $t('decision.args') }}</span>
                  <code class="mono">{{ JSON.stringify(t.args) }}</code>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 5. Resulting version -->
        <div class="card block" v-if="decision.resulting_plan_version_id">
          <div class="row">
            <span class="step-ico" style="background:var(--user-soft);color:var(--user)">📌</span>
            <div>
              <div class="label">{{ $t('decision.resultingVersion') }}</div>
              <button class="primary" style="margin-top:4px;" @click="router.push('/history')">
                {{ $t('decision.viewDiff', { n: decision.resulting_plan_version_id }) }}
              </button>
            </div>
          </div>
        </div>
        <div class="card block" v-else>
          <div class="row">
            <span class="step-ico" style="background:var(--surface-2);color:var(--text-muted)">—</span>
            <div class="muted">{{ $t('decision.noNewVersion') }}</div>
          </div>
        </div>
      </div>

      <div class="faint" style="font-size:12px;margin-top:14px;">{{ $t('decision.created', { date: fmtDate(decision.created_at) }) }}</div>
    </div>
  </div>
</template>

<style scoped>
.block { padding: 16px 18px; }
.step-ico { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; font-size: 16px; flex: none; }
.evidence { background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px;
  font-size: 12.5px; margin: 10px 0 0; overflow-x: auto; }
.phase { margin-top: 14px; }
.phase-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.phase-chip { font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; letter-spacing: .04em; }
.phase-line { flex: 1; height: 2px; background: var(--border); }
.tool-card { padding: 10px 12px; margin-bottom: 8px; border-left: 3px solid var(--border); }
.tool-name { font-weight: 700; font-size: 13.5px; color: var(--text); }
.args { margin-top: 6px; font-size: 12.5px; color: var(--text-muted); }
.args code { background: var(--surface-2); padding: 1px 6px; border-radius: 5px; }
.reasoning { white-space: pre-wrap; }
.trace-toggle { padding: 8px; border-radius: 8px; }
.chevron { transition: transform .15s; color: var(--text-faint); }
.chevron.open { transform: rotate(180deg); }
</style>
