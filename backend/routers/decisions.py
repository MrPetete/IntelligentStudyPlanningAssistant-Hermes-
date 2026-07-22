"""
Agent decision / tool-trace endpoints (the defence artifact).

Lists decisions and returns a full decision incl. the ordered tool trace and the
localized reasoning_text. This is what the frontend's tool-trace viewer renders.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

import models
from db import get_session
from schemas import AgentDecisionOut, AgentDecisionSummary, ToolCall

router = APIRouter(prefix="/goals", tags=["decisions"])


@router.get("/{goal_id}/decisions", response_model=list[AgentDecisionSummary])
def list_decisions(goal_id: int, session: Session = Depends(get_session)) -> list[AgentDecisionSummary]:
    rows = session.exec(
        select(models.AgentDecision).where(models.AgentDecision.goal_id == goal_id)
        .order_by(models.AgentDecision.id)
    ).all()
    return [
        AgentDecisionSummary(
            id=d.id, trigger=d.trigger, decision=d.decision,
            resulting_plan_version_id=d.resulting_plan_version_id, created_at=d.created_at,
        )
        for d in rows
    ]


@router.get("/{goal_id}/decisions/{decision_id}", response_model=AgentDecisionOut)
def get_decision(goal_id: int, decision_id: int,
                 include_trace: bool = Query(
                     False,
                     description="Include the raw tool-call trace. Default false: "
                                 "the student view shows reasoning_text only; the "
                                 "trace is the defence artifact, opt-in behind a "
                                 "'details' toggle (A-RC2-5 / B-RC2-6)."),
                 session: Session = Depends(get_session)) -> AgentDecisionOut:
    d = session.get(models.AgentDecision, decision_id)
    if not d or d.goal_id != goal_id:
        raise HTTPException(404, "decision not found")

    # The raw tool trace clutters the student view (R2-08). It is NOT deleted —
    # it stays in the DB as the defence artifact — but it is only serialized into
    # the payload when explicitly requested (?include_trace=true), so the default
    # student-facing read carries just the human reasoning.
    trace: list[ToolCall] = []
    if include_trace:
        raw_trace = json.loads(d.tool_trace_json) if d.tool_trace_json else []
        trace = [
            ToolCall(tool=tc.get("tool", ""), args=tc.get("args", {}),
                     result_summary=tc.get("result_summary", ""))
            for tc in raw_trace
        ]
    return AgentDecisionOut(
        id=d.id, trigger=d.trigger,
        evidence_snapshot=json.loads(d.evidence_snapshot_json) if d.evidence_snapshot_json else {},
        reasoning_text=d.reasoning_text, tool_trace=trace, decision=d.decision,
        resulting_plan_version_id=d.resulting_plan_version_id, created_at=d.created_at,
    )
