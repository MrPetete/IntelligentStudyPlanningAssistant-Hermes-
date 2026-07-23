<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../store.js'

const props = defineProps({
  goalId: { type: Number, required: true },
  day: { type: String, required: true }
})
const emit = defineEmits(['done']) // done({ passed, per_concept_score, trigger_fired })

const loading = ref(true)
const submitting = ref(false)
const err = ref('')
const checkpoint = ref(null)
const answers = reactive({})
const result = ref(null)

const PASS_THRESHOLD = 0.5 // mirrors config.TRIGGERS.quiz_fail_threshold

async function load() {
  loading.value = true
  err.value = ''
  try {
    checkpoint.value = await api.generateCheckpoint(props.goalId, { day: props.day })
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
    result.value = res
    const scores = Object.values(res.per_concept_score || {})
    const passed = scores.length === 0 || scores.every((s) => s >= PASS_THRESHOLD)
    emit('done', { passed, per_concept_score: res.per_concept_score, trigger_fired: res.trigger_fired })
  } catch (e) {
    err.value = e.message
  } finally {
    submitting.value = false
  }
}
function pct(s) { return Math.round((s ?? 0) * 100) }
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
      <slot name="after-result" :result="result" />
    </div>
  </div>
</template>

<style scoped>
.q { background: var(--surface); }
</style>
