import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as Tabs from '@radix-ui/react-tabs'
import { Shield, Users, Code2, Plug2, Save, RotateCcw, AlertCircle, Loader2 } from 'lucide-react'
import api from '@/lib/axios'
import { useAuthStore, isAdmin, isSuperAdmin } from '@/store/auth'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { cn } from '@/lib/utils'

// ── Tab: Organisation ────────────────────────────────────────────────────────
function OrgTab() {
  const { user } = useAuthStore()
  return (
    <div className="space-y-4 max-w-lg">
      <div className="card p-5 space-y-4">
        <div className="text-sm font-semibold text-text-primary border-b border-border-subtle pb-3">Organisation Details</div>
        {[
          { label:'Organisation name', value: user?.org_name ?? '-' },
          { label:'Your role',         value: user?.role ?? '-' },
          { label:'Your email',        value: user?.email ?? '-' },
          { label:'Organisation ID',   value: `org-${user?.org_id ?? '?'}` },
        ].map(({ label, value }) => (
          <div key={label}>
            <div className="label">{label}</div>
            <div className="text-sm text-text-primary font-medium">{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tab: Users ───────────────────────────────────────────────────────────────
function UsersTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['users'],
    // Real API returns a bare array; the MSW mock returns { items: [...] }.
    queryFn: () => api.get('/auth/users').then((r) => (Array.isArray(r.data) ? r.data : r.data.items ?? [])),
  })

  const roleUpdate = useMutation({
    // Backend route is PATCH /auth/users/{id}/role (PUT returns 405).
    mutationFn: ({ id, role }: { id: number; role: string }) => api.patch(`/auth/users/${id}/role`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  if (isLoading) return <TableSkeleton rows={4} />

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-border-subtle flex items-center justify-between">
        <div className="text-sm font-semibold text-text-primary">Team Members</div>
        <div className="text-xs text-text-muted">{(data ?? []).length} users</div>
      </div>
      <table className="table-base" aria-label="Users list">
        <thead className="bg-bg-elevated">
          <tr>
            <th className="th" scope="col">Name</th>
            <th className="th" scope="col">Email</th>
            <th className="th" scope="col">Role</th>
            <th className="th" scope="col">Status</th>
            <th className="th" scope="col">Joined</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((u: any) => (
            <tr key={u.id} className="hover:bg-bg-elevated/40 transition-colors">
              <td className="td">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-gradient-primary flex items-center justify-center text-white text-xs font-bold">
                    {u.full_name?.[0]?.toUpperCase() ?? '?'}
                  </div>
                  <span className="font-medium">{u.full_name}</span>
                </div>
              </td>
              <td className="td text-text-muted">{u.email}</td>
              <td className="td">
                <select
                  className="text-xs py-1 px-2"
                  value={u.role}
                  onChange={(e) => roleUpdate.mutate({ id:u.id, role:e.target.value })}
                  aria-label={`Role for ${u.full_name}`}
                >
                  {['viewer','analyst','admin','super_admin'].map((r) => (
                    <option key={r} value={r}>{r.replace('_',' ')}</option>
                  ))}
                </select>
              </td>
              <td className="td">
                <span className={cn('badge', u.is_active ? 'badge-success' : 'badge-muted')}>
                  {u.is_active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td className="td text-text-muted text-xs">
                {new Date(u.created_at).toLocaleDateString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Tab: Prompts ─────────────────────────────────────────────────────────────
function PromptsTab() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editContent, setEditContent] = useState<string>('')
  const [saved, setSaved] = useState(false)

  const { data: prompts, isLoading } = useQuery({
    queryKey: ['prompts'],
    queryFn: () => api.get('/pipelines/prompts').then((r) => r.data),
  })

  const update = useMutation({
    mutationFn: ({ id, content }: { id: number; content: string }) =>
      api.put(`/pipelines/prompts/${id}`, { content }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey:['prompts'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  if (isLoading) return <div className="skeleton h-96 rounded-xl" />

  const selected = (prompts ?? []).find((p: any) => p.id === selectedId)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Prompt list */}
      <div className="space-y-2">
        {(prompts ?? []).map((p: any) => (
          <button
            key={p.id}
            className={cn('w-full text-left card p-3 transition-all',
              selectedId === p.id && 'border-accent-primary/50 bg-accent-primary/5')}
            onClick={() => { setSelectedId(p.id); setEditContent(p.content) }}
          >
            <div className="text-sm font-medium text-text-primary">{p.name}</div>
            <div className="text-xs text-text-muted mt-0.5">v{p.version} · {new Date(p.created_at).toLocaleDateString()}</div>
          </button>
        ))}
      </div>

      {/* Editor */}
      <div className="lg:col-span-2">
        {selected ? (
          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-text-primary">{selected.name}</div>
                <div className="text-xs text-text-muted">Version {selected.version} → will create v{selected.version+1}</div>
              </div>
              <div className="flex gap-2">
                <button
                  className="btn-secondary text-sm"
                  onClick={() => setEditContent(selected.content)}
                  aria-label="Reset prompt to saved version"
                >
                  <RotateCcw size={14} /> Reset
                </button>
                <button
                  id="save-prompt-btn"
                  className={cn('btn-primary text-sm', saved && 'bg-accent-success')}
                  onClick={() => update.mutate({ id:selected.id, content:editContent })}
                  disabled={update.isPending || editContent === selected.content || editContent.length < 50}
                >
                  {update.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  {saved ? 'Saved!' : 'Save & version'}
                </button>
              </div>
            </div>
            <textarea
              id="prompt-editor"
              className="w-full h-80 font-mono text-xs resize-none"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              aria-label="Prompt content editor"
            />
            {editContent.length < 50 && (
              <div className="text-xs text-accent-danger">Prompt must be at least 50 characters.</div>
            )}
          </div>
        ) : (
          <div className="card p-12 flex flex-col items-center justify-center text-center h-full">
            <Code2 size={32} className="text-text-muted mb-3" />
            <div className="text-text-secondary">Select a prompt to edit</div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main Settings page ────────────────────────────────────────────────────────
export default function SettingsPage() {
  const { user } = useAuthStore()
  const canAdmin = isAdmin(user?.role)
  const canSuper = isSuperAdmin(user?.role)

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Organisation, users, prompts, and integrations</p>
        </div>
      </div>

      <Tabs.Root defaultValue="org" className="space-y-4">
        <Tabs.List
          className="flex gap-1 bg-bg-elevated p-1 rounded-xl w-fit"
          aria-label="Settings tabs"
        >
          {[
            { value:'org',    label:'Organisation', Icon:Shield,  show:true },
            { value:'users',  label:'Users',        Icon:Users,   show:canAdmin },
            { value:'prompts',label:'Prompts',      Icon:Code2,   show:canSuper },
            { value:'integrations',label:'Integrations',Icon:Plug2,show:canAdmin },
          ].filter((t) => t.show).map(({ value, label, Icon }) => (
            <Tabs.Trigger
              key={value}
              value={value}
              id={`settings-tab-${value}`}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         text-text-muted transition-all
                         data-[state=active]:bg-bg-surface data-[state=active]:text-text-primary
                         data-[state=active]:shadow-card hover:text-text-primary"
            >
              <Icon size={15} aria-hidden />
              {label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="org"><OrgTab /></Tabs.Content>
        <Tabs.Content value="users">{canAdmin ? <UsersTab /> : null}</Tabs.Content>
        <Tabs.Content value="prompts">{canSuper ? <PromptsTab /> : null}</Tabs.Content>
        <Tabs.Content value="integrations">
          <div className="card p-12 flex flex-col items-center justify-center text-center max-w-lg">
            <Plug2 size={36} className="text-text-muted mb-4" />
            <div className="font-semibold text-text-primary">Integrations</div>
            <div className="text-sm text-text-muted mt-1">SSO, Slack, and Webhook integrations coming in v1.1.</div>
          </div>
        </Tabs.Content>
      </Tabs.Root>
    </div>
  )
}
