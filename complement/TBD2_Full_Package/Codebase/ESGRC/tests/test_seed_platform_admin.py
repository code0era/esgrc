"""
Tests for scripts/seed_platform_admin.py - the out-of-band bootstrap for the
first platform SUPER_ADMIN + platform organisation.

Login always looks up by lowercased, stripped email (see
app/crud/auth_crud.py:get_user_by_email / create_user, which both normalise
with .lower().strip()). The seed script must normalise the same way at write
time, or a PLATFORM_ADMIN_EMAIL with any uppercase character seeds a platform
root that can never successfully log in.
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

# scripts/ has no __init__.py - it's run as a standalone script (see the
# script's own sys.path manipulation), so import it the same way here.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_platform_admin  # noqa: E402

from app.crud.auth_crud import get_user_by_email  # noqa: E402
from app.models.models import Organisation, User, UserRole  # noqa: E402


def _run_seed(monkeypatch, db_session, *, email, password="a-strong-password", name="Platform Root"):
    """Run seed_platform_admin.main() against the test's in-memory DB session."""
    monkeypatch.setenv("PLATFORM_ADMIN_EMAIL", email)
    monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", password)
    monkeypatch.setenv("PLATFORM_ADMIN_NAME", name)
    monkeypatch.setattr(seed_platform_admin, "SessionLocal", lambda: db_session)
    return seed_platform_admin.main()


def test_seed_lowercases_mixed_case_email(monkeypatch, db_session):
    rc = _run_seed(monkeypatch, db_session, email="Admin@Example.COM")
    assert rc == 0

    # Scoped to the exact email written by this test - the shared test DB can
    # carry SUPER_ADMIN rows from other fixtures/tests, so a bare
    # role==SUPER_ADMIN filter is not a reliable way to find "the one we made".
    stored = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert stored is not None, "seed did not create a user at the normalised email"
    assert stored.role == UserRole.SUPER_ADMIN
    assert stored.email == "admin@example.com", (
        "seed script must lowercase/strip the email at write time - login "
        "looks it up lowercased (get_user_by_email) so a mixed-case row "
        "would never match"
    )


def test_seeded_admin_is_findable_by_login_lookup(monkeypatch, db_session):
    """The actual regression: a mixed-case seed email must still resolve via
    the exact lookup the login endpoint uses, which lowercases its input."""
    rc = _run_seed(monkeypatch, db_session, email="Root@Platform.Test")
    assert rc == 0

    found = get_user_by_email(db_session, "Root@Platform.Test")
    assert found is not None, (
        "platform root seeded with a mixed-case email cannot be found by "
        "the login lookup - it would be permanently locked out"
    )
    assert found.role == UserRole.SUPER_ADMIN


def test_seed_is_idempotent_regardless_of_input_case(monkeypatch, db_session):
    """Running the seed twice with different casing of the same address must
    not create two users - the existing-user check must compare normalised
    emails too."""
    rc1 = _run_seed(monkeypatch, db_session, email="dup@example.com")
    assert rc1 == 0
    rc2 = _run_seed(monkeypatch, db_session, email="DUP@EXAMPLE.COM")
    assert rc2 == 0

    count = len(
        db_session.scalars(
            select(User).where(User.email == "dup@example.com")
        ).all()
    )
    assert count == 1, "seeding the same email in different cases created two users"


def test_seed_creates_platform_organisation(monkeypatch, db_session):
    rc = _run_seed(monkeypatch, db_session, email="root2@example.com")
    assert rc == 0

    org = db_session.scalar(select(Organisation).where(Organisation.slug == "platform"))
    assert org is not None
