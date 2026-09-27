import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Download, ChevronDown, ChevronUp, ExternalLink,
  FileText, Zap, AlertCircle, GitCompare,
} from 'lucide-react'
import api from '@/lib/axios'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { cn, compareConfidence } from '@/lib/utils'

function LLMOutputCard({ output }: { output: any }) {
  const [expanded, setExpanded] = useState(false)

  const handleDownload = async () => {
    try {
      const res = await api.get(`/pipelines/llm-outputs/${output.id}/download`, { responseType:'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${output.analysis_type.toLowerCase()}_${output.id}.txt`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Download failed for recommendation', output.id, e)
    }
  }

  const typeColor = output.analysis_type === 'GENERAL_RISK' ? 'badge-danger' :
                    output.analysis_type === 'SPC_RPN'      ? 'badge-warning' : 'badge-violet'

  return (
    <div className="bg-bg-elevated border border-border-subtle rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <Zap size={16} className="text-accent-secondary flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn('badge', typeColor)}>{output.analysis_type.replace(/_/g,' ')}</span>
            <span className="text-xs text-text-muted">{output.model_used}</span>
          </div>
          <div className="text-[11px] text-text-muted mt-0.5">
            {output.input_tokens?.toLocaleString()} in · {output.output_tokens?.toLocaleString()} out
            {' · '}{new Date(output.created_at).toLocaleString()}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-ghost text-xs px-2 py-1"
            onClick={handleDownload}
            aria-label="Download recommendation file"
          >
            <Download size={13} /> Download
          </button>
          <button
            className="btn-icon w-7 h-7"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        </div>
      </div>
      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-border-subtle animate-fade-in">
          <pre className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto font-sans">
            {output.response_text}
          </pre>
        </div>
      )}
    </div>
  )
}

function RunCard({ run, onSelect, isSelected }: { run: any; onSelect: () => void; isSelected: boolean }) {
  // The run-list endpoint returns PipelineRunSummary, which carries no LLM
  // output data at all - full text only exists on GET /runs/{id}/recommendations.
  const { data: llmOutputs } = useQuery({
    queryKey: ['recommendations', run.id],
    queryFn: () => api.get(`/pipelines/runs/${run.id}/recommendations`).then((r) => r.data),
  })

  return (
    <div
      className={cn(
        'card p-4 cursor-pointer transition-all',
        isSelected ? 'border-accent-primary/50 bg-accent-primary/5' : 'card-hover'
      )}
      onClick={onSelect}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } }}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <StatusBadge status={run.status} />
            {run.is_current && <span className="text-[10px] text-accent-success font-bold">CURRENT</span>}
          </div>
          <div className="text-xs text-text-muted font-mono mt-1">{run.id}</div>
        </div>
        {run.confidence_score != null && (
          <div className="text-right">
            <div className={cn('text-2xl font-black',
              run.confidence_score >= 0.8 ? 'text-accent-success' :
              run.confidence_score >= 0.6 ? 'text-accent-warning' : 'text-accent-danger'
            )}>
              {(run.confidence_score * 100).toFixed(0)}%
            </div>
            <div className="text-[10px] text-text-muted">confidence</div>
          </div>
        )}
      </div>

      <div className="text-xs text-text-muted flex gap-4">
        <span>Started: {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}</span>
        {run.completed_at && <span>Ended: {new Date(run.completed_at).toLocaleString()}</span>}
      </div>

      {llmOutputs?.length > 0 && (
        <div className="mt-3 space-y-2">
          {llmOutputs.map((o: any) => <LLMOutputCard key={o.id} output={o} />)}
        </div>
      )}

      {run.error_message && (
        <div className="mt-2 bg-accent-danger/5 border border-accent-danger/20 rounded-lg px-3 py-2">
          <div className="text-xs text-accent-danger font-medium">Error</div>
          <div className="text-xs text-text-secondary mt-0.5">{run.error_message}</div>
        </div>
      )}
    </div>
  )
}

