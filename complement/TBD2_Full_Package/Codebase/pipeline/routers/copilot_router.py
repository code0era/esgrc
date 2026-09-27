"""
pipeline/routers/copilot_router.py
Co-Pilot backend - Ask AI streaming panel.

Architecture decision D6: custom Anthropic SDK streaming.
No LangChain. No external dependencies beyond what is already in requirements.txt.

Endpoints:
  POST /copilot/message          Send a message, returns {run_id} immediately
  GET  /copilot/stream/{run_id}  SSE stream of Claude's token-by-token response

Flow:
  1. POST /copilot/message → validate, store conversation, enqueue Celery task,
     return {run_id, status: "streaming"}
  2. Celery task calls Anthropic streaming API, writes each token chunk to Redis
     key copilot:{run_id}:stream as a list
  3. GET /copilot/stream/{run_id} → SSE generator polls Redis, streams tokens
     to browser in real time

Security:
  - Input sanitised server-side before LLM (strip HTML, limit length)
  - Org context injected automatically from current_user - user cannot
    request data from another org
  - History stored per-user in pipeline_copilot_sessions (JSONB)
  - Rate limit: 10 messages/minute per user (inherits middleware)

Mount in main.py:
  from pipeline.routers.copilot_router import router as copilot_router
  app.include_router(copilot_router, prefix="/copilot", tags=["Co-Pilot"])
"""
import asyncio
import html
import json
import logging
import os
import re
import uuid
from typing import AsyncGenerator, List, Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user, get_current_user_sse, require_any_module, require_role
from app.models.models import User
from pipeline.celery_app import app as celery_app
from pipeline.db import get_pipeline_db

logger = logging.getLogger(__name__)

# Co-Pilot answers over the org's pipeline outputs, so it is closed to users with
# no module access at all (SUPER_ADMIN bypasses). Applied at the router level so
# every Co-Pilot endpoint inherits it.
router = APIRouter(dependencies=[Depends(require_any_module)])

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_MESSAGE_LENGTH = 2000          # chars - prevent prompt injection via huge inputs
MAX_HISTORY_TURNS = 20             # keep last 20 turns in context
STREAM_TOKEN_TTL = 60 * 60        # Redis key TTL for stream tokens (1 hour)

# Conversation history TTL. This holds the user's questions AND Claude's complete
# answers about the organisation's data, so it is the longest-lived copy of
# LLM-derived customer content anywhere in the system.
#
# Was 7 days. GDPR erasure cannot reach it: the key is scoped by session, not by
# run, so DELETE /pipelines/runs/{run_id}/files has no way to identify which
# sessions belong to the erased run. Until an org-scoped erasure endpoint exists
# (issue #12), the TTL is the only control over the exposure window, so it is
# shortened to 24h to match the Celery result backend's result_expires.
#
# Trade-off, deliberately accepted: a user returning after more than a day
# starts a fresh Co-Pilot conversation instead of resuming the old one.
SESSION_HISTORY_TTL = 60 * 60 * 24  # 24 hours
COPILOT_MODEL = os.environ.get("SPECIALIST_MODEL", "claude-haiku-4-5")

SYSTEM_PROMPT = """You are the TBD2 AI Co-Pilot, an expert ESG risk intelligence assistant.

You have deep knowledge of:
- ESG (Environmental, Social, Governance) metrics and benchmarks
- Risk management frameworks (ERM, ISO 31000, COSO)
- Compliance standards (GRI, ISO 14001, TCFD, SOC 2, PIPEDA)
- Statistical process control (SPC) and risk priority numbers (RPN)
- The organisation's pipeline outputs and analytical reports

Your role:
- Answer questions about ESG performance, risks, and compliance status
- Explain pipeline outputs and what the statistical findings mean
- Suggest specific, actionable next steps based on data
- Flag cross-module risk patterns the user may have missed

Rules:
- Be concise and direct - users are busy professionals
- Always ground recommendations in the data, not generic advice
- If you don't have enough context, say so and ask what data to look at
- Never fabricate numbers - if you don't know, say so
- You are NOT a substitute for qualified legal or financial advice
"""


# ── Schemas ───────────────────────────────────────────────────────────────────

class CopilotMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for multi-turn conversation. Omit to start a new session.",
    )


class CopilotMessageResponse(BaseModel):
    run_id: str
    session_id: str
    status: str = "streaming"
    message: str = "Stream available at GET /copilot/stream/{run_id}"


class CopilotSession(BaseModel):
    session_id: str
    messages: List[dict]
    created_at: str
    last_active: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitise(text: str) -> str:
    """Strip HTML and control characters from user input."""
    # Decode HTML entities first, then strip all tags
    text = html.unescape(text)
    # Remove script/style blocks entirely (tag + content), then strip remaining tags
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    # Remove null bytes and other control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()[:MAX_MESSAGE_LENGTH]


def _get_redis():
    import redis as redis_lib
    return redis_lib.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
    )


def _session_key(user_id: int, session_id: str) -> str:
    return f"copilot:{user_id}:session:{session_id}"


def _stream_key(user_id: int, run_id: str) -> str:
    # Namespaced by user_id so another authenticated user who learns a run_id
    # cannot read someone else's Co-Pilot token stream (broken-object-level-auth
    # guard). The owning user's id is required to derive the key.
    return f"copilot:{user_id}:{run_id}:stream"


def _stream_done_key(user_id: int, run_id: str) -> str:
    return f"copilot:{user_id}:{run_id}:done"


def _load_session_history(user_id: int, session_id: str) -> List[dict]:
    """Load conversation history from Redis. Returns [] if not found."""
    try:
        r = _get_redis()
        raw = r.get(_session_key(user_id, session_id))
        if raw:
            return json.loads(raw)[-MAX_HISTORY_TURNS * 2:]  # keep last N turns
    except Exception as exc:
        logger.warning("Could not load copilot session %s: %s", session_id, exc)
    return []


def _save_session_history(user_id: int, session_id: str, history: List[dict]) -> None:
    try:
        r = _get_redis()
        r.set(
            _session_key(user_id, session_id),
            json.dumps(history[-MAX_HISTORY_TURNS * 2:]),
            ex=SESSION_HISTORY_TTL,
        )
    except Exception as exc:
        logger.warning("Could not save copilot session %s: %s", session_id, exc)


# Cap on how much of each recommendation's text is inlined into the system
# prompt - keeps the org context block bounded even if a recommendation is long.
ORG_CONTEXT_RECOMMENDATION_CHARS = 1500
ORG_CONTEXT_MAX_RUNS = 5


def _load_org_context(org_id: int) -> str:
    """
    Build a short data block describing this org's most recent completed
    pipeline runs (confidence scores + Claude recommendations), so answers are
    grounded in the org's actual data rather than generic ESG advice.

    FIX: the module docstring and SYSTEM_PROMPT both claim the Co-Pilot has
    "deep knowledge of ... the organisation's pipeline outputs and analytical
    reports" and that "org context [is] injected automatically from
    current_user" - but stream_copilot_response accepted org_id as a parameter
    and never referenced it again; nothing about any run's data ever reached
    the Claude call. This is the fix: a best-effort, org-scoped read of recent
    run results, returned as text to append to the system prompt.

    Scoped strictly by the org_id the caller passes in (which is always
    current_user.organisation_id - see send_copilot_message), so a user can
    only ever see their own organisation's context. Never raises - any DB
    error yields an empty string so a data-layer hiccup degrades to the old
    (generic-answer) behaviour instead of blocking the Co-Pilot response.
    """
    try:
        from sqlalchemy import text
        from pipeline.database import session_ctx

        with session_ctx() as s:
            runs = s.execute(
                text("""
                    SELECT id, pipeline_id, confidence_score, completed_at
                    FROM pipeline_runs
                    WHERE org_id = :org AND status = 'COMPLETED'
                    ORDER BY completed_at DESC
                    LIMIT :limit
                """),
                {"org": org_id, "limit": ORG_CONTEXT_MAX_RUNS},
            ).fetchall()

            if not runs:
                return ""

            run_ids = [row[0] for row in runs]
            placeholders = ", ".join(f":run{i}" for i in range(len(run_ids)))
            params = {f"run{i}": rid for i, rid in enumerate(run_ids)}
            outputs = s.execute(
                text(f"""
                    SELECT run_id, analysis_type, response_text
                    FROM pipeline_llm_outputs
                    WHERE run_id IN ({placeholders})
                    ORDER BY created_at DESC
                """),
                params,
            ).fetchall()

        lines = ["## This organisation's recent pipeline results (most recent first)"]
        for run_id, pipeline_id, confidence_score, completed_at in runs:
            conf = f"{confidence_score:.2f}" if confidence_score is not None else "n/a"
            lines.append(f"- Run {run_id} (pipeline {pipeline_id}, completed {completed_at}): confidence {conf}")

        for run_id, analysis_type, response_text in outputs:
            snippet = (response_text or "")[:ORG_CONTEXT_RECOMMENDATION_CHARS]
            if snippet:
                lines.append(f"\n### {analysis_type} recommendation (run {run_id})\n{snippet}")

        return "\n".join(lines)

    except Exception as exc:
        logger.warning("Could not load org context for Co-Pilot (org=%s): %s", org_id, exc)
        return ""


