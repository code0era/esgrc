"""
CRUD operations for Authentication - Organisation and User management.

Kept in a separate file from the main CRUD to maintain clear boundaries:
- auth_crud.py  → organisations, users, token management
- crud.py       → ESG, Risk, Compliance business data

All password and token handling is delegated to app.services.auth;
no hashing happens directly in this layer.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Organisation, User, UserRole
from app.schemas.schemas import OrganisationCreate, UserRegister
from app.services.auth import hash_password, hash_refresh_token

logger = logging.getLogger(__name__)


# ─── Organisation ─────────────────────────────────────────────────────────────

def create_organisation(db: Session, data: OrganisationCreate) -> Organisation:
    obj = Organisation(name=data.name, slug=data.slug)
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(
            f"Organisation with name '{data.name}' or slug '{data.slug}' already exists."
        )
    db.refresh(obj)
    logger.debug("Created Organisation id=%s slug=%s", obj.id, obj.slug)
    return obj


def get_organisation_by_slug(db: Session, slug: str) -> Organisation | None:
    return db.scalar(
        select(Organisation).where(Organisation.slug == slug)
    )


def get_organisation(db: Session, org_id: int) -> Organisation | None:
    return db.scalar(
        select(Organisation).where(Organisation.id == org_id)
    )


# ─── User ─────────────────────────────────────────────────────────────────────

def create_user(
    db: Session,
    data: UserRegister,
    organisation_id: int,
    role: UserRole = UserRole.ANALYST,
    module_access: list[str] | None = None,
) -> User:
    """
    Create a new user.  The caller is responsible for verifying the
    organisation exists before calling this function.
    """
    obj = User(
        organisation_id=organisation_id,
        email=data.email.lower().strip(),  # normalise email on write
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=role,
        module_access=module_access if module_access is not None else [],
    )
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Email '{data.email}' is already registered.")
    db.refresh(obj)
    logger.debug("Created User id=%s email=%s org_id=%s", obj.id, obj.email, obj.organisation_id)
    return obj


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User).where(User.email == email.lower().strip())
    )


def get_user(db: Session, user_id: int) -> User | None:
    return db.scalar(select(User).where(User.id == user_id))


def get_users_in_org(
    db: Session, org_id: int, *, skip: int = 0, limit: int = 50
) -> list[User]:
    stmt = (
        select(User)
        .where(User.organisation_id == org_id)
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def update_user_role(db: Session, user_id: int, role: UserRole) -> User | None:
    obj = get_user(db, user_id)
    if obj is None:
        return None
    obj.role = role
    db.commit()
    db.refresh(obj)
    logger.debug("Updated User id=%s role=%s", user_id, role)
    return obj


def deactivate_user(db: Session, user_id: int) -> User | None:
    obj = get_user(db, user_id)
    if obj is None:
        return None
    obj.is_active = False
    obj.hashed_refresh_token = None  # invalidate any active session
    obj.refresh_token_expires_at = None
    db.commit()
    db.refresh(obj)
    return obj


# ─── Refresh token management ─────────────────────────────────────────────────

def _refresh_token_expired(expires_at: datetime | None) -> bool:
    """True when a stored refresh token is past its expiry, or has none.

    Treats a missing expiry as expired so sessions issued before the column
    existed cannot outlive the policy; the cost is one extra login.

    The comparison normalises to aware UTC because the two supported backends
    disagree: PostgreSQL returns an aware datetime for TIMESTAMPTZ, SQLite hands
    back a naive one. Comparing those directly raises TypeError.
    """
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def store_refresh_token(db: Session, user_id: int, raw_token: str) -> None:
    """Hash and store the refresh token. Replaces any existing token (rotation)."""
    obj = get_user(db, user_id)
    if obj is not None:
        obj.hashed_refresh_token = hash_refresh_token(raw_token)
        obj.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        db.commit()


def verify_and_rotate_refresh_token(
    db: Session, user_id: int, raw_token: str
) -> bool:
    """
    Return True and clear the stored token if the raw_token matches and is
    still within its expiry window.
    The caller must then issue a new token and store it via store_refresh_token.
    Returns False if the token does not match (replay / theft detected) or has
    expired.
    """
    obj = get_user(db, user_id)
    if obj is None or obj.hashed_refresh_token is None:
        return False
    if obj.hashed_refresh_token != hash_refresh_token(raw_token):
        # Deliberately leaves the stored token in place: a mismatch is the
        # signal of a replayed or forged token, not of the real session ending.
        return False
    if _refresh_token_expired(obj.refresh_token_expires_at):
        # Drop the dead credential rather than leaving it on the row.
        obj.hashed_refresh_token = None
        obj.refresh_token_expires_at = None
        db.commit()
        logger.info("Refresh token expired for user_id=%s; session cleared", user_id)
        return False
    # Invalidate immediately - caller will store the new token
    obj.hashed_refresh_token = None
    obj.refresh_token_expires_at = None
    db.commit()
    return True


def clear_refresh_token(db: Session, user_id: int) -> None:
    """Invalidate the stored refresh token (logout)."""
    obj = get_user(db, user_id)
    if obj is not None:
        obj.hashed_refresh_token = None
        obj.refresh_token_expires_at = None
        db.commit()
