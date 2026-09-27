"""
pipeline/db.py
FastAPI ORM session dependency - used ONLY in pipeline router endpoints.

TWO SESSION FACTORIES EXIST - they serve different purposes:

  pipeline/db.py        (THIS FILE)
    - SQLAlchemy ORM sessions for FastAPI endpoints
    - Used with Depends(get_pipeline_db) in router functions
    - ORM reads AND some writes happen here (e.g. rerun_step, update_prompt in
      pipeline_router.py) - safe only because those tables (PipelineStepResult,
      PipelinePrompt, ...) carry no FK into ESGRC's separate Base. PipelineRun /
      PipelineDefinition DO have such an FK (org_id -> organisations.id) and
      MUST NOT be ORM-written here - use raw text() SQL via pipeline/database.py
      instead, or FK resolution silently fails against the wrong Base.
    - Creates pipeline tables via create_pipeline_tables() on startup

  pipeline/database.py
    - Raw SQL sessions for Celery tasks
    - Used via session_ctx() in shared.py, confidence.py, claude_tasks.py
    - Raw text() SQL bypasses FK resolution (critical for write operations)
    - Lazy-init with double-checked locking (safe for prefork workers)

DO NOT use get_pipeline_db() inside Celery tasks.
DO NOT use session_ctx() inside FastAPI endpoints.
"""
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline.models import PipelineBase

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tbd2.db")

_engine_kwargs = {
    "pool_pre_ping": True,
    "connect_args": {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

pipeline_engine = create_engine(DATABASE_URL, **_engine_kwargs)

def create_pipeline_tables() -> None:
    """Called from main.py lifespan - creates pipeline tables if they don't exist."""
    PipelineBase.metadata.create_all(bind=pipeline_engine)


def get_pipeline_db() -> Generator[Session, None, None]:
    """FastAPI Depends - yields an ORM Session. Commits on success, rolls back on error."""
    with Session(pipeline_engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
