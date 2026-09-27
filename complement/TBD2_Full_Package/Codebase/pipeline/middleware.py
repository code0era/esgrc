"""
pipeline/middleware.py
Production hardening middleware for the TBD2 pipeline layer.

Provides:
  - Request ID middleware  (UUID per request, logged + returned in header)
  - Structured JSON logging via structlog
  - Sentry SDK initialisation
  - slowapi rate limiter (60 req/min general, 10 req/min on trigger)

Usage in main.py (add after existing middleware):
    from pipeline.middleware import (
        add_pipeline_middleware,
        limiter,
        rate_limit_trigger,
        rate_limit_default,
    )
    add_pipeline_middleware(app)

Then on the trigger endpoint:
    @router.post("/{pipeline_id}/trigger")
    @limiter.limit(rate_limit_trigger)
    async def trigger_pipeline(request: Request, ...):
        ...

And on all other pipeline endpoints:
    @router.get("")
    @limiter.limit(rate_limit_default)
    async def list_pipelines(request: Request, ...):
        ...
"""
import logging
import os
import uuid
from typing import Callable

import structlog
from fastapi import FastAPI, Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# ── Rate limit strings ────────────────────────────────────────────────────────
rate_limit_default = "60/minute"
rate_limit_trigger = "10/minute"

# ── slowapi limiter - keyed by IP ─────────────────────────────────────────────
# Disabled under tests via RATE_LIMIT_ENABLED=false. Uses Redis for the counter
# store when REDIS_URL is set: with in-memory storage each uvicorn worker keeps
# its own counters, so under `--workers N` the effective limit is N× and
# unreliable. A shared Redis store makes the limit real across workers.
_RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() not in ("false", "0", "no", "")
_RATE_LIMIT_STORAGE = os.environ.get("REDIS_URL") or "memory://"
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[rate_limit_default],
    storage_uri=_RATE_LIMIT_STORAGE,
    enabled=_RATE_LIMIT_ENABLED,
)


# ── Structlog configuration ───────────────────────────────────────────────────

def configure_structlog() -> None:
    """
    Configure structlog for structured JSON output.
    Call once at application startup.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# ── Request ID middleware ─────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Attaches a unique UUID to every request.
    - Sets structlog context var `request_id` so all log lines include it
    - Returns X-Request-ID header in every response
    - Logs method, path, status, duration on completion
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        import time
        t0 = time.perf_counter()

        response = await call_next(request)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        response.headers["X-Request-ID"] = request_id

        log = structlog.get_logger()
        log.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response


# ── Sentry initialisation ─────────────────────────────────────────────────────

def init_sentry() -> None:
    """
    Initialise Sentry SDK if SENTRY_DSN is set.
    Call once at application startup (in lifespan or module level).
    Safe to call even if sentry-sdk is not installed - logs a warning.
    """
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        logging.getLogger(__name__).info("SENTRY_DSN not set - Sentry disabled")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                CeleryIntegration(monitor_beat_tasks=True),
                SqlalchemyIntegration(),
            ],
            # Don't send PII (user emails, IPs) to Sentry
            send_default_pii=False,
            # Sample 100% of errors, 10% of performance traces
            traces_sample_rate=0.10,
            environment=os.environ.get("RAILWAY_ENVIRONMENT", "development"),
        )
        logging.getLogger(__name__).info("Sentry initialised (DSN set)")
    except ImportError:
        logging.getLogger(__name__).warning(
            "sentry-sdk not installed - Sentry disabled. "
            "Add sentry-sdk[fastapi] to requirements.txt"
        )


# ── Rate limit exceeded handler ───────────────────────────────────────────────

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return structured JSON on 429 - never raw slowapi error text."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please retry shortly.",
            "retry_after": 60,
        },
        headers={"Retry-After": "60"},
    )


# ── Main setup function ───────────────────────────────────────────────────────

def add_pipeline_middleware(app: FastAPI) -> None:
    """
    Register all production middleware onto the FastAPI app.

    Call from main.py after app is created:
        from pipeline.middleware import add_pipeline_middleware
        add_pipeline_middleware(app)
    """
    configure_structlog()
    init_sentry()

    # Rate limiter - must be added before RequestIDMiddleware
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Request ID - outermost so request_id is available to all handlers
    app.add_middleware(RequestIDMiddleware)

    logging.getLogger(__name__).info("Pipeline production middleware registered")
