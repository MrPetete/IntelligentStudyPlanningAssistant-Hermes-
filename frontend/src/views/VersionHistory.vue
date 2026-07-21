<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import store, { api } from '../store.js'
import ConceptTag from '../components/ConceptTag.vue'

const router = useRouter()
const loading = ref(false)
const diff = ref(null)
const fromNo = ref(null)
const toNo = ref(null)
const err = ref('')

async function load() {
  loading.value = true
  try {
    store.versions = await api.getVersions(store.goalId)
    store.decisions = await api.getDecisions(store.goalId)
    // default: latest two versions
    const vs = store.versions
    if (vs.length >= 2) {
      fromNo.value = vs[vs.length - 2].version_no
      toNo.value = vs[vs.length - 1].version_no
    } else if (vs.length === 1) {
      fromNo.value = vs[0].version_no
      toNo.value = vs[0].version_no
    }
    await loadDiff()
  } finally { loading.value = false }
}

async function loadDiff() {
  err.value = ''
  if (fromNo.value == null || toNo.value == null) return
  try {
    diff.value = await api.getDiff(store.goalId, fromNo.value, toNo.value)
  } catch (e) { err.value = e.message }
}

onMounted(load)

const conceptEntries = computed(() => Object.entries(diff.value?.concept_summary || {})
  .filter(([k]) => k !== '_rescheduled'))

function fmtDate(s) {
  try { return new Date(s).toLocaleString() } catch { return s }
}
function decisionForVersion(vid) {
  return store.decisions.find((d) => d.resulting_plan_version_id === vid)
}
</script>

