"""
Authentication router.

Endpoints
─────────
POST /auth/organisations   - create a new organisation (SUPER_ADMIN only; the first
                             super-admin is seeded out-of-band, see
                             ESGRC/scripts/seed_platform_admin.py)
POST /auth/register        - register a user within an existing organisation
POST /auth/login           - issue access + refresh tokens
POST /auth/refresh         - exchange a valid refresh token for a new token pair
POST /auth/logout          - invalidate the current refresh token
GET  /auth/me              - return the current authenticated user
GET  /auth/users           - list users in the caller's org (ADMIN only)
PATCH /auth/users/{id}/role - change a user's role (ADMIN only)
PATCH /auth/users/{id}/deactivate - deactivate a user (ADMIN only)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jwt import PyJWTError as JWTError
from sqlalchemy.orm import Session

from pipeline.middleware import limiter

from app.crud import auth_crud
from app.crud.auth_crud import store_refresh_token, verify_and_rotate_refresh_token
from app.database import get_db
from app.dependencies.auth import (
    get_current_user,
    require_role,
    get_current_org,
    MODULE_PIPELINE_TYPES,
)
from app.models.models import Organisation, User, UserRole
from app.schemas.schemas import (
    ErrorDetail,
    LoginRequest,
    OrganisationCreate,
    OrganisationOut,
    PaginationParams,
    RefreshRequest,
    TokenOut,
    UserOut,
    UserRegister,
    UserUpdateRole,
)
from app.services.auth import (
    create_access_token,
    decode_refresh_token_user_id,
    generate_refresh_token,
    verify_password_or_dummy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

DB = Annotated[Session, Depends(get_db)]
Pagination = Annotated[PaginationParams, Depends()]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]
SuperAdminOnly = Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))]


# ── Organisations ─────────────────────────────────────────────────────────────

@router.post(
    "/organisations",
    response_model=OrganisationOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorDetail}},
    summary="Create a new organisation (SUPER_ADMIN only)",
    description=(
        "Creates a new tenant organisation and, when admin credentials are supplied, "
        "its first full-module ADMIN. SUPER_ADMIN only (decided 18 Jul 2026: client "
        "orgs are provisioned by the platform; future self-serve signup will be a "
        "separate payment-gated flow, never this raw endpoint). The very first "
        "super-admin/org is provisioned out-of-band (seed script)."
    ),
)
def create_organisation(data: OrganisationCreate, _: SuperAdminOnly, db: DB) -> OrganisationOut:
    try:
        org = auth_crud.create_organisation(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    # First-admin bootstrap: if admin credentials were supplied, create the org's
    # first ADMIN with access to every module. This is the only API path to mint
    # an org's initial admin (register only creates empty-module ANALYSTs), so
    # without it a freshly created org would be unusable through the API alone.
    if data.admin_email and data.admin_password and data.admin_full_name:
        admin_data = UserRegister(
            email=data.admin_email,
            full_name=data.admin_full_name,
            password=data.admin_password,
            organisation_slug=org.slug,
        )
        try:
            auth_crud.create_user(
                db,
                admin_data,
                organisation_id=org.id,
                role=UserRole.ADMIN,
                module_access=list(MODULE_PIPELINE_TYPES.keys()),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return org


# ── Registration ──────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorDetail}, 409: {"model": ErrorDetail},
               429: {"model": ErrorDetail}},
    summary="Register a new user",
)
# Registration is unauthenticated and distinguishes a valid organisation slug
# (404 vs 409/201), so without a limit it is an organisation-slug oracle as well
# as an account-creation firehose. The global 60/minute default was the only
# thing standing in front of it.
@limiter.limit("5/minute")
def register(request: Request, data: UserRegister, db: DB) -> UserOut:
    org = auth_crud.get_organisation_by_slug(db, data.organisation_slug)
    if org is None or not org.active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organisation '{data.organisation_slug}' not found or inactive.",
        )
    # Registrants are ANALYST with no module access until an admin grants it, so
    # self-registration into a known org slug discloses nothing (every business
    # router - including /org/snapshot and /copilot - 403s an empty-module user).
    # The org's first admin is created at org-creation time (see create_org).
    try:
        return auth_crud.create_user(db, data, organisation_id=org.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenOut,
    responses={401: {"model": ErrorDetail}, 429: {"model": ErrorDetail}},
    summary="Login - issue access and refresh tokens",
)
@limiter.limit("5/minute")
def login(request: Request, data: LoginRequest, db: DB) -> TokenOut:
    user = auth_crud.get_user_by_email(db, data.email)
    # verify_password_or_dummy always pays the bcrypt cost, even when user is
    # None, so a nonexistent-email attempt and a wrong-password attempt take
    # the same time (see its docstring - closes a response-time oracle).
    password_ok = verify_password_or_dummy(
        data.password, user.hashed_password if user else None
    )
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated. Contact your administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user.id,
        org_id=user.organisation_id,
        role=user.role.value,
    )
    refresh_token = generate_refresh_token(user.id)
    store_refresh_token(db, user.id, refresh_token)

    logger.info("User id=%s logged in", user.id)
    return TokenOut(access_token=access_token, refresh_token=refresh_token)


# ── Token refresh ─────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenOut,
    responses={401: {"model": ErrorDetail}, 429: {"model": ErrorDetail}},
    summary="Exchange a refresh token for a new token pair",
)
# Unauthenticated and takes a bearer-equivalent secret, so it deserves the same
# treatment as login. More generous than login's 5/minute because a legitimate
# client refreshes on its own schedule and StrictMode can double-invoke.
@limiter.limit("20/minute")
def refresh(request: Request, data: RefreshRequest, db: DB) -> TokenOut:
    """
    Implements refresh token rotation: the old refresh token is invalidated
    immediately and a new pair is issued. If the same refresh token is
    presented twice, it has been replayed - both sessions are rejected.
    """
    user_id = decode_refresh_token_user_id(data.refresh_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    valid = verify_and_rotate_refresh_token(db, user_id, data.refresh_token)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or has already been used.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_crud.get_user(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user.id,
        org_id=user.organisation_id,
        role=user.role.value,
    )
    new_refresh = generate_refresh_token(user.id)
    store_refresh_token(db, user.id, new_refresh)

    return TokenOut(access_token=access_token, refresh_token=new_refresh)


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout - invalidate the current refresh token",
)
def logout(current_user: CurrentUser, db: DB) -> None:
    auth_crud.clear_refresh_token(db, current_user.id)
    logger.info("User id=%s logged out", current_user.id)


# ── Current user ──────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the currently authenticated user",
)
def me(current_user: CurrentUser) -> UserOut:
    return current_user


# ── User management (ADMIN only) ──────────────────────────────────────────────

@router.get(
    "/users",
    response_model=list[UserOut],
    summary="List users in the caller's organisation (ADMIN only)",
)
def list_users(
    current_user: AdminOnly,
    pagination: Pagination,
    db: DB,
) -> list[UserOut]:
    return auth_crud.get_users_in_org(
        db,
        current_user.organisation_id,
        skip=pagination.skip,
        limit=pagination.limit,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=UserOut,
    responses={404: {"model": ErrorDetail}, 403: {"model": ErrorDetail}},
    summary="Change a user's role (ADMIN only)",
)
def update_user_role(
    user_id: int,
    data: UserUpdateRole,
    current_user: AdminOnly,
    db: DB,
) -> UserOut:
    target = auth_crud.get_user(db, user_id)
    if target is None or target.organisation_id != current_user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    # Privilege-escalation guard: only a SUPER_ADMIN may grant SUPER_ADMIN or
    # change a user who currently holds it. A regular ADMIN cannot mint one.
    if (
        data.role == UserRole.SUPER_ADMIN or target.role == UserRole.SUPER_ADMIN
    ) and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a super_admin can grant or modify the super_admin role.",
        )
    updated = auth_crud.update_user_role(db, user_id, data.role)
    return updated


@router.patch(
    "/users/{user_id}/deactivate",
    response_model=UserOut,
    responses={404: {"model": ErrorDetail}, 403: {"model": ErrorDetail}},
    summary="Deactivate a user (ADMIN only)",
)
def deactivate_user(
    user_id: int,
    current_user: AdminOnly,
    db: DB,
) -> UserOut:
    target = auth_crud.get_user(db, user_id)
    if target is None or target.organisation_id != current_user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    if target.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot deactivate your own account.",
        )
    # Mirror the role-endpoint guard: a plain ADMIN must not be able to
    # deactivate a SUPER_ADMIN (e.g. the platform root) from within the org.
    if target.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a super_admin can deactivate a super_admin.",
        )
    return auth_crud.deactivate_user(db, user_id)
