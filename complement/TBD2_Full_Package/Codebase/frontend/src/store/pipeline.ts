import { create } from 'zustand'

// ── Types mirroring backend enums ────────────────────────────────────────────
export type RunStatus  = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
export type StepStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'SKIPPED'
// Compile-time TypeScript, so this cannot be derived from pipeline/modules.py.
// Keep in sync with PipelineTypeEnum; test_modules_registry.py guards the pair.
export type PipelineType =
  | 'ESGRC_MODULE' | 'APEX_ENTERPRISE' | 'CUSTOMER_MODULE' | 'SHARED_MODULE' | 'BSPT_MODULE'
  | 'ENTERPRISE_MODULE' | 'ICTM_MODULE' | 'PRODUCT_MODULE' | 'RESOURCE_MODULE' | 'SERVICE_MODULE'
  | 'BRAND_MODULE' | 'MKTS_MODULE' | 'INTEGRATION_MODULE'

export interface StepResult {
  id:               string
  run_id:           string
  step_number:      number
  step_name:        string
  status:           StepStatus
  input_files_json:  string[] | null
  output_files_json: string[] | null
  celery_task_id:   string | null
  started_at:       string | null
  completed_at:     string | null
  duration_ms:      number | null
  error_detail:     string | null
}

export interface SSEStepEvent {
  event:       string
  step:        number
  step_name:   string
  status:      StepStatus
  pct:         number
  outputs:     string[] | null
  duration_ms: number | null
  error:       string | null
}

interface PipelineState {
  activePipelineId: string | null
  activeRunId:      string | null
  runStatus:        RunStatus | null
  progressPct:      number
  stepResults:      Record<number, StepResult>   // step_number → StepResult
  sseStatus:        'idle' | 'connecting' | 'connected' | 'error' | 'closed'

  setActivePipeline:  (id: string) => void
  setActiveRun:       (runId: string) => void
  setRunStatus:       (status: RunStatus, pct?: number) => void
  applySSEEvent:      (event: SSEStepEvent) => void
  setSSEStatus:       (s: PipelineState['sseStatus']) => void
  resetRun:           () => void
}

export const usePipelineStore = create<PipelineState>()((set) => ({
  activePipelineId: null,
  activeRunId:      null,
  runStatus:        null,
  progressPct:      0,
  stepResults:      {},
  sseStatus:        'idle',

  setActivePipeline: (id) => set({ activePipelineId: id }),

  setActiveRun: (runId) => set({
    activeRunId: runId,
    runStatus:   'PENDING',
    progressPct: 0,
    stepResults: {},
    sseStatus:   'idle',
  }),

  setRunStatus: (status, pct) => set((s) => ({
    runStatus:   status,
    progressPct: pct ?? s.progressPct,
  })),

  applySSEEvent: (ev) => set((state) => {
    const updated: StepResult = {
      ...state.stepResults[ev.step],
      id:               state.stepResults[ev.step]?.id ?? '',
      run_id:           state.activeRunId ?? '',
      step_number:      ev.step,
      step_name:        ev.step_name,
      status:           ev.status,
      input_files_json: state.stepResults[ev.step]?.input_files_json ?? null,
      output_files_json: ev.outputs ?? null,
      celery_task_id:   null,
      started_at:       state.stepResults[ev.step]?.started_at ?? null,
      completed_at:     ev.status === 'COMPLETED' || ev.status === 'FAILED'
                          ? new Date().toISOString() : null,
      duration_ms:      ev.duration_ms,
      error_detail:     ev.error ?? null,
    }
    return {
      stepResults: { ...state.stepResults, [ev.step]: updated },
      progressPct: ev.pct,
    }
  }),

  setSSEStatus: (sseStatus) => set({ sseStatus }),

  resetRun: () => set({
    activeRunId: null,
    runStatus:   null,
    progressPct: 0,
    stepResults: {},
    sseStatus:   'idle',
  }),
}))
