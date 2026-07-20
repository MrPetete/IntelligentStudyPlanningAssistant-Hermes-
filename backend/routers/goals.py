"""
Goals + document (single) endpoints.

Phase 0: goal creation is REAL (it's trivial and unblocks everyone); document
upload is a PLACEHOLDER that records a filename/status but does no extraction.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

import models
from config import SINGLE_USER_ID, SUPPORTED_LANGUAGES
from db import get_session
from schemas import DocumentStatusOut, GoalCreate, GoalOut, LanguageUpdate

router = APIRouter(prefix="/goals", tags=["goals"])


def _ensure_user(session: Session) -> None:
    if not session.get(models.User, SINGLE_USER_ID):
        session.add(models.User(id=SINGLE_USER_ID, name="demo"))
        session.commit()


@router.post("", response_model=GoalOut)
def create_goal(body: GoalCreate, session: Session = Depends(get_session)) -> GoalOut:
    if body.explanation_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, f"language must be one of {SUPPORTED_LANGUAGES}")
    _ensure_user(session)
    goal = models.Goal(
        user_id=SINGLE_USER_ID,
        goal_text=body.goal_text,
        deadline=body.deadline,
        weekly_hours=body.weekly_hours,
        explanation_language=body.explanation_language,
    )
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return GoalOut(
        id=goal.id, goal_text=goal.goal_text, deadline=goal.deadline,
        weekly_hours=goal.weekly_hours, explanation_language=goal.explanation_language,
        document_status="none", created_at=goal.created_at,
    )


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: int, session: Session = Depends(get_session)) -> GoalOut:
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")
    doc = session.exec(
        select(models.Document).where(models.Document.goal_id == goal_id)
    ).first()
    return GoalOut(
        id=goal.id, goal_text=goal.goal_text, deadline=goal.deadline,
        weekly_hours=goal.weekly_hours, explanation_language=goal.explanation_language,
        document_status=(doc.status if doc else "none"), created_at=goal.created_at,
    )


@router.patch("/{goal_id}/language", response_model=GoalOut)
def set_language(goal_id: int, body: LanguageUpdate,
                 session: Session = Depends(get_session)) -> GoalOut:
    if body.explanation_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, f"language must be one of {SUPPORTED_LANGUAGES}")
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")
    goal.explanation_language = body.explanation_language
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return GoalOut(
        id=goal.id, goal_text=goal.goal_text, deadline=goal.deadline,
        weekly_hours=goal.weekly_hours, explanation_language=goal.explanation_language,
        created_at=goal.created_at,
    )


@router.post("/{goal_id}/document", response_model=DocumentStatusOut)
def upload_document(goal_id: int, file: UploadFile | None = None,
                    session: Session = Depends(get_session)) -> DocumentStatusOut:
    """
    PLACEHOLDER: records the upload but performs NO extraction in Phase 0.
    Real text extraction + concept generation is Member C's work (see 04 context).
    In the demo, concepts are seeded rather than extracted live.
    """
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")
    filename = file.filename if file else "seeded_sample.pdf"
    doc = session.exec(
        select(models.Document).where(models.Document.goal_id == goal_id)
    ).first()
    if doc:
        doc.filename, doc.status = filename, "uploaded"
    else:
        doc = models.Document(goal_id=goal_id, filename=filename, status="uploaded")
    session.add(doc)
    session.commit()
    return DocumentStatusOut(goal_id=goal_id, filename=filename, status="uploaded")


@router.get("/{goal_id}/document", response_model=DocumentStatusOut)
def get_document_status(goal_id: int, session: Session = Depends(get_session)) -> DocumentStatusOut:
    doc = session.exec(
        select(models.Document).where(models.Document.goal_id == goal_id)
    ).first()
    if not doc:
        return DocumentStatusOut(goal_id=goal_id, status="none")
    return DocumentStatusOut(goal_id=goal_id, filename=doc.filename, status=doc.status)
