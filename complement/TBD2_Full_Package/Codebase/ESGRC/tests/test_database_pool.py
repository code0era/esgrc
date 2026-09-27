"""
Tests for the SQLite pool selection in app/database.py.

Regression covered: the shipped default DATABASE_URL is a file-based SQLite
DB (sqlite:///./esgrc.db), not `:memory:`. StaticPool funnels every checkout
through one shared connection, which is only correct for `:memory:` (whose
data lives only in the connection that created it) - a file-based DB under
concurrent load needs NullPool (one connection per checkout) so WAL mode
actually provides concurrent access instead of being serialized behind a
single shared connection.
"""
from sqlalchemy.pool import NullPool, StaticPool

from app.database import _is_sqlite_memory, _sqlite_poolclass, engine


def test_sqlite_memory_url_uses_static_pool():
    assert _sqlite_poolclass(is_memory=True) is StaticPool


def test_sqlite_file_url_uses_null_pool():
    """The shipped default (sqlite:///./esgrc.db) - and any other file-based
    SQLite URL - must NOT use StaticPool; that was the bug."""
    assert _sqlite_poolclass(is_memory=False) is NullPool


def test_current_test_engine_is_file_based_and_uses_null_pool():
    """tests/conftest.py forces DATABASE_URL to a temp *file* (not :memory:)
    before Settings/engine are constructed, to mirror the shipped default
    (see conftest.py's comment on why). So the actual module-level `engine`
    built at import time is the real regression case: assert it really did
    pick NullPool, not StaticPool.
    """
    assert _is_sqlite_memory is False, (
        "test setup expected to use a file-based sqlite DATABASE_URL "
        "(see tests/conftest.py) - if this changed, the pool assertion "
        "below needs to change with it"
    )
    assert isinstance(engine.pool, NullPool)
