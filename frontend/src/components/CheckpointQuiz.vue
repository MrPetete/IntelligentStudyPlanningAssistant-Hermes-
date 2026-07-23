<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../store.js'

const props = defineProps({
  goalId: { type: Number, required: true },
  day: { type: String, default: null },
  // Remediation blocks span whatever days the agent picked, not one single
  // day — scope by their concepts directly instead (B-V2-2).
  conceptIds: { type: Array, default: null },
  // A previously-saved result for this unit. When present, re-opening the
  // panel shows it directly instead of generating a brand-new quiz — a
  // checkpoint quiz should be a one-shot re-test per unit, not something
  // that regenerates every time the toggle is clicked.
  initialResult: { type: Object, default: null }
})
const emit = defineEmits(['done']) // done({ passed, result }) — result is the full CheckpointResult

const loading = ref(true)
const submitting = ref(false)
const err = ref('')
const checkpoint = ref(null)
const answers = reactive({})
const result = ref(null)

const PASS_THRESHOLD = 0.5 // mirrors config.TRIGGERS.quiz_fail_threshold

function passedFrom(res) {
  const scores = Object.values(res.per_concept_score || {})
  return scores.length === 0 || scores.every((s) => s >= PASS_THRESHOLD)
}

async function load() {
  if (props.initialResult) {
    // Already taken — show the saved result, no new quiz/network call.
    // initialResult carries its own `questions` (saved alongside the result)
    // so questionPrompt() below still has prompts to render.
    checkpoint.value = { questions: props.initialResult.questions || [] }
    result.value = props.initialResult
    loading.value = false
    return
  }
  loading.value = true
  err.value = ''
  try {
    checkpoint.value = await api.generateCheckpoint(props.goalId,
      props.conceptIds && props.conceptIds.length
        ? { conceptIds: props.conceptIds }
        : { day: props.day })
  } catch (e) {
    err.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(load)

const unanswered = computed(() =>
  (checkpoint.value?.questions || []).filter((q) => !answers[q.id]))

async function submit() {
  if (unanswered.value.length) { err.value = ''; return }
  submitting.value = true
  err.value = ''
  try {
    const body = checkpoint.value.questions.map((q) => ({ question_id: q.id, choice: answers[q.id] }))
    const res = await api.submitCheckpoint(props.goalId, checkpoint.value.checkpoint_id, body)
    // Persist the questions alongside the result so a later re-open of this
    // unit's panel can render prompts without re-fetching (see load() above).
    const full = { ...res, questions: checkpoint.value.questions }
    result.value = full
    emit('done', { passed: passedFrom(res), result: full })
  } catch (e) {
    err.value = e.message
  } finally {
    submitting.value = false
  }
}
function pct(s) { return Math.round((s ?? 0) * 100) }
function questionPrompt(questionId) {
  return checkpoint.value?.questions?.find((q) => q.id === questionId)?.prompt || ''
}
</script>

<template>
  <div class="card" style="padding:20px;">
    <div class="eyebrow" style="color:var(--user);">{{ $t('checkpoint.eyebrow') }}</div>
    <h2 style="margin-top:4px;">{{ $t('checkpoint.title') }}</h2>
    <p class="muted">{{ $t('checkpoint.subtitle') }}</p>

    <div v-if="loading" class="empty" style="margin-top:14px;">{{ $t('checkpoint.generating') }}</div>
    <div v-else-if="err && !checkpoint" class="card" style="margin-top:14px;padding:14px;color:var(--danger);">{{ err }}</div>

    <div v-else-if="!result" class="stack" style="margin-top:14px;">
      <div v-for="q in checkpoint.questions" :key="q.id" class="q card" style="padding:14px;">
        <div style="font-weight:600;margin-bottom:8px;">{{ q.prompt }}</div>
        <div class="col" style="gap:6px;">
          <label v-for="opt in q.options" :key="opt" class="row" style="gap:8px;font-weight:500;padding:6px 8px;border:1px solid var(--border);border-radius:8px;cursor:pointer;"
                 :style="answers[q.id] === opt ? 'border-color:var(--brand);background:var(--brand-soft)' : ''">
            <input type="radio" style="width:auto" :name="'cp'+q.id" :value="opt" v-model="answers[q.id]" /> {{ opt }}
          </label>
        </div>
      </div>
      <div v-if="err" class="card" style="padding:10px 14px;color:var(--danger);">{{ err }}</div>
      <div class="row" style="justify-content:flex-end;">
        <button class="primary" :disabled="submitting" @click="unanswered.length ? (err = $t('checkpoint.answerAll')) : submit()">
          {{ $t('checkpoint.submit') }}
        </button>
      </div>
    </div>

    <div v-else>
      <div class="row"><span class="badge ok">{{ $t('checkpoint.resultTitle') }}</span></div>
      <div class="stack" style="margin-top:12px;">
        <div v-for="(score, cid) in result.per_concept_score" :key="cid" class="row">
          <span class="muted">{{ $t('checkpoint.scorePrefix') }} · concept {{ cid }}</span>
          <span class="spacer"></span>
          <strong>{{ pct(score) }}%</strong>
        </div>
      </div>

      <div v-if="result.per_question && result.per_question.length" class="stack" style="margin-top:16px;gap:8px;">
        <div class="muted" style="font-size:13px;">{{ $t('checkpoint.breakdownTitle') }}</div>
        <div v-for="pq in result.per_question" :key="pq.question_id" class="card question-result"
             :class="pq.is_correct ? 'correct' : 'incorrect'" style="padding:12px;">
          <div style="font-weight:600;margin-bottom:6px;">{{ questionPrompt(pq.question_id) }}</div>
          <div class="row" style="gap:6px;flex-wrap:wrap;">
            <span class="badge" :class="pq.is_correct ? 'ok' : 'bad'">
              {{ pq.submitted ?? $t('checkpoint.noAnswer') }}
            </span>
            <span v-if="!pq.is_correct && pq.correct_choice" class="badge ok">
              {{ $t('checkpoint.correctAnswerPrefix') }} {{ pq.correct_choice }}
            </span>
          </div>
        </div>
      </div>

      <slot name="after-result" :result="result" />
    </div>
  </div>
</template>

<style scoped>
.q { background: var(--surface); }
.question-result.correct { border-color: #b7dfc4; background: var(--user-soft, #f0f9f3); }
.question-result.incorrect { border-color: #f0c6c6; background: var(--agent-soft, #fbeeee); }
.badge.bad { background: #f8d7d7; color: #a33a3a; }
</style>