<template>
  <div class="page page-wide">
    <div class="eyebrow" style="color:var(--agent);">Version History</div>
    <h1>The trace of your plan</h1>
    <p class="muted">Every plan change is an immutable new version with an evidence-linked reason. Pick two versions to see what changed.</p>

    <!-- Timeline -->
    <div class="timeline card" style="padding:18px 20px;margin:18px 0;">
      <div class="row" style="gap:0;align-items:stretch;">
        <div v-for="(v, i) in store.versions" :key="v.id" class="tl-item col" style="flex:1;position:relative;">
          <div class="tl-node" :class="v.created_by"></div>
          <div class="tl-card card" :class="{ active: v.version_no === toNo, from: v.version_no === fromNo }"
               @click="toNo = v.version_no; if (fromNo == null) fromNo = store.versions[Math.max(0,i-1)].version_no; loadDiff()">
            <div class="row">
              <strong>v{{ v.version_no }}</strong>
              <span class="spacer"></span>
              <span class="badge" :class="v.created_by === 'agent' ? 'agent' : 'user'">
                {{ v.created_by === 'agent' ? 'TraceLearn agent' : 'you' }}
              </span>
            </div>
            <div class="faint" style="font-size:12px;margin-top:4px;">{{ fmtDate(v.created_at) }}</div>
            <div v-if="v.parent_version_id" class="faint" style="font-size:11px;">from v{{ v.parent_version_id }}</div>
            <div v-if="decisionForVersion(v.id)" class="link" @click.stop="router.push('/decision/' + decisionForVersion(v.id).id)">view decision →</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Diff controls -->
    <div class="row" style="gap:10px;margin-bottom:14px;">
      <span class="label">Compare</span>
      <select v-model.number="fromNo" @change="loadDiff" style="width:auto;">
        <option v-for="v in store.versions" :key="'f'+v.version_no" :value="v.version_no">v{{ v.version_no }}</option>
      </select>
      <span class="muted">→</span>
      <select v-model.number="toNo" @change="loadDiff" style="width:auto;">
        <option v-for="v in store.versions" :key="'t'+v.version_no" :value="v.version_no">v{{ v.version_no }}</option>
      </select>
      <span class="spacer"></span>
      <button class="primary" @click="loadDiff">Show diff</button>
    </div>

    <div v-if="err" class="card" style="padding:10px 14px;color:var(--danger);">{{ err }}</div>

    <!-- Concept summary (the money line) -->
    <div v-if="diff" class="card" style="padding:18px 20px;margin-bottom:16px;">
      <div class="eyebrow">What changed, grouped by concept</div>
      <div v-if="!conceptEntries.length && !diff.added_tasks.length && !diff.removed_tasks.length" class="muted" style="margin-top:8px;">
        These two versions are identical — {{ diff.unchanged_count }} task(s) unchanged.
      </div>
      <div v-else class="stack" style="margin-top:10px;">
        <div v-for="[term, note] in conceptEntries" :key="term" class="row" style="gap:10px;">
          <ConceptTag :term="term" />
          <span class="muted">{{ note }}</span>
        </div>
        <div v-if="diff._rescheduled?.length" class="row" style="gap:10px;">
          <span class="concept-tag" style="background:var(--warn-soft);color:var(--warn);border-color:#ecdcb4;">
            <span class="dot" style="background:var(--warn)"></span>Rescheduled
          </span>
          <span class="muted">{{ diff._rescheduled.length }} task(s) moved to a different day</span>
        </div>
        <div class="faint" style="font-size:12px;">{{ diff.unchanged_count }} task(s) unchanged</div>
      </div>
    </div>

    <!-- Side-by-side diff -->
    <div v-if="diff" class="diff-grid">
      <div class="card" style="padding:16px;">
        <h3>v{{ diff.from_version }} <span class="faint" style="font-weight:500;">(before)</span></h3>
        <div v-for="t in diff.removed_tasks" :key="'r'+t.id" class="drow removed">
          <ConceptTag :term="t.canonical_term" />
          <span class="strike">{{ t.description }}</span>
          <span class="faint">{{ t.day }}</span>
        </div>
        <div v-if="!diff.removed_tasks.length" class="faint" style="font-size:12px;">No tasks removed.</div>
      </div>

      <div class="card" style="padding:16px;">
        <h3>v{{ diff.to_version }} <span class="faint" style="font-weight:500;">(after)</span></h3>
        <div v-for="t in diff.added_tasks" :key="'a'+t.id" class="drow added">
          <ConceptTag :term="t.canonical_term" />
          <span>{{ t.description }}</span>
          <span class="faint">{{ t.day }}</span>
        </div>
        <div v-if="!diff.added_tasks.length" class="faint" style="font-size:12px;">No tasks added.</div>
      </div>
    </div>

    <!-- Jump to the decision that produced the "to" version -->
    <div v-if="diff" class="row" style="justify-content:flex-end;margin-top:18px;">
      <button v-if="decisionForVersion(diff.to_version)" @click="router.push('/decision/' + decisionForVersion(diff.to_version).id)">
        Why did v{{ diff.to_version }} change? →
      </button>
      <span v-else class="faint">v{{ diff.to_version }} was created by you (no agent decision).</span>
    </div>
  </div>
</template>

<style scoped>
.timeline { overflow-x: auto; }
.tl-item { padding: 0 6px; }
.tl-node { width: 14px; height: 14px; border-radius: 50%; background: var(--brand);
  margin: 0 auto 8px; border: 3px solid #fff; box-shadow: 0 0 0 2px var(--border); }
.tl-node.agent { background: var(--agent); }
.tl-node.user { background: var(--user); }
.tl-card { padding: 10px 12px; cursor: pointer; transition: border-color .15s, box-shadow .15s; }
.tl-card:hover { border-color: var(--brand); }
.tl-card.active { border-color: var(--agent); box-shadow: 0 0 0 2px var(--agent-soft); }
.tl-card.from { border-color: var(--text-faint); }
.tl-card .link { color: var(--brand); font-size: 12px; margin-top: 6px; cursor: pointer; }
.diff-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.drow { display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: 8px; margin-bottom: 6px; background: var(--surface-2); }
.drow.added { background: var(--user-soft); }
.drow.removed { background: #fbeceb; }
.strike { text-decoration: line-through; color: var(--text-faint); }
@media (max-width: 760px) { .diff-grid { grid-template-columns: 1fr; } }
</style>
