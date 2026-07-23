/**
 * API client — mapped 1:1 to the endpoints in app/frontend/README_FRONTEND.md.
 *
 * MOCK-FIRST: USE_REAL is a hard switch.
 *   - When USE_REAL = false: every call is served by the in-browser mock server
 *     in src/mock/server.js (no network, no backend dependency).
 *   - When USE_REAL = true: every call goes to the real backend at
 *     http://127.0.0.1:8000. There is NO automatic fallback to the mock.
 *
 * No contract field is invented; the mock mirrors schemas.py.
 */
import { handleMock, resetMock } from './mock/server.js'

const REAL_BASE = 'http://127.0.0.1:8000'
// ---------------------------------------------------------------------------
// Error normalization — surfaces structured errors (.status, .code, real string)
// on BOTH mock and real paths, so the UI can actually map them.
// ---------------------------------------------------------------------------
function throwApiError(status, data, method, path) {
  const detail = data && data.detail
  const isObj = detail && typeof detail === 'object'
  const err = new Error(
    isObj ? (detail.detail || detail.error || String(status))
          : (detail || `${status} ${method} ${path}`)
  )
  err.status = status                           // e.g. 422, 502
  err.code = isObj ? detail.error : undefined   // e.g. 'deadline_too_tight'
  err.body = detail
  throw err
}
const _env = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {}
const USE_REAL = _env.VITE_USE_REAL === 'true' // set in .env: VITE_USE_REAL=true

async function request(method, path, body) {
  const url = REAL_BASE + path
  if (!USE_REAL) {
    // Simulate network latency so loading states are exercised.
    await new Promise((r) => setTimeout(r, 120 + Math.random() * 220))
    const r = handleMock(method, path, body)
    if (r && r.ok === false) throwApiError(r.status, r.data, method, path)
    return r
  }
  const isForm = body instanceof FormData
  let res
  try {
    res = await fetch(url, {
      method,
      headers: isForm ? undefined : { 'Content-Type': 'application/json' },
      body: isForm ? body : (body ? JSON.stringify(body) : undefined)
    })
  } catch (networkErr) {
    // fetch() throws (not a rejected HTTP status) when the request never reached
    // a server: backend down, no network, CORS block, DNS failure, etc. This is
    // NOT the same as a real 200-with-empty-data response — the caller must be
    // able to tell "the server said there's nothing" apart from "we never heard
    // back", so views don't render zeros as if they were real (B-RC2-3).
    const err = new Error('Cannot reach the server. Check your connection and retry.')
    err.offline = true
    err.status = 0
    throw err
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throwApiError(res.status, data, method, path)
  return { ok: true, status: res.status, data }
}

const api = {
  resetMock,

  // ---- Goals ----
  createGoal(body) { return request('POST', '/goals', body).then((r) => r.data) },
  getGoals() { return request('GET', '/goals').then((r) => r.data) },
  getGoal(id) { return request('GET', `/goals/${id}`).then((r) => r.data) },
  setLanguage(id, lang) { return request('PATCH', `/goals/${id}/language`, { explanation_language: lang }).then((r) => r.data) },

  // ---- Documents ----
  uploadDocument(id, file) {
    const fd = new FormData()
    if (file) fd.append('file', file)
    return request('POST', `/goals/${id}/document`, fd).then((r) => r.data)
  },
  getDocument(id) { return request('GET', `/goals/${id}/document`).then((r) => r.data) },

  // ---- Concepts ----
  extractConcepts(id) { return request('POST', `/goals/${id}/concepts:extract`).then((r) => r.data) },
  getConcepts(id) { return request('GET', `/goals/${id}/concepts`).then((r) => r.data) },
  confirmConcepts(id, concepts) { return request('PUT', `/goals/${id}/concepts`, { concepts }).then((r) => r.data) },

  // ---- Diagnostic ----
  generateDiagnostic(id) { return request('POST', `/goals/${id}/diagnostic`).then((r) => r.data) },
  submitDiagnostic(id, answers) { return request('POST', `/goals/${id}/diagnostic/submit`, { answers }).then((r) => r.data) },

  // ---- Checkpoint (end-of-day re-quiz) ----
  generateCheckpoint(id, { conceptIds, day, numQuestions } = {}) {
    return request('POST', `/goals/${id}/checkpoint`, {
      concept_ids: conceptIds || [], day: day || null, num_questions: numQuestions || null
    }).then((r) => r.data)
  },
  submitCheckpoint(id, checkpointId, answers) {
    return request('POST', `/goals/${id}/checkpoint/submit`, { checkpoint_id: checkpointId, answers }).then((r) => r.data)
  },

  // ---- Plans ----
  generatePlan(id) { return request('POST', `/goals/${id}/plan/generate`).then((r) => r.data) },
  getCurrentPlan(id) { return request('GET', `/goals/${id}/plan/current`).then((r) => r.data) },
  getVersions(id) { return request('GET', `/goals/${id}/plan/versions`).then((r) => r.data) },
  getVersion(id, versionNo) { return request('GET', `/goals/${id}/plan/versions/${versionNo}`).then((r) => r.data) },
  getDiff(id, from, to) { return request('GET', `/goals/${id}/plan/diff?from=${from}&to=${to}`).then((r) => r.data) },

  // ---- Tasks / Evidence ----
  completeTask(taskId) { return request('POST', `/tasks/${taskId}/complete`).then((r) => r.data) },
  uncompleteTask(taskId) { return request('POST', `/tasks/${taskId}/uncomplete`).then((r) => r.data) },
  addEvidence(id, body) { return request('POST', `/goals/${id}/evidence`, body).then((r) => r.data) },

  // ---- Replan / Simulate ----
  replan(id) { return request('POST', `/goals/${id}/replan`).then((r) => r.data) },
  simulate(id, scenario) { return request('POST', `/goals/${id}/simulate`, { scenario }).then((r) => r.data) },

  // ---- Decisions ----
  getDecisions(id) { return request('GET', `/goals/${id}/decisions`).then((r) => r.data) },
  getDecision(id, decisionId, includeTrace = false) {
    const q = includeTrace ? '?include_trace=true' : ''
    return request('GET', `/goals/${id}/decisions/${decisionId}${q}`).then((r) => r.data)
  }
}

export default api
