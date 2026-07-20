"""
TraceLearn — database engine + session helpers (SQLite + SQLModel).

Phase 0: connection, create_all(), and a FastAPI session dependency.
No migrations, no ORM ceremony — a single local SQLite file (Decision: no prod deploy).
"""
from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from config import DATABASE_URL

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


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, closes it after the request."""
    with Session(engine) as session:
        yield session
