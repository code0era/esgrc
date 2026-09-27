import { useQuery } from '@tanstack/react-query'
import {
  RadialBarChart, RadialBar, ResponsiveContainer, Tooltip, Legend,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import {
  TrendingUp, TrendingDown, Minus, Activity, AlertCircle, CheckCircle2, Loader2,
} from 'lucide-react'
import api from '@/lib/axios'
import { DashboardSkeleton } from '@/components/ui/Skeleton'
import { cn } from '@/lib/utils'
import { normalizeDashboard } from '@/lib/normalize'

function ScoreGauge({ score }: { score: number }) {
  const color = score >= 70 ? '#10b981' : score >= 50 ? '#f59e0b' : '#ef4444'
  return (
    <div className="flex flex-col items-center">
      <div
        className={cn(
          'text-7xl font-black tabular-nums',
          score >= 70 ? 'text-accent-success' : score >= 50 ? 'text-accent-warning' : 'text-accent-danger'
        )}
        style={{ textShadow: `0 0 40px ${color}40` }}
      >
        {score.toFixed(1)}
      </div>
      <div className="text-text-muted text-sm mt-1">Overall ESG Score</div>
      <div className="mt-3 h-2 w-48 rounded-full bg-bg-elevated overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-1000"
          style={{ width:`${score}%`, background:`linear-gradient(90deg, ${color}80, ${color})` }}
        />
      </div>
    </div>
  )
}

function TrendIcon({ trend }: { trend: number }) {
  if (trend > 0) return <TrendingUp size={13} className="text-accent-success" />
  if (trend < 0) return <TrendingDown size={13} className="text-accent-danger" />
  return <Minus size={13} className="text-text-muted" />
}

function AgentStatusWidget() {
  const { data, isLoading } = useQuery({
    queryKey: ['agent-status'],
    queryFn: () => api.get('/agent/status').then((r) => r.data),
    refetchInterval: 60_000,
  })

  if (isLoading) return <div className="skeleton h-20 rounded-xl" />

  const statusColor = data?.last_run_status === 'success' ? 'accent-success' : 'accent-danger'
  return (
    <div className="card p-4 flex items-center gap-4">
      <div className={cn('w-10 h-10 rounded-full flex items-center justify-center',
        data?.last_run_status === 'success' ? 'bg-accent-success/10' : 'bg-accent-danger/10'
      )}>
        {data?.last_run_status === 'success'
          ? <CheckCircle2 size={20} className="text-accent-success" />
          : <AlertCircle  size={20} className="text-accent-danger" />}
      </div>
      <div className="flex-1">
        <div className="text-sm font-medium text-text-primary">Scoring Agent</div>
        <div className="text-xs text-text-muted">
          Last run: {data?.last_run_at ? new Date(data.last_run_at).toLocaleString() : '-'}
          {' · '}{data?.metrics_scored ?? 0} metrics scored
          {' · '}{data?.requirements_flagged ?? 0} flagged
        </div>
      </div>
      <div className={`sse-dot w-2 h-2 rounded-full bg-${statusColor}`} />
    </div>
  )
}

export default function DashboardPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/esg/dashboard').then((r) => normalizeDashboard(r.data)),
  })

  if (isLoading) return <DashboardSkeleton />

  if (isError) return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
      <AlertCircle size={40} className="text-accent-danger" />
      <div className="text-text-secondary">Failed to load dashboard data</div>
      <button className="btn-primary" onClick={() => refetch()}>Retry</button>
    </div>
  )

  if (!data) return null

  const radialData = [
    { name:'Governance',    value: data.pillar_scores.governance,    fill:'#8b5cf6' },
    { name:'Social',        value: data.pillar_scores.social,        fill:'#3b82f6' },
    { name:'Environmental', value: data.pillar_scores.environmental, fill:'#10b981' },
  ]

  const trendData = data.categories.slice(0, 6).map((c: any, i: number) => ({
    name: c.name.split(' ')[0],
    score: c.score,
    prev:  Math.round(c.score - c.trend),
  }))

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">ESG Dashboard</h1>
          <p className="page-subtitle">Real-time environmental, social &amp; governance performance</p>
        </div>
        <div className="text-xs text-text-muted">
          Updated: {data.last_updated ? new Date(data.last_updated).toLocaleString() : '-'}
        </div>
      </div>

      {/* Agent status */}
      <AgentStatusWidget />

      {/* Top stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Org score */}
        <div className="card p-6 lg:col-span-1 flex flex-col items-center justify-center">
          <ScoreGauge score={data.org_score} />
        </div>

        {/* Pillar scores */}
        {([
          { label:'Environmental', key:'environmental', color:'text-accent-success', bg:'bg-accent-success/10' },
          { label:'Social',        key:'social',        color:'text-accent-info',    bg:'bg-accent-info/10' },
          { label:'Governance',    key:'governance',    color:'text-accent-secondary', bg:'bg-accent-secondary/10' },
        ] as const).map(({ label, key, color, bg }) => (
          <div key={key} className="card p-5 flex flex-col gap-3">
            <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center', bg)}>
              <Activity size={18} className={color} />
            </div>
            <div>
              <div className="text-text-muted text-xs uppercase tracking-wider">{label}</div>
              <div className={cn('text-3xl font-bold mt-1', color)}>
                {data.pillar_scores[key].toFixed(1)}
              </div>
            </div>
            <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
              <div
                className={cn('h-full rounded-full', color.replace('text-', 'bg-'))}
                style={{ width:`${data.pillar_scores[key]}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Radial bar */}
        <div className="card p-5">
          <div className="text-sm font-semibold text-text-primary mb-4">Score by Pillar</div>
          <ResponsiveContainer width="100%" height={240}>
            <RadialBarChart cx="50%" cy="50%" innerRadius={50} outerRadius={110} data={radialData}>
              <RadialBar dataKey="value" cornerRadius={6} />
              <Tooltip
                contentStyle={{ background:'#111827', border:'1px solid #1f2937', borderRadius:8 }}
                labelStyle={{ color:'#f9fafb' }}
                formatter={(v: any) => [`${v.toFixed(1)}`, 'Score']}
              />
              <Legend
                iconType="circle"
                formatter={(v) => <span className="text-xs text-text-secondary">{v}</span>}
              />
            </RadialBarChart>
          </ResponsiveContainer>
        </div>

        {/* Area chart */}
        <div className="card p-5">
          <div className="text-sm font-semibold text-text-primary mb-4">Category Score Trend</div>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={trendData} margin={{ top:4, right:4, bottom:0, left:-20 }}>
              <defs>
                <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="name" tick={{ fill:'#6b7280', fontSize:11 }} />
              <YAxis domain={[0,100]} tick={{ fill:'#6b7280', fontSize:11 }} />
              <Tooltip
                contentStyle={{ background:'#111827', border:'1px solid #1f2937', borderRadius:8 }}
                labelStyle={{ color:'#f9fafb' }}
              />
              <Area type="monotone" dataKey="score" stroke="#6366f1" fill="url(#scoreGrad)" strokeWidth={2} dot={{ fill:'#6366f1', r:3 }} />
              <Area type="monotone" dataKey="prev"  stroke="#374151" fill="none" strokeWidth={1} strokeDasharray="4 4" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Category table */}
      <div className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-border-subtle flex items-center justify-between">
          <div className="text-sm font-semibold text-text-primary">Category Scores</div>
          <div className="text-xs text-text-muted">{data.categories.length} metrics</div>
        </div>
        <div className="overflow-x-auto">
          <table className="table-base" aria-label="ESG category scores">
            <thead className="bg-bg-elevated">
              <tr>
                <th className="th" scope="col">Category</th>
                <th className="th" scope="col">Pillar</th>
                <th className="th" scope="col">Code</th>
                <th className="th" scope="col">Score</th>
                <th className="th" scope="col">Trend</th>
                <th className="th" scope="col">Period</th>
              </tr>
            </thead>
            <tbody>
              {[...data.categories]
                .sort((a: any, b: any) => b.score - a.score)
                .map((cat: any) => (
                <tr key={cat.id} className="hover:bg-bg-elevated/50 transition-colors">
                  <td className="td font-medium">{cat.name}</td>
                  <td className="td">
                    <span className={cn('badge',
                      cat.pillar === 'environmental' ? 'badge-success' :
                      cat.pillar === 'social'        ? 'badge-info'    : 'badge-violet'
                    )}>
                      {cat.pillar}
                    </span>
                  </td>
                  <td className="td text-text-muted font-mono text-xs">{cat.metric_code}</td>
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width:`${cat.score}%`,
                            background: cat.score >= 70 ? '#10b981' : cat.score >= 50 ? '#f59e0b' : '#ef4444',
                          }}
                        />
                      </div>
                      <span className={cn('text-sm font-bold',
                        cat.score >= 70 ? 'text-accent-success' :
                        cat.score >= 50 ? 'text-accent-warning' : 'text-accent-danger'
                      )}>
                        {cat.score}
                      </span>
                    </div>
                  </td>
                  <td className="td">
                    <div className="flex items-center gap-1">
                      <TrendIcon trend={cat.trend} />
                      <span className={cn('text-xs',
                        cat.trend > 0 ? 'text-accent-success' :
                        cat.trend < 0 ? 'text-accent-danger' : 'text-text-muted'
                      )}>
                        {cat.trend > 0 ? '+' : ''}{cat.trend.toFixed(1)}
                      </span>
                    </div>
                  </td>
                  <td className="td text-text-muted text-xs">{cat.period}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
