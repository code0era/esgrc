"""
Database engine, session factory, and declarative base.

SQLAlchemy 2.x patterns used throughout:
- DeclarativeBase class (not the legacy declarative_base() function).
- get_db() rolls back the session on any unhandled exception before closing,
  so a dirty transaction never poisons the next request on the same connection.
- pool_pre_ping=True verifies connections are alive before use, preventing
  stale-connection errors after database restarts or idle timeouts.
- pool_size / max_overflow are configurable via settings for production Postgres.
  SQLite ignores those settings entirely - it uses StaticPool only for the
  in-memory `:memory:` case (tests), and NullPool (one connection per
  checkout) for the shipped file-based default, since StaticPool would funnel
  every request through a single shared connection and defeat the WAL
  concurrency below.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, Pool, StaticPool

from app.config import settings

# ── Connection arguments ───────────────────────────────────────────────────────

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_is_sqlite_memory = _is_sqlite and ":memory:" in settings.DATABASE_URL


def _sqlite_poolclass(is_memory: bool) -> type[Pool]:
    """
    Pick the pool class for a SQLite engine.

    - In-memory (`:memory:`) only exists within the connection that created
      it - a second connection would see a brand-new empty database, so
      StaticPool must keep every checkout on that one connection. This is
      what tests (see tests/conftest.py) rely on.
    - File-based SQLite (the shipped default, sqlite:///./esgrc.db) has no
      such constraint - independent connections all open the same file.
      NullPool hands out a fresh connection per checkout instead of
      funnelling every concurrent request through one shared
      connection/cursor. WAL mode (enabled below) is what actually makes
      that concurrent file access safe; StaticPool here would serialize
      everything onto a single connection and defeat it.
    """
    return StaticPool if is_memory else NullPool


_engine_kwargs: dict = {
    "pool_pre_ping": True,
}

if _is_sqlite:
    # SQLite is not safe for concurrent threads without this flag.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    _engine_kwargs["poolclass"] = _sqlite_poolclass(_is_sqlite_memory)
else:
    # Production (Postgres, etc.) - configure pool for concurrent load.
    _engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    _engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

# Enable WAL mode for SQLite - significantly improves concurrent read performance.
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

# ── Session factory ────────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # avoids lazy-load after commit in the same request
)


# ── Declarative base ───────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """
    SQLAlchemy 2.x declarative base (class form, not legacy function form).
    All ORM models inherit from this class.
    """
    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """
    Yield one database session per request.

    On any unhandled exception the session is rolled back before being closed,
    so a failed transaction never leaves the connection in a broken state for
    the next request that picks it up from the pool.
    """
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
