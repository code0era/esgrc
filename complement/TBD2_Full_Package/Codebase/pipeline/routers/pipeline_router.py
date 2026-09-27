"""
pipeline/routers/pipeline_router.py
All 15 pipeline FastAPI endpoints.

Mounted in ESGRC main.py with:
    app.include_router(pipeline_router, prefix="/pipelines", tags=["Pipeline"])

Auth uses the existing ESGRC get_current_user / require_role dependencies.

CHANGES FROM ORIGINAL (June 2026 audit):
1. _enqueue_pipeline() wrapped in try/except - if apply_async() raises
   (broker unreachable, serialization error, etc.) the run row is marked
   FAILED with a clear error message instead of left as a zombie PENDING
   row with no chord_id and no error. This satisfies Section 7.3 extreme-
   scenario requirements without touching commit ordering, which is already
   correct per Celery 5.6.3 official docs (commit before dispatch).
2. list_runs() total count fixed - replaced full-row fetch with a
   select(func.count()) so counting rows does not load every column of
   every run into memory.
3. Dead import removed - get_user_by_id was imported but never used.
4. update_prompt() Super Admin check clarified - the manual
   `if current_user.role.value != "admin"` was a redundant re-check of
   the dependency that was already enforcing "admin". Left as-is pending
   confirmation of whether a distinct "super_admin" role exists in the
   ESGRC User.role enum (open item - not assumed either way).

COMMIT ORDERING - NOT CHANGED:
Per Celery 5.6.3 official documentation (celeryq.dev/userguide/tasks.html,
confirmed live June 2026): "ensure that the transaction is committed before
triggering the task." The run row (status=PENDING) is committed before
apply_async(). delay_on_commit() is Django-only and does not return the
task ID - inapplicable here. The existing ordering is correct.
"""
import importlib
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import (
    get_current_user,
    get_current_user_sse,
    require_role,
    require_module,
    allowed_pipeline_types,
)
from app.models.models import User

from pipeline.db import get_pipeline_db
from pipeline.middleware import limiter, rate_limit_trigger

# Upload ceiling for /upload-input. The real inputs are small - the largest
# module's input_metric_values CSV is around 1 MB - so 100 MB is generous
# headroom while still bounding what a single request can consume. Override with
# MAX_UPLOAD_MB.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024

from pipeline.modules import module_for_pipeline_type, step_counts
from pipeline.models import (
    PipelineDefinition,
    PipelineLLMOutput,
    PipelineRun,
    PipelineStepResult,
    RunStatusEnum,
    StepStatusEnum,
)
from pipeline.routers.sse import pipeline_event_generator
from pipeline.llm.labeling import label_output
from pipeline.schemas import (
    EmergencyStopRequest,
    EmergencyStopResponse,
    HandoffProvenanceItem,
    InputFilesStatus,
    LabelItem,
    LLMOutputOut,
    PipelineDefinitionOut,
    PipelineRunListOut,
    PipelineRunOut,
    PipelineRunSummary,
    ProcessLogEntry,
    PromptHistoryOut,
    PromptOut,
    PromptUpdate,
    RollbackResponse,
    StepRerunResponse,
    TriggerRequest,
    TriggerResponse,
    UploadedFileInfo,
)
from pipeline.tasks.r2 import (
    R2Error,
    file_exists,
    get_apex_handoff_provenance,
    reference_key,
    upload_file,
)
from pipeline.tasks.shared import mark_run_failed

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_pipeline_or_404(
    pipeline_id: str,
    org_id: int,
    db: Session,
    user=None,
) -> PipelineDefinition:
    pipeline = db.execute(
        select(PipelineDefinition).where(
            PipelineDefinition.id == pipeline_id,
            PipelineDefinition.org_id == org_id,
        )
    ).scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found.")
    # Module scope: a user may only touch pipelines in a module they can access.
    # Return 404 (not 403) so a scoped user can't even probe another module's ids.
    if user is not None:
        allowed = allowed_pipeline_types(user)
        if allowed is not None and _pipeline_type_value(pipeline) not in allowed:
            raise HTTPException(status_code=404, detail="Pipeline not found.")
    return pipeline


def _pipeline_type_value(pipeline: PipelineDefinition) -> str:
    """Normalise pipeline_type to its string value (it may be an enum)."""
    pt = pipeline.pipeline_type
    return getattr(pt, "value", pt)


def _enforce_run_module_scope(run: PipelineRun, user, db: Session) -> None:
    """
    Module scope for run-level access: a run belongs to a pipeline of some type,
    and a module-scoped user may only touch runs whose pipeline type is in their
    allowed set. Raise 404 (not 403) so a scoped user can't even probe another
    module's run ids. No-op for SUPER_ADMIN (allowed is None) or when user is None.
    """
    if user is None:
        return
    allowed = allowed_pipeline_types(user)
    if allowed is None:
        return
    pipeline = db.execute(
        select(PipelineDefinition).where(PipelineDefinition.id == run.pipeline_id)
    ).scalar_one_or_none()
    if pipeline is None or _pipeline_type_value(pipeline) not in allowed:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")


