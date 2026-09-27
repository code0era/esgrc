"""
Authentication service - pure functions with no FastAPI or DB dependencies.

Responsibilities
────────────────
- Password hashing and verification (bcrypt directly - passlib's crypt backend
  is deprecated in Python 3.12 and removed in 3.13)
- JWT access token creation and decoding
- Refresh token generation and hashing (SHA-256 for secure DB storage)

Design notes
────────────
- Access tokens (30 min): short-lived, signed JWTs carrying user_id, org_id,
  and role. Stateless - no DB lookup needed to validate.
- Refresh tokens (7 days): opaque random bytes prefixed with user_id for
  extraction without a DB lookup. Stored as SHA-256 hash in the users table.
  Rotation: old token invalidated on each refresh.
- Passwords: bcrypt with cost factor 12. Never stored or logged in plaintext.
- TOKEN_TYPE claim distinguishes access from refresh so a refresh token cannot
  be used as a bearer token and vice versa.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt import PyJWTError as JWTError

from app.config import settings

# ── Password hashing ──────────────────────────────────────────────────────────

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# Fixed hash used only to keep verify_password's ~100-300ms bcrypt cost on the
# "no such user" path in login(). Without this, `user is None or not
# verify_password(...)` short-circuits and skips bcrypt entirely when the
# email doesn't exist, but runs it when the email exists with a wrong
# password - a timing side-channel that lets a caller enumerate registered
# emails by measuring response time, independent of the identical error
# message both paths already return.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_hex(32))


def verify_password_or_dummy(plain: str, hashed: str | None) -> bool:
    """Like verify_password, but always pays the bcrypt cost even when
    `hashed` is None (no such user) - checks against a fixed dummy hash
    instead of short-circuiting, so a login attempt against a nonexistent
    email takes the same time as one against a real email with a wrong
    password."""
    return verify_password(plain, hashed if hashed is not None else _DUMMY_PASSWORD_HASH)


# ── Refresh token helpers ─────────────────────────────────────────────────────

def generate_refresh_token(user_id: int) -> str:
    """
    Return a refresh token encoding the user_id as a prefix.
    Format: "{user_id}:{64 random hex bytes}"
    This lets the refresh endpoint extract the user_id without a DB lookup
    so it can verify the token in a single query.
    """
    return f"{user_id}:{secrets.token_hex(64)}"


def decode_refresh_token_user_id(token: str) -> int | None:
    """
    Extract the user_id from a refresh token prefix.
    Returns None if the token is malformed.
    """
    try:
        prefix, _ = token.split(":", 1)
        return int(prefix)
    except (ValueError, AttributeError):
        return None


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 hex digest of the refresh token for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── JWT access token ──────────────────────────────────────────────────────────

_ACCESS = "access"
_REFRESH = "refresh"


def create_access_token(user_id: int, org_id: int, role: str) -> str:
    """
    Create a signed JWT access token.

    Claims:
        sub  - user ID (string, per JWT spec)
        org  - organisation ID
        role - user role string
        typ  - "access" (prevents refresh tokens being used as access tokens)
        exp  - expiry timestamp
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "org": org_id,
        "role": role,
        "typ": _ACCESS,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Raises:
        JWTError: if the token is invalid, expired, or the wrong type.
    """
    payload = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("typ") != _ACCESS:
        raise JWTError("Token is not an access token.")
    return payload
