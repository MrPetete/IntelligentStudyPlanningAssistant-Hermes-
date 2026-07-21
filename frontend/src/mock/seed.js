/**
 * Seed data for the TraceLearn mock backend.
 *
 * Source of truth for shapes: ../../app/backend/schemas.py (READ-ONLY).
 * Two shapes are wired VERBATIM from mock_api_examples/:
 *   - agent_decision.json  -> decision #1 (new_version) and #2 (no_change)
 *   - plan_version.json    -> the two Normalization remediation tasks (ids 11,12)
 *
 * V1 (PlanVersionOut, version_no 1) is authored here because the provided mocks
 * only ship V2. It is constructed within the exact schema so the diff V1->V2
 * shows added / removed / unchanged tasks grouped by concept. This is frontend
 * demo seed data — no contract field is invented.
 */

export const seedGoal = {
  id: 1,
  goal_text: 'Learn database design for my final exam',
  deadline: '2026-08-15',
  weekly_hours: 6,
  explanation_language: 'zh',
  document_status: 'ready',
  created_at: '2026-07-19T09:00:00+00:00'
}

// concepts: verbatim from mock_api_examples/concept.json
export const seedConcepts = [
  {
    id: 1,
    canonical_term: 'Normalization',
    name: 'Database normalization',
    explanation: '把关系分解为 1NF-3NF，消除冗余，基于函数依赖。',
    order_index: 1,
    parent_concept_id: null,
    source: 'material',
    confirmed: true
  },
  {
    id: 2,
    canonical_term: 'Indexing',
    name: 'Indexing',
    explanation: 'B 树与哈希索引，以及索引何时有用。',
    order_index: 2,
    parent_concept_id: null,
    source: 'material',
    confirmed: true
  }
]

// Diagnostic questions (DiagnosticOut). Human-facing (localized) prompts.
export const seedDiagnostic = {
  diagnostic_id: 1,
  questions: [
    {
      id: 101,
      concept_id: 1,
      prompt: '以下哪项描述最符合 3NF（第三范式）？',
      options: [
        '每个字段都是原子的',
        '每个非主键字段都函数依赖于整个主键',
        '非主键字段之间不存在传递依赖',
        '表中没有重复行'
      ]
    },
    {
      id: 102,
      concept_id: 1,
      prompt: '给定关系 R(A,B,C)，函数依赖 B→C，它违反了哪一类范式？',
      options: ['1NF', '2NF', '3NF', '均已满足']
    },
    {
      id: 103,
      concept_id: 1,
      prompt: '规范化（Normalization）的主要目的通常是？',
      options: ['提高查询速度', '减少冗余与更新异常', '压缩存储空间', '简化索引']
    },
    {
      id: 104,
      concept_id: 2,
      prompt: 'B 树索引相比哈希索引的主要优势是？',
      options: [
        '只支持等值查询',
        '支持范围查询与有序遍历',
        '占用空间更小',
        '写入更快'
      ]
    },
    {
      id: 105,
      concept_id: 2,
      prompt: '以下哪种情况索引最可能帮助性能？',
      options: [
        '对小表做全表扫描',
        '高频按列过滤的大表查询',
        '频繁更新的单行',
        '聚合所有行'
      ]
    }
  ]
}

export const seedDiagnosticResult = {
  per_concept_score: { 1: 0.3, 2: 0.85 }
}

/**
 * V1 — the initial roadmap (created_by 'user' = the learner's starting plan).
 * Compact 4-task starter across the two concepts.
 */
export const seedV1Tasks = [
  {
    id: 1,
    concept_id: 1,
    canonical_term: 'Normalization',
    day: '2026-07-21',
    description: '阅读 1NF–3NF 理论，理解函数依赖。',
    est_minutes: 40,
    status: 'done'
  },
  {
    id: 2,
    concept_id: 1,
    canonical_term: 'Normalization',
    day: '2026-07-22',
    description: '练习：找出给定关系中的更新异常。',
    est_minutes: 40,
    status: 'pending'
  },
  {
    id: 3,
    concept_id: 2,
    canonical_term: 'Indexing',
    day: '2026-07-21',
    description: '阅读 B 树与哈希索引的对比。',
    est_minutes: 35,
    status: 'done'
  },
  {
    id: 4,
    concept_id: 2,
    canonical_term: 'Indexing',
    day: '2026-07-22',
    description: '实验：何时应该建索引。',
    est_minutes: 35,
    status: 'pending'
  }
]

/**
 * V2 — FULL MERGE of V1 (all V1 tasks carried forward, status preserved)
 * plus two appended Normalization remediation tasks (ids 11,12).
 * Diff V1 -> V2: added [11,12], removed [], unchanged [1,2,3,4].
 * The remediation tasks' descriptions are verbatim from mock_api_examples/plan_version.json.
 */