def _get_run_or_404(run_id: str, org_id: int, db: Session, user=None) -> PipelineRun:
    run = db.execute(
        select(PipelineRun).where(
            PipelineRun.id == run_id,
            PipelineRun.org_id == org_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")
    _enforce_run_module_scope(run, user, db)
    return run


# ─────────────────────────────────────────────────────────────────────────────
# 49 - List pipeline definitions
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=List[PipelineDefinitionOut],
    summary="List pipeline definitions for the caller's org",
)
def list_pipelines(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    query = (
        select(PipelineDefinition)
        .where(PipelineDefinition.org_id == current_user.organisation_id)
        .order_by(PipelineDefinition.created_at)
    )
    # Module scope: show only pipelines whose type is in a module the caller can
    # access. allowed is None for SUPER_ADMIN → no filter (sees everything).
    allowed = allowed_pipeline_types(current_user)
    if allowed is not None:
        query = query.where(PipelineDefinition.pipeline_type.in_(allowed))
    pipelines = db.execute(query).scalars().all()
    return pipelines


# ─────────────────────────────────────────────────────────────────────────────
# 61-63 - Prompt management
#
# NOTE: these static "/prompts" routes MUST be declared before the "/{pipeline_id}"
# catch-all below. FastAPI matches routes in definition order, so if "/{pipeline_id}"
# comes first it captures GET /prompts as pipeline_id="prompts" and returns 404
# (which silently breaks the Settings → Prompts tab). Do not move these back down.
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/prompts",
    response_model=List[PromptOut],
    summary="List active pipeline prompts (Admin+)",
    dependencies=[Depends(require_role("admin"))],
)
def list_prompts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    from pipeline.prompt_models import PipelinePrompt
    prompts = db.execute(
        select(PipelinePrompt).where(PipelinePrompt.is_active == True)  # noqa: E712
        .order_by(PipelinePrompt.name)
    ).scalars().all()
    return prompts


@router.put(
    "/prompts/{prompt_id}",
    response_model=PromptOut,
    summary="Update a prompt - creates new version (Super Admin only)",
    dependencies=[Depends(require_role("super_admin"))],
)
def update_prompt(
    prompt_id: int,
    body: PromptUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    from pipeline.prompt_models import PipelinePrompt

    # The template must carry the {report_text} placeholder, or LLMClient.analyze's
    # .replace() silently no-ops and the report never reaches Claude.
    if "{report_text}" not in body.content:
        raise HTTPException(
            status_code=422,
            detail="Prompt content must contain the {report_text} placeholder.",
        )

    old = db.execute(
        select(PipelinePrompt).where(PipelinePrompt.id == prompt_id)
    ).scalar_one_or_none()

    if not old:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    # Deactivate whichever version is currently active for this name (may differ
    # from `old` when restoring an older version), and compute the next version
    # from the max so we never collide with uq_prompt_name_version.
    db.execute(
        update(PipelinePrompt)
        .where(PipelinePrompt.name == old.name, PipelinePrompt.is_active.is_(True))
        .values(is_active=False)
    )
    next_version = db.execute(
        select(func.max(PipelinePrompt.version)).where(PipelinePrompt.name == old.name)
    ).scalar_one() + 1

    new_prompt = PipelinePrompt(
        name=old.name,
        version=next_version,
        content=body.content,
        is_active=True,
    )
    db.add(new_prompt)
    db.commit()
    db.refresh(new_prompt)
    return new_prompt


@router.get(
    "/prompts/{prompt_id}/history",
    response_model=List[PromptHistoryOut],
    summary="All historical versions of a prompt (Admin+)",
    dependencies=[Depends(require_role("admin"))],
)
def prompt_history(
    prompt_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    from pipeline.prompt_models import PipelinePrompt

    prompt = db.execute(
        select(PipelinePrompt).where(PipelinePrompt.id == prompt_id)
    ).scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    history = db.execute(
        select(PipelinePrompt)
        .where(PipelinePrompt.name == prompt.name)
        .order_by(PipelinePrompt.version.desc())
    ).scalars().all()

    return history


# ─────────────────────────────────────────────────────────────────────────────
# Module handoff provenance (data-freshness for the UI badge)
# NOTE: static path - MUST be declared before the "/{pipeline_id}" catch-all below,
# or FastAPI's in-order matching routes "/handoff-provenance" into get_pipeline.
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/handoff-provenance",
    response_model=List[HandoffProvenanceItem],
    summary="Per-module Apex handoff freshness (source run + produced-at timestamp)",
)
def get_handoff_provenance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    """Data source for the 'Data as of … · Run #…' badge. One entry per known
    module; present=False means that module has not produced a handoff yet."""
    return get_apex_handoff_provenance(str(current_user.organisation_id))


# ─────────────────────────────────────────────────────────────────────────────
# Process log - executed steps across runs (user · timestamp · step · pass/fail)
# NOTE: static path - MUST stay before the "/{pipeline_id}" catch-all below.
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/process-log",
    response_model=List[ProcessLogEntry],
    summary="Executed pipeline steps across runs, as a chronological log",
)
def get_process_log(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    run_id: Optional[str] = Query(None, description="Filter to a single run"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
    app_db: Session = Depends(get_db),
):
    """
    Org-scoped log of every executed pipeline step, newest first.

    Per-run detail is already available on GET /pipelines/runs/{id}; this lists steps
    ACROSS runs and resolves the triggering user to a name/email so it reads as an
    audit log rather than raw ids.
    """
    q = (
        select(PipelineStepResult, PipelineRun)
        .join(PipelineRun, PipelineStepResult.run_id == PipelineRun.id)
        .where(PipelineRun.org_id == current_user.organisation_id)
    )
    # Module scoping: a module-scoped user (e.g. apex-only) must not see other
    # modules' step names / error_detail. Mirror list_pipelines' filter.
    allowed = allowed_pipeline_types(current_user)
    if allowed is not None:
        q = q.join(
            PipelineDefinition, PipelineRun.pipeline_id == PipelineDefinition.id
        ).where(PipelineDefinition.pipeline_type.in_(allowed))
    if run_id:
        q = q.where(PipelineRun.id == run_id)
    # Deterministic ordering: started_at is nullable and can tie, so add stable
    # tiebreakers or limit/offset paging can repeat/drop rows.
    q = q.order_by(
        PipelineStepResult.started_at.desc().nullslast(),
        PipelineStepResult.run_id,
        PipelineStepResult.step_number,
    ).limit(limit).offset(offset)

    rows = db.execute(q).all()

    # Resolve triggering users in ONE query (User lives in the ESGRC Base, hence the
    # separate session - see the cross-Base note in pipeline/models.py).
    # Best-effort: the log is the primary data, the name is enrichment. A failed
    # lookup (deleted user, unavailable session) must never break the log.
    user_ids = {run.triggered_by for _, run in rows if run.triggered_by is not None}
    users: dict[int, User] = {}
    if user_ids:
        try:
            for u in app_db.execute(select(User).where(User.id.in_(user_ids))).scalars().all():
                users[u.id] = u
        except Exception:
            logger.warning("process-log: could not resolve triggering users", exc_info=True)

    entries = []
    for step, run in rows:
        u = users.get(run.triggered_by) if run.triggered_by is not None else None
        entries.append(
            ProcessLogEntry(
                run_id=step.run_id,
                pipeline_id=run.pipeline_id,
                step_number=step.step_number,
                step_name=step.step_name,
                status=step.status,
                started_at=step.started_at,
                completed_at=step.completed_at,
                duration_ms=step.duration_ms,
                error_detail=step.error_detail,
                triggered_by=run.triggered_by,
                triggered_by_email=getattr(u, "email", None),
                triggered_by_name=getattr(u, "full_name", None),
            )
        )
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# 50 - Get one pipeline definition
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{pipeline_id}",
    response_model=PipelineDefinitionOut,
    summary="Get a pipeline definition",
)
def get_pipeline(
    pipeline_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    return _get_pipeline_or_404(pipeline_id, current_user.organisation_id, db, user=current_user)


# ─────────────────────────────────────────────────────────────────────────────
# 51 - Trigger a pipeline run
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{pipeline_id}/trigger",
    response_model=TriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a new pipeline run (Analyst+)",
    dependencies=[Depends(require_role("analyst"))],
    responses={429: {"description": "Rate limit exceeded"}},
)
@limiter.limit(rate_limit_trigger)
def trigger_pipeline(
    request: Request,          # required by slowapi's key function
    pipeline_id: str,
    body: TriggerRequest = TriggerRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    pipeline = _get_pipeline_or_404(pipeline_id, current_user.organisation_id, db, user=current_user)

    if not pipeline.is_active:
        raise HTTPException(status_code=400, detail="Pipeline is inactive.")

    # Validate required input files exist in R2
    config = pipeline.config_json or {}
    required_inputs: List[str] = config.get("required_input_files", [])
    org_id = current_user.organisation_id

    # input_file_overrides supplies raw R2 keys (see TriggerRequest's own
    # docstring: "Map of input_name -> R2 key"), and every chain task uses
    # them verbatim (esgrc_chain.py, _module_chain_factory.py) with no
    # org check of its own - each step trusts the router to have already
    # scoped them. Without this guard, any analyst+ on ANY org could point
    # an override at "org/<other_org_id>/reference/..." or
    # "org/<other_org_id>/module_outputs/..." and have that org's ESG/
    # compliance data read straight into their own run's output. Every
    # override must therefore live under the caller's own org prefix.
    org_prefix = f"org/{org_id}/"
    invalid_overrides = {
        name: key
        for name, key in (body.input_file_overrides or {}).items()
        if not key.startswith(org_prefix)
    }
    if invalid_overrides:
        raise HTTPException(
            status_code=400,
            detail=(
                "input_file_overrides must be R2 keys scoped to your own "
                f"organisation (expected keys under '{org_prefix}'): "
                f"{invalid_overrides}"
            ),
        )

    missing = []
    for r2_key in required_inputs:
        if not file_exists(r2_key.format(org_id=org_id)):
            missing.append(r2_key)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Required input files missing in R2: {missing}",
        )

    # Create the pipeline_run row via raw SQL - NOT db.add()/db.commit().
    # CONFIRMED via direct test: PipelineRun.org_id/triggered_by are FKs
    # into ESGRC's separate Base metadata. Any ORM INSERT flush triggers
    # SQLAlchemy's FK-dependency sort, which raises NoReferencedTableError
    # every time, regardless of whether the real tables exist in Postgres.
    # Matches the same raw-SQL pattern already used in shared.py.
    import uuid as _uuid
    from sqlalchemy import text as _text

    run_id = str(_uuid.uuid4())
    db.execute(
        _text("""
            INSERT INTO pipeline_runs
                (id, pipeline_id, org_id, triggered_by, status, is_current, progress_pct)
            VALUES
                (:id, :pipeline_id, :org_id, :triggered_by, 'PENDING', FALSE, 0)
        """),
        {
            "id": run_id,
            "pipeline_id": pipeline_id,
            "org_id": org_id,
            "triggered_by": current_user.id,
        },
    )

    # Pre-seed one PENDING pipeline_step_results row per step this pipeline
    # type will run. Without this, rows are created lazily by mark_step_running
    # only as each step actually starts - so mark_step_failed's own
    # "SKIP all subsequent PENDING steps" UPDATE (shared.py) had nothing to
    # act on: downstream steps that never got a chance to start simply had no
    # row at all instead of being marked SKIPPED, leaving the process-log/step
    # history silently incomplete on a failed run. This is deliberately NOT a
    # chord-level fix (attaching link_error to a chord's header group raises
    # "Cannot add link to group" in Celery - see the comments in
    # esgrc_chain.build_esgrc_chain / apex_chord.build_apex_pipeline /
    # _module_chain_factory.build_module_chain) - it just gives the
    # already-correct, already-tested SKIP query real rows to find.
    step_total = step_counts().get(_pipeline_type_value(pipeline), 7)
    for step_number in range(1, step_total + 1):
        db.execute(
            _text("""
                INSERT INTO pipeline_step_results (id, run_id, step_number, step_name, status)
                VALUES (:id, :run_id, :step_number, '', 'PENDING')
            """),
            {"id": str(_uuid.uuid4()), "run_id": run_id, "step_number": step_number},
        )

    db.commit()

    run = db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    ).scalar_one()

    # Dispatch to Celery. apply_async() is wrapped so a broker/serialization
    # failure marks the run FAILED immediately rather than leaving a zombie
    # PENDING row with no chord_id. Commit ordering is unchanged - run row
    # is fully committed before any dispatch attempt.
    try:
        import uuid as _uuid2
        chord_id = str(_uuid2.uuid4())
        db.execute(
            _text("UPDATE pipeline_runs SET celery_chord_id = :cid WHERE id = :rid"),
            {"cid": chord_id, "rid": run.id},
        )
        db.commit()
        _enqueue_pipeline(pipeline, run, body.input_file_overrides or {}, db, chord_id)
    except Exception as exc:
        # Dispatch failed after the run row was committed.
        # Mark the run FAILED so it doesn't sit silently as PENDING forever.
        # Uses the same mark_run_failed() helper the Celery tasks themselves
        # use (pipeline/tasks/shared.py) - raw-SQL write + Redis key, not a
        # second, divergent ORM-based failure path.
        error_msg = f"Celery dispatch failed: {type(exc).__name__}: {exc}"
        logger.exception("Pipeline dispatch failed for run %s: %s", run.id, error_msg)
        try:
            mark_run_failed(run.id, error_msg)
        except Exception:
            # If this also fails, log and give up - don't mask the
            # original exception. The run row may remain PENDING; this is
            # survivable since the worker will never pick it up.
            logger.exception(
                "Failed to mark run %s FAILED after dispatch error", run.id
            )
        raise HTTPException(
            status_code=503,
            detail="Pipeline could not be started - task broker unavailable. "
                   "The run has been marked FAILED.",
        )

    logger.info(
        "Pipeline %s triggered by user %s - run_id=%s chord_id=%s",
        pipeline_id, current_user.id, run.id, chord_id,
    )
    return TriggerResponse(run_id=run.id, status=RunStatusEnum.PENDING)


