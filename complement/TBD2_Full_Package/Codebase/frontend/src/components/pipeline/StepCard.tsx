import { useState } from 'react'
import {
  CheckCircle2, XCircle, Clock, Loader2, MinusCircle,
  ChevronDown, ChevronUp, File, RefreshCw, Download,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { StepResult, StepStatus } from '@/store/pipeline'
import api from '@/lib/axios'

interface StepCardProps {
  step:        StepResult | null
  stepNumber:  number
  stepName:    string
  runId:       string
  onRerun:     () => void
  llmText?:    string | null
}

const STATUS_UI: Record<StepStatus, {
  border: string; bg: string; Icon: React.ElementType; iconClass: string; label: string
}> = {
  PENDING:   { border:'border-border-subtle', bg:'bg-bg-surface',       Icon:Clock,        iconClass:'text-text-muted',      label:'Pending'   },
  RUNNING:   { border:'border-accent-primary/40', bg:'bg-accent-primary/5', Icon:Loader2,  iconClass:'text-accent-primary animate-spin', label:'Running' },
  COMPLETED: { border:'border-accent-success/40', bg:'bg-accent-success/5', Icon:CheckCircle2, iconClass:'text-accent-success', label:'Completed' },
  FAILED:    { border:'border-accent-danger/40',  bg:'bg-accent-danger/5',  Icon:XCircle,  iconClass:'text-accent-danger',   label:'Failed'    },
  SKIPPED:   { border:'border-border-subtle',      bg:'bg-bg-surface',       Icon:MinusCircle, iconClass:'text-text-muted',  label:'Skipped'   },
}

function formatDuration(ms: number | null): string {
  // !ms treats a genuine 0ms duration the same as null/undefined, showing
  // "-" (looks like no duration recorded) for a step that legitimately
  // completed instantly - the caller already uses `!= null` specifically so
  // a real 0ms duration renders this row at all.
  if (ms == null) return '-'
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

export function StepCard({ step, stepNumber, stepName, runId, onRerun, llmText }: StepCardProps) {
  const [expanded, setExpanded] = useState(false)
  const status: StepStatus = step?.status ?? 'PENDING'
  const cfg = STATUS_UI[status]
  const { border, bg, Icon, iconClass, label } = cfg

  const isRunning   = status === 'RUNNING'
  const isCompleted = status === 'COMPLETED'
  const isFailed    = status === 'FAILED'

  // Download a step output file from R2 (as_pdf renders .txt/.md to PDF server-side)
  const downloadFile = async (filename: string, asPdf: boolean) => {
    try {
      const res = await api.get(
        `/pipelines/runs/${runId}/steps/${stepNumber}/files/${encodeURIComponent(filename)}`,
        { params: asPdf ? { as_pdf: true } : {}, responseType: 'blob' },
      )
      const url = URL.createObjectURL(res.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = asPdf ? filename.replace(/\.(txt|md)$/i, '.pdf') : filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Download failed for', filename, e)
    }
  }

  return (
    <div
      className={cn(
        'border rounded-xl transition-all duration-300',
        border, bg,
        isRunning && 'step-running',
      )}
    >
      {/* Card header */}
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Step number */}
        <div className={cn(
          'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
          isCompleted ? 'bg-accent-success/20 text-accent-success' :
          isFailed    ? 'bg-accent-danger/20  text-accent-danger'  :
          isRunning   ? 'bg-accent-primary/20 text-accent-primary' :
                        'bg-bg-elevated text-text-muted'
        )}>
          {stepNumber}
        </div>

        {/* Icon */}
        <Icon size={18} className={cn('flex-shrink-0', iconClass)} aria-hidden />

        {/* Name + status */}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-text-primary truncate">{stepName}</div>
          {step?.duration_ms != null && isCompleted && (
            <div className="text-xs text-text-muted">{formatDuration(step.duration_ms)}</div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={cn(
            'text-xs font-medium px-2 py-0.5 rounded-full',
            isCompleted ? 'text-accent-success bg-accent-success/10' :
            isFailed    ? 'text-accent-danger  bg-accent-danger/10'  :
            isRunning   ? 'text-accent-primary bg-accent-primary/10' :
                          'text-text-muted bg-bg-elevated'
          )}>
            {label}
          </span>

          {isFailed && (
            <button
              className="btn-icon w-7 h-7"
              onClick={onRerun}
              aria-label={`Re-run step ${stepNumber}`}
              title="Re-run this step"
            >
              <RefreshCw size={13} />
            </button>
          )}

          {(isCompleted || isFailed) && (
            <button
              className="btn-icon w-7 h-7"
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? 'Collapse step details' : 'Expand step details'}
            >
              {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          )}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border-subtle pt-3 animate-fade-in">
          {/* Error */}
          {isFailed && step?.error_detail && (
            <div className="bg-accent-danger/5 border border-accent-danger/20 rounded-lg p-3">
              <div className="text-xs font-medium text-accent-danger mb-1">Error</div>
              <pre className="text-xs text-text-secondary whitespace-pre-wrap font-mono break-all">
                {step.error_detail}
              </pre>
            </div>
          )}

          {/* Output files */}
          {step?.output_files_json && step.output_files_json.length > 0 && (
            <div>
              <div className="text-xs font-medium text-text-muted mb-1.5">Output files</div>
              <div className="space-y-1">
                {step.output_files_json.map((f) => {
                  const name = f.split('/').pop() as string
                  const isText = /\.(txt|md)$/i.test(name)
                  return (
                    <div key={f} className="flex items-center gap-2 text-xs">
                      <File size={11} className="text-text-muted flex-shrink-0" />
                      <button
                        className="text-accent-primary hover:underline truncate text-left"
                        onClick={() => downloadFile(name, false)}
                        title={`Download ${name}`}
                      >
                        {name}
                      </button>
                      {isText && (
                        <button
                          className="text-[10px] text-text-muted hover:text-accent-secondary border border-border-subtle rounded px-1 leading-4 flex-shrink-0"
                          onClick={() => downloadFile(name, true)}
                          title="Download as PDF"
                        >
                          PDF
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* LLM recommendation (Claude steps) */}
          {llmText && (
            <div className="bg-accent-secondary/5 border border-accent-secondary/20 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-medium text-accent-secondary">AI Recommendation</div>
                <button
                  className="text-[10px] text-text-muted hover:text-text-primary flex items-center gap-1"
                  onClick={() => {
                    const blob = new Blob([llmText], { type:'text/plain' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url; a.download = `step_${stepNumber}_recommendation.txt`; a.click()
                    URL.revokeObjectURL(url)
                  }}
                  aria-label="Download recommendation"
                >
                  <Download size={10} /> Download
                </button>
              </div>
              <div className="text-xs text-text-secondary leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
                {llmText}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
