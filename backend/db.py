"""
TraceLearn — database engine + session helpers (SQLite + SQLModel).

Phase 0: connection, create_all(), and a FastAPI session dependency.
No migrations, no ORM ceremony — a single local SQLite file (Decision: no prod deploy).
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from config import DATABASE_URL
from logging_config import get_logger

_log = get_logger("db")

# check_same_thread=False lets FastAPI's threadpool share the SQLite connection.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    """Create all tables from the SQLModel metadata. Called on app startup."""
    # Import models so their tables register on SQLModel.metadata before create_all.
    import models  # noqa: F401  (side-effect import)

    SQLModel.metadata.create_all(engine)
    # create_all only CREATES missing tables — it never ALTERs an existing one.
    # A DB created before PR #12 (which added goals.hours_per_day) therefore keeps
    # the old schema, and every GET /goals/{id} 500s with `no such column`
    # (R2-01). Run a tiny, idempotent additive migration so nobody with prior
    # test data hits that wall.
    _migrate_hours_per_day()


def _migrate_hours_per_day() -> None:
    """Idempotent startup migration: ensure goals.hours_per_day exists (R2-01).

    Additive only — checks PRAGMA table_info and ALTERs the column in if it's
    missing. Backfills existing rows from the pre-pivot `weekly_hours` column
    (hours_per_day = weekly_hours / 7) when that column is still present, else a
    sane default so old rows aren't NULL. Safe to run on every startup: on a
    fresh/current DB the column already exists and this is a no-op.
    """
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(goals)")}
        if not cols or "hours_per_day" in cols:
            # No goals table yet (fresh DB — create_all made it with the column
            # already), or the column is already present. Nothing to migrate.
            return

        _log.warning("migrating goals: adding missing column hours_per_day (R2-01)")
        conn.exec_driver_sql("ALTER TABLE goals ADD COLUMN hours_per_day FLOAT")

        if "weekly_hours" in cols:
            # Backfill day-accurate hours from the old weekly figure. NULLIF guards
            # against a 0/NULL weekly_hours producing a nonsensical value.
            conn.exec_driver_sql(
                "UPDATE goals SET hours_per_day = weekly_hours / 7.0 "
                "WHERE hours_per_day IS NULL AND weekly_hours IS NOT NULL"
            )
        # Any rows still NULL (no weekly_hours to backfill from) get a sane default
        # so reads never see NULL for a NOT-NULL-in-the-model field.
        conn.exec_driver_sql(
            "UPDATE goals SET hours_per_day = 2.0 WHERE hours_per_day IS NULL"
        )


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, closes it after the request."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """A standalone session for code OUTSIDE a request (e.g. a FastAPI
    BackgroundTask, whose work runs after the request's session is closed).
    Commits on clean exit, rolls back on error, always closes."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
