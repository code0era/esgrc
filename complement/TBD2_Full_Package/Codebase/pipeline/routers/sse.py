"""
pipeline/routers/sse.py
SSE generator for GET /pipelines/runs/{run_id}/stream

Polls Redis every second for step state changes.
Yields JSON events as text/event-stream.
Closes on COMPLETED / FAILED / CANCELLED or client disconnect.
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from pipeline.modules import step_counts
from pipeline.tasks.shared import get_run_status, get_step_state

logger = logging.getLogger(__name__)

# How many steps each pipeline type has. Derived from the module registry so a
# new module never needs an edit here - see pipeline/modules.py.
PIPELINE_STEP_COUNTS = step_counts()
POLL_INTERVAL = 1.0          # seconds between Redis polls
MAX_POLL_SECONDS = 7200      # 2 hours - hard timeout


async def pipeline_event_generator(
    run_id: str,
    pipeline_type: str,
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams SSE events for a pipeline run.

    Event format (text/event-stream):
        data: {"event": "step_completed", "step": 3, ...}\n\n

    Terminal events:
        run_completed, run_failed, run_cancelled

    The generator exits cleanly on GeneratorExit (client disconnect).
    """
    total_steps = PIPELINE_STEP_COUNTS.get(pipeline_type, 8)
    emitted: set[str] = set()   # track which (step, status) keys we've already sent
    elapsed = 0.0

    # Send a heartbeat immediately so the client knows the stream is alive
    yield _fmt({"event": "connected", "run_id": run_id, "total_steps": total_steps})

    try:
        while elapsed < MAX_POLL_SECONDS:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            # ── Check run-level status first ─────────────────────────────
            run_status = get_run_status(run_id)

            # ── Emit any new step events ──────────────────────────────────
            for step in range(1, total_steps + 1):
                state = get_step_state(run_id, step)
                if not state:
                    continue

                event_key = f"{step}:{state['status']}"
                if event_key in emitted:
                    continue

                emitted.add(event_key)
                pct = _pct(step, total_steps, state["status"])

                event_payload: dict = {
                    "event": f"step_{state['status'].lower()}",
                    "step": step,
                    "step_name": state.get("step_name", ""),
                    "status": state["status"],
                    "pct": pct,
                }

                if state["status"] == "COMPLETED":
                    event_payload["outputs"] = state.get("outputs", [])
                    event_payload["duration_ms"] = state.get("duration_ms")

                if state["status"] == "FAILED":
                    event_payload["error"] = state.get("error", "Unknown error")

                yield _fmt(event_payload)

            # ── Terminal run states ───────────────────────────────────────
            if run_status in ("COMPLETED", "FAILED", "CANCELLED"):
                terminal = {
                    "event": f"run_{run_status.lower()}",
                    "status": run_status,
                    "message": _terminal_message(run_status),
                }
                yield _fmt(terminal)
                logger.info("SSE stream closed for run %s - %s", run_id, run_status)
                return

            # ── Keep-alive comment every 30s (prevents proxy timeouts) ───
            if int(elapsed) % 30 == 0:
                yield ": keep-alive\n\n"

        # Timeout reached
        yield _fmt({
            "event": "timeout",
            "message": "Stream timed out after 2 hours. Check run status via API.",
        })

    except asyncio.CancelledError:
        # Client disconnected - exit cleanly
        logger.info("SSE client disconnected for run %s", run_id)
        return


def _fmt(payload: dict) -> str:
    """Format a dict as a valid SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _pct(step: int, total: int, status: str) -> int:
    """Calculate progress percentage for a step event."""
    if status in ("COMPLETED", "SKIPPED", "FAILED"):
        return int((step / total) * 100)
    if status == "RUNNING":
        return int(((step - 1) / total) * 100)
    return 0


def _terminal_message(status: str) -> str:
    messages = {
        "COMPLETED": "Pipeline completed successfully.",
        "FAILED": "Pipeline failed. Check step details for the error.",
        "CANCELLED": "Pipeline was cancelled by an administrator.",
    }
    return messages.get(status, status)
