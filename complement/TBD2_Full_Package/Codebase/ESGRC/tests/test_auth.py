"""
Tests for Phase 3: Authentication and user management.

Uses raw_client (no dependency overrides) so the real auth flow -
JWT decoding, get_current_user, require_role - is exercised end-to-end.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.services.auth import (
    hash_password, verify_password,
    generate_refresh_token, decode_refresh_token_user_id,
    create_access_token, decode_access_token,
    hash_refresh_token,
)


# ── Pure service unit tests ────────────────────────────────────────────────────

def test_password_hash_and_verify():
    h = hash_password("SecureP@ss1")
    assert verify_password("SecureP@ss1", h)
    assert not verify_password("wrong", h)


def test_password_hashes_are_unique():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


def test_refresh_token_encodes_user_id():
    rt = generate_refresh_token(99)
    assert decode_refresh_token_user_id(rt) == 99


def test_refresh_token_malformed_returns_none():
    assert decode_refresh_token_user_id("not-a-valid-token") is None
    assert decode_refresh_token_user_id("abc:rest") is None
    assert decode_refresh_token_user_id("") is None


def test_access_token_round_trip():
    tok = create_access_token(user_id=7, org_id=3, role="analyst")
    payload = decode_access_token(tok)
    assert payload["sub"] == "7"
    assert payload["org"] == 3
    assert payload["role"] == "analyst"
    assert payload["typ"] == "access"


def test_hash_refresh_token_is_deterministic():
    rt = "sometoken"
    assert hash_refresh_token(rt) == hash_refresh_token(rt)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def org(raw_client, platform_admin_header):
    uid = uuid.uuid4().hex[:8]
    r = raw_client.post("/auth/organisations", json={
        "name": f"Acme Corp {uid}",
        "slug": f"acme-{uid}",
    }, headers=platform_admin_header)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def org2(raw_client, platform_admin_header):
    uid = uuid.uuid4().hex[:8]
    r = raw_client.post("/auth/organisations", json={
        "name": f"Globex {uid}",
        "slug": f"globex-{uid}",
    }, headers=platform_admin_header)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def admin_user(raw_client, org):
    uid = uuid.uuid4().hex[:8]
    email = f"admin-{uid}@acme.com"
    r = raw_client.post("/auth/register", json={
        "email": email,
        "full_name": "Admin User",
        "password": "Admin1234!",
        "organisation_slug": org["slug"],
    })
    assert r.status_code == 201, r.text
    data = r.json()
    data["_password"] = "Admin1234!"
    return data


@pytest.fixture
def admin_token(raw_client, admin_user):
    r = raw_client.post("/auth/login", json={
        "email": admin_user["email"],
        "password": admin_user["_password"],
    })
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def analyst_user(raw_client, org, admin_token):
    uid = uuid.uuid4().hex[:8]
    email = f"analyst-{uid}@acme.com"
    r = raw_client.post("/auth/register", json={
        "email": email,
        "full_name": "Analyst User",
        "password": "Analyst1234!",
        "organisation_slug": org["slug"],
    })
    assert r.status_code == 201, r.text
    data = r.json()
    data["_password"] = "Analyst1234!"
    return data


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Organisation tests ─────────────────────────────────────────────────────────

def test_create_organisation(raw_client, platform_admin_header):
    r = raw_client.post("/auth/organisations", json={
        "name": "Test Org",
        "slug": "test-org-unique",
    }, headers=platform_admin_header)
    assert r.status_code == 201
    data = r.json()
    assert data["slug"] == "test-org-unique"
    assert data["active"] is True


def test_create_organisation_unauthenticated_rejected(raw_client):
    # SECURITY (18 Jul decision): org creation is SUPER_ADMIN-only. An
    # unauthenticated caller must never be able to mint a tenant + admin.
    r = raw_client.post("/auth/organisations", json={
        "name": "Rogue Org",
        "slug": "rogue-org",
    })
    assert r.status_code in (401, 403)


def test_create_organisation_org_admin_rejected(raw_client, org, admin_user):
    # A tenant ADMIN (not SUPER_ADMIN) must not be able to create new orgs.
    # Registration defaults to ANALYST, so forge a genuine admin-role token to
    # actually exercise the ADMIN->403 path (not the ANALYST path).
    from app.services.auth import create_access_token
    admin_access = create_access_token(user_id=admin_user["id"], org_id=org["id"], role="admin")
    r = raw_client.post("/auth/organisations", json={
        "name": "Sneaky Org",
        "slug": "sneaky-org",
    }, headers=_auth_header(admin_access))
    assert r.status_code == 403


def test_duplicate_org_slug_returns_409(raw_client, platform_admin_header):
    raw_client.post("/auth/organisations", json={"name": "Org A", "slug": "org-a-dup"},
                    headers=platform_admin_header)
    r = raw_client.post("/auth/organisations", json={"name": "Org A2", "slug": "org-a-dup"},
                       headers=platform_admin_header)
    assert r.status_code == 409


def test_invalid_org_slug_rejected(raw_client, platform_admin_header):
    r = raw_client.post("/auth/organisations", json={"name": "Bad", "slug": "Bad Slug!"},
                       headers=platform_admin_header)
    assert r.status_code == 422


def test_role_override_never_persists_to_db(raw_client, db_session):
    """SECURITY regression: a request whose token asserts a HIGHER role than the
    DB must NOT write that role back to the users table when the request commits.
    Otherwise a user holding a stale higher-role token could permanently restore
    a role that was revoked in the DB (get_current_user's role override must be
    request-scoped only)."""
    import uuid
    from app.services.auth import create_access_token, hash_password
    from app.models.models import Organisation, User, UserRole

    uid = uuid.uuid4().hex[:8]
    org = Organisation(name=f"Persist {uid}", slug=f"persist-{uid}")
    db_session.add(org)
    db_session.flush()
    demoted = User(
        organisation_id=org.id, email=f"demoted-{uid}@t.com", full_name="Demoted",
        hashed_password=hash_password("x"), role=UserRole.ADMIN, is_active=True,
    )
    db_session.add(demoted)
    db_session.flush()
    pk = demoted.id

    # Stale token claims super_admin; the DB says admin.
    stale = create_access_token(user_id=pk, org_id=org.id, role="super_admin")
    # /auth/logout commits (clear_refresh_token) on the request-scoped session.
    r = raw_client.post("/auth/logout", headers=_auth_header(stale))
    assert r.status_code in (200, 204), r.text

    db_session.expire_all()
    fresh = db_session.get(User, pk)
    assert fresh.role == UserRole.ADMIN, "token role was persisted to the DB - privilege restore!"


# ── Registration tests ─────────────────────────────────────────────────────────

def test_register_user(raw_client, org):
    r = raw_client.post("/auth/register", json={
        "email": "user@acme.com",
        "full_name": "Test User",
        "password": "Secure1234!",
        "organisation_slug": org["slug"],
    })
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "user@acme.com"
    assert data["role"] == "analyst"
    assert "hashed_password" not in data


def test_register_duplicate_email_returns_409(raw_client, org):
    payload = {
        "email": "dup@acme.com",
        "full_name": "A",
        "password": "Pass1234!",
        "organisation_slug": org["slug"],
    }
    raw_client.post("/auth/register", json=payload)
    r = raw_client.post("/auth/register", json=payload)
    assert r.status_code == 409


def test_register_unknown_org_returns_404(raw_client):
    r = raw_client.post("/auth/register", json={
        "email": "x@x.com",
        "full_name": "X",
        "password": "Pass1234!",
        "organisation_slug": "no-such-org",
    })
    assert r.status_code == 404


def test_register_short_password_rejected(raw_client, org):
    r = raw_client.post("/auth/register", json={
        "email": "x@x.com",
        "full_name": "X",
        "password": "short",
        "organisation_slug": org["slug"],
    })
    assert r.status_code == 422


def test_register_oversized_password_rejected(raw_client, org):
    """
    Password fields were previously unbounded above the min_length=8 floor,
    so an unauthenticated client could push an arbitrarily large string into
    bcrypt hashing. Capped at 128 chars - bcrypt itself only uses the first
    72 bytes, so this rejects only pathological input, never a real password.
    """
    r = raw_client.post("/auth/register", json={
        "email": "y@x.com",
        "full_name": "Y",
        "password": "a" * 129,
        "organisation_slug": org["slug"],
    })
    assert r.status_code == 422


# ── Login tests ────────────────────────────────────────────────────────────────

def test_login_success(raw_client, admin_user):
    r = raw_client.post("/auth/login", json={
        "email": admin_user["email"],
        "password": admin_user["_password"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password_returns_401(raw_client, admin_user):
    r = raw_client.post("/auth/login", json={
        "email": admin_user["email"],
        "password": "WrongPass",
    })
    assert r.status_code == 401


def test_login_unknown_email_returns_401(raw_client):
    r = raw_client.post("/auth/login", json={
        "email": "nobody@x.com",
        "password": "Pass1234!",
    })
    assert r.status_code == 401


def test_login_unknown_email_still_pays_bcrypt_cost(raw_client, monkeypatch):
    """
    Regression: login() used to short-circuit `user is None or not
    verify_password(...)`, so a nonexistent email skipped the ~100-300ms
    bcrypt call entirely while a wrong password on a real email always paid
    it - a response-time oracle letting a caller enumerate registered
    emails, independent of the identical 401 body both paths return.
    bcrypt.checkpw must now run on both paths (against a fixed dummy hash
    when there's no user).
    """
    import bcrypt as bcrypt_module
    calls = []
    real_checkpw = bcrypt_module.checkpw

    def _counting_checkpw(password, hashed):
        calls.append(hashed)
        return real_checkpw(password, hashed)

    monkeypatch.setattr(bcrypt_module, "checkpw", _counting_checkpw)

    r = raw_client.post("/auth/login", json={
        "email": "nobody-at-all@example.com",
        "password": "Pass1234!",
    })
    assert r.status_code == 401
    assert len(calls) == 1


def test_login_oversized_password_rejected(raw_client, admin_user):
    """LoginRequest.password was previously unbounded - see
    test_register_oversized_password_rejected for the registration side."""
    r = raw_client.post("/auth/login", json={
        "email": admin_user["email"],
        "password": "a" * 129,
    })
    assert r.status_code == 422


# ── Token / auth tests ─────────────────────────────────────────────────────────

def test_protected_endpoint_without_token_returns_401(raw_client):
    r = raw_client.get("/auth/me")
    assert r.status_code == 401


def test_me_returns_current_user(raw_client, admin_user, admin_token):
    r = raw_client.get("/auth/me", headers=_auth_header(admin_token["access_token"]))
    assert r.status_code == 200
    assert r.json()["email"] == admin_user["email"]


def test_invalid_token_returns_401(raw_client):
    r = raw_client.get("/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert r.status_code == 401


# ── Refresh token tests ────────────────────────────────────────────────────────

def test_refresh_token_rotation(raw_client, admin_token):
    r = raw_client.post("/auth/refresh", json={"refresh_token": admin_token["refresh_token"]})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != admin_token["refresh_token"]
    assert len(data["access_token"]) > 20


def test_refresh_token_replay_returns_401(raw_client, admin_token):
    rt = admin_token["refresh_token"]
    r1 = raw_client.post("/auth/refresh", json={"refresh_token": rt})
    assert r1.status_code == 200
    r2 = raw_client.post("/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 401


def test_refresh_with_invalid_token_returns_401(raw_client):
    r = raw_client.post("/auth/refresh", json={"refresh_token": "not-valid-at-all"})
    assert r.status_code == 401


def test_logout_invalidates_refresh_token(raw_client, admin_token):
    raw_client.post(
        "/auth/logout",
        headers=_auth_header(admin_token["access_token"]),
    )
    r = raw_client.post("/auth/refresh", json={"refresh_token": admin_token["refresh_token"]})
    assert r.status_code == 401


# ── Refresh token expiry ───────────────────────────────────────────────────────
# REFRESH_TOKEN_EXPIRE_DAYS was configured but never read: tokens carry no
# timestamp and rotation only compared hashes, so a stolen refresh token was
# usable indefinitely. These pin the expiry that now backs it.

def _load_user(db_session, email):
    from app.models.models import User

    db_session.expire_all()  # drop identity-map copies the request just wrote
    return db_session.query(User).filter(User.email == email.lower()).one()


def _as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def test_login_stamps_refresh_token_expiry(raw_client, admin_user, admin_token, db_session):
    from app.config import settings

    user = _load_user(db_session, admin_user["email"])
    assert user.refresh_token_expires_at is not None, (
        "login stored a refresh token with no expiry, so it would never age out"
    )
    expected = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    drift = abs((_as_utc(user.refresh_token_expires_at) - expected).total_seconds())
    assert drift < 300, f"expiry is {drift}s from the configured window"


def test_expired_refresh_token_returns_401(raw_client, admin_user, admin_token, db_session):
    user = _load_user(db_session, admin_user["email"])
    user.refresh_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    r = raw_client.post(
        "/auth/refresh", json={"refresh_token": admin_token["refresh_token"]}
    )
    assert r.status_code == 401


def test_expired_refresh_token_is_cleared_from_the_row(
    raw_client, admin_user, admin_token, db_session
):
    """A rejected-because-expired token should not be left sitting on the user."""
    user = _load_user(db_session, admin_user["email"])
    user.refresh_token_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    raw_client.post("/auth/refresh", json={"refresh_token": admin_token["refresh_token"]})

    user = _load_user(db_session, admin_user["email"])
    assert user.hashed_refresh_token is None
    assert user.refresh_token_expires_at is None


def test_refresh_token_without_expiry_fails_closed(
    raw_client, admin_user, admin_token, db_session
):
    """Sessions predating the expiry column must not be honoured forever."""
    user = _load_user(db_session, admin_user["email"])
    user.refresh_token_expires_at = None
    db_session.commit()

    r = raw_client.post(
        "/auth/refresh", json={"refresh_token": admin_token["refresh_token"]}
    )
    assert r.status_code == 401


def test_rotation_extends_the_expiry_window(
    raw_client, admin_user, admin_token, db_session
):
    """Each rotation issues a fresh window rather than inheriting the old one."""
    user = _load_user(db_session, admin_user["email"])
    user.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    db_session.commit()

    r = raw_client.post(
        "/auth/refresh", json={"refresh_token": admin_token["refresh_token"]}
    )
    assert r.status_code == 200

    user = _load_user(db_session, admin_user["email"])
    assert _as_utc(user.refresh_token_expires_at) > datetime.now(timezone.utc) + timedelta(
        hours=1
    )


# ── Role enforcement tests ─────────────────────────────────────────────────────

def test_list_users_requires_admin(raw_client, admin_user, analyst_user, admin_token):
    analyst_login = raw_client.post("/auth/login", json={
        "email": analyst_user["email"],
        "password": analyst_user["_password"],
    })
    analyst_token = analyst_login.json()["access_token"]

    # Analyst cannot list users
    r = raw_client.get("/auth/users", headers=_auth_header(analyst_token))
    assert r.status_code == 403

    # Forge an admin-role token for the admin_user
    admin_access = create_access_token(
        user_id=admin_user["id"],
        org_id=admin_user["organisation_id"],
        role="admin",
    )
    r2 = raw_client.get("/auth/users", headers=_auth_header(admin_access))
    assert r2.status_code == 200


def test_update_role_requires_admin(raw_client, admin_user, analyst_user):
    analyst_login = raw_client.post("/auth/login", json={
        "email": analyst_user["email"],
        "password": analyst_user["_password"],
    })
    analyst_access = analyst_login.json()["access_token"]

    r = raw_client.patch(
        f"/auth/users/{admin_user['id']}/role",
        json={"role": "viewer"},
        headers=_auth_header(analyst_access),
    )
    assert r.status_code == 403


def test_admin_can_update_role(raw_client, admin_user, analyst_user):
    admin_access = create_access_token(
        user_id=admin_user["id"],
        org_id=admin_user["organisation_id"],
        role="admin",
    )
    r = raw_client.patch(
        f"/auth/users/{analyst_user['id']}/role",
        json={"role": "viewer"},
        headers=_auth_header(admin_access),
    )
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"


def test_admin_cannot_deactivate_themselves(raw_client, admin_user):
    admin_access = create_access_token(
        user_id=admin_user["id"],
        org_id=admin_user["organisation_id"],
        role="admin",
    )
    r = raw_client.patch(
        f"/auth/users/{admin_user['id']}/deactivate",
        headers=_auth_header(admin_access),
    )
    assert r.status_code == 403


def test_admin_cannot_manage_other_org_users(raw_client, org, org2, admin_user):
    other_r = raw_client.post("/auth/register", json={
        "email": "other@globex.com",
        "full_name": "Other User",
        "password": "Other1234!",
        "organisation_slug": org2["slug"],
    })
    other_id = other_r.json()["id"]
    admin_access = create_access_token(
        user_id=admin_user["id"],
        org_id=admin_user["organisation_id"],
        role="admin",
    )
    r = raw_client.patch(
        f"/auth/users/{other_id}/role",
        json={"role": "viewer"},
        headers=_auth_header(admin_access),
    )
    assert r.status_code == 404


def test_deactivated_user_cannot_login(raw_client, org):
    uid = uuid.uuid4().hex[:8]
    admin_email = f"admin2-{uid}@acme.com"
    admin_reg = raw_client.post("/auth/register", json={
        "email": admin_email,
        "full_name": "Admin2",
        "password": "Admin1234!",
        "organisation_slug": org["slug"],
    })
    admin_id = admin_reg.json()["id"]
    org_id = admin_reg.json()["organisation_id"]

    target_email = f"target-{uid}@acme.com"
    target_reg = raw_client.post("/auth/register", json={
        "email": target_email,
        "full_name": "Target",
        "password": "Target1234!",
        "organisation_slug": org["slug"],
    })
    target_id = target_reg.json()["id"]

    admin_tok = create_access_token(user_id=admin_id, org_id=org_id, role="admin")
    r_deact = raw_client.patch(
        f"/auth/users/{target_id}/deactivate",
        headers=_auth_header(admin_tok),
    )
    assert r_deact.status_code == 200, r_deact.text

    r = raw_client.post("/auth/login", json={
        "email": target_email,
        "password": "Target1234!",
    })
    assert r.status_code == 401


# ── First-admin bootstrap + module-gated snapshot ───────────────────────────────

class TestOrgAdminBootstrap:
    def test_org_creation_with_admin_mints_first_admin(self, raw_client, platform_admin_header):
        """Supplying admin_* to org creation bootstraps an ADMIN with full module
        access - the only API path to mint an org's first admin."""
        uid = uuid.uuid4().hex[:8]
        email = f"boss-{uid}@boot.com"
        r = raw_client.post("/auth/organisations", json={
            "name": "Boot Org",
            "slug": f"boot-{uid}",
            "admin_email": email,
            "admin_full_name": "Boss",
            "admin_password": "Boss1234!",
        }, headers=platform_admin_header)
        assert r.status_code == 201, r.text

        login = raw_client.post("/auth/login", json={"email": email, "password": "Boss1234!"})
        assert login.status_code == 200, login.text
        tok = login.json()["access_token"]

        me = raw_client.get("/auth/me", headers=_auth_header(tok))
        assert me.status_code == 200
        body = me.json()
        assert body["role"] == "admin"
        assert set(body["module_access"]) >= {"esgrc", "apex"}

    def test_org_creation_without_admin_mints_no_user(self, raw_client, platform_admin_header):
        """Legacy behaviour preserved: omit admin_* and no user is created."""
        uid = uuid.uuid4().hex[:8]
        r = raw_client.post("/auth/organisations", json={"name": "Empty", "slug": f"empty-{uid}"},
                            headers=platform_admin_header)
        assert r.status_code == 201
        # No admin was minted, so there is no one to log in as.
        login = raw_client.post("/auth/login", json={
            "email": f"nobody-{uid}@empty.com", "password": "Whatever1!"
        })
        assert login.status_code == 401

    def test_snapshot_requires_module_access(self, raw_client, platform_admin_header):
        """A registered ANALYST with no module access is 403'd from /org/snapshot,
        matching the sibling business routers (regression for the disclosure gap
        where the snapshot was reachable by any authenticated org member)."""
        uid = uuid.uuid4().hex[:8]
        slug = f"gate-{uid}"
        email = f"analyst-{uid}@gate.com"
        raw_client.post("/auth/organisations", json={"name": "Gate Org", "slug": slug},
                        headers=platform_admin_header)
        reg = raw_client.post("/auth/register", json={
            "email": email, "full_name": "A",
            "password": "Pass1234!", "organisation_slug": slug,
        })
        assert reg.status_code == 201, reg.text
        assert reg.json()["module_access"] == []

        login = raw_client.post("/auth/login", json={"email": email, "password": "Pass1234!"})
        assert login.status_code == 200
        tok = login.json()["access_token"]

        r = raw_client.get("/org/snapshot", headers=_auth_header(tok))
        assert r.status_code == 403

    def test_snapshot_allowed_for_bootstrapped_admin(self, raw_client, platform_admin_header):
        """The bootstrapped admin (full module access) can read the snapshot."""
        uid = uuid.uuid4().hex[:8]
        email = f"boss-{uid}@ok.com"
        raw_client.post("/auth/organisations", json={
            "name": "OK Org", "slug": f"ok-{uid}",
            "admin_email": email, "admin_full_name": "Boss", "admin_password": "Boss1234!",
        }, headers=platform_admin_header)
        tok = raw_client.post(
            "/auth/login", json={"email": email, "password": "Boss1234!"}
        ).json()["access_token"]
        r = raw_client.get("/org/snapshot", headers=_auth_header(tok))
        assert r.status_code == 200, r.text
