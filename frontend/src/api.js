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
const USE_REAL = false // flip to true once Member A's backend is live

async function request(method, path, body) {
  const url = REAL_BASE + path
  if (!USE_REAL) {
    // Simulate network latency so loading states are exercised.
    await new Promise((r) => setTimeout(r, 120 + Math.random() * 220))
    return handleMock(method, path, body)
  }
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `${res.status} ${method} ${path}`)
  return { ok: true, status: res.status, data }
}

const api = {
  resetMock,

  // ---- Goals ----
  createGoal(body) { return request('POST', '/goals', body).then((r) => r.data) },
  getGoal(id) { return request('GET', `/goals/${id}`).then((r) => r.data) },
  setLanguage(id, lang) { return request('PATCH', `/goals/${id}/language`, { explanation_language: lang }).then((r) => r.data) },

  // ---- Documents ----
  uploadDocument(id, filename) { return request('POST', `/goals/${id}/document`, { filename }).then((r) => r.data) },
  getDocument(id) { return request('GET', `/goals/${id}/document`).then((r) => r.data) },

  // ---- Concepts ----
  extractConcepts(id) { return request('POST', `/goals/${id}/concepts:extract`).then((r) => r.data) },
  getConcepts(id) { return request('GET', `/goals/${id}/concepts`).then((r) => r.data) },
  confirmConcepts(id, concepts) { return request('PUT', `/goals/${id}/concepts`, { concepts }).then((r) => r.data) },

  // ---- Diagnostic ----
  generateDiagnostic(id) { return request('POST', `/goals/${id}/diagnostic`).then((r) => r.data) },
  submitDiagnostic(id, answers) { return request('POST', `/goals/${id}/diagnostic/submit`, { answers }).then((r) => r.data) },

  // ---- Plans ----
  generatePlan(id) { return request('POST', `/goals/${id}/plan/generate`).then((r) => r.data) },
  getCurrentPlan(id) { return request('GET', `/goals/${id}/plan/current`).then((r) => r.data) },
  getVersions(id) { return request('GET', `/goals/${id}/plan/versions`).then((r) => r.data) },
  getVersion(id, versionNo) { return request('GET', `/goals/${id}/plan/versions/${versionNo}`).then((r) => r.data) },
  getDiff(id, from, to) { return request('GET', `/goals/${id}/plan/diff?from=${from}&to=${to}`).then((r) => r.data) },

  // ---- Tasks / Evidence ----
  completeTask(taskId) { return request('POST', `/tasks/${taskId}/complete`).then((r) => r.data) },
  addEvidence(id, body) { return request('POST', `/goals/${id}/evidence`, body).then((r) => r.data) },

  // ---- Replan / Simulate ----
  replan(id) { return request('POST', `/goals/${id}/replan`).then((r) => r.data) },
  simulate(id, scenario) { return request('POST', `/goals/${id}/simulate`, { scenario }).then((r) => r.data) },

  // ---- Decisions ----
  getDecisions(id) { return request('GET', `/goals/${id}/decisions`).then((r) => r.data) },
  getDecision(id, decisionId) { return request('GET', `/goals/${id}/decisions/${decisionId}`).then((r) => r.data) }
}

export default api
