"""
Diagnostic endpoints: generate (placeholder via MOCK LLM) + submit (scores).

Questions are generated from confirmed concepts. The correct answer is kept
server-side (in questions_json) and never returned to the client. Submission
produces a per-concept score (a heuristic signal, not a measurement).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

import models
from agent import llm_client
from agent.llm_client import LLMUnavailableError
from agent.replan import evaluate_and_schedule
from config import DIAGNOSTIC_NUM_QUESTIONS
from db import get_session
from schemas import (
    CheckpointGenerate,
    CheckpointOut,
    CheckpointResult,
    CheckpointSubmit,
    DiagnosticOut,
    DiagnosticQuestion,
    DiagnosticResult,
    DiagnosticSubmit,
)

router = APIRouter(prefix="/goals", tags=["diagnostic"])


def _score_answers(questions: list[dict], answers: dict[int, str]) -> dict[int, float]:
    """Tally correct/total per concept -> {concept_id: 0..1}.

    Shared by the onboarding diagnostic and the checkpoint re-quiz so scoring is
    identical. The stored answer key is an option LETTER ("A".."D"); the client
    submits the option TEXT it selected (the frontend binds the radio :value to
    the option string). Resolve the letter to its option text before comparing;
    also accept a submitted letter directly (keeps the degenerate mock case
    options == ["A","B","C","D"] and any letter-submitting client green)."""
    per_concept: dict[int, list[int]] = {}
    for q in questions:
        cid = q["concept_id"]
        submitted = answers.get(q["id"])
        letter = (q.get("answer") or "").strip().upper()
        options = q.get("options") or []
        idx = ord(letter) - ord("A") if len(letter) == 1 and "A" <= letter <= "Z" else -1
        correct_text = options[idx] if 0 <= idx < len(options) else None
        correct = 1 if submitted is not None and submitted in (correct_text, letter) else 0
        bucket = per_concept.setdefault(cid, [0, 0])
        bucket[0] += correct
        bucket[1] += 1
    return {cid: (c / t if t else 0.0) for cid, (c, t) in per_concept.items()}


@router.post("/{goal_id}/diagnostic", response_model=DiagnosticOut)
def generate_diagnostic(goal_id: int, session: Session = Depends(get_session)) -> DiagnosticOut:
    """PLACEHOLDER generation via MOCK LLM over confirmed concepts."""
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")
    concepts = session.exec(
        select(models.Concept).where(models.Concept.goal_id == goal_id)
    ).all()
    if not concepts:
        raise HTTPException(400, "confirm a concept map first")

    concept_dicts = [{"id": c.id, "canonical_term": c.canonical_term} for c in concepts]
    try:
        questions = llm_client.generate_diagnostic(
            concepts=concept_dicts,
            num_questions=DIAGNOSTIC_NUM_QUESTIONS,
            explanation_language=goal.explanation_language,
        )
    except LLMUnavailableError as exc:
        # A3: live model unavailable -> clean, retryable error (never a 500).
        raise HTTPException(502, {"error": "diagnostic generation unavailable, please retry",
                                  "detail": str(exc)}) from exc

    diag = models.Diagnostic(goal_id=goal_id, questions_json=json.dumps(questions, ensure_ascii=False))
    session.add(diag)
    session.commit()
    session.refresh(diag)

    # Strip the answer key before returning to the client.
    public = [
        DiagnosticQuestion(id=q["id"], concept_id=q["concept_id"],
                           prompt=q["prompt"], options=q["options"])
        for q in questions
    ]
    return DiagnosticOut(diagnostic_id=diag.id, questions=public)


@router.post("/{goal_id}/diagnostic/submit", response_model=DiagnosticResult)
def submit_diagnostic(goal_id: int, body: DiagnosticSubmit,
                      session: Session = Depends(get_session)) -> DiagnosticResult:
    """
    Score answers -> per-concept score, then write quiz_result evidence per concept
    so the mastery signal is seeded. Scoring keys on concept_id (language-independent).
    """
    diag = session.exec(
        select(models.Diagnostic).where(models.Diagnostic.goal_id == goal_id)
        .order_by(models.Diagnostic.id.desc())
    ).first()
    if not diag:
        raise HTTPException(400, "generate a diagnostic first")

    questions = list(json.loads(diag.questions_json))
    answers = {a.question_id: a.choice for a in body.answers}
    scores = _score_answers(questions, answers)

    diag.answers_json = json.dumps(answers, ensure_ascii=False)
    diag.per_concept_score_json = json.dumps(scores, ensure_ascii=False)
    session.add(diag)

    # Seed evidence so mastery + triggers have data to work with.
    for cid, score in scores.items():
        session.add(models.Evidence(
            goal_id=goal_id, concept_id=cid, type="quiz_result",
            payload_json=json.dumps({"score": score, "source": "diagnostic"}, ensure_ascii=False),
        ))
    session.commit()
    return DiagnosticResult(per_concept_score=scores)


# ===========================================================================
# Checkpoint re-quiz (A-RC2-4) — the missing link that lets mastery MOVE.
#
# Onboarding produces ONE diagnostic; remediation tasks keep targeting weak
# concepts but nothing ever re-tests them, so mastery is stuck and low_mastery
# stays true on every event (feeding R2-02's over-firing). A checkpoint quiz
# re-tests a chosen concept subset (e.g. the day's concepts) and writes
# quiz_result evidence per concept — real re-test signal for the trigger gate.
#
# Reuses the SAME generation (llm_client.generate_diagnostic), question shape,
# scoring (_score_answers) and evidence type as the onboarding path; only the
# concept SCOPING and the source tag differ.
# ===========================================================================
def _concepts_for_day(session: Session, goal_id: int, day: str) -> list[int]:
    """Concept ids scheduled on `day` in the current plan (for the end-of-day
    quiz). Reads the latest plan version's tasks."""
    pv = session.exec(
        select(models.PlanVersion).where(models.PlanVersion.goal_id == goal_id)
        .order_by(models.PlanVersion.version_no.desc())
    ).first()
    if not pv:
        return []
    tasks = session.exec(
        select(models.Task).where(models.Task.plan_version_id == pv.id)
    ).all()
    return [t.concept_id for t in tasks
            if t.day == day and t.concept_id is not None]


