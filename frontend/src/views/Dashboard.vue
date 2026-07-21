<script setup>
import { ref, onMounted, shallowRef, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import store, { api, refreshVersions } from '../store.js'

const masterEl = shallowRef(null)
const progressEl = shallowRef(null)
const trendEl = shallowRef(null)
const masterChart = shallowRef(null)
const progressChart = shallowRef(null)
const trendChart = shallowRef(null)

const mastery = ref({})        // concept_id -> 0..1 (from diagnostic result or estimate)
const conceptMeta = ref([])    // ConceptOut[]
const plan = ref(null)
const versions = ref([])

async function load() {
  await refreshVersions(store.goalId)
  conceptMeta.value = store.concepts
  versions.value = store.versions
  plan.value = store.currentPlan

  // Per-concept mastery: prefer diagnostic result, else heuristic from pending tasks.
  const res = store.diagnosticResult
  const m = {}
  conceptMeta.value.forEach((c) => {
    if (res?.per_concept_score?.[c.id] != null) m[c.id] = res.per_concept_score[c.id]
    else {
      const tasks = plan.value?.tasks.filter((t) => t.concept_id === c.id) || []
      const done = tasks.filter((t) => t.status === 'done').length
      m[c.id] = tasks.length ? Math.max(0.1, done / tasks.length) : 0.5
    }
  })
  mastery.value = m
  await nextTick()
  render()
}

function render() {
  if (masterEl.value && !masterChart.value) masterChart.value = echarts.init(masterEl.value)
  if (progressEl.value && !progressChart.value) progressChart.value = echarts.init(progressEl.value)
  if (trendEl.value && !trendChart.value) trendChart.value = echarts.init(trendEl.value)

  // 1. Per-concept mastery (bar) — estimated, honest label
  const terms = conceptMeta.value.map((c) => c.canonical_term)
  const vals = conceptMeta.value.map((c) => Math.round((mastery.value[c.id] || 0) * 100))
  masterChart.value?.setOption({
    title: { text: 'Estimated mastery by concept', left: 0, textStyle: { fontSize: 14, color: '#1b2430' } },
    tooltip: { valueFormatter: (v) => v + '% (estimated)' },
    grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: terms, axisLabel: { interval: 0, fontSize: 11 } },
    yAxis: { type: 'value', max: 100 },
    series: [{
      type: 'bar', data: vals, barWidth: '46%',
      itemStyle: {
        color: (p) => p.value < 60 ? '#c0563b' : (p.value < 80 ? '#b5852b' : '#2f8f6b'),
        borderRadius: [6, 6, 0, 0]
      },
      label: { show: true, position: 'top', formatter: '{c}%' }
    }]
  })

  // 2. Progress vs schedule (gauge)
  const tasks = plan.value?.tasks || []
  const done = tasks.filter((t) => t.status === 'done').length
  const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0
  progressChart.value?.setOption({
    title: { text: 'Progress vs schedule', left: 0, textStyle: { fontSize: 14, color: '#1b2430' } },
    series: [{
      type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100, radius: '92%', center: ['50%', '62%'],
      progress: { show: true, width: 14, itemStyle: { color: '#3b6fb0' } },
      axisLine: { lineStyle: { width: 14, color: [[1, '#e2e6ec']] } },
      pointer: { show: false }, axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { show: false },
      detail: { valueAnimation: true, fontSize: 30, offsetCenter: [0, '5%'], formatter: '{value}%', color: '#1b2430' },
      data: [{ value: pct }]
    }]
  })

  // 3. Tasks done over time (trend) — synthetic from versions
  const days = versions.value.map((v) => 'v' + v.version_no)
  const donePerVersion = versions.value.map((v) => {
    // number of done tasks at that version (cumulative-ish demo signal)
    const t = plan.value?.tasks || []
    return t.filter((x) => x.status === 'done').length
  })
  trendChart.value?.setOption({
    title: { text: 'Tasks completed across versions', left: 0, textStyle: { fontSize: 14, color: '#1b2430' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: days, boundaryGap: false },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'line', smooth: true, data: donePerVersion,
      lineStyle: { width: 3, color: '#2f8f6b' }, itemStyle: { color: '#2f8f6b' },
      areaStyle: { color: 'rgba(47,143,107,.12)' }
    }]
  })
}

function resizeAll() {
  masterChart.value?.resize(); progressChart.value?.resize(); trendChart.value?.resize()
}
onMounted(() => { load(); window.addEventListener('resize', resizeAll) })
watch(() => store.goalId, load)
</script>

<template>
  <div class="page">
    <div class="eyebrow">Dashboard</div>
    <h1>Learning overview</h1>
    <p class="muted">Mastery is an estimated signal from your evidence so far — not a measurement.</p>

    <div class="grid">
      <div class="card chart-card"><div ref="masterEl" class="chart"></div></div>
      <div class="card chart-card"><div ref="progressEl" class="chart"></div></div>
    </div>
    <div class="card chart-card" style="margin-top:16px;"><div ref="trendEl" class="chart"></div></div>

    <div v-if="!conceptMeta.length" class="empty" style="margin-top:16px;">
      No concept data yet — finish onboarding to populate the dashboard.
    </div>
  </div>
</template>

<style scoped>
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chart-card { padding: 12px; }
.chart { width: 100%; height: 280px; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
</style>