# ── Module chain resolution ──────────────────────────────────────────────────
# Every module chain exposes the same three names, keyed off its token:
#   build_{token}_chain   {token}_step7_claude   {TOKEN}_STEP_TASKS
# That convention holds for the hand-written ESGRC chain and for every
# factory-built one, so the router resolves them from pipeline/modules.py rather
# than carrying a hardcoded map and an elif ladder. Imports stay lazy (inside the
# functions) exactly as before, to keep celery task registration order unchanged.

def _module_chain_builder(pipeline_type: str):
    """(build_chain, step7_task) for a module pipeline type, or None for Apex."""
    spec = module_for_pipeline_type(pipeline_type)
    if spec is None:
        return None
    mod = importlib.import_module(spec.chain_module)
    return (
        getattr(mod, f"build_{spec.token}_chain"),
        getattr(mod, f"{spec.token}_step7_claude"),
    )


def _module_step_tasks(spec) -> dict:
    """{step_number: task} for a module, used by single-step re-runs."""
    mod = importlib.import_module(spec.chain_module)
    return getattr(mod, f"{spec.token.upper()}_STEP_TASKS")


def _enqueue_pipeline(
    pipeline: PipelineDefinition,
    run: PipelineRun,
    overrides: dict,
    db: Session,
    chord_id: str,
) -> str:
    """
    Dispatch to the correct Celery entry task. Returns the chord_id.

    task_id is set to the client-generated chord_id, but this is NOT what
    emergency_stop relies on for revocation: Signature.freeze() only assigns an
    id to a task that doesn't already have one, and every step in the chain/
    chord below is dispatched with its own preset id (`{run.id}_step{n}`, set
    via `.si(...).set(task_id=...)`) - so chord_id here lands on nothing for
    module chains, or the finalize callback for Apex, never step 1. It's kept
    for the ORM column and a defence-in-depth revoke call; emergency_stop
    revokes every step's deterministic id directly, which needs no fixed-up
    relationship to chord_id to work.

    Does NOT set run.celery_chord_id directly - that ORM attribute mutation
    plus a later db.commit() would flush pipeline_runs through the unit-of-
    work, which crashes with NoReferencedTableError exactly like the INSERT
    did (same table, same FK columns, flush-plan sorting applies to UPDATE
    too, not just INSERT). Caller already persisted chord_id via raw SQL
    before calling this function.

    Raises on any Celery/broker error - caller wraps in try/except.
    """
    from pipeline.tasks.apex_chord import build_apex_pipeline

    # Module chains share one shape: build_chain(...) | step7. Apex is the odd one
    # out (its own builder already includes finalize), hence the else branch.
    # Resolved from the module registry, so a new module needs no edit here.
    builder = _module_chain_builder(pipeline.pipeline_type.value)
    if builder is not None:
        build_fn, step7_task = builder
        chain = build_fn(run.id, str(pipeline.org_id), overrides)
        full_chain = chain | step7_task.si(
            run.id, str(pipeline.org_id), overrides
        ).set(task_id=f"{run.id}_step7")
        result = full_chain.apply_async(task_id=chord_id)
    else:
        result = build_apex_pipeline(
            run.id, str(pipeline.org_id), overrides
        ).apply_async(task_id=chord_id)

    return result.id

