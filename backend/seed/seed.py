"""
TraceLearn — demo seed.

Creates the rehearsed demo scenario end-to-end so a replan can be shown on demand:
  - one goal (databases final, EN by default)
  - a confirmed concept map (databases concepts)
  - a diagnostic-derived mastery baseline
  - Roadmap Version 1 (user-created)

Run:
    cd app/backend
    python -m seed.seed            # EN
    python -m seed.seed zh         # ZH explanations

After seeding, use POST /goals/{id}/simulate to inject the normalization failure
and watch the Agent produce Version 2. Or call seed/simulate.py directly.
"""
from __future__ import annotations

import sys

from sqlmodel import Session, select

import models
from agent import llm_client, tools
from db import create_db_and_tables, engine
from config import SINGLE_USER_ID


def seed(language: str = "en") -> int:
    create_db_and_tables()
    with Session(engine) as session:
        # user
        if not session.get(models.User, SINGLE_USER_ID):
            session.add(models.User(id=SINGLE_USER_ID, name="demo"))
            session.commit()

        # goal
        goal = models.Goal(
            user_id=SINGLE_USER_ID,
            goal_text="Pass my databases final",
            deadline="2026-08-10",
            hours_per_day=1.0,
            explanation_language=language,
        )
        session.add(goal)
        session.commit()
        session.refresh(goal)

        # document (placeholder — marks that material 'exists')
        session.add(models.Document(goal_id=goal.id, filename="sample_db_course.txt", status="ready"))
        session.commit()

        # confirmed concept map (seeded via mock extraction, marked confirmed)
        raw = llm_client.extract_concepts(material_text="", explanation_language=language)
        concepts: list[models.Concept] = []
        for item in raw:
            c = models.Concept(
                goal_id=goal.id, canonical_term=item["canonical_term"],
                name=item.get("name", item["canonical_term"]),
                explanation=item.get("explanation"), order_index=item.get("order_index"),
                source="material", confirmed=True,
            )
            session.add(c)
            concepts.append(c)
        session.commit()
        for c in concepts:
            session.refresh(c)

        # baseline mastery via a seeded quiz_result per concept (mid/high, so V1 is stable)
        for c in concepts:
            session.add(models.Evidence(
                goal_id=goal.id, concept_id=c.id, type="quiz_result",
                payload_json='{"score": 0.7, "source": "seed_diagnostic"}',
            ))
        session.commit()

        # Roadmap Version 1 (user-created), validated implicitly by construction
        concept_dicts = [{"id": c.id, "canonical_term": c.canonical_term} for c in concepts]
        plan = llm_client.generate_plan(
            goal={"deadline": goal.deadline, "hours_per_day": goal.hours_per_day},
            concepts=concept_dicts, scores={}, explanation_language=language,
        )
        # resolve concept_id from the mock plan (mock uses order-based ids)
        by_term = {c.canonical_term: c.id for c in concepts}
        for i, t in enumerate(plan["tasks"]):
            t["concept_id"] = concepts[i].id if i < len(concepts) else None
        created = tools.create_plan_version(session, goal.id, plan, created_by="user")

        # Mark every task EXCEPT Normalization as already done. Without this,
        # get_progress_summary() reads 100% of tasks as "due and incomplete" on
        # a freshly seeded goal (Phase 0's due==total simplification), which
        # makes the `behind_schedule` trigger fire before the Normalization
        # quiz/mastery signal is ever evaluated. The intended demo story is a
        # student who is otherwise on track and struggling specifically with
        # Normalization — this seeds that state honestly instead of a
        # coincidentally-behind-on-everything student.
        norm_id = by_term.get("Normalization")
        tasks = session.exec(
            select(models.Task).where(models.Task.plan_version_id == created["plan_version_id"])
        ).all()
        for t in tasks:
            if t.concept_id != norm_id:
                t.status = "done"
                session.add(t)
                session.add(models.Evidence(
                    goal_id=goal.id, concept_id=t.concept_id, type="task_done",
                    payload_json=f'{{"task_id": {t.id}, "minutes": {t.est_minutes}, "source": "seed"}}',
                ))
        session.commit()

        print(f"Seeded goal_id={goal.id} (language={language}), "
              f"{len(concepts)} concepts, Roadmap V1 created.")
        print(f"Next: POST /goals/{goal.id}/simulate  {{'scenario':'normalization_failure'}}")
        return goal.id


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "en"
    seed(lang)
