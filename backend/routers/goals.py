"""
Goals + document (single) endpoints.

Phase 0: goal creation is REAL (it's trivial and unblocks everyone); document
upload is a PLACEHOLDER that records a filename/status but does no extraction.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

import ingestion
import models
import storage
from config import SINGLE_USER_ID, SUPPORTED_LANGUAGES
from db import get_session, session_scope
from logging_config import get_logger
from schemas import DocumentStatusOut, GoalCreate, GoalOut, LanguageUpdate

_log = get_logger("ingestion")

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
        hours_per_day=body.hours_per_day,
        explanation_language=body.explanation_language,
    )
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return GoalOut(
        id=goal.id, goal_text=goal.goal_text, deadline=goal.deadline,
        hours_per_day=goal.hours_per_day, explanation_language=goal.explanation_language,
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
        hours_per_day=goal.hours_per_day, explanation_language=goal.explanation_language,
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
        hours_per_day=goal.hours_per_day, explanation_language=goal.explanation_language,
        created_at=goal.created_at,
    )


@router.post("/{goal_id}/document", response_model=DocumentStatusOut)
async def upload_document(goal_id: int, background: BackgroundTasks,
                          file: UploadFile | None = None,
                          session: Session = Depends(get_session)) -> DocumentStatusOut:
    """
    A4: save the file (if any), mark it `processing`, schedule the extract ->
    concept-map pipeline as a background task, and RETURN IMMEDIATELY. The
    frontend then polls GET /goals/{id}/document for none->processing->ready/failed.

    The file is OPTIONAL. With no material (no file, or an empty one) we still
    produce a usable concept map from the goal topic alone (D4 fallback), so
    onboarding never blocks on having a document — the no-file path the
    placeholder endpoint supported keeps working.

    The heavy work (text extraction + real concept extraction, which may hit
    the live model) runs in `_process_document` after the response is sent, so
    onboarding never blocks on it (Option C flow).
    """
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")

    content = await file.read() if file is not None else b""

    # With material, persist bytes to disk (Member C's storage helper) before
    # returning. Without, storage_path stays None and the background task uses
    # the goal-topic fallback.
    storage_path: str | None = None
    filename: str | None = None
    if content:
        filename = file.filename or "upload"
        storage_path = storage.save_upload(goal_id, filename, content)

    doc = session.exec(
        select(models.Document).where(models.Document.goal_id == goal_id)
    ).first()
    if doc:
        doc.filename, doc.storage_path, doc.status = filename, storage_path, "processing"
    else:
        doc = models.Document(goal_id=goal_id, filename=filename,
                              storage_path=storage_path, status="processing")
    session.add(doc)
    session.commit()

    # Schedule the pipeline; the response is sent first, work runs after.
    background.add_task(_process_document, goal_id, storage_path,
                        goal.explanation_language, goal.goal_text)
    return DocumentStatusOut(goal_id=goal_id, filename=filename, status="processing")


def _process_document(goal_id: int, storage_path: str | None,
                      explanation_language: str, goal_text: str) -> None:
    """
    Background pipeline (runs AFTER the upload response). Owns its own session
    (the request's is already closed). Extracts text -> builds the real concept
    map (with C's goal-topic fallback for broken/empty files) -> writes concepts
    -> status `ready`. On any failure, status `failed` and, if possible, the
    goal-topic fallback still yields a usable concept list (D4).

    `storage_path` is None when no file was uploaded: skip extraction and go
    straight to the goal-topic map (still `ready`, source='goal_topic').

    Never raises — a background task has no caller to catch it; every outcome
    is recorded as a document status.
    """
    # Operational logging only: goal_id, whether a file was present, and the
    # resulting status + concept count. Never logs the document text or the
    # extracted concept names.
    _log.info("document pipeline start (goal_id=%s, has_file=%s)", goal_id, storage_path is not None)
    with session_scope() as session:
        try:
            material_text = ""
            if storage_path:
                try:
                    material_text = ingestion.extract_text(storage_path)
                except ingestion.UnsupportedDocumentError:
                    # Out-of-scope file type -> treat as no usable material; the
                    # goal-topic fallback below still produces a concept list.
                    material_text = ""

            # build_concept_map runs the real extract_concepts on usable text,
            # and falls back to a goal-topic map on empty/broken text OR a model
            # error (D4). Passing goal_text guarantees a usable list either way —
            # including the no-file case (material_text stays "").
            concepts = ingestion.build_concept_map(
                material_text, explanation_language, goal_text=goal_text
            )
            _write_concepts(session, goal_id, concepts)
            _set_document_status(session, goal_id, "ready")
            _log.info("document pipeline -> ready (goal_id=%s, concept_count=%d, source=%s)",
                      goal_id, len(concepts),
                      concepts[0].get("source") if concepts else "none")
        except Exception as exc:  # noqa: BLE001 — background task must not propagate
            _log.error("document pipeline -> failed (goal_id=%s): %s: %s",
                       goal_id, type(exc).__name__, exc)
            # Last-resort: even the goal-topic fallback failed (e.g. model down).
            # Mark failed so the frontend shows a retry state; do not leave the
            # document stuck in `processing`.
            _set_document_status(session, goal_id, "failed", reason=str(exc))


def _write_concepts(session: Session, goal_id: int, concepts: list) -> None:
    """Replace this goal's unconfirmed concept set with the freshly extracted
    ones (mirrors routers/concepts.py extraction write). Confirmed concepts are
    left alone so a re-upload never destroys the user's confirmed grounding."""
    existing = session.exec(
        select(models.Concept)
        .where(models.Concept.goal_id == goal_id)
        .where(models.Concept.confirmed == False)  # noqa: E712
    ).all()
    for c in existing:
        session.delete(c)
    session.flush()
    for item in concepts:
        session.add(models.Concept(
            goal_id=goal_id,
            canonical_term=item["canonical_term"],
            name=item.get("name", item["canonical_term"]),
            explanation=item.get("explanation"),
            order_index=item.get("order_index"),
            source=item.get("source", "material"),
            confirmed=False,
        ))


def _set_document_status(session: Session, goal_id: int, status: str,
                         reason: str | None = None) -> None:
    doc = session.exec(
        select(models.Document).where(models.Document.goal_id == goal_id)
    ).first()
    if doc:
        doc.status = status
        session.add(doc)
    if status == "failed" and reason:
        # The frozen `documents` schema has no reason column and DocumentStatusOut
        # doesn't expose one, so we log rather than silently drop it. Single-user
        # dev tool — stderr is enough to diagnose a failed upload.
        logging.getLogger("tracelearn.ingestion").warning(
            "document processing failed for goal_id=%s: %s", goal_id, reason
        )


@router.get("/{goal_id}/document", response_model=DocumentStatusOut)
def get_document_status(goal_id: int, session: Session = Depends(get_session)) -> DocumentStatusOut:
    doc = session.exec(
        select(models.Document).where(models.Document.goal_id == goal_id)
    ).first()
    if not doc:
        return DocumentStatusOut(goal_id=goal_id, status="none")
    return DocumentStatusOut(goal_id=goal_id, filename=doc.filename, status=doc.status)