# ─────────────────────────────────────────────────────────────────────────────
# 52 - Emergency stop
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/emergency-stop",
    response_model=EmergencyStopResponse,
    summary="Kill all Celery tasks for a run (Admin only)",
    dependencies=[Depends(require_role("admin"))],
)
def emergency_stop(
    body: EmergencyStopRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    run = _get_run_or_404(body.run_id, current_user.organisation_id, db, current_user)

    if run.status in (RunStatusEnum.COMPLETED, RunStatusEnum.CANCELLED, RunStatusEnum.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Run is already in terminal state: {run.status.value}",
        )

    pipeline = db.execute(
        select(PipelineDefinition).where(PipelineDefinition.id == run.pipeline_id)
    ).scalar_one()
    total_steps = step_counts()[_pipeline_type_value(pipeline)]

    from pipeline.celery_app import app as celery_app
    from sqlalchemy import text as _text

    # Every step is dispatched with a deterministic task_id (`{run_id}_step{n}`,
    # see _enqueue_pipeline / build_apex_pipeline) - true from the moment the
    # run is created, regardless of whether the step has actually started. So
    # revoke every step number up front instead of only the steps that already
    # have a pipeline_step_results row (those rows are created lazily by
    # mark_step_running): a run cancelled before step 1 even starts has ZERO
    # rows, which meant the old row-driven loop revoked nothing for it - the
    # worker ran the full pipeline (including real Claude spend) once it came
    # back online, and the cancellation just vanished.
    #
    # run.celery_chord_id is also revoked below for defence-in-depth, but it
    # does NOT reliably identify a real task: Signature.freeze() only assigns
    # an id if a task doesn't already have one, and every step here already
    # carries a preset id, so in practice chord_id lands on nothing (module
    # chains) or the finalize callback (Apex) - never step 1. It is not a
    # substitute for the per-step loop, and no longer a precondition for
    # cancelling (a run can be stopped before chord_id is even persisted).
    if run.celery_chord_id:
        celery_app.control.revoke(run.celery_chord_id, terminate=True, signal="SIGTERM")
    for step_number in range(1, total_steps + 1):
        celery_app.control.revoke(
            f"{run.id}_step{step_number}", terminate=True, signal="SIGTERM"
        )

    db.execute(
        _text("UPDATE pipeline_runs SET status = 'CANCELLED' WHERE id = :rid"),
        {"rid": run.id},
    )
    db.commit()

    from pipeline.tasks.shared import _get_redis, _redis_run_key, REDIS_TTL
    _get_redis().set(_redis_run_key(body.run_id), "CANCELLED", ex=REDIS_TTL)

    return EmergencyStopResponse(
        run_id=body.run_id,
        message="Celery tasks revoked. Run marked CANCELLED.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 53 - List runs for a pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{pipeline_id}/runs",
    response_model=PipelineRunListOut,
    summary="Paginated run history for a pipeline",
)
def list_runs(
    pipeline_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    _get_pipeline_or_404(pipeline_id, current_user.organisation_id, db, user=current_user)

    # org_id is also included here, even though pipeline_id alone already
    # narrows to one org (it's a globally-unique UUID PK, and _get_pipeline_or_404
    # above already 404s if it isn't this org's) - every other run query in this
    # router filters by org_id explicitly (get_run, rollback_run, ...) and this
    # was the one exception. Matching that pattern is defense-in-depth: it keeps
    # this query correct even if pipeline_id's uniqueness assumption ever changes.
    total = db.execute(
        select(func.count()).select_from(PipelineRun)
        .where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.org_id == current_user.organisation_id,
        )
    ).scalar_one()

    runs = db.execute(
        select(PipelineRun)
        .where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.org_id == current_user.organisation_id,
        )
        .order_by(PipelineRun.started_at.desc().nullslast())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).scalars().all()

    return PipelineRunListOut(
        total=total,
        page=page,
        page_size=page_size,
        items=[PipelineRunSummary.model_validate(r) for r in runs],
    )