@router.post("/{goal_id}/checkpoint", response_model=CheckpointOut)
def generate_checkpoint(goal_id: int, body: CheckpointGenerate,
                        session: Session = Depends(get_session)) -> CheckpointOut:
    """Generate a checkpoint quiz scoped to a concept subset. Scope resolution:
    explicit concept_ids > `day`'s concepts > all confirmed concepts."""
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")

    all_concepts = session.exec(
        select(models.Concept).where(models.Concept.goal_id == goal_id)
    ).all()
    if not all_concepts:
        raise HTTPException(400, "confirm a concept map first")

    if body.concept_ids:
        wanted = set(body.concept_ids)
        scoped = [c for c in all_concepts if c.id in wanted]
    elif body.day:
        wanted = set(_concepts_for_day(session, goal_id, body.day))
        scoped = [c for c in all_concepts if c.id in wanted]
    else:
        scoped = list(all_concepts)  # full re-test

    if not scoped:
        raise HTTPException(400, "no concepts match the requested checkpoint scope")

    num_questions = body.num_questions or DIAGNOSTIC_NUM_QUESTIONS
    concept_dicts = [{"id": c.id, "canonical_term": c.canonical_term} for c in scoped]
    try:
        questions = llm_client.generate_diagnostic(
            concepts=concept_dicts,
            num_questions=num_questions,
            explanation_language=goal.explanation_language,
        )
    except LLMUnavailableError as exc:
        raise HTTPException(502, {"error": "checkpoint quiz generation unavailable, please retry",
                                  "detail": str(exc)}) from exc

    # Persist as a Diagnostic row (reuse the table); tag source so submit knows
    # this is a checkpoint (evidence source="checkpoint", not "diagnostic").
    diag = models.Diagnostic(
        goal_id=goal_id,
        questions_json=json.dumps(
            {"kind": "checkpoint", "questions": questions}, ensure_ascii=False),
    )
    session.add(diag)
    session.commit()
    session.refresh(diag)

    public = [
        DiagnosticQuestion(id=q["id"], concept_id=q["concept_id"],
                           prompt=q["prompt"], options=q["options"])
        for q in questions
    ]
    covered = sorted({q["concept_id"] for q in questions})
    return CheckpointOut(checkpoint_id=diag.id, concept_ids=covered, questions=public)


@router.post("/{goal_id}/checkpoint/submit", response_model=CheckpointResult)
def submit_checkpoint(goal_id: int, body: CheckpointSubmit, background: BackgroundTasks,
                      session: Session = Depends(get_session)) -> CheckpointResult:
    """Score a checkpoint quiz -> per-concept quiz_result evidence (source
    'checkpoint'), then evaluate the replan trigger. This is the real re-test
    signal A-RC2-2 wants replans to fire on (through the existing gate — a low
    score becomes quiz_result evidence; the gate + cooldown decide, never a raw
    "1 wrong = replan")."""
    diag = session.get(models.Diagnostic, body.checkpoint_id)
    if not diag or diag.goal_id != goal_id:
        raise HTTPException(404, "checkpoint not found")

    stored = json.loads(diag.questions_json)
    # Checkpoint rows are wrapped {"kind","questions"}; tolerate a bare list too.
    questions = stored.get("questions") if isinstance(stored, dict) else stored
    answers = {a.question_id: a.choice for a in body.answers}
    scores = _score_answers(list(questions), answers)

    diag.answers_json = json.dumps(answers, ensure_ascii=False)
    diag.per_concept_score_json = json.dumps(scores, ensure_ascii=False)
    session.add(diag)

    for cid, score in scores.items():
        session.add(models.Evidence(
            goal_id=goal_id, concept_id=cid, type="quiz_result",
            payload_json=json.dumps({"score": score, "source": "checkpoint"}, ensure_ascii=False),
        ))
    session.commit()

    # Re-test signal goes through the SAME trigger gate + cooldown as everything
    # else; if it fires, the agent runs in the background (poll decisions).
    fired, _ = evaluate_and_schedule(session, goal_id, background)
    return CheckpointResult(per_concept_score=scores, trigger_fired=fired)
