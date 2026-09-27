import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, History, AlertCircle, Loader2 } from 'lucide-react'
import api from '@/lib/axios'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 100

// Matches StepCard.tsx's formatDuration - kept as a local copy (same as that
// component) rather than a shared util, following this codebase's convention
// of small per-page formatting helpers.
function formatDuration(ms: number | null): string {
  if (!ms) return '-'
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

type ProcessLogStatus = 'COMPLETED' | 'FAILED' | 'RUNNING' | 'SKIPPED' | 'PENDING'

interface ProcessLogEntry {
  run_id: string
  pipeline_id: string
  step_number: number
  step_name: string
  status: ProcessLogStatus
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  error_detail: string | null
  triggered_by: number | null
  triggered_by_email: string | null
  triggered_by_name: string | null
}

function LogRow({ entry }: { entry: ProcessLogEntry }) {
  const [expanded, setExpanded] = useState(false)
  const canExpand = entry.status === 'FAILED' && !!entry.error_detail

  return (
    <>
      <tr
        className={cn('hover:bg-bg-elevated/40 transition-colors', canExpand && 'cursor-pointer')}
        onClick={canExpand ? () => setExpanded((v) => !v) : undefined}
        aria-expanded={canExpand ? expanded : undefined}
      >
        <td className="td text-text-muted text-xs whitespace-nowrap">
          {entry.started_at ? new Date(entry.started_at).toLocaleString() : '-'}
        </td>
        <td className="td text-text-secondary text-sm">
          {entry.triggered_by_name ?? entry.triggered_by_email ?? '-'}
        </td>
        <td className="td text-text-primary text-sm">
          <span className="text-text-muted mr-1.5">#{entry.step_number}</span>
          {entry.step_name}
        </td>
        <td className="td"><StatusBadge status={entry.status} /></td>
        <td className="td text-text-secondary text-sm whitespace-nowrap">{formatDuration(entry.duration_ms)}</td>
        <td className="td w-8">
          {canExpand && (
            expanded
              ? <ChevronUp size={14} className="text-text-muted" aria-hidden />
              : <ChevronDown size={14} className="text-text-muted" aria-hidden />
          )}
        </td>
      </tr>
      {expanded && canExpand && (
        <tr>
          <td colSpan={6} className="td border-t-0 pt-0 pb-3">
            <div className="bg-accent-danger/5 border border-accent-danger/20 rounded-lg px-3 py-2 text-xs text-accent-danger whitespace-pre-wrap">
              {entry.error_detail}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function ProcessLogPage() {
  // Optional ?run_id= filter - e.g. a future "view log" link from a specific
  // run. Org-scoping/module-scoping is enforced server-side (see
  // pipeline_router.get_process_log), so this page shows whatever the
  // endpoint returns without any client-side module filtering.
  const [searchParams] = useSearchParams()
  const runId = searchParams.get('run_id') ?? undefined

  const [offset, setOffset] = useState(0)
  const [entries, setEntries] = useState<ProcessLogEntry[]>([])

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ['process-log', runId, offset],
    queryFn: () =>
      api.get('/pipelines/process-log', {
        params: { limit: PAGE_SIZE, offset, ...(runId ? { run_id: runId } : {}) },
      }).then((r) => r.data as ProcessLogEntry[]),
  })

  // Reset accumulated pages when the run filter changes.
  useEffect(() => {
    setOffset(0)
    setEntries([])
  }, [runId])

  // Append each fetched page - offset 0 replaces (covers the filter-change
  // reset above), later offsets accumulate for "Load more".
  useEffect(() => {
    if (!data) return
    setEntries((prev) => (offset === 0 ? data : [...prev, ...data]))
  }, [data, offset])

  const hasMore = (data?.length ?? 0) === PAGE_SIZE

  if (isLoading) return <TableSkeleton rows={8} />

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <AlertCircle size={40} className="text-accent-danger" />
        <div className="text-text-secondary">Failed to load the process log</div>
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Process Log</h1>
          <p className="page-subtitle">
            {runId
              ? `Executed steps for run ${runId}`
              : 'History of executed pipeline steps across all runs'}
          </p>
        </div>
      </div>

      {entries.length === 0 && (
        <div className="card p-12 flex flex-col items-center justify-center text-center">
          <History size={40} className="text-text-muted mb-4" />
          <div className="text-text-secondary font-medium">No steps logged yet</div>
          <div className="text-sm text-text-muted mt-1">Trigger a pipeline run to see its steps appear here</div>
        </div>
      )}

      {entries.length > 0 && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="table-base" aria-label="Process log">
              <thead className="bg-bg-elevated">
                <tr>
                  <th className="th" scope="col">When</th>
                  <th className="th" scope="col">Who</th>
                  <th className="th" scope="col">Step</th>
                  <th className="th" scope="col">Status</th>
                  <th className="th" scope="col">Duration</th>
                  <th className="th" scope="col" aria-hidden />
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, i) => (
                  <LogRow key={`${entry.run_id}-${entry.step_number}-${i}`} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {hasMore && (
        <div className="flex justify-center">
          <button
            className="btn-secondary text-sm"
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            disabled={isFetching}
          >
            {isFetching ? <Loader2 size={15} className="animate-spin" /> : null}
            Load more
          </button>
        </div>
      )}
    </div>
  )
}