# ─────────────────────────────────────────────────────────────────────────────
# 54 - Get full run detail
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}",
    response_model=PipelineRunOut,
    summary="Full run detail with step results and LLM output summaries",
)
def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    run = _get_run_or_404(run_id, current_user.organisation_id, db, current_user)
    return run


# ─────────────────────────────────────────────────────────────────────────────
# 55 - SSE stream
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}/stream",
    summary="SSE stream - live step events for a pipeline run",
    response_class=StreamingResponse,
)
def stream_run(
    run_id: str,
    current_user: User = Depends(get_current_user_sse),
    db: Session = Depends(get_pipeline_db),
):
    run = _get_run_or_404(run_id, current_user.organisation_id, db, current_user)

    pipeline = db.execute(
        select(PipelineDefinition).where(PipelineDefinition.id == run.pipeline_id)
    ).scalar_one()

    return StreamingResponse(
        pipeline_event_generator(
            run_id=run_id,
            pipeline_type=pipeline.pipeline_type.value,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 56 - Rollback
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/runs/{run_id}/rollback",
    response_model=RollbackResponse,
    summary="Roll back to this run (Admin only)",
    dependencies=[Depends(require_role("admin"))],
)
def rollback_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    target_run = _get_run_or_404(run_id, current_user.organisation_id, db, current_user)

    if target_run.status != RunStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Target run must be in COMPLETED status to roll back to it.",
        )

    current_run = db.execute(
        select(PipelineRun).where(
            PipelineRun.pipeline_id == target_run.pipeline_id,
            PipelineRun.org_id == current_user.organisation_id,
            PipelineRun.is_current == True,  # noqa: E712
        )
    ).scalar_one_or_none()

    if current_run is None:
        raise HTTPException(status_code=400, detail="No previous run to rollback to.")

    if current_run.id == target_run.id:
        raise HTTPException(status_code=400, detail="Target run is already current.")

    db.execute(
        update(PipelineRun)
        .where(
            PipelineRun.pipeline_id == target_run.pipeline_id,
            PipelineRun.org_id == current_user.organisation_id,
        )
        .values(is_current=False)
    )
    db.execute(
        update(PipelineRun)
        .where(PipelineRun.id == target_run.id)
        .values(is_current=True)
    )
    db.commit()

    logger.info(
        "Rollback: org=%s pipeline=%s %s → %s",
        current_user.organisation_id, target_run.pipeline_id,
        current_run.id, target_run.id,
    )

    return RollbackResponse(
        previous_run_id=current_run.id,
        current_run_id=target_run.id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 57 - Step re-run
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/runs/{run_id}/steps/{step_number}/rerun",
    response_model=StepRerunResponse,
    summary="Re-run a single step (Analyst+)",
    dependencies=[Depends(require_role("analyst"))],
)
def rerun_step(
    run_id: str,
    step_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    run = _get_run_or_404(run_id, current_user.organisation_id, db, current_user)

    if run.status == RunStatusEnum.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot re-run a step while the pipeline is running.",
        )

    if step_number > 1:
        prereqs = db.execute(
            select(PipelineStepResult).where(
                PipelineStepResult.run_id == run_id,
                PipelineStepResult.step_number < step_number,
            )
        ).scalars().all()

        not_done = [
            s.step_number for s in prereqs
            if s.status != StepStatusEnum.COMPLETED
        ]
        if not_done:
            raise HTTPException(
                status_code=400,
                detail=f"Prerequisite steps not completed: {not_done}",
            )

    step_result = db.execute(
        select(PipelineStepResult).where(
            PipelineStepResult.run_id == run_id,
            PipelineStepResult.step_number == step_number,
        )
    ).scalar_one_or_none()

    if step_result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Step {step_number} not found for this run.",
        )

    step_result.status = StepStatusEnum.PENDING
    step_result.error_detail = None
    step_result.completed_at = None
    db.commit()

    pipeline = db.execute(
        select(PipelineDefinition).where(PipelineDefinition.id == run.pipeline_id)
    ).scalar_one()

    _enqueue_single_step(
        pipeline_type=pipeline.pipeline_type.value,
        run_id=run_id,
        org_id=str(current_user.organisation_id),
        step_number=step_number,
    )

    return StepRerunResponse(
        run_id=run_id,
        step_number=step_number,
        step_result_id=step_result.id,
        status=StepStatusEnum.PENDING,
    )


