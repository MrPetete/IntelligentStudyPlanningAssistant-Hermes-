"""
TraceLearn — Member A V1.1-rc2 migration test (R2-01 / A-RC2-3).

PR #12 added goals.hours_per_day to the model but SQLModel.metadata.create_all
never ALTERs an existing table, so a DB created before PR #12 500s on every
GET /goals/{id} with `no such column: goals.hours_per_day`. The startup migration
in db.create_db_and_tables must add the column idempotently and backfill from the
old weekly_hours (weekly_hours / 7) when present.

This test builds an OLD-SCHEMA goals table by hand (weekly_hours, NO
hours_per_day), runs the migration, and asserts the column exists, is backfilled,
and an ORM read (the thing that used to 500) now works.

Plain-script style — run with `python tests/test_migration.py`. Needs sqlmodel;
skips cleanly otherwise (run for real in the python:3.12-slim Docker sandbox).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _db_available() -> bool:
    try:
        import sqlmodel  # noqa: F401
        return True
    except Exception:
        return False


def _reload_db(tmp_name: str):
    import importlib
    import config as _config
    _config.DATABASE_URL = f"sqlite:///./_test_{tmp_name}.db"
    import db as _db
    importlib.reload(_db)
    return _db


def _make_old_schema_goals(engine) -> None:
    """Create a pre-PR12 goals table: weekly_hours, NO hours_per_day. Insert one
    row so the backfill path is exercised."""
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS goals")
        conn.exec_driver_sql(
            "CREATE TABLE goals ("
            " id INTEGER PRIMARY KEY,"
            " user_id INTEGER,"
            " goal_text VARCHAR,"
            " deadline VARCHAR,"
            " weekly_hours FLOAT,"
            " explanation_language VARCHAR,"
            " created_at VARCHAR)"
        )
        conn.exec_driver_sql(
            "INSERT INTO goals (id, user_id, goal_text, deadline, weekly_hours,"
            " explanation_language, created_at) VALUES"
            " (1, 1, 'pass databases', '2026-08-10', 14.0, 'en', '2026-07-01T00:00:00+00:00')"
        )


def _columns(engine) -> set:
    with engine.begin() as conn:
        return {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(goals)")}


def test_old_schema_db_migrates_and_backfills():
    if not _db_available():
        print("SKIP  test_old_schema_db_migrates_and_backfills (no sqlmodel)")
        return
    _db = _reload_db("mig_backfill")
    _make_old_schema_goals(_db.engine)
    assert "hours_per_day" not in _columns(_db.engine), "precondition: column absent"

    # Run startup exactly as the app does. create_all leaves the existing goals
    # table alone; the migration adds + backfills the column.
    _db.create_db_and_tables()

    cols = _columns(_db.engine)
    assert "hours_per_day" in cols, "migration must add hours_per_day"

    # Backfilled from weekly_hours (14 / 7 == 2.0).
    with _db.engine.begin() as conn:
        val = list(conn.exec_driver_sql(
            "SELECT hours_per_day FROM goals WHERE id=1"))[0][0]
    assert abs(val - 2.0) < 1e-9, f"expected backfill 14/7=2.0, got {val}"


def test_orm_read_after_migration_does_not_500():
    """The exact failure R2-01 describes: GET /goals/{id} 500s because the ORM
    selects hours_per_day. After migration an ORM read must succeed."""
    if not _db_available():
        print("SKIP  test_orm_read_after_migration_does_not_500 (no sqlmodel)")
        return
    _db = _reload_db("mig_ormread")
    _make_old_schema_goals(_db.engine)
    _db.create_db_and_tables()

    from sqlmodel import Session
    import models
    with Session(_db.engine) as s:
        g = s.get(models.Goal, 1)          # this SELECT is what used to raise
        assert g is not None
        assert g.hours_per_day is not None
        assert abs(g.hours_per_day - 2.0) < 1e-9


def test_migration_is_idempotent():
    """Running the migration twice (two startups) must not error or double-apply."""
    if not _db_available():
        print("SKIP  test_migration_is_idempotent (no sqlmodel)")
        return
    _db = _reload_db("mig_idem")
    _make_old_schema_goals(_db.engine)
    _db.create_db_and_tables()
    # Second startup on the now-current schema: no-op, no exception.
    _db.create_db_and_tables()
    assert "hours_per_day" in _columns(_db.engine)


def test_fresh_db_has_column_and_no_weekly_hours_needed():
    """A brand-new DB: create_all makes goals WITH hours_per_day, migration is a
    clean no-op (no weekly_hours column to backfill from)."""
    if not _db_available():
        print("SKIP  test_fresh_db_has_column_and_no_weekly_hours_needed (no sqlmodel)")
        return
    _db = _reload_db("mig_fresh")
    from sqlmodel import SQLModel
    SQLModel.metadata.drop_all(_db.engine)
    _db.create_db_and_tables()
    cols = _columns(_db.engine)
    assert "hours_per_day" in cols
    assert "weekly_hours" not in cols, "the current model has no weekly_hours column"


ALL_TESTS = [
    test_old_schema_db_migrates_and_backfills,
    test_orm_read_after_migration_does_not_500,
    test_migration_is_idempotent,
    test_fresh_db_has_column_and_no_weekly_hours_needed,
]


if __name__ == "__main__":
    passed = failed = 0
    for test in ALL_TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)
