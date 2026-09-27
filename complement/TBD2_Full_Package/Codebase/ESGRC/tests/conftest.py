"""
Pytest configuration and shared fixtures.

Uses an in-memory SQLite database so tests are fully isolated.
Each test runs inside a SAVEPOINT (nested transaction) that is rolled back
after the test, leaving the schema intact for the next test.

Org scoping
───────────
All business endpoints (ESG, Risk, Compliance) now require authentication
via get_current_org. The `client` fixture creates a default Organisation and
overrides the dependency so tests don't need to log in for every call.
Auth-specific tests (test_auth.py) use the raw `client` without the override
so they can test the auth flow end-to-end.
"""
import sys
import os
from pathlib import Path

# DATABASE_URL must be forced to :memory: BEFORE Settings is ever imported
# (Settings is @lru_cache'd, so whatever is set here is what every module
# gets for the rest of the process). Without this, alembic/env.py reads
# settings.DATABASE_URL directly during lifespan() and runs real Alembic
# migrations against the real on-disk file from .env (esgrc_imported.db)
# instead of the test session's in-memory DB.
import tempfile

_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"
import atexit

def _cleanup_tmp_db():
    try:
        from app.database import engine
        engine.dispose()
    except Exception:
        pass
    
    # Also attempt to dispose the test db_engine if it exists
    try:
        os.close(_tmp_db_fd)
    except OSError:
        pass
    try:
        os.remove(_tmp_db_path)
    except OSError:
        pass

atexit.register(_cleanup_tmp_db)
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")  # don't throttle the test client
os.environ.setdefault("DEBUG", "true")

# Make both ESGRC/ and the TBD2/ root importable regardless of cwd -
# main.py imports both `app.*` and `pipeline.*`.
_ESGRC_DIR = Path(__file__).resolve().parents[1]
_TBD2_ROOT = _ESGRC_DIR.parent
sys.path.insert(0, str(_ESGRC_DIR))
sys.path.insert(0, str(_TBD2_ROOT))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.dependencies.auth import get_current_org, get_current_user
from app.models.models import Organisation, User, UserRole
from main import app
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """
    Wraps each test in a SAVEPOINT so the DB is reset after every test
    without a SAWarning, even when the test triggers an IntegrityError.
    """
    connection = db_engine.connect()
    connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    yield session

    session.close()
    connection.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """
    TestClient with:
    - DB session injected via dependency override
    - A unique Organisation created per test and injected via get_current_org override
      so all business endpoints work without requiring a real JWT login.

    Auth tests that need to test the real auth flow should use `raw_client`
    which has no dependency overrides.
    """
    import uuid
    uid = uuid.uuid4().hex[:8]
    default_org = Organisation(name=f"Test Organisation {uid}", slug=f"test-org-{uid}")
    db_session.add(default_org)
    db_session.flush()  # get the id without committing

    def override_get_db():
        yield db_session

    def override_get_current_org():
        return default_org

    def override_get_current_user():
        # Business-endpoint tests run as a super_admin so every require_role()
        # write/admin gate passes. Role-denial is covered separately (live probes
        # + dedicated tests), so happy-path business tests need not each log in.
        return User(
            id=1,
            email=f"test-admin-{uid}@example.com",
            full_name="Test Admin",
            role=UserRole.SUPER_ADMIN,
            is_active=True,
            organisation_id=default_org.id,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_org] = override_get_current_org
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def raw_client(db_session):
    """
    TestClient with only the DB session overridden.
    get_current_org is NOT overridden - used by test_auth.py to test
    real login and token flows end-to-end.
    """
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def platform_admin_header(db_session):
    """
    Authorization header for a platform SUPER_ADMIN, minted via the real token
    path against a real DB user (no dependency overrides).

    POST /auth/organisations is SUPER_ADMIN-gated (client orgs are provisioned
    by the platform - 18 Jul 2026 decision), so org-creating fixtures/tests use
    this header. Mirrors production, where the first super-admin + platform org
    are provisioned out-of-band (seed script) - here that bootstrap is done
    directly via the ORM.
    """
    import uuid as _uuid
    from app.services.auth import create_access_token

    uid = _uuid.uuid4().hex[:8]
    platform_org = Organisation(name=f"Platform {uid}", slug=f"platform-{uid}")
    db_session.add(platform_org)
    db_session.flush()
    root = User(
        organisation_id=platform_org.id,
        email=f"root-{uid}@platform.test",
        full_name="Platform Root",
        hashed_password="x",  # never logs in via password in these tests
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(root)
    db_session.flush()

    token = create_access_token(user_id=root.id, org_id=platform_org.id, role="super_admin")
    return {"Authorization": f"Bearer {token}"}