def _enqueue_single_step(
    pipeline_type: str,
    run_id: str,
    org_id: str,
    step_number: int,
) -> None:
    spec = module_for_pipeline_type(pipeline_type)
    if spec is not None:
        task_fn = _module_step_tasks(spec).get(step_number)
    else:
        from pipeline.tasks.apex_chord import APEX_STEP_TASKS
        task_fn = APEX_STEP_TASKS.get(step_number)

    if task_fn is None:
        raise HTTPException(status_code=400, detail=f"No task registered for step {step_number}.")

    # Every step task requires a third positional `overrides` dict (input-key
    # overrides). A single-step re-run uses the defaults, so pass an empty dict -
    # without it the worker raises TypeError: missing 'overrides' and the step
    # never runs (the endpoint would still return 200/PENDING to the caller).
    task_fn.apply_async(args=[run_id, org_id, {}])


# ─────────────────────────────────────────────────────────────────────────────
# Contextual-labeling enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _labeled_output(orm_output: PipelineLLMOutput) -> LLMOutputOut:
    """
    Build the served LLMOutputOut from an ORM row, adding the contextual-labeling
    view (business names substituted for codes) at serve time.

    response_text is returned untouched (codes = source of truth). Labelling is
    fail-safe: any error leaves response_text_labeled == response_text with
    labeling_status="failed", so the report is always served.
    """
    out = LLMOutputOut.model_validate(orm_output)
    try:
        result = label_output(orm_output.response_text)
        out.response_text_labeled = result.labeled_text
        out.labels = [LabelItem(**item) for item in result.labels]
        out.labeling_status = result.status
    except Exception:  # pragma: no cover - never let labelling break the endpoint
        logging.getLogger(__name__).exception("labeling failed for output %s", orm_output.id)
        out.response_text_labeled = orm_output.response_text
        out.labeling_status = "failed"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 58 - All Claude outputs for a run
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}/recommendations",
    response_model=List[LLMOutputOut],
    summary="All Claude LLM outputs for a run",
)
def get_recommendations(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    _get_run_or_404(run_id, current_user.organisation_id, db, current_user)

    outputs = db.execute(
        select(PipelineLLMOutput)
        .where(PipelineLLMOutput.run_id == run_id)
        .order_by(PipelineLLMOutput.created_at)
    ).scalars().all()

    return [_labeled_output(o) for o in outputs]


# ─────────────────────────────────────────────────────────────────────────────
# 59 - Single LLM output
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/llm-outputs/{output_id}",
    response_model=LLMOutputOut,
    summary="Get a single Claude output with full response text",
)
def get_llm_output(
    output_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    output = db.execute(
        select(PipelineLLMOutput).where(PipelineLLMOutput.id == output_id)
    ).scalar_one_or_none()

    if not output:
        raise HTTPException(status_code=404, detail="LLM output not found.")

    run = db.execute(
        select(PipelineRun).where(PipelineRun.id == output.run_id)
    ).scalar_one_or_none()

    if not run or run.org_id != current_user.organisation_id:
        raise HTTPException(status_code=404, detail="LLM output not found.")
    _enforce_run_module_scope(run, current_user, db)

    return _labeled_output(output)


# ─────────────────────────────────────────────────────────────────────────────
# 60 - Download LLM output .txt from R2
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/llm-outputs/{output_id}/download",
    summary="Download Claude recommendation as .txt file",
)
def download_llm_output(
    output_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    output = db.execute(
        select(PipelineLLMOutput).where(PipelineLLMOutput.id == output_id)
    ).scalar_one_or_none()

    if not output:
        raise HTTPException(status_code=404, detail="LLM output not found.")

    run = db.execute(
        select(PipelineRun).where(PipelineRun.id == output.run_id)
    ).scalar_one_or_none()

    if not run or run.org_id != current_user.organisation_id:
        raise HTTPException(status_code=404, detail="LLM output not found.")
    _enforce_run_module_scope(run, current_user, db)

    if not output.response_text:
        raise HTTPException(status_code=404, detail="No recommendation text available.")

    filename = f"recommendation_{output.analysis_type.value.lower()}_{output_id[:8]}.txt"

    return StreamingResponse(
        iter([output.response_text]),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 61 - Download any step output file from R2 (csv/txt/pdf); .txt/.md -> PDF
# ─────────────────────────────────────────────────────────────────────────────

_STEP_FILE_CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "json": "application/json",
    "pdf": "application/pdf",
}


@router.get(
    "/runs/{run_id}/steps/{step_number}/files/{filename}",
    summary="Download a step output file; as_pdf=true renders a .txt/.md file to PDF",
)
def download_step_file(
    run_id: str,
    step_number: int,
    filename: str,
    as_pdf: bool = Query(False, description="Render a .txt/.md output to PDF"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    from pipeline.tasks import r2

    run = db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    ).scalar_one_or_none()
    if not run or run.org_id != current_user.organisation_id:
        raise HTTPException(status_code=404, detail="Run not found.")
    _enforce_run_module_scope(run, current_user, db)

    step = db.execute(
        select(PipelineStepResult).where(
            PipelineStepResult.run_id == run_id,
            PipelineStepResult.step_number == step_number,
        )
    ).scalar_one_or_none()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found.")

    # Only serve files this step actually produced - the R2 key comes from our
    # own output list, so a crafted filename can't reach another tenant's keys.
    key = next(
        (k for k in (step.output_files_json or []) if k.split("/")[-1] == filename),
        None,
    )
    if not key:
        raise HTTPException(status_code=404, detail="File not found for this step.")

    try:
        data = r2.download_bytes(key)
    except Exception:
        raise HTTPException(status_code=404, detail="File not available in storage.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if as_pdf and ext in ("txt", "md"):
        from pipeline.routers.file_pdf import text_to_pdf
        pdf = text_to_pdf(data.decode("utf-8", errors="replace"), title=filename)
        out_name = filename.rsplit(".", 1)[0] + ".pdf"
        return StreamingResponse(
            iter([pdf]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
        )

    return StreamingResponse(
        iter([data]),
        media_type=_STEP_FILE_CONTENT_TYPES.get(ext, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Upload input file
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{pipeline_id}/upload-input",
    response_model=UploadedFileInfo,
    summary="Upload a pipeline input file to R2 (Analyst+)",
    dependencies=[Depends(require_role("analyst"))],
)
async def upload_input_file(
    pipeline_id: str,
    request: Request,
    filename: str = Query(..., description="Target filename in R2", max_length=255),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    pipeline = _get_pipeline_or_404(pipeline_id, current_user.organisation_id, db, user=current_user)

    import tempfile
    import os as _os
    import re as _re

    # Path-traversal guard: `filename` flows into both the R2 object key
    # (org/{org_id}/reference/{filename}) and the temp-file suffix. A '/' or
    # '..' would craft an arbitrary key (e.g. org/4/reference/../../999/...)
    # breaking tenant isolation, and a '/' also breaks the temp path (500).
    # Reduce to a bare basename and allow only a safe charset - reject, don't rewrite.
    safe_name = _os.path.basename(filename.strip())
    if not safe_name or safe_name in {".", ".."} or not _re.fullmatch(r"[A-Za-z0-9._-]+", safe_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename. Use a plain filename (letters, digits, '.', '_', '-' only).",
        )
    filename = safe_name

    # Reference/config files (the ESG hierarchy JSON, module mapping/matrix) are
    # backend-provided and may only be uploaded/replaced by a SUPER_ADMIN - an
    # analyst uploads DATA files only. Everything else keeps the Analyst+ floor.
    config = pipeline.config_json or {}
    reference_basenames = {t.split("/")[-1] for t in config.get("reference_files", [])}
    role_val = getattr(current_user.role, "value", current_user.role)
    if filename in reference_basenames and role_val != "super_admin":
        raise HTTPException(
            status_code=403,
            detail=(
                f"'{filename}' is a backend-provided configuration file. "
                "Only a super admin can upload or replace it."
            ),
        )

    # Body handling. This used to be `body = await request.body()`, which buffers
    # the whole upload in the API process before anything checks its size, so a
    # single large POST could exhaust worker memory. Now the body streams
    # straight to a temp file with a running total, and is abandoned the moment
    # it crosses the cap, so neither an allowed nor a rejected upload is ever
    # held in memory in full.
    #
    # Content-Length is checked first as a courtesy - it lets an honest client
    # fail fast - but it is client-supplied, so the streaming total below is the
    # real enforcement and does not trust it.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )

    total = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
        tmp_path = tmp.name
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB "
                            "upload limit."
                        ),
                    )
                tmp.write(chunk)
        except BaseException:
            tmp.close()
            _os.unlink(tmp_path)
            raise

    if total == 0:
        _os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail="Request body is empty.")

    try:
        r2_key = reference_key(str(current_user.organisation_id), filename)
        upload_file(tmp_path, r2_key)
    except R2Error as exc:
        # Log the full botocore detail server-side, but never return the R2
        # endpoint host / bucket / key layout to the client (info disclosure).
        logger.error("R2 upload failed for key %s: %s", r2_key, exc)
        raise HTTPException(status_code=502, detail="File storage upload failed. Please try again.")
    finally:
        _os.unlink(tmp_path)

    return UploadedFileInfo(
        filename=filename,
        r2_key=r2_key,
        size_bytes=total,
        last_modified=None,
    )


@router.get(
    "/{pipeline_id}/input-files",
    response_model=InputFilesStatus,
    summary="Check which required input files are present in R2",
)
def check_input_files(
    pipeline_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    pipeline = _get_pipeline_or_404(pipeline_id, current_user.organisation_id, db, user=current_user)
    org_id = current_user.organisation_id
    config = pipeline.config_json or {}
    required: List[str] = config.get("required_input_files", [])
    # Backend/super-admin-provided config files (JSON hierarchy, mapping/matrix).
    reference: List[str] = config.get("reference_files", [])
    # Files the analyst uploads (data). Explicit if configured, else everything in
    # required that isn't a reference file - keeps older definitions working.
    user_input: List[str] = config.get(
        "user_input_files",
        [f for f in required if f not in reference],
    )

    def _presence(templates: List[str]):
        up, miss = [], []
        for t in templates:
            key = t.format(org_id=org_id)
            if file_exists(key):
                up.append(UploadedFileInfo(
                    filename=key.split("/")[-1], r2_key=key, size_bytes=0, last_modified=None,
                ))
            else:
                miss.append(t)
        return up, miss

    uploaded, missing = _presence(required)
    user_uploaded, user_missing = _presence(user_input)
    ref_uploaded, ref_missing = _presence(reference)

    return InputFilesStatus(
        pipeline_id=pipeline_id,
        required_files=required,
        uploaded_files=uploaded,
        missing_files=missing,
        all_present=len(missing) == 0,
        user_input_files=user_input,
        user_files_present=len(user_missing) == 0,
        missing_user_files=user_missing,
        reference_files=reference,
        reference_files_present=len(ref_missing) == 0,
        missing_reference_files=ref_missing,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GDPR Erasure
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/runs/{run_id}/files",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="GDPR erasure - delete all R2 files for a run (Admin only)",
    dependencies=[Depends(require_role("admin"))],
)
def gdpr_erase_run_files(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_pipeline_db),
):
    run = _get_run_or_404(run_id, current_user.organisation_id, db, current_user)

    steps = db.execute(
        select(PipelineStepResult).where(PipelineStepResult.run_id == run_id)
    ).scalars().all()

    deleted_keys = []
    errors = []

    from pipeline.tasks.r2 import delete_file, R2Error

    for step in steps:
        for key in (step.output_files_json or []):
            try:
                delete_file(key)
                deleted_keys.append(key)
            except R2Error as exc:
                logger.error("R2 delete failed for key %s: %s", key, exc)
                errors.append(f"{key}: deletion failed")

    # Also erase the stable module-handoff CSV + provenance manifest, but ONLY for
    # modules whose CURRENT handoff was produced by this run (manifest.source_run_id).
    # The handoff lives at an org-level stable path shared across runs, so deleting
    # another run's handoff here would be data loss.
    from pipeline.tasks.r2 import (
        APEX_MODULE_NAMES,
        module_handoff_csv_key,
        module_manifest_key,
        read_module_handoff_manifest,
    )
    org_id = str(current_user.organisation_id)
    for module in APEX_MODULE_NAMES:
        manifest = read_module_handoff_manifest(org_id, module)
        if not manifest or manifest.get("source_run_id") != run_id:
            continue
        for key in (module_handoff_csv_key(org_id, module), module_manifest_key(org_id, module)):
            try:
                delete_file(key)
                deleted_keys.append(key)
            except R2Error as exc:
                logger.error("R2 delete failed for key %s: %s", key, exc)
                errors.append(f"{key}: deletion failed")

    llm_outputs = db.execute(
        select(PipelineLLMOutput).where(PipelineLLMOutput.run_id == run_id)
    ).scalars().all()

    for output in llm_outputs:
        output.response_text = None
        output.output_file_r2_path = None

    db.commit()

    # ── Redis purge ──────────────────────────────────────────────────────────
    # R2 and those two columns were not the only copies. Three run-scoped Redis
    # keys survived every erasure until now:
    #
    #   pipeline:{run_id}:status         25h TTL, a status string
    #   copilot:{user}:{run_id}:stream   1h TTL, a LIST holding EVERY TOKEN of
    #                                    Claude's answer about this org's data
    #   copilot:{user}:{run_id}:done     1h TTL, a completion flag
    #
    # The stream list is the one that matters: it is the model's full response
    # text, and erasure claimed to remove exactly that. The copilot key is
    # namespaced by user_id, so the pattern scan covers every user who opened
    # the Co-Pilot against this run, not just the caller.
    #
    # NOT covered here, deliberately: copilot:{user}:session:{session_id} holds
    # the full conversation history (questions plus Claude's complete answers)
    # on a SEVEN DAY TTL. It is keyed by session, not by run, so a per-run
    # endpoint cannot target it without deleting unrelated conversations. That
    # needs an org- or user-scoped erasure endpoint, which is a product
    # decision rather than something to infer here.
    redis_deleted = 0
    try:
        from pipeline.tasks.shared import _get_redis, _redis_run_key

        r = _get_redis()
        keys = [_redis_run_key(run_id)]
        for pattern in (f"copilot:*:{run_id}:stream", f"copilot:*:{run_id}:done"):
            # scan_iter, not keys() - keys() blocks the whole Redis server.
            keys.extend(r.scan_iter(match=pattern, count=100))
        if keys:
            redis_deleted = r.delete(*keys)
    except Exception as exc:
        # Report rather than swallow. An erasure that silently skipped a copy
        # is the failure mode this whole endpoint exists to prevent.
        logger.error("GDPR erasure: Redis purge failed for run %s: %s", run_id, exc)
        errors.append("redis: cached response purge failed")

    logger.info(
        "GDPR erasure: run=%s org=%s deleted_files=%d redis_keys=%d errors=%d by_user=%s",
        run_id,
        current_user.organisation_id,
        len(deleted_keys),
        redis_deleted,
        len(errors),
        current_user.id,
    )

    if errors:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=207,
            content={
                "deleted": deleted_keys,
                "errors": errors,
                "message": (
                    f"Partial erasure: {len(deleted_keys)} files deleted, "
                    f"{len(errors)} failed."
                ),
            },
        )