"""
ESGRC API - application entry point.

Startup / shutdown:
  Tables are created inside the lifespan context manager (not at module
  import time) so test suites can override DATABASE_URL before the app boots.

CORS:
  allow_origins=["*"] + allow_credentials=True is rejected by all browsers
  (CORS spec §3.2).  When ALLOWED_ORIGINS is empty (dev default) we use
  wildcard origins with credentials disabled.  Set ALLOWED_ORIGINS to a
  comma-separated list of explicit origins to enable credentialed requests.

Logging:
  Basic logging is configured here so all modules that call
  logging.getLogger(__name__) inherit the root handler.

Global exception handler:
  Unhandled exceptions are caught, logged, and returned as structured JSON
  with status 500 rather than letting FastAPI emit a plain-text traceback.
"""
import sys
import os

# Load .env into the process environment BEFORE any pipeline module is imported.
# app.config (pydantic-settings) reads .env on its own, but the pipeline layer
# reads os.environ directly (e.g. pipeline/db.py DATABASE_URL default tbd2.db).
# Without this, a local run where DATABASE_URL lives only in .env leaves the
# pipeline endpoints pointing at a different DB than the migrated ESGRC schema.
# override=False so real env vars (Docker/prod) always take precedence.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:  # python-dotenv always present in requirements; be defensive
    pass

# Make pipeline/ importable from within the esgrc_api container
# (the Docker build context includes both ESGRC/ and pipeline/)
sys.path.insert(0, "/app")  # /app is the container working directory

# Import pipeline router
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import Base, engine
from app.routers import auth, compliance, esg, risk, scoring, agent, org_router
from app.schemas.schemas import ErrorDetail
from pipeline.routers.pipeline_router import router as pipeline_router
from pipeline.routers.copilot_router import router as copilot_router
from pipeline.middleware import add_pipeline_middleware

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan - startup and shutdown logic.

    Schema management strategy
    ──────────────────────────
    Development / testing:
        create_all() builds the schema from the ORM models so the app works
        out of the box without any manual steps.  alembic_stamp() then marks
        the DB at the current head revision so that running
        `alembic upgrade head` afterwards is a safe no-op rather than
        trying to re-create tables that already exist.

    Production:
        Run `alembic upgrade head` as part of your deployment pipeline BEFORE
        starting the application.  The lifespan create_all() will find all
        tables already present and do nothing; stamp() will be a no-op because
        alembic_version is already populated.
    """
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    # Add inside the lifespan function, before Base.metadata.create_all:
    if settings.SECRET_KEY == "change-me-in-production-use-secrets-token-hex-32":
        if not settings.DEBUG:
            raise RuntimeError(
                "SECRET_KEY is set to the default placeholder. "
                "Generate a real key: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        else:
            logger.warning("WARNING: Using default SECRET_KEY - never do this in production.")
    # FIX: create_all() + conditional stamp only ever built ESGRC's 9 tables
    # (Base here is ESGRC's own declarative base, not PipelineBase), but then
    # stamped alembic_version to the chain's overall head - which includes the
    # pipeline-tables migration. That made a later `alembic upgrade head` a
    # silent no-op, even though the pipeline tables were never actually
    # created. Running the real migration here instead creates BOTH sets of
    # tables correctly (real SQL DDL - no cross-Base Python metadata issue)
    # and is naturally idempotent if already at head.
    from pathlib import Path
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    from app.services import single_instance

    alembic_ini_path = Path(__file__).resolve().parent / "alembic.ini"
    alembic_cfg = AlembicConfig(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(alembic_ini_path.parent / "alembic"))
    try:
        # Serialised across uvicorn workers: every worker runs this lifespan, and
        # two concurrent `alembic upgrade head` runs contend on PostgreSQL DDL
        # locks. The first worker in migrates; the rest wait here and then find
        # the chain already at head, which is a no-op.
        with single_instance.exclusive(
            single_instance.default_lock_path("esgrc-migrate.lock")
        ):
            alembic_command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied (head)")
    except Exception as exc:
        logger.exception("Alembic upgrade failed during startup: %s", exc)
        raise

    logger.info("Database schema ready")

    # Start the batch agent scheduler
    from app.agent.scheduler import start_scheduler, stop_scheduler
    start_scheduler()

    yield

    stop_scheduler()
    logger.info("Shutting down %s", settings.APP_NAME)


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "ESG, Risk & Compliance (ESGRC) Management API. "
        "Provides endpoints for ESG metric tracking, risk register management, "
        "and compliance framework / requirement tracking."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ─── CORS ─────────────────────────────────────────────────────────────────────

_origins: list[str] = (
    [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if settings.ALLOWED_ORIGINS
    else ["*"]
)
_credentials: bool = _origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global exception handler ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler so unhandled exceptions return structured JSON rather
    than an empty 500 body or a plain-text traceback.
    """
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(esg.router)
app.include_router(risk.router)
app.include_router(compliance.router)
app.include_router(scoring.router)
app.include_router(agent.router)
app.include_router(org_router.router)
app.include_router(pipeline_router, prefix="/pipelines", tags=["Pipeline"])
app.include_router(copilot_router,  prefix="/copilot",   tags=["Co-Pilot"])
add_pipeline_middleware(app)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get(
    "/",
    tags=["Health"],
    summary="Root - basic liveness check",
    response_model=dict[str, str],
)
def root() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get(
    "/health",
    tags=["Health"],
    summary="Liveness probe for orchestrators (k8s, ECS, etc.)",
    response_model=dict[str, str],
)
def health() -> dict[str, str]:
    return {"status": "healthy"}
