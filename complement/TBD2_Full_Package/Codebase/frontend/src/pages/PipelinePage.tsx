import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Play, StopCircle, RotateCcw, Upload, Wifi, WifiOff, Loader2,
  GitBranch, CheckCircle2, XCircle, Clock, AlertTriangle,
} from 'lucide-react'
import api from '@/lib/axios'
import { StepCard } from '@/components/pipeline/StepCard'
import { FileUploadModal } from '@/components/pipeline/FileUploadModal'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PipelineMonitorSkeleton } from '@/components/ui/Skeleton'
import { usePipelineStore } from '@/store/pipeline'
import { usePipelineSSE } from '@/hooks/usePipelineSSE'
import { useAuthStore, isAdmin } from '@/store/auth'
import { cn } from '@/lib/utils'

// Module chains all share the ESGRC 7-step shape; only the regression label differs,
// so the 7 labels are generated from the module's display name.
const moduleSteps = (label: string) => [
  'Data Preparation I','Data Preparation II','Correlation CHAID FT Analysis',
  'SPC & RPN Analysis',`Regression ${label}`,'Combine Reports','Claude AI - Module Unified',
]
const ESGRC_STEPS = moduleSteps('ESGRC')
const APEX_STEPS  = ['All Module Low Perf','Correlation CHAID L0','SPC RPN L0','Regression L0','Combine General Reports','Claude AI - General Risk','Combine Statistical Reports','Claude AI - SPC RPN']

// Display names for the Data Freshness panel - matches pipeline/modules.py's
// MODULES list (module token -> human label). Apex isn't in here: it's the
// consumer of these handoffs, not a producer, so it never appears in the
// /handoff-provenance response.
const MODULE_LABELS: Record<string, string> = {
  esgrc: 'ESGRC', customer: 'Customer', shared: 'Shared', bspt: 'Business Partner',
  enterprise: 'Enterprise', ictm: 'IT Processes', product: 'Product',
  resource: 'Resource', service: 'Service', brand: 'Brand Management',
  mkts: 'Market and Sales', integration: 'Integration',
}

