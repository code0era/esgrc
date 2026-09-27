"""
pipeline/schemas.py
Pydantic v2 request/response schemas for all pipeline endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipeline.models import (
    AnalysisTypeEnum,
    PipelineTypeEnum,
    RunStatusEnum,
    StepStatusEnum,
)


# â”€â”€ Pipeline Definition â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PipelineDefinitionOut(BaseModel):
    id: str
    org_id: int
    name: str
    pipeline_type: PipelineTypeEnum
    schedule_cron: Optional[str]
    is_active: bool
    config_json: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PipelineDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    schedule_cron: Optional[str] = None
    is_active: Optional[bool] = None
    config_json: Optional[Dict[str, Any]] = None


# â”€â”€ Trigger â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TriggerRequest(BaseModel):
    """Body for POST /pipelines/{id}/trigger â€” all fields optional."""
    input_file_overrides: Optional[Dict[str, str]] = Field(
        default=None,
        description="Map of input_name â†’ R2 key. Overrides defaults in config_json.",
    )


class TriggerResponse(BaseModel):
    run_id: str
    status: RunStatusEnum
    message: str = "Pipeline run queued."


# â”€â”€ Step Result â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class StepResultOut(BaseModel):
    id: str
    run_id: str
    step_number: int
    step_name: str
    status: StepStatusEnum
    input_files_json: Optional[List[str]]
    output_files_json: Optional[List[str]]
    celery_task_id: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    error_detail: Optional[str]

    model_config = {"from_attributes": True}


# â”€â”€ LLM Output â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class LabelItem(BaseModel):
    """One code->name entry actually used in a report (contextual-labeling legend)."""
    code: str
    name: str
    level: str  # "module" | "sub_module" | "group" | "metric"


class ProcessLogEntry(BaseModel):
    """
    One executed pipeline step, as a log line (Praveen's process-log criteria:
    user details · timestamp · process step executed · pass/fail status).

    Per-run this data is already available via GET /pipelines/runs/{id}; this shape
    exists so steps can be listed as a chronological log ACROSS runs, with the
    triggering user resolved to a name/email rather than a bare id.
    """
    run_id: str
    pipeline_id: str
    step_number: int
    step_name: str
    status: StepStatusEnum          # COMPLETED / FAILED / RUNNING / SKIPPED - the pass/fail
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    error_detail: Optional[str]
    triggered_by: Optional[int]     # user id
    triggered_by_email: Optional[str] = None    # resolved user details
    triggered_by_name: Optional[str] = None


class HandoffProvenanceItem(BaseModel):
    """Data-freshness for one module's Apex handoff (source of the UI 'Data as of' badge)."""
    module: str
    present: bool                        # has this module produced a handoff yet?
    produced_at: Optional[str] = None    # ISO-8601 UTC timestamp from the manifest
    source_run_id: Optional[str] = None


class LLMOutputOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)

    id: str
    run_id: str
    step_result_id: str
    analysis_type: AnalysisTypeEnum
    prompt_hash: str
    model_used: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    response_text: Optional[str]
    output_file_r2_path: Optional[str]
    created_at: datetime

    # ── Contextual labeling (additive; see pipeline/llm/labeling.py) ──────────────
    # response_text stays the source of truth (codes). These fields are the
    # display-time labelled *view*: business names substituted for codes, plus the
    # legend and a status the frontend can trust. labeling_status:
    #   "ok"      - names substituted, validation gate passed
    #   "failed"  - gate failed; labeled text == code text (safe fallback)
    #   "skipped" - empty text or reference data unavailable
    response_text_labeled: Optional[str] = None
    labels: List[LabelItem] = Field(default_factory=list)
    labeling_status: str = "skipped"


class LLMOutputSummary(BaseModel):
    """Lightweight version â€” no response_text. Used in run list views."""
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)

    id: str
    analysis_type: AnalysisTypeEnum
    model_used: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    output_file_r2_path: Optional[str]
    created_at: datetime


# â”€â”€ Pipeline Run â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PipelineRunOut(BaseModel):
    id: str
    pipeline_id: str
    org_id: int
    triggered_by: Optional[int]
    status: RunStatusEnum
    is_current: bool
    progress_pct: int
    confidence_score: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    celery_chord_id: Optional[str]
    step_results: List[StepResultOut] = []
    llm_outputs: List[LLMOutputSummary] = []

    model_config = {"from_attributes": True}


class PipelineRunSummary(BaseModel):
    """Lightweight â€” used in paginated run history lists."""
    id: str
    pipeline_id: str
    status: RunStatusEnum
    is_current: bool
    progress_pct: int
    confidence_score: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class PipelineRunListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[PipelineRunSummary]


# â”€â”€ Rollback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RollbackRequest(BaseModel):
    target_run_id: str = Field(description="Run ID to roll back to (make is_current=True).")


class RollbackResponse(BaseModel):
    previous_run_id: str
    current_run_id: str
    message: str = "Rollback successful."


# â”€â”€ Emergency Stop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class EmergencyStopRequest(BaseModel):
    run_id: str


class EmergencyStopResponse(BaseModel):
    run_id: str
    message: str


# â”€â”€ Step Re-run â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class StepRerunResponse(BaseModel):
    run_id: str
    step_number: int
    step_result_id: str
    status: StepStatusEnum
    message: str = "Step re-run queued."


# â”€â”€ File Upload â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class UploadedFileInfo(BaseModel):
    filename: str
    r2_key: str
    size_bytes: int
    last_modified: Optional[datetime]


class InputFilesStatus(BaseModel):
    pipeline_id: str
    required_files: List[str]
    uploaded_files: List[UploadedFileInfo]
    missing_files: List[str]
    all_present: bool
    # Split of required_files into the analyst-uploaded DATA files vs the
    # backend/super-admin-provided CONFIG (reference) files. The frontend only
    # surfaces user_input_files for upload; reference files are provided by the
    # backend and hidden from analysts. A run needs both present (all_present),
    # but the two gates are reported separately so the UI can tell an analyst
    # "upload your data" apart from "config missing - a super admin must provide it".
    user_input_files: List[str] = []
    user_files_present: bool = True
    missing_user_files: List[str] = []
    reference_files: List[str] = []
    reference_files_present: bool = True
    missing_reference_files: List[str] = []


# â”€â”€ Prompt Management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PromptOut(BaseModel):
    id: int
    name: str
    version: int
    content: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PromptUpdate(BaseModel):
    content: str = Field(min_length=50, description="New prompt content. Creates a new version.")


class PromptHistoryOut(BaseModel):
    id: int
    version: int
    content: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# â”€â”€ SSE Event shapes (documented, not used as response_model) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class SSEStepEvent(BaseModel):
    event: str  # "step_running" | "step_completed" | "step_failed" | "step_skipped"
    step: int
    step_name: str
    status: StepStatusEnum
    pct: int
    outputs: Optional[List[str]] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class SSERunTerminalEvent(BaseModel):
    event: str  # "run_completed" | "run_failed" | "run_cancelled"
    status: RunStatusEnum
    message: str