export default function ReportsPage() {
  const [selectedPipe, setSelectedPipe] = useState<string>('')
  const [compareIds,   setCompareIds]   = useState<string[]>([])

  // Fetch the real pipelines (UUID ids) - no more hardcoded mock ids.
  const { data: pipelines, isLoading: pipesLoading } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => api.get('/pipelines').then((r) => r.data),
  })

  // Default to the first pipeline until the user picks one.
  const activePipe = selectedPipe || (pipelines?.[0]?.id ?? '')

  const { data: runsData, isLoading: runsLoading, isError } = useQuery({
    queryKey: ['runs', activePipe],
    queryFn: () => api.get(`/pipelines/${activePipe}/runs`).then((r) => r.data),
    enabled: !!activePipe,
  })

  const runs: any[] = runsData?.items?.filter((r: any) => r.status === 'COMPLETED') ?? []

  const toggleCompare = (id: string) => {
    setCompareIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev.slice(-1), id]
    )
  }

  if (pipesLoading || (!!activePipe && runsLoading)) return <TableSkeleton rows={4} />

  if (isError) return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
      <AlertCircle size={40} className="text-accent-danger" />
      <div className="text-text-secondary">Failed to load reports</div>
    </div>
  )

  const compareRuns = runs.filter((r) => compareIds.includes(r.id))

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Reports</h1>
          <p className="page-subtitle">AI-generated analysis and LLM recommendations from completed pipeline runs</p>
        </div>
        <div className="flex items-center gap-2">
          {(pipelines ?? []).map((p: any) => (
            <button
              key={p.id}
              className={cn('btn-ghost text-sm px-3 py-1.5',
                activePipe === p.id && 'bg-accent-primary/10 text-accent-primary border border-accent-primary/20'
              )}
              onClick={() => { setSelectedPipe(p.id); setCompareIds([]) }}
            >
              {p.name}
            </button>
          ))}
        </div>
      </div>

      {/* Comparison panel */}
      {compareRuns.length === 2 && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <GitCompare size={18} className="text-accent-secondary" />
            <span className="font-semibold text-text-primary">Run Comparison</span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {compareRuns.map((r) => (
              <div key={r.id} className="bg-bg-elevated rounded-xl p-4">
                <div className="text-xs text-text-muted font-mono mb-2">{r.id}</div>
                <div className={cn('text-4xl font-black',
                  r.confidence_score >= 0.8 ? 'text-accent-success' :
                  r.confidence_score >= 0.6 ? 'text-accent-warning' : 'text-accent-danger'
                )}>
                  {(r.confidence_score * 100).toFixed(0)}%
                </div>
                <div className="text-xs text-text-muted mt-1">
                  {new Date(r.started_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-text-muted mt-3 text-center">
            {(() => {
              const cmp = compareConfidence(compareRuns[0].confidence_score, compareRuns[1].confidence_score)
              if (cmp.winner === 'tie') return 'Both runs have equal confidence'
              const winnerRun = cmp.winner === 'a' ? compareRuns[0] : compareRuns[1]
              return `Run ${winnerRun.id.split('-').slice(0,3).join('-')} has higher confidence (+${cmp.deltaPct.toFixed(1)}%)`
            })()}
          </div>
        </div>
      )}

      {runs.length === 0 && (
        <div className="card p-12 flex flex-col items-center justify-center text-center">
          <FileText size={40} className="text-text-muted mb-4" />
          <div className="text-text-secondary font-medium">No completed runs yet</div>
          <div className="text-sm text-text-muted mt-1">Trigger a pipeline run from the Pipeline Monitor page</div>
        </div>
      )}

      <div className="space-y-4">
        {runs.map((run) => (
          <div key={run.id} className="relative">
            {compareIds.length < 2 || compareIds.includes(run.id) ? (
              <button
                className={cn(
                  'absolute top-3 right-3 z-10 btn-ghost text-xs px-2 py-1',
                  compareIds.includes(run.id) && 'text-accent-secondary'
                )}
                onClick={(e) => { e.stopPropagation(); toggleCompare(run.id) }}
                aria-label={compareIds.includes(run.id) ? 'Remove from comparison' : 'Add to comparison'}
              >
                <GitCompare size={12} />
                {compareIds.includes(run.id) ? 'Remove' : 'Compare'}
              </button>
            ) : null}
            <RunCard run={run} onSelect={() => {}} isSelected={compareIds.includes(run.id)} />
          </div>
        ))}
      </div>
    </div>
  )
}
