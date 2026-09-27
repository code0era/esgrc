"""
FastAPI auth dependencies.

Usage in any router:
    CurrentUser = Annotated[User, Depends(get_current_user)]
    AdminOnly   = Annotated[User, Depends(require_role(UserRole.ADMIN))]

get_current_user
────────────────
Extracts Bearer token from the Authorization header, decodes and validates it,
fetches the user from the DB, and verifies the user is still active.
Raises HTTP 401 on any failure so the error is always consistent.

require_role
────────────
Factory that returns a dependency enforcing a minimum role level.
Role hierarchy: SUPER_ADMIN > ADMIN > ANALYST > VIEWER.
A request with role ADMIN satisfies require_role(ANALYST).

get_current_org
───────────────
Convenience dependency returning the Organisation ORM object for the caller.
Used in business-data routers to scope queries to the caller's tenant.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError as JWTError
from sqlalchemy.orm import Session

from app.crud.auth_crud import get_user, get_organisation
from app.database import get_db
from app.models.models import Organisation, User, UserRole
from app.services.auth import decode_access_token

logger = logging.getLogger(__name__)

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
# auto_error=False lets us return a clean 401 instead of FastAPI's default 403
_bearer = HTTPBearer(auto_error=False)

# Role hierarchy - higher index = more privileged
_ROLE_HIERARCHY: list[UserRole] = [
    UserRole.VIEWER,
    UserRole.ANALYST,
    UserRole.ADMIN,
    UserRole.SUPER_ADMIN,
]

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Decode the Bearer JWT, validate claims, and return the active User.

    The JWT role claim is attached directly to the returned user object so
    require_role() uses the token-asserted role rather than re-reading from
    the DB. This is intentional: the token is the authority for the lifetime
    of the request; a role change takes effect on next login.

    Raises HTTP 401 for any auth failure.
    """
    if credentials is None:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        token_role = payload["role"]
    except (JWTError, KeyError, ValueError):
        logger.debug("JWT decode failed", exc_info=True)
        raise CREDENTIALS_EXCEPTION

    user = get_user(db, user_id)
    if user is None or not user.is_active:
        raise CREDENTIALS_EXCEPTION

    # Detach the user from the session BEFORE overriding the role. The override
    # (token = authority for the request) must NOT be persisted: this is the same
    # request-scoped session every auth_crud/business commit runs on, so a dirty
    # mapped `role` would be flushed back to the DB - letting a user with a stale
    # higher-role token permanently restore a role that was revoked in the DB.
    # Detaching keeps every already-loaded column readable (all consumers read
    # only columns: role, module_access, organisation_id) while making the
    # override transient. A role change still takes effect on next login.
    db.expunge(user)
    user.role = UserRole(token_role)
    return user


def get_current_user_sse(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    token: Annotated[str | None, Query()] = None,
) -> User:
    """
    Auth dependency for SSE endpoints.

    EventSource (browser native API) cannot set custom headers, so the JWT
    must arrive as ?token=<jwt> instead of Authorization: Bearer <jwt>.
    This dependency accepts either form; the Authorization header takes
    precedence when both are present.
    """
    raw = credentials.credentials if credentials else token
    if not raw:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(raw)
        user_id = int(payload["sub"])
        token_role = payload["role"]
    except (JWTError, KeyError, ValueError):
        logger.debug("JWT decode failed (SSE)", exc_info=True)
        raise CREDENTIALS_EXCEPTION

    user = get_user(db, user_id)
    if user is None or not user.is_active:
        raise CREDENTIALS_EXCEPTION

    db.expunge(user)
    user.role = UserRole(token_role)
    return user


def require_role(minimum_role: UserRole):
    """
    Dependency factory.  Returns a dependency that requires at least
    `minimum_role` in the role hierarchy (VIEWER < ANALYST < ADMIN).

    Usage:
        @router.delete("/{id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """
    # Accept either a UserRole or its string value (the pipeline router passes
    # strings, e.g. require_role("admin")). Normalise once so index/.value below
    # are always operating on a UserRole.
    required = UserRole(minimum_role)

    def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        caller_level = _ROLE_HIERARCHY.index(user.role)
        required_level = _ROLE_HIERARCHY.index(required)
        if caller_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{required.value}' or higher.",
            )
        return user
    return _check


# ── Module scoping (layered on top of org isolation + role RBAC) ──────────────
# Each user carries `module_access` - the module keys they may see/act on. A
# module maps to a set of pipeline types (+ its business-data routers). This
# gives per-module logins: an "esgrc" user sees only the ESGRC pipeline and its
# ESG/risk/compliance data; an "apex" user sees only the Apex pipeline. A
# SUPER_ADMIN bypasses module scope entirely. Derived from the module registry
# (pipeline/modules.py), so a new module needs no edit here.
from pipeline.modules import module_scope_map

MODULE_PIPELINE_TYPES: dict[str, set[str]] = module_scope_map()


def user_modules(user: User) -> set[str]:
    """The set of module keys a user is scoped to (empty for none)."""
    return set(user.module_access or [])


def allowed_pipeline_types(user: User) -> set[str] | None:
    """
    The pipeline-type values this user may see. None means 'all' (SUPER_ADMIN) -
    callers should skip filtering in that case.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return None
    types: set[str] = set()
    for m in user_modules(user):
        types |= MODULE_PIPELINE_TYPES.get(m, set())
    return types


def require_module(module_key: str):
    """
    Dependency factory: require the caller to have `module_key` in their
    module_access (SUPER_ADMIN bypasses). Mirrors require_role. Usage:

        router = APIRouter(dependencies=[Depends(require_module("esgrc"))])
    """
    def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role == UserRole.SUPER_ADMIN:
            return user
        if module_key not in user_modules(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires access to the '{module_key}' module.",
            )
        return user
    return _check


def require_any_module(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Require the caller to have access to at least one module (SUPER_ADMIN
    bypasses). For cross-module surfaces like the Co-Pilot that aren't tied to a
    single module but must still be closed to users with no module access at all
    (e.g. a freshly self-registered user whose module_access is empty).
    """
    if user.role == UserRole.SUPER_ADMIN:
        return user
    if not user_modules(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires access to at least one module.",
        )
    return user


def get_current_org(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Organisation:
    """
    Return the Organisation the current user belongs to.
    Used in business-data routers to scope all queries to the caller's tenant.
    """
    org = get_organisation(db, user.organisation_id)
    if org is None or not org.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organisation is inactive. Contact support.",
        )
    return org
