/**
 * Stateful mock backend. Implements every endpoint in
 * app/frontend/README_FRONTEND.md against the schemas.py contract, so the
 * frontend is never blocked waiting on Member A.
 *
 * Goal id 1 is pre-seeded with the rich demo data (concepts, V1+V2 plans,
 * decisions, evidence) from mock_api_examples/, so the diff + tool-trace
 * screens are fully populated on first load. New goals created through
 * onboarding get synthetic-but-plausible content generated on the fly.
 *
 * All shapes match schemas.py exactly. No field is invented.
 */
import {
  seedGoal, seedConcepts, seedDiagnostic, seedDiagnosticResult,
  seedV1Tasks, seedV2Tasks, seedDecisions, seedEvidence
} from './seed.js'

const clone = (o) => JSON.parse(JSON.stringify(o))
const nowIso = () => new Date().toISOString().replace('.000', '')

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------
const state = {
  goals: new Map(),
  concepts: new Map(),    // goalId -> ConceptOut[]
  diagnostics: new Map(), // goalId -> DiagnosticOut
  diagnosticResults: new Map(), // goalId -> DiagnosticResult
  versions: new Map(),    // goalId -> Map(version_no -> PlanVersionOut)
  currentVersion: new Map(), // goalId -> version_no
  decisions: new Map(),   // goalId -> AgentDecisionOut[]
  evidence: new Map(),    // goalId -> EvidenceCreate[]
  docStatus: new Map()    // goalId -> DocumentStatusOut
}

function seedGoal1() {
  const g = clone(seedGoal)
  state.goals.set(g.id, g)
  state.concepts.set(g.id, clone(seedConcepts))
  state.diagnostics.set(g.id, clone(seedDiagnostic))
  state.diagnosticResults.set(g.id, clone(seedDiagnosticResult))
  const vm = new Map()
  vm.set(1, { id: 1, version_no: 1, created_by: 'user', parent_version_id: null,
              created_at: '2026-07-19T12:00:00+00:00', tasks: clone(seedV1Tasks) })
  vm.set(2, { id: 2, version_no: 2, created_by: 'agent', parent_version_id: 1,
              created_at: '2026-07-20T10:32:11+00:00', tasks: clone(seedV2Tasks) })
  state.versions.set(g.id, vm)
  state.currentVersion.set(g.id, 2)
  state.decisions.set(g.id, clone(seedDecisions))
  state.evidence.set(g.id, clone(seedEvidence))
  state.docStatus.set(g.id, { goal_id: g.id, filename: 'db_course_notes.pdf', status: 'ready' })
}
seedGoal1()

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function conceptsForGoal(goalId) {
  return state.concepts.get(goalId) || []
}
function nextConceptId(goalId) {
  const list = conceptsForGoal(goalId)
  return list.reduce((m, c) => Math.max(m, c.id || 0), 0) + 1
}
function buildVersion(goalId, version_no, created_by, parent_version_id, tasks) {
  return {
    id: version_no,
    version_no,
    created_by,
    parent_version_id,
    created_at: nowIso(),
    tasks
  }
}

// Synthetic concept generation for newly created goals.
function generateConcepts(goal) {
  const lang = goal.explanation_language || 'en'
  if (goal.document_status === 'ready') {
    // Material grounded: reuse the sample DB concept set (demo narrative).
    return clone(seedConcepts).map((c) => ({ ...c, confirmed: false }))
  }
  // No material: derive from the goal topic (source='goal_topic').
  const words = (goal.goal_text || 'General study').trim().split(/\s+/).slice(0, 3)
    .join(' ')
  const topic = words.charAt(0).toUpperCase() + words.slice(1)
  const ex = lang === 'zh'
    ? `基于目标「${goal.goal_text}」推导出的核心主题，作为无资料时的后备概念。`
    : `Core topic derived from the goal "${goal.goal_text}" — fallback used when no material is uploaded.`
  return [
    { id: 1, canonical_term: topic, name: topic, explanation: ex, order_index: 1,
      parent_concept_id: null, source: 'goal_topic', confirmed: false },
    { id: 2, canonical_term: 'Practice', name: 'Practice',
      explanation: lang === 'zh' ? '通过练习巩固上述主题。' : 'Reinforce the topic through practice.',
      order_index: 2, parent_concept_id: null, source: 'goal_topic', confirmed: false }
  ]
}

