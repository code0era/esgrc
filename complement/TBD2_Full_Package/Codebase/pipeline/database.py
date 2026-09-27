"""
pipeline/database.py
Standalone sync SQLAlchemy engine for Celery workers.

WHY THIS EXISTS (not using ESGRC's app/database.py):
  - ESGRC uses an async engine (asyncpg). Celery tasks run synchronously.
  - ESGRC's Base includes ForeignKey("organisations.id") and ForeignKey("users.id").
    When pipeline ORM models try update(PipelineRun).values(...), SQLAlchemy resolves
    all FK targets at flush time. If ESGRC's metadata isn't imported, those FK targets
    don't exist in the pipeline's Base, causing a NoReferencedTableError at runtime.
  - Solution: use raw text() SQL in shared.py - no ORM flush, no FK resolution.

LAZY INIT:
  Engine is created on first access inside a Celery worker process (after fork).
  Creating it at import time causes "engine created before fork" warnings with psycopg.

THREAD SAFETY:
  Double-checked locking pattern - safe for Celery prefork pool where multiple
  threads can call get_engine() simultaneously during warmup.
"""
import os
import threading
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_engine_lock = threading.Lock()
_SessionFactory = None


def get_engine() -> Engine:
    """Return the singleton engine, creating it on first call (thread-safe)."""
    global _engine, _SessionFactory
    if _engine is None:
        with _engine_lock:
            if _engine is None:  # double-checked
                db_url = os.environ["DATABASE_URL"]
                kwargs = {
                    "pool_pre_ping": True,
                    "pool_size": 5,
                    "max_overflow": 10,
                }
                if db_url.startswith("sqlite"):
                    # SQLite in tests - no pool settings
                    kwargs = {"connect_args": {"check_same_thread": False}}

                _engine = create_engine(db_url, **kwargs)
                _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def session_ctx() -> Generator[Session, None, None]:
    """
    Context manager yielding a SQLAlchemy Session.
    Commits on clean exit, rolls back on exception.
    Always closes the session.

    Usage in Celery tasks:
        with session_ctx() as session:
            session.execute(text("UPDATE pipeline_runs SET ..."), {...})
    """
    factory = _SessionFactory
    if factory is None:
        get_engine()  # initialise
        factory = _SessionFactory

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """
    Return a raw Session for use in non-context-manager scenarios.
    Caller is responsible for commit/rollback/close.
    Prefer session_ctx() for task code.
    """
    if _SessionFactory is None:
        get_engine()
    return _SessionFactory()
