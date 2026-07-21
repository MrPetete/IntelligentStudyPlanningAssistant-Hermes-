"""
Diagnostic endpoints: generate (placeholder via MOCK LLM) + submit (scores).

Questions are generated from confirmed concepts. The correct answer is kept
server-side (in questions_json) and never returned to the client. Submission
produces a per-concept score (a heuristic signal, not a measurement).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import models
from agent import llm_client
from agent.llm_client import LLMUnavailableError
from config import DIAGNOSTIC_NUM_QUESTIONS
from db import get_session
from schemas import (
    DiagnosticOut,
    DiagnosticQuestion,
    DiagnosticResult,
    DiagnosticSubmit,
)

router = APIRouter(prefix="/goals", tags=["diagnostic"])


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

    questions = {q["id"]: q for q in json.loads(diag.questions_json)}
    answers = {a.question_id: a.choice for a in body.answers}

    # Tally correct/total per concept.
    per_concept: dict[int, list[int]] = {}
    for qid, q in questions.items():
        cid = q["concept_id"]
        correct = 1 if answers.get(qid) == q.get("answer") else 0
        bucket = per_concept.setdefault(cid, [0, 0])
        bucket[0] += correct
        bucket[1] += 1

    scores = {cid: (c / t if t else 0.0) for cid, (c, t) in per_concept.items()}

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