function freshnessBadgeText(item: { present: boolean; produced_at: string | null; source_run_id: string | null }): string {
  if (!item.present || !item.produced_at) return 'No data yet'
  const date = new Date(item.produced_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  const shortRun = item.source_run_id ? item.source_run_id.split('-')[0] : '—'
  return `Data as of ${date} · Run #${shortRun}`
}

// New modules add one entry here. Unknown types fall back to the ESGRC labels.
const STEP_NAMES_BY_TYPE: Record<string, string[]> = {
  ESGRC_MODULE:        ESGRC_STEPS,
  CUSTOMER_MODULE:     moduleSteps('Customer'),
  SHARED_MODULE:       moduleSteps('Shared'),
  BSPT_MODULE:         moduleSteps('Business Partner'),
  ENTERPRISE_MODULE:   moduleSteps('Enterprise'),
  ICTM_MODULE:         moduleSteps('IT Processes'),
  PRODUCT_MODULE:      moduleSteps('Product'),
  RESOURCE_MODULE:     moduleSteps('Resource'),
  SERVICE_MODULE:      moduleSteps('Service'),
  BRAND_MODULE:        moduleSteps('Brand Management'),
  MKTS_MODULE:         moduleSteps('Market and Sales'),
  INTEGRATION_MODULE:  moduleSteps('Integration'),
  APEX_ENTERPRISE:     APEX_STEPS,
}

function SSEIndicator({ status }: { status: string }) {
  return (
    <div className={cn('flex items-center gap-1.5 text-xs',
      status === 'connected'   ? 'text-accent-success' :
      status === 'connecting'  ? 'text-accent-warning' :
      status === 'error'       ? 'text-accent-danger'  : 'text-text-muted'
    )}>
      {status === 'connected' ? <Wifi size={12} /> : <WifiOff size={12} />}
      {status === 'connected' ? 'Live' : status === 'connecting' ? 'Connecting…' : status === 'error' ? 'Reconnecting' : 'Idle'}
    </div>
  )
}

function RunHistoryItem({ run, isActive, onClick }: { run: any; isActive: boolean; onClick: () => void }) {
  return (
    <button
      className={cn(
        'w-full text-left px-3 py-2.5 rounded-lg border transition-all',
        isActive
          ? 'bg-accent-primary/10 border-accent-primary/30'
          : 'border-border-subtle hover:bg-bg-elevated'
      )}
      onClick={onClick}
      aria-pressed={isActive}
    >
      <div className="flex items-center justify-between mb-1">
        <StatusBadge status={run.status} showIcon={false} />
        {run.is_current && <span className="text-[10px] text-accent-success font-medium">CURRENT</span>}
      </div>
      <div className="text-xs text-text-muted font-mono truncate">{run.id.split('-').slice(0,3).join('-')}</div>
      {run.confidence_score != null && (
        <div className="text-xs text-text-secondary mt-0.5">
          Confidence: {(run.confidence_score * 100).toFixed(0)}%
        </div>
      )}
      {run.started_at && (
        <div className="text-[10px] text-text-muted mt-0.5">
          {new Date(run.started_at).toLocaleString()}
        </div>
      )}
    </button>
  )
}

// Inner component so usePipelineSSE has access to activeRunId
function PipelineMonitorInner() {
  const { user }   = useAuthStore()
  const qc         = useQueryClient()
  const canAdmin   = isAdmin(user?.role)

  const activePipelineId  = usePipelineStore((s) => s.activePipelineId)
  const activeRunId       = usePipelineStore((s) => s.activeRunId)
  const runStatus         = usePipelineStore((s) => s.runStatus)
  const stepResults       = usePipelineStore((s) => s.stepResults)
  const progressPct       = usePipelineStore((s) => s.progressPct)
  const setActivePipeline = usePipelineStore((s) => s.setActivePipeline)
  const setActiveRun      = usePipelineStore((s) => s.setActiveRun)
  const setRunStatus      = usePipelineStore((s) => s.setRunStatus)
  const resetRun          = usePipelineStore((s) => s.resetRun)

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [showUpload,    setShowUpload]     = useState(false)

  // SSE hook - connects when there's an active running run
  const sseLiveRunId = runStatus === 'RUNNING' || runStatus === 'PENDING' ? activeRunId : null
  const { connectionStatus } = usePipelineSSE(sseLiveRunId)

  // Load pipeline list
  const { data: pipelines, isLoading: pipesLoading } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => api.get('/pipelines').then((r) => r.data),
  })

  // Data-freshness badge source - one entry per module, org-scoped, not tied
  // to whichever pipeline is currently selected.
  const { data: handoffProvenance } = useQuery({
    queryKey: ['handoff-provenance'],
    queryFn: () => api.get('/pipelines/handoff-provenance').then((r) => r.data),
  })

  // Load runs for active pipeline
  const activePipe = pipelines?.find((p: any) => p.id === activePipelineId)
  const { data: runsData, isLoading: runsLoading } = useQuery({
    queryKey: ['runs', activePipelineId],
    queryFn: () => api.get(`/pipelines/${activePipelineId}/runs`).then((r) => r.data),
    enabled: !!activePipelineId,
  })
  const runs: any[] = runsData?.items ?? []

  // The run this page is showing: a selected historical run, or the live run.
  const displayRunId = selectedRunId ?? activeRunId
  const isTerminal = runStatus === 'COMPLETED' || runStatus === 'FAILED' || runStatus === 'CANCELLED'

  // Full run detail, with real step_result ids. Needed for two things a live
  // run's SSE events never carry: step ids to match LLM outputs against (SSE
  // step events use empty-string ids), and the historical step list when a
  // past run is selected. Only fetched once there's something worth fetching -
  // for the live run that means waiting for it to finish.
  const { data: runDetail } = useQuery({
    queryKey: ['run', displayRunId],
    queryFn: () => api.get(`/pipelines/runs/${displayRunId}`).then((r) => r.data),
    enabled: !!displayRunId && (!!selectedRunId || isTerminal),
  })

  // Writing setRunStatus directly inside the queryFn above (as this used to)
  // reads `selectedRunId` from that call's own closure, captured when the
  // fetch started - not when it resolves. If the user clicks run A then
  // quickly clicks run B, and A's response happens to arrive after B's (real
  // network jitter, not exotic), A's stale closure still says "selectedRunId
  // was truthy" and overwrites the store's global runStatus/progressPct with
  // run A's data while run B is what's actually being displayed. Keying off
  // `runDetail` here instead is safe: React Query only ever populates `data`
  // for the query matching the *current* ['run', displayRunId] key, so this
  // effect never fires with a different run's response.
  useEffect(() => {
    if (runDetail && selectedRunId) setRunStatus(runDetail.status, runDetail.progress_pct)
  }, [runDetail, selectedRunId, setRunStatus])

  // Full LLM output text - GET /runs/{id} only returns lightweight summaries
  // (no response_text, no step_result_id), so recommendations need their own
  // fetch. Real Claude output only exists once a run has actually finished.
  const { data: recommendations } = useQuery({
    queryKey: ['recommendations', displayRunId],
    queryFn: () => api.get(`/pipelines/runs/${displayRunId}/recommendations`).then((r) => r.data),
    enabled: !!displayRunId && (!!selectedRunId || isTerminal),
  })

  // The Run History list otherwise has no reason to refetch: its query key
  // (['runs', activePipelineId]) doesn't change when the live run finishes, so
  // the sidebar's status badge, confidence score and CURRENT flag stay frozen
  // at whatever they were when the run started until the user re-selects the
  // pipeline or reloads. Fire once per live run reaching a terminal state.
  useEffect(() => {
    if (activeRunId && !selectedRunId && isTerminal) {
      qc.invalidateQueries({ queryKey: ['runs', activePipelineId] })
    }
  }, [activeRunId, selectedRunId, isTerminal, activePipelineId, qc])

  // Input files
  const { data: inputFiles } = useQuery({
    queryKey: ['input-files', activePipelineId],
    queryFn: () => api.get(`/pipelines/${activePipelineId}/input-files`).then((r) => r.data),
    enabled: !!activePipelineId,
  })

  // Actions
  const triggerMutation = useMutation({
    mutationFn: () => api.post(`/pipelines/${activePipelineId}/trigger`),
    onSuccess: (res) => {
      const runId = res.data.run_id
      setActiveRun(runId)
      setSelectedRunId(null)
      qc.invalidateQueries({ queryKey: ['runs', activePipelineId] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => api.post('/pipelines/emergency-stop', { run_id: displayRunId }),
    onSuccess: () => setRunStatus('CANCELLED'),
  })

  const rollbackMutation = useMutation({
    mutationFn: (targetId: string) => api.post(`/pipelines/runs/${targetId}/rollback`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs', activePipelineId] }),
  })

  const rerunStepMutation = useMutation({
    mutationFn: (stepNum: number) => api.post(`/pipelines/runs/${displayRunId}/steps/${stepNum}/rerun`),
  })

  // Determine which step names to use
  const stepNames = STEP_NAMES_BY_TYPE[activePipe?.pipeline_type ?? ''] ?? ESGRC_STEPS

  // Determine display steps: real step_results once fetched (historical run,
  // or the live run once it finishes), SSE-driven approximations while it's
  // still running (real ids arrive later via runDetail, once isTerminal).
  const displaySteps: Record<number, any> = runDetail
    ? Object.fromEntries(runDetail.step_results.map((s: any) => [s.step_number, s]))
    : (activeRunId && !selectedRunId ? stepResults : {})

  // Recommendations always carry a real step_result_id; nothing to match
  // against until runDetail (real step ids) has loaded too.
  const getLLMForStep = (stepNum: number): string | null => {
    const stepResultId = displaySteps[stepNum]?.id
    if (!stepResultId || !recommendations) return null
    const output = recommendations.find((o: any) => o.step_result_id === stepResultId)
    if (!output) return null
    // Prefer the labeled (business-name) text; fall back to raw codes if
    // labeling didn't succeed for this output.
    return (output.labeling_status === 'ok' ? output.response_text_labeled : output.response_text) ?? null
  }

  const isRunning = runStatus === 'RUNNING' || runStatus === 'PENDING'
  const isCompleted = runStatus === 'COMPLETED'
  const canTrigger = !!activePipelineId && !isRunning && (inputFiles?.all_present ?? true)

  if (pipesLoading) return <PipelineMonitorSkeleton />

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Pipeline Monitor</h1>
          <p className="page-subtitle">Live AI orchestration and step execution tracking</p>
        </div>
        <SSEIndicator status={connectionStatus} />
      </div>

      <div className="flex gap-4 min-h-0">
        {/* Left panel */}
        <div className="w-72 flex-shrink-0 space-y-3">
          {/* Pipeline selector */}
          <div className="card p-3">
            <label className="label text-xs">Select Pipeline</label>
            <select
              className="w-full text-sm"
              value={activePipelineId ?? ''}
              onChange={(e) => {
                // activeRunId/runStatus/stepResults/sseStatus are global, not
                // per-pipeline - without resetting them here, a still-RUNNING
                // run on the previous pipeline keeps its SSE stream feeding
                // stepResults, keeps isRunning true (blocking Trigger on the
                // newly-selected pipeline), and its progress bar/step cards
                // keep rendering under the new pipeline's name.
                resetRun()
                setActivePipeline(e.target.value)
                setSelectedRunId(null)
              }}
              id="pipeline-selector"
              aria-label="Select pipeline"
            >
              <option value="" disabled>Choose a pipeline…</option>
              {(pipelines ?? []).map((p: any) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          {/* Actions */}
          <div className="space-y-2">
            <button
              id="trigger-pipeline-btn"
              className="btn-primary w-full justify-center"
              disabled={!canTrigger || triggerMutation.isPending}
              onClick={() => triggerMutation.mutate()}
            >
              {triggerMutation.isPending
                ? <Loader2 size={15} className="animate-spin" />
                : <Play size={15} />}
              Trigger Run
            </button>

            {/* Analyst uploads DATA files only. Config/reference files are
                backend-provided and never surfaced here. */}
            {activePipelineId && inputFiles && !inputFiles.user_files_present && (
              <button
                className="btn-secondary w-full justify-center text-sm"
                onClick={() => setShowUpload(true)}
                id="upload-files-btn"
              >
                <Upload size={15} /> Upload Data ({inputFiles.missing_user_files?.length ?? '?'} missing)
              </button>
            )}

            {/* Missing backend config is a setup issue an analyst cannot fix. */}
            {activePipelineId && inputFiles && !inputFiles.reference_files_present && (
              <div
                className="w-full text-xs text-accent-warning bg-accent-warning/10 border border-accent-warning/30 rounded-lg px-3 py-2"
                role="status"
              >
                Configuration missing - a super admin must provide the pipeline's
                reference files before this run can start.
              </div>
            )}

            {isRunning && (
              <button
                className="btn-danger w-full justify-center"
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
                id="emergency-stop-btn"
              >
                <StopCircle size={15} /> Emergency Stop
              </button>
            )}

            {canAdmin && isCompleted && selectedRunId && runs.length > 1 && (
              <button
                className="btn-secondary w-full justify-center text-sm"
                onClick={() => {
                  const prev = runs.find((r: any) => r.id !== selectedRunId && r.status === 'COMPLETED')
                  if (prev) rollbackMutation.mutate(prev.id)
                }}
                id="rollback-btn"
              >
                <RotateCcw size={15} /> Rollback to Previous
              </button>
            )}
          </div>

          {/* Progress bar (live runs) */}
          {isRunning && (
            <div className="card p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-muted">Progress</span>
                <span className="text-xs font-bold text-accent-primary">
                  {progressPct}%
                </span>
              </div>
              <div className="h-2 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-primary rounded-full transition-all duration-500"
                  style={{ width:`${progressPct}%` }}
                />
              </div>
            </div>
          )}

          {/* Run history */}
          <div className="card overflow-hidden">
            <div className="px-3 py-2 border-b border-border-subtle text-xs font-medium text-text-muted uppercase tracking-wider">
              Run History
            </div>
            <div className="p-2 space-y-1 max-h-80 overflow-y-auto">
              {runsLoading && <div className="skeleton h-14 rounded-lg" />}
              {runs.length === 0 && !runsLoading && (
                <div className="text-xs text-text-muted text-center py-4">No runs yet</div>
              )}
              {runs.map((run: any) => (
                <RunHistoryItem
                  key={run.id}
                  run={run}
                  isActive={selectedRunId === run.id}
                  onClick={() => {
                    setSelectedRunId(run.id)
                    setRunStatus(run.status, run.progress_pct)
                  }}
                />
              ))}
            </div>
          </div>

          {/* Data freshness - per-module handoff provenance for the Apex roll-up */}
          <div className="card overflow-hidden">
            <div className="px-3 py-2 border-b border-border-subtle text-xs font-medium text-text-muted uppercase tracking-wider">
              Data Freshness
            </div>
            <div className="p-2 space-y-1 max-h-64 overflow-y-auto">
              {!handoffProvenance && <div className="skeleton h-8 rounded-lg" />}
              {(handoffProvenance ?? []).map((item: any) => (
                <div key={item.module} className="px-2 py-1.5 rounded-lg flex items-center justify-between gap-2">
                  <span className="text-xs text-text-secondary">{MODULE_LABELS[item.module] ?? item.module}</span>
                  <span className={cn('text-[10px] whitespace-nowrap', item.present ? 'text-text-muted' : 'text-accent-warning')}>
                    {freshnessBadgeText(item)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right panel - step cards */}
        <div className="flex-1 space-y-3 overflow-y-auto">
          {!activePipelineId && (
            <div className="card p-12 flex flex-col items-center justify-center text-center">
              <GitBranch size={40} className="text-text-muted mb-4" />
              <div className="text-text-secondary font-medium">Select a pipeline to monitor</div>
              <div className="text-sm text-text-muted mt-1">Choose ESGRC Module or Apex Enterprise from the left panel</div>
            </div>
          )}

          {activePipelineId && stepNames.map((name, i) => {
            const stepNum = i + 1
            return (
              <StepCard
                key={stepNum}
                step={displaySteps[stepNum] ?? null}
                stepNumber={stepNum}
                stepName={name}
                runId={displayRunId ?? ''}
                onRerun={() => rerunStepMutation.mutate(stepNum)}
                llmText={getLLMForStep(stepNum)}
              />
            )
          })}
        </div>
      </div>

      {/* File upload modal */}
      {showUpload && activePipelineId && (
        <FileUploadModal
          pipelineId={activePipelineId}
          // Only the analyst's DATA files (user_input_files) are uploadable here;
          // backend-provided config files are intentionally excluded. Keys are
          // full R2 paths (org/{id}/reference/<name>) - the modal works in plain
          // filenames, matching the basenames the backend returns for uploads.
          requiredFiles={(inputFiles?.user_input_files ?? []).map((k: string) => k.split('/').pop() as string)}
          uploadedFiles={inputFiles?.uploaded_files?.map((f: any) => f.filename) ?? []}
          onClose={() => setShowUpload(false)}
          onAllUploaded={() => qc.invalidateQueries({ queryKey:['input-files', activePipelineId] })}
        />
      )}
    </div>
  )
}

export default function PipelinePage() {
  return <PipelineMonitorInner />
}
