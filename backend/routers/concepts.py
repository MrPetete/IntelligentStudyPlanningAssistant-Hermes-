"""
Concept map endpoints: extract (placeholder via MOCK LLM) + confirm (real).

The concept map is the spine. Extraction here uses llm_client (MOCK in Phase 0),
so the shape is real even though the model is fake. Confirmation is real DB work
because it's cheap and central to the human-in-the-loop grounding step.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import ingestion
import models
from agent import llm_client
from agent.llm_client import LLMUnavailableError
from db import get_session
from schemas import ConceptConfirm, ConceptOut

router = APIRouter(prefix="/goals", tags=["concepts"])


def _to_out(c: models.Concept) -> ConceptOut:
    return ConceptOut(
        id=c.id, canonical_term=c.canonical_term, name=c.name,
        explanation=c.explanation, order_index=c.order_index,
        parent_concept_id=c.parent_concept_id, source=c.source, confirmed=c.confirmed,
    )


@router.post("/{goal_id}/concepts:extract", response_model=list[ConceptOut])
def extract_concepts(goal_id: int, session: Session = Depends(get_session)) -> list[ConceptOut]:
    """
    PLACEHOLDER extraction: calls llm_client.extract_concepts (MOCK returns the
    seeded databases concept map). Real extraction from uploaded text is later.
    Idempotent-ish: clears prior unconfirmed concepts for this goal first.
    """
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")

    # No document text here: route through the goal-topic fallback (D4) so this
    # endpoint returns a usable map from the goal alone (source='goal_topic')
    # instead of sending the live model an empty "Course material:" prompt (which
    # yields non-JSON -> 502). This mirrors the no-file /document pipeline and is
    # what the frontend's no-file onboarding relies on.
    try:
        raw = ingestion.build_concept_map(
            "", goal.explanation_language, goal_text=goal.goal_text
        )
    except LLMUnavailableError as exc:
        # A3: live model unavailable -> clean, retryable error (never a 500).
        raise HTTPException(502, {"error": "concept extraction unavailable, please retry",
                                  "detail": str(exc)}) from exc
    created: list[models.Concept] = []
    for item in raw:
        c = models.Concept(
            goal_id=goal_id,
            canonical_term=item["canonical_term"],
            name=item.get("name", item["canonical_term"]),
            explanation=item.get("explanation"),
            order_index=item.get("order_index"),
            source=item.get("source", "material"),
            confirmed=False,
        )
        session.add(c)
        created.append(c)
    session.commit()
    for c in created:
        session.refresh(c)
    return [_to_out(c) for c in created]


@router.get("/{goal_id}/concepts", response_model=list[ConceptOut])
def get_concepts(goal_id: int, session: Session = Depends(get_session)) -> list[ConceptOut]:
    rows = session.exec(
        select(models.Concept).where(models.Concept.goal_id == goal_id)
        .order_by(models.Concept.order_index)
    ).all()
    return [_to_out(c) for c in rows]


@router.put("/{goal_id}/concepts", response_model=list[ConceptOut])
def confirm_concepts(goal_id: int, body: ConceptConfirm,
                     session: Session = Depends(get_session)) -> list[ConceptOut]:
    """
    Human-in-the-loop grounding: replace the goal's concept set with the
    user-confirmed/edited list, marking all confirmed=True. canonical_term is
    preserved verbatim (never translated).
    """
    goal = session.get(models.Goal, goal_id)
    if not goal:
        raise HTTPException(404, "goal not found")

    # Clear existing concepts for this goal, then insert the confirmed set.
    for c in session.exec(select(models.Concept).where(models.Concept.goal_id == goal_id)).all():
        session.delete(c)
    session.commit()

    out: list[models.Concept] = []
    for item in body.concepts:
        c = models.Concept(
            goal_id=goal_id,
            canonical_term=item.canonical_term,
            name=item.name,
            explanation=item.explanation,
            order_index=item.order_index,
            parent_concept_id=item.parent_concept_id,
            source=("user_added" if item.id is None else "material"),
            confirmed=True,
        )
        session.add(c)
        out.append(c)
    session.commit()
    for c in out:
        session.refresh(c)
    return [_to_out(c) for c in out]
