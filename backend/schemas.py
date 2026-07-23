"""
TraceLearn — API contracts (Pydantic request/response models).

THESE ARE THE PARALLELIZATION CONTRACT. The three shapes that matter most —
PlanVersionOut, AgentDecisionOut (with ToolCall trace), and ConceptOut —
should be treated as frozen in hour 1 so frontend/data can build against mocks.

Phase 0: shapes are final; endpoint bodies return mock instances of these.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Language = Literal["en", "zh"]


# ===========================================================================
# Goals
# ===========================================================================
class GoalCreate(BaseModel):
    goal_text: str
    deadline: str                       # ISO date
    hours_per_day: float                # study hours committed per day
    explanation_language: Language = "en"


class GoalOut(BaseModel):
    id: int
    goal_text: str
    deadline: str
    hours_per_day: float
    explanation_language: Language
    document_status: str = "none"       # convenience mirror of the document state
    created_at: str


class LanguageUpdate(BaseModel):
    explanation_language: Language


class GoalListItem(BaseModel):
    """Lightweight row for the multi-goal switcher (GET /goals). A-RC2-6."""
    id: int
    goal_text: str
    deadline: str
    hours_per_day: float
    explanation_language: Language
    document_status: str = "none"
    created_at: str


# ===========================================================================
# Documents (single document, placeholder processing)
# ===========================================================================
class DocumentStatusOut(BaseModel):
    goal_id: int
    filename: str | None = None
    status: Literal["none", "uploaded", "processing", "ready", "failed"] = "none"


# ===========================================================================
# Concepts — canonical_term is the language-neutral anchor
# ===========================================================================
class ConceptOut(BaseModel):
    id: int
    canonical_term: str                 # preserved verbatim, never translated
    name: str
    explanation: str | None = None      # localized
    order_index: int | None = None
    parent_concept_id: int | None = None
    source: str = "material"
    confirmed: bool = False


class ConceptEdit(BaseModel):
    """One concept in a user-confirmed map. id is null for user-added concepts."""
    id: int | None = None
    canonical_term: str
    name: str
    explanation: str | None = None
    order_index: int | None = None
    parent_concept_id: int | None = None


class ConceptConfirm(BaseModel):
    """PUT body: the full confirmed/edited concept list (sets confirmed=True)."""
    concepts: list[ConceptEdit]


# ===========================================================================
# Diagnostic (placeholder generation)
# ===========================================================================
class DiagnosticQuestion(BaseModel):
    id: int
    concept_id: int
    prompt: str                         # localized
    options: list[str]
    # NOTE: the correct answer is NOT sent to the client; kept server-side.


class DiagnosticOut(BaseModel):
    diagnostic_id: int
    questions: list[DiagnosticQuestion]


class DiagnosticAnswer(BaseModel):
    question_id: int
    choice: str                         # the option the user selected


class DiagnosticSubmit(BaseModel):
    answers: list[DiagnosticAnswer]


class PerQuestionResult(BaseModel):
    """Question-by-question right/wrong for the result screen (B-f1). Safe to
    reveal the correct option now — the quiz is over. `correct_choice` is the
    resolved option TEXT (not the stored letter); `submitted` is what the learner
    picked (None if unanswered)."""
    question_id: int
    submitted: str | None = None
    correct_choice: str | None = None
    is_correct: bool = False


class DiagnosticResult(BaseModel):
    per_concept_score: dict[int, float]  # {concept_id: 0..1} — heuristic signal, not a measurement
    # Onboarding isn't a graded re-test, but we return the same per-question
    # detail for UI consistency (B-f1, "worth deciding" note). Optional — an
    # onboarding screen may ignore it.
    per_question: list[PerQuestionResult] = Field(default_factory=list)


# ===========================================================================
# Checkpoint re-quiz (A-RC2-4) — mid-plan re-test scoped to specific concepts.
# Reuses the diagnostic question/scoring shapes; writes quiz_result evidence per
# concept so mastery can actually move and the trigger gate sees real re-test
# signal (not just raw task completions).
# ===========================================================================
class CheckpointGenerate(BaseModel):
    """Generate a checkpoint quiz scoped to a concept subset. Empty/omitted
    concept_ids => all confirmed concepts (a full re-test). `day` is an optional
    convenience for the frontend's end-of-day quiz (scopes to that day's tasks'
    concepts when concept_ids is not given)."""
    concept_ids: list[int] = Field(default_factory=list)
    day: str | None = None
    num_questions: int | None = None     # default: config.DIAGNOSTIC_NUM_QUESTIONS


class CheckpointOut(BaseModel):
    checkpoint_id: int                   # a Diagnostic row id (reused table)
    concept_ids: list[int]               # the concepts this quiz actually covers
    questions: list[DiagnosticQuestion]


class CheckpointSubmit(BaseModel):
    checkpoint_id: int                   # which checkpoint quiz these answers are for
    answers: list[DiagnosticAnswer]


class CheckpointResult(BaseModel):
    per_concept_score: dict[int, float]  # {concept_id: 0..1}
    trigger_fired: bool = False          # did the re-test signal queue a replan?
    # Question-by-question right/wrong for the checkpoint result screen (B-f1).
    # Shape agreed with B: {question_id, submitted, correct_choice, is_correct}.
    per_question: list[PerQuestionResult] = Field(default_factory=list)


# ===========================================================================
# Plans / tasks / versions
# ===========================================================================
class TaskOut(BaseModel):
    id: int
    concept_id: int | None = None
    canonical_term: str | None = None    # convenience for concept tagging in the UI
    day: str | None = None
    description: str                     # localized
    est_minutes: int | None = None
    status: Literal["pending", "done", "skipped"] = "pending"


class PlanVersionOut(BaseModel):
    id: int
    version_no: int
    created_by: Literal["user", "agent"]
    parent_version_id: int | None = None
    created_at: str
    tasks: list[TaskOut] = Field(default_factory=list)
    # Honest feasibility note when a tight deadline forced a trimmed core plan
    # (e.g. "Tight deadline: core 6 of 20 concepts covered; rest deferred.").
    # None when the plan covers every confirmed concept.
    coverage_note: str | None = None


class PlanVersionSummary(BaseModel):
    """Lightweight row for the version-history timeline."""
    id: int
    version_no: int
    created_by: Literal["user", "agent"]
    parent_version_id: int | None = None
    created_at: str


class PlanDiff(BaseModel):
    """Structured diff between two versions, grouped where possible by concept."""
    from_version: int
    to_version: int
    added_tasks: list[TaskOut] = Field(default_factory=list)
    removed_tasks: list[TaskOut] = Field(default_factory=list)
    unchanged_count: int = 0
    concept_summary: dict[str, str] = Field(default_factory=dict)  # {canonical_term: change note}


# ===========================================================================
# Evidence + simulation
# ===========================================================================
class EvidenceCreate(BaseModel):
    type: Literal["task_done", "task_skipped", "quiz_result", "time_logged", "question"]
    concept_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskCompleteOut(BaseModel):
    task_id: int
    status: str
    # A replan trigger fired and was QUEUED (background), not necessarily finished.
    # The frontend polls GET /goals/{id}/decisions for the resulting new version.
    trigger_fired: bool


class TaskUncompleteOut(BaseModel):
    task_id: int
    status: str                          # 'pending' after a successful uncheck
    evidence_removed: int = 0            # task_done evidence rows invalidated


class SimulateRequest(BaseModel):
    """Demo control: inject a canned failure pattern without waiting real days."""
    scenario: Literal["normalization_failure", "missed_tasks"] = "normalization_failure"


class SimulateOut(BaseModel):
    scenario: str
    evidence_created: int
    trigger_fired: bool
    decision_id: int | None = None       # the agent_decision produced, if the trigger fired


# ===========================================================================
# Agent decisions — the DEFENCE ARTIFACT (tool trace)
# ===========================================================================
class ToolCall(BaseModel):
    tool: str                            # tool name (machine layer — English)
    args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""             # short human-readable summary of the return


class AgentDecisionOut(BaseModel):
    id: int
    trigger: str
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    reasoning_text: str                  # localized, human-facing ("why did my plan change?")
    tool_trace: list[ToolCall] = Field(default_factory=list)
    decision: Literal["no_change", "new_version"]
    resulting_plan_version_id: int | None = None
    created_at: str


class AgentDecisionSummary(BaseModel):
    id: int
    trigger: str
    decision: Literal["no_change", "new_version"]
    resulting_plan_version_id: int | None = None
    created_at: str