# ── Celery task ───────────────────────────────────────────────────────────────



@celery_app.task(name="pipeline.copilot.stream_response", bind=True, max_retries=1)
def stream_copilot_response(
    self,
    run_id: str,
    user_id: int,
    org_id: int,
    session_id: str,
    message: str,
    history: List[dict],
):
    """
    Celery task: call Anthropic streaming API, write chunks to Redis.
    The SSE endpoint polls Redis and forwards chunks to the browser.
    """
    r = _get_redis()
    stream_key = _stream_key(user_id, run_id)
    done_key = _stream_done_key(user_id, run_id)

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        # Build messages: history + new user message
        messages = history + [{"role": "user", "content": message}]

        # FIX: org_id was accepted as a parameter and never used again - no org
        # data ever reached the Claude call despite the docstring/system prompt
        # claiming it was "injected automatically". Scoped strictly by this
        # org_id (the caller's own organisation_id), so this cannot leak
        # another org's data.
        org_context = _load_org_context(org_id)
        system_prompt = f"{SYSTEM_PROMPT}\n\n{org_context}" if org_context else SYSTEM_PROMPT

        full_response = ""

        with client.messages.stream(
            model=COPILOT_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text_chunk in stream.text_stream:
                full_response += text_chunk
                # Push each chunk to Redis list
                r.rpush(stream_key, json.dumps({"type": "token", "text": text_chunk}))
                r.expire(stream_key, STREAM_TOKEN_TTL)

        # Save updated history
        updated_history = messages + [{"role": "assistant", "content": full_response}]
        _save_session_history(user_id, session_id, updated_history)

        # Signal stream completion
        r.set(done_key, "1", ex=STREAM_TOKEN_TTL)
        r.rpush(stream_key, json.dumps({"type": "done", "text": ""}))
        r.expire(stream_key, STREAM_TOKEN_TTL)

        logger.info("Co-Pilot stream complete: run=%s tokens=%d", run_id, len(full_response))

    except anthropic.AuthenticationError:
        r.rpush(stream_key, json.dumps({
            "type": "error",
            "text": "AI service authentication failed. Contact your administrator.",
        }))
        r.set(done_key, "error", ex=STREAM_TOKEN_TTL)

    except Exception as exc:
        logger.error("Co-Pilot stream error: run=%s error=%s", run_id, exc)
        r.rpush(stream_key, json.dumps({
            "type": "error",
            "text": "An error occurred generating the response. Please try again.",
        }))
        r.set(done_key, "error", ex=STREAM_TOKEN_TTL)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/message",
    response_model=CopilotMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a Co-Pilot message - returns stream ID immediately",
)
def send_copilot_message(
    body: CopilotMessageRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Accepts a user message, queues the Celery streaming task,
    and returns a run_id the client uses to open the SSE stream.
    """
    # Sanitise input
    clean_message = _sanitise(body.message)
    if not clean_message:
        raise HTTPException(status_code=400, detail="Message is empty after sanitisation.")

    # Session management
    session_id = body.session_id or str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    # Load conversation history
    history = _load_session_history(current_user.id, session_id)

    # Enqueue streaming task
    stream_copilot_response.apply_async(
        args=[
            run_id,
            current_user.id,
            current_user.organisation_id,
            session_id,
            clean_message,
            history,
        ],
        task_id=run_id,
    )

    logger.info(
        "Co-Pilot message queued: user=%s session=%s run=%s",
        current_user.id, session_id, run_id,
    )

    return CopilotMessageResponse(
        run_id=run_id,
        session_id=session_id,
    )


@router.get(
    "/stream/{run_id}",
    summary="SSE stream - Co-Pilot token-by-token response",
    response_class=StreamingResponse,
)
def stream_copilot(
    run_id: str,
    current_user: User = Depends(get_current_user_sse),
):
    """
    SSE endpoint - polls Redis for tokens written by the Celery task
    and streams them to the browser one chunk at a time.
    """
    return StreamingResponse(
        _copilot_sse_generator(run_id, current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _copilot_sse_generator(
    run_id: str,
    user_id: int,
) -> AsyncGenerator[str, None]:
    """
    Async generator: reads token chunks from Redis list and yields SSE events.
    Exits when a 'done' or 'error' chunk is encountered, or after timeout.
    """
    r = _get_redis()
    stream_key = _stream_key(user_id, run_id)
    cursor = 0
    max_wait = 120       # seconds before giving up
    elapsed = 0.0
    poll_interval = 0.1  # 100ms polling - fast enough for smooth token streaming

    # Send connected event
    yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"

    try:
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # Read new items from Redis list since last cursor
            try:
                items = r.lrange(stream_key, cursor, -1)
            except Exception:
                items = []

            for item in items:
                cursor += 1
                try:
                    chunk = json.loads(item)
                except json.JSONDecodeError:
                    continue

                yield f"data: {json.dumps(chunk)}\n\n"

                if chunk.get("type") in ("done", "error"):
                    return

            # Keep-alive comment every 15s
            if int(elapsed / poll_interval) % int(15 / poll_interval) == 0 and elapsed > 0:
                yield ": keep-alive\n\n"

        # Timeout
        yield f"data: {json.dumps({'type': 'error', 'text': 'Response timed out.'})}\n\n"

    except asyncio.CancelledError:
        logger.info("Co-Pilot SSE client disconnected: run=%s", run_id)
        return


def _scan(r, pattern: str) -> List[str]:
    """SCAN, never KEYS. KEYS blocks the entire Redis server for the duration."""
    return list(r.scan_iter(match=pattern, count=100))


def _purge_user_copilot_data(r, user_id: int) -> int:
    """Delete every Co-Pilot Redis key belonging to one user.

    Covers all three shapes, not just conversation history: an erasure that left
    the token stream behind would leave the model's full response text readable.
    """
    keys: List[str] = []
    for pattern in (
        f"copilot:{user_id}:session:*",
        f"copilot:{user_id}:*:stream",
        f"copilot:{user_id}:*:done",
    ):
        keys.extend(_scan(r, pattern))
    return r.delete(*keys) if keys else 0


@router.get(
    "/sessions",
    summary="List conversation sessions for current user",
)
def list_sessions(
    current_user: User = Depends(get_current_user),
):
    """
    Returns a list of active session IDs for the current user.
    Sessions live in Redis and expire after SESSION_HISTORY_TTL (24h).
    """
    try:
        r = _get_redis()
        keys = _scan(r, f"copilot:{current_user.id}:session:*")
        session_ids = [k.split(":")[-1] for k in keys]
        return {"sessions": session_ids, "count": len(session_ids)}
    except Exception as exc:
        logger.warning("Could not list copilot sessions: %s", exc)
        return {"sessions": [], "count": 0}


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear one conversation session",
    responses={502: {"description": "Cache unavailable; nothing was deleted"}},
)
def clear_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete conversation history for a single session of the current user.

    A failure is surfaced, not swallowed. This previously logged a warning and
    returned 204 regardless, so a Redis outage looked identical to a successful
    deletion. For anything on a deletion path that is the one outcome that must
    never be silent.
    """
    try:
        _get_redis().delete(_session_key(current_user.id, session_id))
    except Exception as exc:
        logger.error("Could not clear copilot session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Conversation store unavailable. Nothing was deleted; please retry.",
        )


# ── GDPR erasure for Co-Pilot data (issue #12) ───────────────────────────────
# The per-run erasure endpoint (DELETE /pipelines/runs/{id}/files) cannot reach
# Co-Pilot history: its keys are scoped by SESSION while that endpoint is scoped
# by RUN, so there is no way to tell which sessions relate to an erased run.
#
# Decisions taken 2026-08-07, recorded here because the issue asked for them:
#
#   1. Erasure unit: USER and ORGANISATION, not session. Session-level clearing
#      already exists above and is a UX control, not an erasure control. The two
#      requests that actually arrive are "this customer is leaving, delete their
#      data" (org) and "this individual is exercising their rights" (user).
#   2. Who can invoke: a user may always erase their own. ADMIN may erase any
#      user in their own organisation, or the whole organisation. SUPER_ADMIN
#      may do either for any organisation. This mirrors the RBAC already used by
#      the per-run erasure endpoint.
#   3. DB-side history: there is none. Co-Pilot conversations exist only in
#      Redis; there is no ORM model for them in either Base. Verified before
#      building, so there is nothing further to clear.
#   4. TTL: 24h stands. It matches the Celery result backend's result_expires.
#      Shorter would drop a user's context within a single working day.


@router.delete(
    "/sessions",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Erase all of the current user's own Co-Pilot data",
    responses={502: {"description": "Cache unavailable; nothing was deleted"}},
)
def erase_own_copilot_data(
    current_user: User = Depends(get_current_user),
):
    """Self-service erasure. Any authenticated user, no admin needed."""
    try:
        deleted = _purge_user_copilot_data(_get_redis(), current_user.id)
    except Exception as exc:
        logger.error("Co-Pilot self-erasure failed for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=502,
            detail="Conversation store unavailable. Nothing was deleted; please retry.",
        )
    logger.info("Co-Pilot erasure: user=%s keys=%d (self)", current_user.id, deleted)


@router.delete(
    "/erasure/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Erase one user's Co-Pilot data (Admin+)",
    dependencies=[Depends(require_role("admin"))],
    responses={404: {"description": "User not found in your organisation"},
               502: {"description": "Cache unavailable; nothing was deleted"}},
)
def erase_user_copilot_data(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    role = getattr(current_user.role, "value", current_user.role)
    # 404 rather than 403 for a cross-tenant target: matches the existing
    # multi-tenant rule that another org's resources do not exist to you.
    if target is None or (
        role != "super_admin" and target.organisation_id != current_user.organisation_id
    ):
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        deleted = _purge_user_copilot_data(_get_redis(), user_id)
    except Exception as exc:
        logger.error("Co-Pilot erasure failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Conversation store unavailable. Nothing was deleted; please retry.",
        )
    logger.info(
        "Co-Pilot erasure: user=%s keys=%d by_user=%s", user_id, deleted, current_user.id
    )


@router.delete(
    "/erasure/organisations/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Erase a whole organisation's Co-Pilot data (Admin+)",
    dependencies=[Depends(require_role("admin"))],
    responses={404: {"description": "Organisation not found"},
               502: {"description": "Cache unavailable; nothing was deleted"}},
)
def erase_org_copilot_data(
    org_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = getattr(current_user.role, "value", current_user.role)
    if role != "super_admin" and org_id != current_user.organisation_id:
        raise HTTPException(status_code=404, detail="Organisation not found.")

    # Resolve members from the database rather than by scanning Redis: a key
    # only exists for users who have actually used the Co-Pilot, so scanning
    # would silently skip anyone whose data had not yet been written.
    user_ids = list(
        db.execute(select(User.id).where(User.organisation_id == org_id)).scalars()
    )

    try:
        r = _get_redis()
        deleted = sum(_purge_user_copilot_data(r, uid) for uid in user_ids)
    except Exception as exc:
        logger.error("Co-Pilot erasure failed for org %s: %s", org_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Conversation store unavailable. Nothing was deleted; please retry.",
        )
    logger.info(
        "Co-Pilot erasure: org=%s users=%d keys=%d by_user=%s",
        org_id, len(user_ids), deleted, current_user.id,
    )
