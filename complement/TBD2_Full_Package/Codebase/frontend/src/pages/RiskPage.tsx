import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Filter, ChevronUp, ChevronDown, AlertCircle } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import api from '@/lib/axios'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { useAuthStore, isAnalyst } from '@/store/auth'
import { cn } from '@/lib/utils'
import { normalizeList } from '@/lib/normalize'

const RISK_LEVELS = ['critical','high','medium','low'] as const
type RiskLevel = typeof RISK_LEVELS[number]

const LEVEL_COLORS: Record<RiskLevel, string> = {
  critical: 'bg-accent-danger/80',
  high:     'bg-accent-warning/80',
  medium:   'bg-yellow-500/60',
  low:      'bg-accent-success/60',
}

function RiskHeatmap({ risks }: { risks: any[] }) {
  const [selected, setSelected] = useState<{l:number;i:number} | null>(null)

  const getCount = (l: number, i: number) =>
    risks.filter((r) => r.likelihood === l && r.impact === i).length

  const getColor = (l: number, i: number) => {
    const score = l * i
    if (score >= 16) return 'bg-accent-danger hover:bg-accent-danger/80'
    if (score >= 9)  return 'bg-accent-warning hover:bg-accent-warning/80'
    if (score >= 4)  return 'bg-yellow-600 hover:bg-yellow-500'
    return 'bg-accent-success/70 hover:bg-accent-success/60'
  }

  return (
    <div className="card p-5">
      <div className="text-sm font-semibold text-text-primary mb-4">5×5 Risk Heatmap</div>
      <div className="flex gap-4">
        <div className="flex flex-col justify-end">
          <div className="text-xs text-text-muted text-center mb-1 -rotate-90 translate-y-12 w-20">← Likelihood</div>
        </div>
        <div>
          <div className="flex gap-1 mb-1">
            {[1,2,3,4,5].map((i) => (
              <div key={i} className="w-12 text-center text-xs text-text-muted">{i}</div>
            ))}
          </div>
          {[5,4,3,2,1].map((likelihood) => (
            <div key={likelihood} className="flex gap-1 mb-1 items-center">
              <span className="text-xs text-text-muted w-4 text-right mr-1">{likelihood}</span>
              {[1,2,3,4,5].map((impact) => {
                const count = getCount(likelihood, impact)
                const isSelected = selected?.l === likelihood && selected?.i === impact
                return (
                  <button
                    key={impact}
                    className={cn(
                      'w-12 h-12 rounded-lg text-white font-bold text-sm transition-all cursor-pointer',
                      getColor(likelihood, impact),
                      isSelected && 'ring-2 ring-white scale-110',
                      count === 0 && 'opacity-40'
                    )}
                    onClick={() => setSelected(isSelected ? null : { l:likelihood, i:impact })}
                    aria-label={`Cell: likelihood ${likelihood}, impact ${impact}, ${count} risks`}
                  >
                    {count > 0 ? count : ''}
                  </button>
                )
              })}
            </div>
          ))}
          <div className="text-xs text-text-muted text-center mt-2">Impact →</div>
        </div>
      </div>
      {selected && (
        <div className="mt-3 text-xs text-text-secondary bg-bg-elevated rounded-lg px-3 py-2">
          Showing risks at L{selected.l}×I{selected.i} (score {selected.l * selected.i}).
          {getCount(selected.l, selected.i) === 0 && ' No risks at this cell.'}
        </div>
      )}
    </div>
  )
}

