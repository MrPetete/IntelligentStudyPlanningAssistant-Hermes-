<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import store, { api } from '../store.js'
import ConceptTag from '../components/ConceptTag.vue'

const route = useRoute()
const router = useRouter()
const decision = ref(null)
const loading = ref(false)
const err = ref('')

// Classify each tool call into the four-phase story (read → reason → act → record)
// so a non-technical viewer immediately sees the agent loop.
function phaseOf(tool) {
  if (tool.startsWith('get_') || tool === 'search_learning_material') return 'read'
  if (tool.startsWith('llm.')) return 'reason'
  if (tool.startsWith('create_') || tool.startsWith('record_') || tool.startsWith('validator')) return 'act'
  if (tool.startsWith('record_agent_decision')) return 'record'
  return 'reason'
}
const PHASE_META = {
  read:   { label: 'READ',     color: 'var(--brand)',     soft: 'var(--brand-soft)',     icon: '📥' },
  reason: { label: 'REASON',   color: 'var(--accent)',    soft: '#efeaf9',               icon: '🧠' },
  act:    { label: 'ACT',      color: 'var(--agent)',     soft: 'var(--agent-soft)',     icon: '✏️' },
  record: { label: 'RECORD',   color: 'var(--user)',      soft: 'var(--user-soft)',      icon: '📝' }
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    decision.value = await api.getDecision(store.goalId, Number(route.params.id))
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}
onMounted(load)

const grouped = computed(() => {
  if (!decision.value) return []
  const order = ['read', 'reason', 'act', 'record']
  const g = { read: [], reason: [], act: [], record: [] }
  decision.value.tool_trace.forEach((t) => { g[phaseOf(t.tool)].push(t) })
  return order.map((k) => ({ key: k, meta: PHASE_META[k], calls: g[k] })).filter((g) => g.calls.length)
})
function fmtDate(s) { try { return new Date(s).toLocaleString() } catch { return s } }
</script>

<template>
  <div class="page page-wide">
    <button class="ghost" style="margin-bottom:8px;" @click="router.push('/history')">← Version history</button>

    <div v-if="loading" class="empty">Loading decision…</div>
    <div v-else-if="err" class="card" style="padding:14px;color:var(--danger);">{{ err }}</div>
    <div v-else-if="decision">
      <!-- Header -->
      <div class="row">
        <div>
          <div class="eyebrow" :style="decision.decision === 'no_change' ? 'color:var(--text-muted)' : 'color:var(--agent)'">
            Agent decision #{{ decision.id }}
          </div>
          <h1 style="margin:4px 0 0;">Why did your plan change?</h1>
        </div>
        <span class="spacer"></span>
        <span class="badge" :class="decision.decision === 'new_version' ? 'agent' : 'muted'">
          {{ decision.decision === 'new_version' ? 'Changed the plan' : 'No change needed' }}
        </span>
      </div>

      <!-- no_change banner -->
      <div v-if="decision.decision === 'no_change'" class="card" style="margin:16px 0;padding:14px 16px;background:var(--surface-2);border-color:var(--border);">
        <strong>Considered, then left unchanged.</strong>
        <span class="muted"> The agent reviewed the evidence and judged the current plan still fits. Showing the reasoning proves it is judging, not blindly rewriting.</span>
      </div>

      <div class="stack" style="margin-top:14px;">

        <!-- 1. Trigger -->
        <div class="card block">
          <div class="row">
            <span class="step-ico" style="background:var(--warn-soft);color:var(--warn)">⚡</span>
            <div>
              <div class="label">Trigger that fired</div>
              <div style="font-weight:650;">{{ decision.trigger }}</div>
              <div class="faint" style="font-size:12px;">A deterministic condition decided when the agent woke up.</div>
            </div>
          </div>
        </div>

        <!-- 2. Evidence snapshot -->
        <div class="card block">
          <div class="label">Evidence the agent saw</div>
          <pre class="evidence mono">{{ JSON.stringify(decision.evidence_snapshot, null, 2) }}</pre>
          <div class="faint" style="font-size:12px;margin-top:6px;">Written by the app from your learning events. The agent only reads it.</div>
        </div>

        <!-- 3. Tool trace — the loop, in order -->
        <div class="card block">
          <div class="row">
            <span class="step-ico" style="background:var(--brand-soft);color:var(--brand)">🔗</span>
            <div>
              <div class="label">Tool trace — read → reason → act → record</div>
              <div class="muted" style="font-size:13px;">Each card is one tool call, in the order the agent made it.</div>
            </div>
          </div>

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
                <span class="faint">args:</span>
                <code class="mono">{{ JSON.stringify(t.args) }}</code>
              </div>
            </div>
          </div>
        </div>

        <!-- 4. Reasoning -->
        <div class="card block" :style="decision.decision === 'new_version' ? 'background:var(--agent-soft);border-color:#f0cfc6' : ''">
          <div class="row">
            <span class="step-ico" style="background:#efeaf9;color:var(--accent)">🧠</span>
            <div>
              <div class="label">Reasoning — the answer to "why?"</div>
              <div class="reasoning" style="font-size:15px;line-height:1.7;margin-top:4px;">{{ decision.reasoning_text }}</div>
            </div>
          </div>
        </div>

        <!-- 5. Resulting version -->
        <div class="card block" v-if="decision.resulting_plan_version_id">
          <div class="row">
            <span class="step-ico" style="background:var(--user-soft);color:var(--user)">📌</span>
            <div>
              <div class="label">Resulting plan version</div>
              <button class="primary" style="margin-top:4px;" @click="router.push('/history')">
                View diff for version {{ decision.resulting_plan_version_id }} →
              </button>
            </div>
          </div>
        </div>
        <div class="card block" v-else>
          <div class="row">
            <span class="step-ico" style="background:var(--surface-2);color:var(--text-muted)">—</span>
            <div class="muted">No new version was created. The plan was left as-is.</div>
          </div>
        </div>
      </div>

      <div class="faint" style="font-size:12px;margin-top:14px;">Created {{ fmtDate(decision.created_at) }}</div>
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
</style>
