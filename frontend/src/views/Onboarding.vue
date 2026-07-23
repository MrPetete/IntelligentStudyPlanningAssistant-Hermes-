<script setup>
import { ref, reactive, computed, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import store, { api, initGoal, syncLocale } from '../store.js'
import ConceptTag from '../components/ConceptTag.vue'

const router = useRouter()
const { t } = useI18n()

// ---- step state ----
const step = ref(1) // 1 goal, 2 warmup, 3 concepts, 4 diagnostic, 5 reveal
const busy = ref(false)
const error = ref('')
const docStatus = ref('none') // none | uploaded | processing | ready | failed
let pollTimer = null

const steps = computed(() => [
  { n: 1, title: t('onboarding.steps.goal') },
  { n: 2, title: t('onboarding.steps.warmup') },
  { n: 3, title: t('onboarding.steps.concepts') },
  { n: 4, title: t('onboarding.steps.diagnostic') },
  { n: 5, title: t('onboarding.steps.reveal') }
])

// ---- Screen 1: goal ----
const goalForm = reactive({
  goal_text: '',
  deadline: '',
  hours_per_day: 2,
  explanation_language: 'en',
  filename: ''
})
// Interface follows the same field the moment it's picked (B-RC2-8: one
// setting drives both UI chrome and content language, even mid-onboarding).
watch(() => goalForm.explanation_language, (lang) => syncLocale(lang))
// Realistic cap: hours left until deadline (same-day = until midnight; future = 16h)
const maxHoursPerDay = computed(() => {
  if (!goalForm.deadline) return 16
  const now = new Date()
  const dl = new Date(goalForm.deadline + 'T23:59:59')
  const sameDay = dl.toDateString() === now.toDateString()
  if (sameDay) return Math.max(1, Math.floor((dl - now) / 3.6e6))
  return 16
})
watch(maxHoursPerDay, (m) => { if (goalForm.hours_per_day > m) goalForm.hours_per_day = m })
const fileInput = ref(null)
function onPickFile(e) {
  const f = e.target.files?.[0]
  goalForm.filename = f ? f.name : ''
}
async function submitGoal() {
  error.value = ''
  if (!goalForm.goal_text.trim() || !goalForm.deadline) {
    error.value = t('onboarding.missingFields')
    return
  }
  busy.value = true
  try {
    const goal = await api.createGoal({ ...goalForm })
    store.goalId = goal.id
    store.goal = goal
    // Material: begin async processing; no-material -> nothing to process.
    if (goalForm.filename) {
      docStatus.value = 'uploaded'
      try {
        await api.uploadDocument(goal.id, fileInput.value?.files?.[0])
        docStatus.value = 'processing'
        startDocPoll(goal.id)
      } catch (e) {
        // Upload failed — still allow the user to continue with goal-topic concepts
        error.value = 'Upload failed: ' + e.message + '. Continuing with goal-topic concepts.'
        docStatus.value = 'failed'
      }
    } else {
      docStatus.value = 'none'
    }
    step.value = 2
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function startDocPoll(id) {
  clearInterval(pollTimer)
  let attempts = 0
  const maxAttempts = 40 // ~60s with 1.5s interval (real backend can take 5–20s for extraction)
  pollTimer = setInterval(async () => {
    attempts++
    if (attempts > maxAttempts) {
      clearInterval(pollTimer)
      docStatus.value = 'failed'
      error.value = 'Document analysis timed out. You can continue with goal-topic concepts.'
      return
    }
    try {
      const d = await api.getDocument(id)
      docStatus.value = d.status
      if (d.status === 'ready' || d.status === 'failed') clearInterval(pollTimer)
    } catch { /* ignore transient errors during poll */ }
  }, 1500)
}

// ---- Screen 2: warm-up (context only, NOT the diagnostic) ----
const warmup = reactive({ studied: null, fromScratch: null, comfort: null })
const warmupDone = computed(() => warmup.studied !== null && warmup.fromScratch !== null)
function continueFromWarmup() {
  step.value = 3
}

// ---- Screen 3: concept confirmation (human-in-the-loop) ----
const concepts = ref([])
const extracting = ref(false)
const confirmDone = ref(false)
async function loadConcepts() {
  extracting.value = true
  error.value = ''
  try {
    let list = await api.getConcepts(store.goalId)
    if (!list.length) list = await api.extractConcepts(store.goalId)
    // editable copy
    concepts.value = list.map((c, i) => ({
      id: c.id ?? null,
      canonical_term: c.canonical_term,
      name: c.name ?? c.canonical_term,
      explanation: c.explanation ?? '',
      order_index: c.order_index ?? i + 1,
      parent_concept_id: c.parent_concept_id ?? null,
      source: c.source ?? 'material'
    }))
  } catch (e) {
    error.value = e.message
  } finally {
    extracting.value = false
  }
}
async function confirmConcepts() {
  error.value = ''
  busy.value = true
  try {
    const body = concepts.value.map((c, i) => ({
      id: c.id ?? null,
      canonical_term: c.canonical_term.trim(),
      name: c.name.trim(),
      explanation: c.explanation,
      order_index: i + 1,
      parent_concept_id: c.parent_concept_id ?? null
    }))
    const confirmed = await api.confirmConcepts(store.goalId, body)
    store.concepts = confirmed
    confirmDone.value = true
    step.value = 4
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function addConcept() {
  concepts.value.push({
    id: null, canonical_term: '', name: '', explanation: '',
    order_index: concepts.value.length + 1, parent_concept_id: null, source: 'user_added'
  })
}
function removeConcept(i) { concepts.value.splice(i, 1) }
function moveConcept(i, dir) {
  const j = i + dir
  if (j < 0 || j >= concepts.value.length) return
  const t = concepts.value[i]; concepts.value[i] = concepts.value[j]; concepts.value[j] = t
}

// ---- Screen 4: diagnostic ----
const diag = ref(null)
const answers = reactive({}) // questionId -> chosen option
const diagGenerating = ref(false)
const diagResult = ref(null)
async function generateDiag() {
  diagGenerating.value = true
  error.value = ''
  try {
    const d = await api.generateDiagnostic(store.goalId)
    diag.value = d
    Object.keys(answers).forEach((k) => delete answers[k])
  } catch (e) {
    error.value = e.message
  } finally {
    diagGenerating.value = false
  }
}
async function submitDiag() {
  error.value = ''
  const unanswered = diag.value.questions.filter((q) => !answers[q.id])
  if (unanswered.length) { error.value = t('onboarding.answerToContinue'); return }
  busy.value = true
  try {
    const body = diag.value.questions.map((q) => ({ question_id: q.id, choice: answers[q.id] }))
    const res = await api.submitDiagnostic(store.goalId, body)
    diagResult.value = res
    store.diagnosticResult = res
    step.value = 5
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function scorePct(cid) {
  const s = diagResult.value?.per_concept_score?.[cid]
  return s == null ? null : Math.round(s * 100)
}

// ---- Screen 5: roadmap reveal ----
const plan = ref(null)
const planGenerating = ref(false)
const planError = ref(null)
async function generatePlan() {
  planGenerating.value = true
  error.value = ''
  planError.value = null
  try {
    const v = await api.generatePlan(store.goalId)
    plan.value = v
    await initGoal(store.goalId) // refresh store so nav shows goal + versions
  } catch (e) {
    planError.value = e
    error.value = e.message
  } finally {
    planGenerating.value = false
  }
}
function goToApp() { router.push('/home') }

const friendlyPlanError = computed(() => {
  const e = planError.value
  const code = e?.code, status = e?.status
  if (code === 'deadline_too_tight') return t('onboarding.errDeadlineTight')
  if (status === 502) return t('onboarding.errBusy')
  return t('onboarding.errGeneric')
})

// enter concept load when arriving at step 3
watch(step, (s) => {
  if (s === 3 && !concepts.value.length && !confirmDone.value) loadConcepts()
  if (s === 4 && !diag.value && !diagResult.value) generateDiag()
  if (s === 5 && !plan.value) generatePlan()
})

onUnmounted(() => clearInterval(pollTimer))
</script>

<template>
  <div class="page" style="max-width:760px;">
    <div class="eyebrow">{{ $t('onboarding.eyebrow') }}</div>
    <h1>{{ $t('onboarding.title') }}</h1>
    <p class="muted">{{ $t('onboarding.subtitle') }}</p>

    <!-- Stepper -->
    <div class="stepper" style="margin:18px 0 26px;">
      <template v-for="(s, i) in steps" :key="s.n">
        <div class="step" :class="{ active: step === s.n, done: step > s.n }">
          <span class="num">{{ step > s.n ? '✓' : s.n }}</span>{{ s.title }}
        </div>
        <div v-if="i < steps.length - 1" class="line"></div>
      </template>
    </div>

    <div v-if="error" class="card" style="padding:10px 14px;color:var(--danger);border-color:#f0cfc6;background:#fdf1ee;margin-bottom:16px;">{{ error }}</div>

    <!-- ============ Screen 1: goal ============ -->
    <section v-if="step === 1" class="card" style="padding:22px;">
      <div class="stack">
        <div>
          <div class="label">{{ $t('onboarding.goalLabel') }}</div>
          <textarea v-model="goalForm.goal_text" rows="2" :placeholder="$t('onboarding.goalPlaceholder')"></textarea>
        </div>
        <div class="row">
          <div style="flex:1">
            <div class="label">{{ $t('onboarding.deadlineLabel') }}</div>
            <input type="date" v-model="goalForm.deadline" />
          </div>
          <div style="flex:1">
            <div class="label">{{ $t('onboarding.hoursLabel') }}</div>
            <select v-model.number="goalForm.hours_per_day">
              <option v-for="h in maxHoursPerDay" :key="h" :value="h">{{ h }}</option>
            </select>
          </div>
        </div>
        <div>
          <div class="label">{{ $t('onboarding.languageLabel') }}</div>
          <div class="row" style="gap:10px;margin-top:4px;">
            <label class="row" style="gap:6px;font-weight:500;">
              <input type="radio" style="width:auto" value="en" v-model="goalForm.explanation_language" /> English
            </label>
            <label class="row" style="gap:6px;font-weight:500;">
              <input type="radio" style="width:auto" value="zh" v-model="goalForm.explanation_language" /> 中文
            </label>
          </div>
          <div class="faint" style="font-size:12px;margin-top:4px;">{{ $t('onboarding.languageHint') }}</div>
        </div>
        <div>
          <div class="label">{{ $t('onboarding.materialLabel') }}</div>
          <div class="drop" @click="fileInput?.click()">
            <div v-if="!goalForm.filename" class="muted">{{ $t('onboarding.dropHint') }}</div>
            <div v-else><strong>{{ goalForm.filename }}</strong> <span class="faint">{{ $t('onboarding.replaceHint') }}</span></div>
            <input ref="fileInput" type="file" accept=".pdf,.txt" style="display:none" @change="onPickFile" />
          </div>
          <div class="faint" style="font-size:12px;margin-top:4px;">{{ $t('onboarding.noMaterialHint') }}</div>
        </div>
        <div class="row" style="justify-content:flex-end;margin-top:6px;">
          <button class="primary" :disabled="busy" @click="submitGoal">{{ busy ? $t('onboarding.starting') : $t('onboarding.start') }}</button>
        </div>
      </div>
    </section>

    <!-- ============ Screen 2: warm-up ============ -->
    <section v-else-if="step === 2" class="card" style="padding:22px;">
      <h2>{{ $t('onboarding.warmupTitle') }}</h2>
      <p class="muted"><strong>{{ $t('onboarding.warmupNote') }}</strong></p>

      <div class="stack" style="margin-top:10px;">
        <div>
          <div class="label">{{ $t('onboarding.studiedQ') }}</div>
          <div class="row" style="gap:8px;margin-top:4px;">
            <button :class="{ primary: warmup.studied === true }" @click="warmup.studied = true">{{ $t('onboarding.studiedYes') }}</button>
            <button :class="{ primary: warmup.studied === false }" @click="warmup.studied = false">{{ $t('onboarding.studiedNo') }}</button>
          </div>
        </div>
        <div>
          <div class="label">{{ $t('onboarding.scratchQ') }}</div>
          <div class="row" style="gap:8px;margin-top:4px;">
            <button :class="{ primary: warmup.fromScratch === true }" @click="warmup.fromScratch = true">{{ $t('onboarding.scratchYes') }}</button>
            <button :class="{ primary: warmup.fromScratch === false }" @click="warmup.fromScratch = false">{{ $t('onboarding.scratchNo') }}</button>
          </div>
        </div>
        <div>
          <div class="label">{{ $t('onboarding.comfortQ') }}</div>
          <div class="row" style="gap:8px;margin-top:4px;">
            <button :class="{ primary: warmup.comfort === 'low' }" @click="warmup.comfort = 'low'">{{ $t('onboarding.comfortLow') }}</button>
            <button :class="{ primary: warmup.comfort === 'mid' }" @click="warmup.comfort = 'mid'">{{ $t('onboarding.comfortMid') }}</button>
            <button :class="{ primary: warmup.comfort === 'high' }" @click="warmup.comfort = 'high'">{{ $t('onboarding.comfortHigh') }}</button>
          </div>
        </div>
      </div>

      <!-- background material indicator -->
      <div v-if="goalForm.filename" class="card" style="margin-top:18px;padding:12px 14px;background:var(--surface-2);">
        <div class="row">
          <span v-if="docStatus === 'ready'" class="badge ok">{{ $t('onboarding.materialReady') }}</span>
          <span v-else-if="docStatus === 'failed'" class="badge warn">{{ $t('onboarding.materialFailed') }}</span>
          <span v-else class="badge muted">{{ $t('onboarding.materialAnalyzing') }}</span>
          <span class="spacer"></span>
          <span class="faint" v-if="docStatus !== 'ready' && docStatus !== 'failed'">{{ $t('onboarding.materialBackground') }}</span>
        </div>
        <div v-if="docStatus === 'processing' || docStatus === 'uploaded'" class="bar" style="margin-top:8px;"><span style="width:60%"></span></div>
      </div>
      <div v-else class="faint" style="margin-top:18px;">{{ $t('onboarding.noMaterialUploaded') }}</div>

      <div class="row" style="justify-content:flex-end;margin-top:18px;">
        <button class="primary" :disabled="!warmupDone" @click="continueFromWarmup">
          {{ warmupDone ? $t('onboarding.continue') : $t('onboarding.answerToContinue') }}
        </button>
      </div>
    </section>

    <!-- ============ Screen 3: concept confirmation ============ -->
    <section v-else-if="step === 3" class="card" style="padding:22px;">
      <div class="row">
        <h2 style="margin:0;">{{ $t('onboarding.confirmMapTitle') }}</h2>
        <span class="spacer"></span>
        <span class="badge user">{{ $t('onboarding.humanInLoop') }}</span>
      </div>
      <p class="muted">{{ $t('onboarding.confirmMapNote') }}</p>

      <div v-if="extracting" class="empty" style="margin-top:16px;">
        {{ $t('onboarding.extracting', { source: goalForm.filename ? $t('onboarding.material') : $t('onboarding.goalWord') }) }}
      </div>
      <div v-else class="stack" style="margin-top:14px;">
        <div v-for="(c, i) in concepts" :key="i" class="concept-edit card" style="padding:12px 14px;">
          <div class="row">
            <button class="ghost" style="padding:4px 8px;" @click="moveConcept(i, -1)" title="Move up">↑</button>
            <button class="ghost" style="padding:4px 8px;" @click="moveConcept(i, +1)" title="Move down">↓</button>
            <input v-model="c.canonical_term" :placeholder="$t('onboarding.canonicalPlaceholder')" style="font-weight:600;" />
            <button class="ghost" style="padding:4px 8px;color:var(--danger)" @click="removeConcept(i)" title="Remove">✕</button>
          </div>
          <input v-model="c.explanation" :placeholder="$t('onboarding.explanationPlaceholder')" style="margin-top:8px;font-size:13px;" />
          <div class="faint" style="font-size:11px;margin-top:4px;">{{ $t('onboarding.sourceNote', { source: c.source }) }}</div>
        </div>
        <button class="ghost" style="align-self:flex-start;" @click="addConcept">{{ $t('onboarding.addConcept') }}</button>
      </div>

      <div class="row" style="justify-content:space-between;margin-top:18px;">
        <button @click="step = 2">{{ $t('onboarding.back') }}</button>
        <button class="primary" :disabled="busy || !concepts.length" @click="confirmConcepts">
          {{ busy ? $t('onboarding.saving') : $t('onboarding.confirmConcepts') }}
        </button>
      </div>
    </section>

    <!-- ============ Screen 4: diagnostic ============ -->
    <section v-else-if="step === 4" class="card" style="padding:22px;">
      <h2>{{ $t('onboarding.diagnosticTitle') }}</h2>
      <p class="muted">{{ $t('onboarding.diagnosticNote') }}</p>
      <div v-if="diagGenerating" class="empty" style="margin-top:16px;">{{ $t('onboarding.generatingQuestions') }}</div>
      <div v-else-if="!diagResult" class="stack" style="margin-top:14px;">
        <div v-for="q in diag.questions" :key="q.id" class="q card" style="padding:14px;">
          <div class="row" style="gap:8px;">
            <ConceptTag :term="concepts.find(c => c.id === q.concept_id)?.canonical_term || (store.concepts.find(c=>c.id===q.concept_id)?.canonical_term)" />
          </div>
          <div style="margin:8px 0 6px;font-weight:600;">{{ q.prompt }}</div>
          <div class="col" style="gap:6px;">
            <label v-for="opt in q.options" :key="opt" class="row" style="gap:8px;font-weight:500;padding:6px 8px;border:1px solid var(--border);border-radius:8px;cursor:pointer;"
                   :style="answers[q.id] === opt ? 'border-color:var(--brand);background:var(--brand-soft)' : ''">
              <input type="radio" style="width:auto" :name="'q'+q.id" :value="opt" v-model="answers[q.id]" /> {{ opt }}
            </label>
          </div>
        </div>
        <div class="row" style="justify-content:space-between;margin-top:6px;">
          <button @click="step = 3">{{ $t('onboarding.back') }}</button>
          <button class="primary" :disabled="busy" @click="submitDiag">{{ $t('onboarding.submitDiagnostic') }}</button>
        </div>
      </div>
      <div v-else>
        <div class="row"><span class="badge ok">{{ $t('onboarding.diagnosticComplete') }}</span></div>
        <div class="stack" style="margin-top:12px;">
          <div v-for="c in concepts" :key="c.id" class="row">
            <ConceptTag :term="c.canonical_term" />
            <span class="spacer"></span>
            <span class="muted">{{ $t('onboarding.estimatedMastery') }}</span>
            <strong>{{ scorePct(c.id) }}%</strong>
          </div>
        </div>
        <p class="faint" style="font-size:12px;margin-top:8px;">{{ $t('onboarding.masteryDisclaimer') }}</p>
      </div>
    </section>

    <!-- ============ Screen 5: roadmap reveal ============ -->
    <section v-else-if="step === 5" class="card" style="padding:22px;">
      <div class="eyebrow" style="color:var(--user);">{{ $t('onboarding.roadmapEyebrow') }}</div>
      <h2 style="margin-top:4px;">{{ $t('onboarding.roadmapTitle') }}</h2>
      <div v-if="planGenerating" class="empty" style="margin-top:14px;">{{ $t('onboarding.generatingRoadmap') }}</div>

      <!-- failure state: plan gen errored and we have no plan -->
      <div v-else-if="error && !plan" class="card"
           style="margin-top:14px;padding:16px;border-color:#f0cfc6;background:#fdf1ee;">
        <strong style="color:var(--danger);">{{ $t('onboarding.roadmapFailedTitle') }}</strong>
        <p class="muted" style="margin:8px 0 12px;">{{ friendlyPlanError }}</p>
        <button class="primary" @click="generatePlan()">{{ $t('onboarding.retry') }}</button>
      </div>

      <!-- success state -->
      <div v-else-if="plan && plan.tasks">
        <div v-if="diagResult" class="card" style="padding:10px 14px;background:var(--user-soft);border-color:#cfe9dd;margin-bottom:14px;">
          <strong>{{ $t('onboarding.weakConcepts') }}</strong>
          <span v-for="c in concepts.filter(c => scorePct(c.id) !== null && scorePct(c.id) < 60)" :key="c.id" style="margin-left:6px;">
            <ConceptTag :term="c.canonical_term" />
          </span>
        </div>
        <div v-if="plan.coverage_note" class="card"
             style="padding:10px 14px;background:var(--surface-2);margin-bottom:14px;">
          <span class="faint">{{ plan.coverage_note }}</span>
        </div>
        <div class="stack">
          <div v-for="t in plan.tasks" :key="t.id" class="task-row row" style="padding:10px 12px;">
            <span v-if="t.status === 'done'" class="badge ok">✓ done</span>
            <span v-else class="badge muted">{{ t.day }}</span>
            <ConceptTag :term="t.canonical_term" />
            <span>{{ t.description }}</span>
            <span class="spacer"></span>
            <span class="faint">{{ t.est_minutes }} min</span>
          </div>
        </div>
        <div class="row" style="justify-content:flex-end;margin-top:18px;">
          <button class="primary" @click="goToApp">{{ $t('onboarding.openRoadmap') }}</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.drop {
  border: 1.5px dashed var(--border); border-radius: var(--radius-sm);
  padding: 18px; text-align: center; cursor: pointer; margin-top: 6px;
  background: var(--surface-2);
}
.drop:hover { border-color: var(--brand); }
.concept-edit input { width: 100%; }
.task-row { background: var(--surface-2); border-radius: var(--radius-sm); gap: 10px; }
.q { background: var(--surface); }
</style>