function generateDiagnostic(goalId) {
  const concepts = conceptsForGoal(goalId)
  const lang = state.goals.get(goalId).explanation_language
  const qTemplates = lang === 'zh'
    ? [
        (t) => `关于 ${t}，以下哪项描述最准确？`,
        (t) => `在 ${t} 中，最常见的错误是什么？`,
        (t) => `为什么 ${t} 在数据库设计中很重要？`
      ]
    : [
        (t) => `Which statement best describes ${t}?`,
        (t) => `In ${t}, what is the most common mistake?`,
        (t) => `Why does ${t} matter in database design?`
      ]
  const opt = lang === 'zh'
    ? ['定义清晰', '应用熟练', '能够迁移', '尚未掌握']
    : ['Clearly defined', 'Applied fluently', 'Can transfer', 'Not yet grasped']
  const questions = []
  let qid = 100
  concepts.forEach((c, ci) => {
    const n = Math.min(3, 3)
    for (let i = 0; i < n; i++) {
      questions.push({
        id: qid++,
        concept_id: c.id,
        prompt: qTemplates[i % qTemplates.length](c.canonical_term),
        options: opt
      })
    }
  })
  return { diagnostic_id: 1, questions }
}

function generateV1(goalId) {
  const concepts = conceptsForGoal(goalId)
  const lang = state.goals.get(goalId).explanation_language
  const start = new Date(state.goals.get(goalId).created_at || nowIso())
  const tasks = []
  let tid = 1
  concepts.forEach((c, ci) => {
    for (let d = 0; d < 2; d++) {
      const day = new Date(start)
      day.setDate(start.getDate() + ci * 2 + d)
      tasks.push({
        id: tid++,
        concept_id: c.id,
        canonical_term: c.canonical_term,
        day: day.toISOString().slice(0, 10),
        description: lang === 'zh'
          ? `${c.canonical_term}：第 ${d + 1} 步学习任务。`
          : `${c.canonical_term}: learning task ${d + 1}.`,
        est_minutes: 40,
        status: 'pending'
      })
    }
  })
  return tasks
}

