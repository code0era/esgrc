import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { ChevronDown, ChevronRight, CheckCircle2, AlertCircle } from 'lucide-react'
import api from '@/lib/axios'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { useAuthStore, isAnalyst } from '@/store/auth'
import { cn } from '@/lib/utils'

const COMPLIANCE_COLORS: Record<string, string> = {
  compliant:     '#10b981',
  partial:       '#f59e0b',
  non_compliant: '#ef4444',
  not_assessed:  '#6b7280',
}

const STATUS_OPTIONS = ['compliant', 'partial', 'non_compliant', 'not_assessed']

function FrameworkCard({ fw, canEdit }: { fw: any; canEdit: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const qc = useQueryClient()

  const pieData = [
    { name:'Compliant',     value: fw.compliant,     key:'compliant'     },
    { name:'Partial',       value: fw.partial,        key:'partial'       },
    { name:'Non-Compliant', value: fw.non_compliant,  key:'non_compliant' },
    { name:'Not Assessed',  value: fw.not_assessed,   key:'not_assessed'  },
  ].filter((d) => d.value > 0)

  const compliancePct = fw.requirements_count > 0
    ? Math.round((fw.compliant / fw.requirements_count) * 100)
    : 0

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.patch(`/compliance/requirements/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['frameworks'] }),
  })

  const bulkUpdate = useMutation({
    // Backend: PATCH /compliance/requirements/bulk with a list of { id, status }.
    mutationFn: ({ ids, status }: { ids: number[]; status: string }) =>
      api.patch('/compliance/requirements/bulk', ids.map((id) => ({ id, status }))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['frameworks'] }); setSelected(new Set()) },
  })

  return (
    <div className="card overflow-hidden">
      {/* Framework header */}
      <div
        className="flex items-center gap-4 p-5 cursor-pointer hover:bg-bg-elevated/50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded((v) => !v) } }}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
      >
        <div className="w-10 h-10 flex items-center justify-center">
          {expanded ? <ChevronDown size={20} className="text-accent-primary" /> : <ChevronRight size={20} className="text-text-muted" />}
        </div>

        {/* Donut chart */}
        <div className="w-20 h-20 flex-shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={26} outerRadius={36} dataKey="value" startAngle={90} endAngle={-270}>
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={COMPLIANCE_COLORS[entry.key]} strokeWidth={0} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Info */}
        <div className="flex-1">
          <div className="text-base font-bold text-text-primary">{fw.name}</div>
          <div className="text-xs text-text-muted">{fw.version} · {fw.requirements_count} requirements</div>
          <div className="flex gap-3 mt-2">
            {pieData.map((d) => (
              <div key={d.key} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full" style={{ background: COMPLIANCE_COLORS[d.key] }} />
                <span className="text-xs text-text-muted">{d.value} {d.name.split('-')[0]}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Compliance % */}
        <div className="text-right flex-shrink-0">
          <div className={cn('text-2xl font-black',
            compliancePct >= 80 ? 'text-accent-success' :
            compliancePct >= 50 ? 'text-accent-warning' : 'text-accent-danger'
          )}>
            {compliancePct}%
          </div>
          <div className="text-xs text-text-muted">compliant</div>
        </div>
      </div>

      {/* Expanded requirements */}
      {expanded && (
        <div className="border-t border-border-subtle animate-fade-in">
          {/* Bulk actions */}
          {canEdit && selected.size > 0 && (
            <div className="flex items-center gap-3 px-5 py-3 bg-accent-primary/5 border-b border-border-subtle">
              <span className="text-sm text-accent-primary font-medium">{selected.size} selected</span>
              {STATUS_OPTIONS.map((s) => (
                <button
                  key={s}
                  className="btn-ghost text-xs px-2 py-1"
                  onClick={() => bulkUpdate.mutate({ ids: [...selected], status: s })}
                >
                  Mark {s.replace('_', ' ')}
                </button>
              ))}
              <button className="btn-ghost text-xs px-2 py-1 ml-auto" onClick={() => setSelected(new Set())}>Clear</button>
            </div>
          )}
          <table className="table-base" aria-label={`${fw.name} requirements`}>
            <thead className="bg-bg-elevated">
              <tr>
                {canEdit && <th className="th w-10" scope="col"><span className="sr-only">Select</span></th>}
                <th className="th" scope="col">Code</th>
                <th className="th" scope="col">Requirement</th>
                <th className="th" scope="col">Status</th>
                <th className="th" scope="col">Evidence</th>
                <th className="th" scope="col">Review Date</th>
              </tr>
            </thead>
            <tbody>
              {fw.requirements.map((req: any) => (
                <tr key={req.id} className="hover:bg-bg-elevated/40 transition-colors">
                  {canEdit && (
                    <td className="td">
                      <input
                        type="checkbox"
                        className="w-4 h-4 accent-accent-primary cursor-pointer"
                        checked={selected.has(req.id)}
                        onChange={(e) => {
                          const s = new Set(selected)
                          e.target.checked ? s.add(req.id) : s.delete(req.id)
                          setSelected(s)
                        }}
                        aria-label={`Select requirement ${req.code}`}
                      />
                    </td>
                  )}
                  <td className="td font-mono text-xs text-accent-primary font-bold">{req.code}</td>
                  <td className="td text-sm font-medium">{req.title}</td>
                  <td className="td">
                    {canEdit ? (
                      <select
                        className="text-xs py-1 px-2"
                        value={req.status}
                        onChange={(e) => updateMutation.mutate({ id: req.id, status: e.target.value })}
                        aria-label={`Status for ${req.code}`}
                      >
                        {STATUS_OPTIONS.map((s) => (
                          <option key={s} value={s}>{s.replace(/_/g,' ')}</option>
                        ))}
                      </select>
                    ) : (
                      <StatusBadge status={req.status} />
                    )}
                  </td>
                  <td className="td text-xs text-text-muted">{req.evidence ?? '-'}</td>
                  <td className="td text-xs text-text-muted">
                    {req.review_date ? new Date(req.review_date).toLocaleDateString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function CompliancePage() {
  const { user } = useAuthStore()
  const canEdit  = isAnalyst(user?.role)

  // The real API splits this across three endpoints:
  //   /compliance/summary       → per-framework counts (no requirements, no version)
  //   /compliance/requirements  → all requirement rows (bare array)
  //   /compliance/frameworks    → framework name + version
  // Merge them into the rich { …counts, requirements[] } shape the cards render.
  const { data, isLoading, isError } = useQuery({
    queryKey: ['frameworks'],
    queryFn: async () => {
      const [summary, reqs, fwList] = await Promise.all([
        api.get('/compliance/summary').then((r) => r.data),
        api.get('/compliance/requirements').then((r) => (Array.isArray(r.data) ? r.data : r.data.items ?? [])),
        api.get('/compliance/frameworks').then((r) => (Array.isArray(r.data) ? r.data : r.data.items ?? [])).catch(() => []),
      ])
      // MSW mock already returns the rich framework array - pass it through.
      if (Array.isArray(summary)) return summary
      const versionById: Record<number, string> = {}
      fwList.forEach((f: any) => { versionById[f.id] = f.version ?? '' })
      const reqsByFw: Record<number, any[]> = {}
      reqs.forEach((rq: any) => { (reqsByFw[rq.framework_id] ??= []).push(rq) })
      return (summary.frameworks ?? []).map((f: any) => ({
        id:                 f.framework_id,
        name:               f.framework_name,
        version:            versionById[f.framework_id] ?? '',
        requirements_count: f.total,
        compliant:          f.compliant,
        partial:            f.partial,
        non_compliant:      f.non_compliant,
        not_assessed:       f.not_assessed,
        requirements:       reqsByFw[f.framework_id] ?? [],
      }))
    },
  })

  if (isLoading) return <TableSkeleton rows={4} />

  if (isError) return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
      <AlertCircle size={40} className="text-accent-danger" />
      <div className="text-text-secondary">Failed to load compliance data</div>
    </div>
  )

  const frameworks: any[] = data ?? []
  const totalReqs   = frameworks.reduce((s, f) => s + f.requirements_count, 0)
  const totalOk     = frameworks.reduce((s, f) => s + f.compliant, 0)
  const globalRate  = totalReqs > 0 ? Math.round((totalOk / totalReqs) * 100) : 0

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Compliance</h1>
          <p className="page-subtitle">Framework adherence across {frameworks.length} active standards</p>
        </div>
        <div className="flex items-center gap-3">
          <div className={cn('text-4xl font-black',
            globalRate >= 80 ? 'text-accent-success' :
            globalRate >= 50 ? 'text-accent-warning' : 'text-accent-danger'
          )}>
            {globalRate}%
          </div>
          <div className="text-xs text-text-muted">global<br/>rate</div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label:'Total Requirements', value: totalReqs,  color:'text-text-primary' },
          { label:'Compliant',          value: totalOk,    color:'text-accent-success' },
          { label:'Partial',            value: frameworks.reduce((s,f)=>s+f.partial,0), color:'text-accent-warning' },
          { label:'Non-Compliant',      value: frameworks.reduce((s,f)=>s+f.non_compliant,0), color:'text-accent-danger' },
        ].map(({ label, value, color }) => (
          <div key={label} className="card p-4">
            <div className="text-xs text-text-muted uppercase tracking-wider">{label}</div>
            <div className={cn('text-3xl font-black mt-1', color)}>{value}</div>
          </div>
        ))}
      </div>

      {/* Framework cards */}
      <div className="space-y-4">
        {frameworks.map((fw) => (
          <FrameworkCard key={fw.id} fw={fw} canEdit={canEdit} />
        ))}
      </div>
    </div>
  )
}