function RiskForm({ initial, onSave, onCancel }: { initial?: any; onSave: (data: any) => void; onCancel: () => void }) {
  const [form, setForm] = useState(initial ?? {
    title:'', category:'operational', likelihood:3, impact:3, status:'open', owner:'', description:'', due_date:''
  })
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))

  return (
    <div className="space-y-4">
      <div><label className="label">Title</label>
        <input className="w-full" value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="Risk title" /></div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className="label">Category</label>
          <select className="w-full" value={form.category} onChange={(e) => set('category', e.target.value)}>
            {['operational','cyber','hr','environmental','governance','financial'].map((c) => (
              <option key={c} value={c}>{c.charAt(0).toUpperCase()+c.slice(1)}</option>
            ))}
          </select></div>
        <div><label className="label">Status</label>
          <select className="w-full" value={form.status} onChange={(e) => set('status', e.target.value)}>
            {['open','in_progress','mitigated','closed'].map((s) => (
              <option key={s} value={s}>{s.replace('_',' ')}</option>
            ))}
          </select></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className="label">Likelihood (1-5)</label>
          <input type="range" min={1} max={5} className="w-full" value={form.likelihood} onChange={(e) => set('likelihood', Number(e.target.value))} />
          <div className="text-xs text-accent-primary text-center">{form.likelihood}</div></div>
        <div><label className="label">Impact (1-5)</label>
          <input type="range" min={1} max={5} className="w-full" value={form.impact} onChange={(e) => set('impact', Number(e.target.value))} />
          <div className="text-xs text-accent-primary text-center">{form.impact}</div></div>
      </div>
      <div><label className="label">Owner</label>
        <input className="w-full" value={form.owner} onChange={(e) => set('owner', e.target.value)} placeholder="Team or person" /></div>
      <div><label className="label">Description</label>
        <textarea className="w-full" rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} placeholder="Risk description..." /></div>
      <div><label className="label">Due date</label>
        <input type="date" className="w-full" value={form.due_date} onChange={(e) => set('due_date', e.target.value)} /></div>
      <div className="flex gap-2 pt-2">
        <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="btn-primary" onClick={() => onSave(form)}>Save risk</button>
      </div>
    </div>
  )
}