// Compute PlanDiff between two task lists.
function computeDiff(fromNo, toNo, fromTasks, toTasks) {
  const fromIds = new Set(fromTasks.map((t) => t.id))
  const toIds = new Set(toTasks.map((t) => t.id))
  const added = toTasks.filter((t) => !fromIds.has(t.id))
  const removed = fromTasks.filter((t) => !toIds.has(t.id))
  const unchanged = fromTasks.filter((t) => toIds.has(t.id)).length
  // reschedules: same id, different day
  const fromById = new Map(fromTasks.map((t) => [t.id, t]))
  const rescheduled = []
  toTasks.forEach((t) => {
    const f = fromById.get(t.id)
    if (f && f.day && t.day && f.day !== t.day) rescheduled.push({ id: t.id, from: f.day, to: t.day })
  })
  // concept summary
  const conceptSummary = {}
  const tally = (list, verb) => {
    const byC = {}
    list.forEach((t) => { byC[t.canonical_term] = (byC[t.canonical_term] || 0) + 1 })
    Object.entries(byC).forEach(([term, n]) => {
      conceptSummary[term] = (conceptSummary[term] ? conceptSummary[term] + '; ' : '') +
        `${n} ${verb}`
    })
  }
  tally(added, 'added')
  tally(removed, 'removed')
  if (rescheduled.length) {
    conceptSummary['_rescheduled'] = `${rescheduled.length} task(s) rescheduled`
  }
  return {
    from_version: fromNo,
    to_version: toNo,
    added_tasks: added,
    removed_tasks: removed,
    unchanged_count: unchanged,
    concept_summary: conceptSummary,
    _rescheduled: rescheduled
  }
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
export function handleMock(method, path, body) {
  const t0 = Date.now()
  const respond = (data, status = 200) => ({
    ok: status >= 200 && status < 300, status, data, ms: Date.now() - t0
  })
  const fail = (status, msg) => ({ ok: false, status, data: { detail: msg } })
  try {
    return respond(route(method, path, body))
  } catch (e) {
    if (e && e._status) return fail(e._status, e.message)
    console.error('[mock] error', e)
    return fail(500, String(e))
  }
}

function httpError(status, msg) { const e = new Error(msg); e._status = status; throw e }

function route(method, path, body) {
  const [m, p] = [method.toUpperCase(), path]
  const goalRe = /^\/goals\/(\d+)/
  const goalMatch = p.match(goalRe)

  // POST /goals
  if (m === 'POST' && p === '/goals') {
    const id = (Math.max(1, ...state.goals.keys()) || 1) + 1
    const g = {
      id,
      goal_text: body.goal_text,
      deadline: body.deadline,
      weekly_hours: body.weekly_hours,
      explanation_language: body.explanation_language || 'en',
      document_status: body.filename ? 'uploaded' : 'none',
      created_at: nowIso()
    }
    state.goals.set(id, g)
    state.concepts.set(id, [])
    state.diagnostics.set(id, null)
    state.versions.set(id, new Map())
    state.currentVersion.set(id, null)
    state.decisions.set(id, [])
    state.evidence.set(id, [])
    state.docStatus.set(id, { goal_id: id, filename: body.filename || null,
      status: body.filename ? 'uploaded' : 'none' })
    return g
  }

  // POST /tasks/{task_id}/complete  (NOT goal-prefixed — handle before the goalMatch guard)
  const taskRe = /^\/tasks\/(\d+)\/complete$/
  const taskM = p.match(taskRe)
  if (m === 'POST' && taskM) {
    const taskId = Number(taskM[1])
    // Find the goal that owns this task (tasks live under a goal's versions).
    let goalId = null
    for (const [gid, vm] of state.versions.entries()) {
      for (const v of vm.values()) {
        if (v.tasks.some((t) => t.id === taskId)) { goalId = gid; break }
      }
      if (goalId != null) break
    }
    if (goalId == null) httpError(404, 'task not found')
    const vm = state.versions.get(goalId)
    let found = false
    vm.forEach((v) => {
      v.tasks.forEach((t) => { if (t.id === taskId) { t.status = 'done'; found = true } })
    })
    const res = state.diagnosticResults.get(goalId)
    const scores = res?.per_concept_score || {}
    const triggerFired = Object.values(scores).some((s) => s < 0.5)
    // Option A: when the trigger fires, actually run a replan (like the real backend)
    // so the toast is truthful and Version History shows a new version.
    const result = { task_id: taskId, status: found ? 'done' : 'pending', trigger_fired: triggerFired }
    if (triggerFired) {
      // doReplan returns { scenario, evidence_created, trigger_fired, decision_id } directly
      // (not wrapped in .data like handleMock responses).
      const g = state.goals.get(goalId)
      const simDec = doReplan(goalId, 'low_mastery', g?.explanation_language || 'en')
      result.decision_id = simDec.decision_id
    }
    return result
  }

  if (!goalMatch) return httpError(404, 'unknown endpoint ' + m + ' ' + p)
  const goalId = Number(goalMatch[1])
  const g = state.goals.get(goalId)
  if (!g) httpError(404, 'goal not found')

  // GET /goals/{id}
  if (m === 'GET' && p === `/goals/${goalId}`) return g

  // PATCH /goals/{id}/language
  if (m === 'PATCH' && p === `/goals/${goalId}/language`) {
    g.explanation_language = body.explanation_language
    return { id: goalId, explanation_language: g.explanation_language }
  }

  // POST /goals/{id}/document
  if (m === 'POST' && p === `/goals/${goalId}/document`) {
    const filename = body.filename || 'uploaded.pdf'
    state.docStatus.set(goalId, { goal_id: goalId, filename, status: 'uploaded' })
    g.document_status = 'uploaded'
    // simulate async processing -> ready
    setTimeout(() => {
      const ds = state.docStatus.get(goalId)
      if (ds) { ds.status = 'ready' }
      g.document_status = 'ready'
    }, 1800)
    return state.docStatus.get(goalId)
  }

  // GET /goals/{id}/document
  if (m === 'GET' && p === `/goals/${goalId}/document`) {
    return state.docStatus.get(goalId) || { goal_id: goalId, filename: null, status: 'none' }
  }

  // POST /goals/{id}/concepts:extract
  if (m === 'POST' && p === `/goals/${goalId}/concepts:extract`) {
    const list = generateConcepts(g).map((c) => ({ id: c.id, ...c }))
    state.concepts.set(goalId, list)
    return list
  }

  // GET /goals/{id}/concepts
  if (m === 'GET' && p === `/goals/${goalId}/concepts`) {
    return conceptsForGoal(goalId)
  }

  // PUT /goals/{id}/concepts
  if (m === 'PUT' && p === `/goals/${goalId}/concepts`) {
    const confirmed = body.concepts.map((c, i) => ({
      id: c.id != null ? c.id : nextConceptId(goalId) + i,
      canonical_term: c.canonical_term,
      name: c.name,
      explanation: c.explanation,
      order_index: c.order_index != null ? c.order_index : i + 1,
      parent_concept_id: c.parent_concept_id,
      source: c.id != null ? (conceptsForGoal(goalId).find((x) => x.id === c.id)?.source || 'material') : 'user_added',
      confirmed: true
    }))
    state.concepts.set(goalId, confirmed)
    return confirmed
  }

  // POST /goals/{id}/diagnostic
  if (m === 'POST' && p === `/goals/${goalId}/diagnostic`) {
    if (!conceptsForGoal(goalId).length) httpError(400, 'confirm concepts first')
    const d = generateDiagnostic(goalId)
    state.diagnostics.set(goalId, d)
    return d
  }

  // POST /goals/{id}/diagnostic/submit
  if (m === 'POST' && p === `/goals/${goalId}/diagnostic/submit`) {
    const diag = state.diagnostics.get(goalId)
    const per = {}
    conceptsForGoal(goalId).forEach((c) => { per[c.id] = 0.75 })
    // heuristic: first option chosen => high, later => lower (mock signal only)
    ;(body.answers || []).forEach((a) => {
      const idx = diag?.questions.find((q) => q.id === a.question_id)?.options.indexOf(a.choice) ?? 0
      per[a.question_id === undefined ? 0 : (diag?.questions.find((q) => q.id === a.question_id)?.concept_id)] =
        Math.max(0.2, 1 - idx * 0.25)
    })
    // collapse to per-concept
    const perConcept = {}
    conceptsForGoal(goalId).forEach((c) => { perConcept[c.id] = per[c.id] || 0.7 })
    const res = { per_concept_score: perConcept }
    state.diagnosticResults.set(goalId, res)
    return res
  }

  // POST /goals/{id}/plan/generate
  if (m === 'POST' && p === `/goals/${goalId}/plan/generate`) {
    const vm = state.versions.get(goalId)
    const v1 = buildVersion(goalId, 1, 'user', null, generateV1(goalId))
    vm.set(1, v1)
    state.currentVersion.set(goalId, 1)
    return v1
  }

  // GET /goals/{id}/plan/current
  if (m === 'GET' && p === `/goals/${goalId}/plan/current`) {
    const cur = state.currentVersion.get(goalId)
    if (!cur) httpError(404, 'no plan yet')
    return state.versions.get(goalId).get(cur)
  }

  // GET /goals/{id}/plan/versions
  if (m === 'GET' && p === `/goals/${goalId}/plan/versions`) {
    const vm = state.versions.get(goalId)
    return [...vm.values()].sort((a, b) => a.version_no - b.version_no).map((v) => ({
      id: v.id, version_no: v.version_no, created_by: v.created_by,
      parent_version_id: v.parent_version_id, created_at: v.created_at
    }))
  }

  // GET /goals/{id}/plan/versions/{version_no}
  const vRe = /^\/goals\/\d+\/plan\/versions\/(\d+)$/
  const vM = p.match(vRe)
  if (m === 'GET' && vM) {
    const v = state.versions.get(goalId).get(Number(vM[1]))
    if (!v) httpError(404, 'version not found')
    return v
  }

  // GET /goals/{id}/plan/diff?from=1&to=2
  if (m === 'GET' && p.startsWith(`/goals/${goalId}/plan/diff`)) {
    const q = new URLSearchParams(p.split('?')[1] || '')
    const fromNo = Number(q.get('from'))
    const toNo = Number(q.get('to'))
    const vm = state.versions.get(goalId)
    const from = vm.get(fromNo), to = vm.get(toNo)
    if (!from || !to) httpError(404, 'version not found')
    return computeDiff(fromNo, toNo, from.tasks, to.tasks)
  }

  // POST /goals/{id}/evidence
  if (m === 'POST' && p === `/goals/${goalId}/evidence`) {
    const ev = { id: (state.evidence.get(goalId).length || 0) + 1, ...body, created_at: nowIso() }
    state.evidence.get(goalId).push(ev)
    return ev
  }

  // POST /goals/{id}/replan  (manual replan control)
  if (m === 'POST' && p === `/goals/${goalId}/replan`) {
    return doReplan(goalId, 'explicit_user_request', 'en')
  }

  // POST /goals/{id}/simulate
  if (m === 'POST' && p === `/goals/${goalId}/simulate`) {
    const scenario = body.scenario || 'normalization_failure'
    if (scenario === 'missed_tasks') {
      // 25% overdue trigger -> new version
      const vm = state.versions.get(goalId)
      const last = [...vm.values()].sort((a, b) => a.version_no - b.version_no).pop()
      const nextNo = last.version_no + 1
      const newTasks = clone(last.tasks)
      newTasks.push({
        id: 900 + nextNo, concept_id: conceptsForGoal(goalId)[0]?.id || 1,
        canonical_term: conceptsForGoal(goalId)[0]?.canonical_term || 'Catch-up',
        day: new Date().toISOString().slice(0, 10),
        description: 'Catch-up task added after missed deadline.', est_minutes: 30, status: 'pending'
      })
      const v = buildVersion(goalId, nextNo, 'agent', last.version_no, newTasks)
      vm.set(nextNo, v)
      state.currentVersion.set(goalId, nextNo)
      const dec = {
        id: (state.decisions.get(goalId).length || 0) + 1,
        trigger: 'behind_schedule',
        evidence_snapshot: { progress: { tasks_due: 8, tasks_incomplete: 6 }, evidence_count: 3 },
        reasoning_text: '25% of tasks are overdue. Added a catch-up task to recover the schedule.',
        tool_trace: [
          { tool: 'get_learner_state', args: { goal_id: goalId }, result_summary: 'goal, deadline, weekly_hours' },
          { tool: 'get_progress_summary', args: { goal_id: goalId }, result_summary: 'tasks_due=8, tasks_incomplete=6' },
          { tool: 'get_evidence_since_last_plan', args: { goal_id: goalId }, result_summary: '3 items' },
          { tool: 'llm.decide_replan', args: { explanation_language: g.explanation_language }, result_summary: 'decision=new_version' },
          { tool: 'validator.validate_plan', args: { attempt: 0 }, result_summary: 'ok' },
          { tool: 'create_plan_version', args: { task_count: newTasks.length }, result_summary: `version_no=${nextNo}` }
        ],
        decision: 'new_version', resulting_plan_version_id: v.id, created_at: nowIso()
      }
      state.decisions.get(goalId).push(dec)
      return { scenario, evidence_created: 3, trigger_fired: true, decision_id: dec.id }
    }
    // default: normalization_failure -> reuse seed decision 1 pattern for this goal
    return doReplan(goalId, 'low_mastery', g.explanation_language)
  }

  // GET /goals/{id}/decisions
  if (m === 'GET' && p === `/goals/${goalId}/decisions`) {
    return state.decisions.get(goalId).map((d) => ({
      id: d.id, trigger: d.trigger, decision: d.decision,
      resulting_plan_version_id: d.resulting_plan_version_id, created_at: d.created_at
    }))
  }

  // GET /goals/{id}/decisions/{decision_id}
  const dRe = /^\/goals\/\d+\/decisions\/(\d+)$/
  const dM = p.match(dRe)
  if (m === 'GET' && dM) {
    const d = state.decisions.get(goalId).find((x) => x.id === Number(dM[1]))
    if (!d) httpError(404, 'decision not found')
    return d
  }

  return httpError(404, 'unknown endpoint ' + m + ' ' + p)
}

function doReplan(goalId, trigger, lang) {
  const vm = state.versions.get(goalId)
  const last = [...vm.values()].sort((a, b) => a.version_no - b.version_no).pop()
  const nextNo = last.version_no + 1
  const newTasks = clone(last.tasks)
  newTasks.push({
    id: 900 + nextNo,
    concept_id: conceptsForGoal(goalId).find((c) => c.canonical_term === 'Normalization')?.id || conceptsForGoal(goalId)[0]?.id || 1,
    canonical_term: 'Normalization',
    day: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
    description: 'Remediation: review 1NF-3NF with worked examples.',
    est_minutes: 40, status: 'pending'
  })
  const v = buildVersion(goalId, nextNo, 'agent', last.version_no, newTasks)
  vm.set(nextNo, v)
  state.currentVersion.set(goalId, nextNo)
  const dec = {
    id: (state.decisions.get(goalId).length || 0) + 1,
    trigger,
    evidence_snapshot: { progress: { tasks_total: 5, tasks_done: 1, tasks_due: 5, tasks_incomplete: 4 }, evidence_count: 4 },
    reasoning_text: lang === 'zh'
      ? '你最近关于 Normalization 的测验得分较低，且多个 Normalization 任务未完成。由于该概念是后续主题的基础，我在继续之前新增了两个 Normalization 巩固任务。'
      : 'Your recent Normalization quiz score was low and several Normalization tasks are incomplete. Since this concept is foundational, I added a Normalization remediation task before continuing.',
    tool_trace: [
      { tool: 'get_learner_state', args: { goal_id: goalId }, result_summary: 'goal_text, deadline, weekly_hours, explanation_language' },
      { tool: 'get_progress_summary', args: { goal_id: goalId }, result_summary: 'tasks_total, tasks_done, tasks_due, tasks_incomplete' },
      { tool: 'get_evidence_since_last_plan', args: { goal_id: goalId }, result_summary: '4 items' },
      { tool: 'get_current_plan', args: { goal_id: goalId }, result_summary: 'plan_version_id, version_no, tasks' },
      { tool: 'llm.decide_replan', args: { explanation_language: lang, evidence_count: 4 }, result_summary: 'decision=new_version' },
      { tool: 'validator.validate_plan', args: { attempt: 0 }, result_summary: 'ok' },
      { tool: 'create_plan_version', args: { task_count: newTasks.length }, result_summary: `version_no=${nextNo}` },
      { tool: 'record_agent_decision', args: { decision_id: (state.decisions.get(goalId).length || 0) + 1 }, result_summary: 'recorded' }
    ],
    decision: 'new_version', resulting_plan_version_id: v.id, created_at: nowIso()
  }
  state.decisions.get(goalId).push(dec)
  return { scenario: trigger, evidence_created: 4, trigger_fired: true, decision_id: dec.id }
}

// Expose a reset for the demo.
export function resetMock() {
  state.goals.clear(); state.concepts.clear(); state.diagnostics.clear()
  state.diagnosticResults.clear(); state.versions.clear(); state.currentVersion.clear()
  state.decisions.clear(); state.evidence.clear(); state.docStatus.clear()
  seedGoal1()
}