export const seedV2Tasks = [
  // --- carried forward from V1 (status preserved) ---
  {
    id: 1,
    concept_id: 1,
    canonical_term: 'Normalization',
    day: '2026-07-21',
    description: '阅读 1NF–3NF 理论，理解函数依赖。',
    est_minutes: 40,
    status: 'done'
  },
  {
    id: 2,
    concept_id: 1,
    canonical_term: 'Normalization',
    day: '2026-07-22',
    description: '练习：找出给定关系中的更新异常。',
    est_minutes: 40,
    status: 'pending'
  },
  {
    id: 3,
    concept_id: 2,
    canonical_term: 'Indexing',
    day: '2026-07-21',
    description: '阅读 B 树与哈希索引的对比。',
    est_minutes: 35,
    status: 'done'
  },
  {
    id: 4,
    concept_id: 2,
    canonical_term: 'Indexing',
    day: '2026-07-22',
    description: '实验：何时应该建索引。',
    est_minutes: 35,
    status: 'pending'
  },
  // --- appended remediation (verbatim from mock_api_examples/plan_version.json) ---
  {
    id: 11,
    concept_id: 1,
    canonical_term: 'Normalization',
    day: '2026-07-23',
    description: 'Remediation: review 1NF-3NF with worked examples.',
    est_minutes: 40,
    status: 'pending'
  },
  {
    id: 12,
    concept_id: 1,
    canonical_term: 'Normalization',
    day: '2026-07-24',
    description: 'Remediation: decompose 5 relations to 3NF.',
    est_minutes: 40,
    status: 'pending'
  }
]

// Decisions — VERBATIM from mock_api_examples/agent_decision.json (decision #1 trigger updated to 'low_mastery' to match backend's real reason strings)
export const seedDecisions = [
  {
    id: 1,
    trigger: 'low_mastery',
    evidence_snapshot: {
      progress: { tasks_total: 5, tasks_done: 1, tasks_due: 5, tasks_incomplete: 4 },
      evidence_count: 4
    },
    reasoning_text:
      '你最近关于 Normalization 的测验得分较低，且多个 Normalization 任务未完成。由于该概念是后续主题的基础，我在继续之前新增了两个 Normalization 巩固任务。',
    tool_trace: [
      { tool: 'get_learner_state', args: { goal_id: 1 }, result_summary: 'goal_text, deadline, weekly_hours, explanation_language' },
      { tool: 'get_progress_summary', args: { goal_id: 1 }, result_summary: 'tasks_total, tasks_done, tasks_due, tasks_incomplete' },
      { tool: 'get_evidence_since_last_plan', args: { goal_id: 1 }, result_summary: '4 items' },
      { tool: 'get_current_plan', args: { goal_id: 1 }, result_summary: 'plan_version_id, version_no, tasks' },
      { tool: 'llm.decide_replan', args: { explanation_language: 'zh', evidence_count: 4 }, result_summary: 'decision=new_version' },
      { tool: 'validator.validate_plan', args: { attempt: 0 }, result_summary: 'ok' },
      { tool: 'create_plan_version', args: { task_count: 2 }, result_summary: 'version_no=2' },
      { tool: 'record_agent_decision', args: { decision_id: 1 }, result_summary: 'recorded' }
    ],
    decision: 'new_version',
    resulting_plan_version_id: 2,
    created_at: '2026-07-20T10:32:11+00:00'
  },
  {
    id: 2,
    trigger: 'behind_schedule',
    evidence_snapshot: { progress: { tasks_due: 5, tasks_incomplete: 2 }, evidence_count: 3 },
    reasoning_text: 'Evidence reviewed; current plan still fits the deadline and mastery signals. No change needed.',
    tool_trace: [
      { tool: 'get_learner_state', args: { goal_id: 1 }, result_summary: '...' },
      { tool: 'get_progress_summary', args: { goal_id: 1 }, result_summary: '...' },
      { tool: 'get_evidence_since_last_plan', args: { goal_id: 1 }, result_summary: '3 items' },
      { tool: 'llm.decide_replan', args: { explanation_language: 'en' }, result_summary: 'decision=no_change' }
    ],
    decision: 'no_change',
    resulting_plan_version_id: null,
    created_at: '2026-07-20T11:05:00+00:00'
  }
]

// Evidence log (written by the app, read by the agent).
export const seedEvidence = [
  { id: 1, type: 'quiz_result', concept_id: 1, payload: { score: 0.3 }, created_at: '2026-07-20T10:00:00+00:00' },
  { id: 2, type: 'task_done', concept_id: 1, payload: { task_id: 1 }, created_at: '2026-07-20T10:10:00+00:00' },
  { id: 3, type: 'task_done', concept_id: 2, payload: { task_id: 3 }, created_at: '2026-07-20T10:15:00+00:00' }
]