export default function RiskPage() {
  const { user }   = useAuthStore()
  const qc         = useQueryClient()
  const [sortKey, setSortKey]     = useState<string>('risk_score')
  const [sortDir, setSortDir]     = useState<'asc'|'desc'>('desc')
  const [statusFilter, setStatusFilter] = useState('all')
  const [showForm, setShowForm]   = useState(false)
  const [editRisk, setEditRisk]   = useState<any | null>(null)
  const canEdit = isAnalyst(user?.role)

  const { data, isLoading } = useQuery({
    queryKey: ['risks'],
    // Real API returns a bare array; the MSW mock returns { items: [...] }.
    queryFn: () => api.get('/risks').then((r) => normalizeList(r.data)),
  })

  const createMutation = useMutation({
    mutationFn: (body: any) => api.post('/risks', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey:['risks'] }); setShowForm(false) },
  })
  const updateMutation = useMutation({
    // PATCH, not PUT: the API serves PATCH /risks/{risk_id} (partial update).
    // This called PUT and returned 405 against the real backend. It was hidden
    // because the MSW mock answered PUT, so it worked in dev and only in dev.
    mutationFn: ({ id, ...body }: any) => api.patch(`/risks/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey:['risks'] }); setEditRisk(null) },
  })

  const risks: any[] = data ?? []

  const sorted = [...risks]
    .filter((r) => statusFilter === 'all' || r.status === statusFilter)
    .sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      return sortDir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
    })

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const SortIcon = ({ k }: { k: string }) =>
    sortKey === k ? (sortDir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />) : null

  if (isLoading) return <TableSkeleton rows={6} />

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Risk Register</h1>
          <p className="page-subtitle">Identify, assess and manage enterprise risks</p>
        </div>
        {canEdit && (
          <button className="btn-primary" onClick={() => setShowForm(true)} id="add-risk-btn">
            <Plus size={16} /> Add risk
          </button>
        )}
      </div>

      {/* Heatmap */}
      <RiskHeatmap risks={risks} />

      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <Filter size={15} className="text-text-muted" />
        <span className="text-sm text-text-muted">Status:</span>
        {['all','open','in_progress','mitigated','closed'].map((s) => (
          <button
            key={s}
            className={cn('btn-ghost text-xs px-3 py-1',
              statusFilter === s && 'bg-accent-primary/10 text-accent-primary border border-accent-primary/20')}
            onClick={() => setStatusFilter(s)}
          >
            {s === 'all' ? 'All' : s.replace('_', ' ')}
          </button>
        ))}
        <span className="ml-auto text-xs text-text-muted">{sorted.length} risks</span>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table-base" aria-label="Risk register">
            <thead className="bg-bg-elevated">
              <tr>
                {[
                  { label:'Risk', key:'title' },
                  { label:'Category', key:'category' },
                  { label:'L', key:'likelihood' },
                  { label:'I', key:'impact' },
                  { label:'Score', key:'risk_score' },
                  { label:'Status', key:'status' },
                  { label:'Owner', key:'owner' },
                  { label:'Due', key:'due_date' },
                ].map(({ label, key }) => (
                  <th key={key} className="th cursor-pointer select-none group" onClick={() => toggleSort(key)} scope="col">
                    <div className="flex items-center gap-1">
                      {label}<SortIcon k={key} />
                    </div>
                  </th>
                ))}
                {canEdit && <th className="th" scope="col">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.id} className="hover:bg-bg-elevated/40 transition-colors">
                  <td className="td">
                    <div className="font-medium text-text-primary max-w-xs truncate">{r.title}</div>
                    {r.description && <div className="text-xs text-text-muted mt-0.5 max-w-xs truncate">{r.description}</div>}
                  </td>
                  <td className="td"><span className="badge badge-muted capitalize">{r.category}</span></td>
                  <td className="td text-center font-bold text-text-secondary">{r.likelihood}</td>
                  <td className="td text-center font-bold text-text-secondary">{r.impact}</td>
                  <td className="td">
                    <span className={cn('text-lg font-black',
                      r.risk_score >= 16 ? 'text-accent-danger' :
                      r.risk_score >= 9  ? 'text-accent-warning' :
                      r.risk_score >= 4  ? 'text-yellow-400' : 'text-accent-success'
                    )}>
                      {r.risk_score}
                    </span>
                  </td>
                  <td className="td"><StatusBadge status={r.status} /></td>
                  <td className="td text-text-secondary text-sm">{r.owner}</td>
                  <td className="td text-text-muted text-xs">
                    {r.due_date ? new Date(r.due_date).toLocaleDateString() : '-'}
                  </td>
                  {canEdit && (
                    <td className="td">
                      <button className="btn-ghost text-xs px-2 py-1"
                        onClick={() => setEditRisk(r)}>Edit</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add form dialog */}
      <Dialog.Root open={showForm} onOpenChange={setShowForm}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 animate-fade-in" />
          <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
            w-full max-w-lg bg-bg-surface border border-border-default rounded-2xl shadow-card-hover z-50 p-6 animate-slide-up"
            aria-describedby="add-risk-desc">
            <Dialog.Title className="text-lg font-bold text-text-primary mb-4">Add new risk</Dialog.Title>
            <Dialog.Description id="add-risk-desc" className="text-sm text-text-secondary mb-4">
              Define the risk details and assessment.
            </Dialog.Description>
            <RiskForm
              onSave={(data) => createMutation.mutate(data)}
              onCancel={() => setShowForm(false)}
            />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Edit form dialog */}
      <Dialog.Root open={!!editRisk} onOpenChange={(open) => !open && setEditRisk(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 animate-fade-in" />
          <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
            w-full max-w-lg bg-bg-surface border border-border-default rounded-2xl shadow-card-hover z-50 p-6 animate-slide-up"
            aria-describedby="edit-risk-desc">
            <Dialog.Title className="text-lg font-bold text-text-primary mb-4">Edit risk</Dialog.Title>
            <Dialog.Description id="edit-risk-desc" className="sr-only">Edit the risk details</Dialog.Description>
            {editRisk && (
              <RiskForm
                initial={editRisk}
                onSave={(data) => updateMutation.mutate({ id:editRisk.id, ...data })}
                onCancel={() => setEditRisk(null)}
              />
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
