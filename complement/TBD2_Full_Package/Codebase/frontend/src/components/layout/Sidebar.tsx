import { NavLink, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  LayoutDashboard, ShieldAlert, ClipboardCheck,
  GitBranch, FileText, History, Settings, LogOut, Zap,
} from 'lucide-react'
import { useAuthStore, isAdmin, hasModule } from '@/store/auth'
import { cn } from '@/lib/utils'
import api from '@/lib/axios'

// `module`: gate the item to users who can access that module (super_admin sees
// all). Dashboard/Risk/Compliance are ESGRC-module data; Pipeline/Reports are
// shared (the pipeline list is already module-filtered by the API).
const NAV_ITEMS = [
  { to: '/dashboard',   label: 'Dashboard',    Icon: LayoutDashboard, roles: null, module: 'esgrc' },
  { to: '/risk',        label: 'Risk Register',Icon: ShieldAlert,     roles: null, module: 'esgrc' },
  { to: '/compliance',  label: 'Compliance',   Icon: ClipboardCheck,  roles: null, module: 'esgrc' },
  { to: '/pipeline',    label: 'Pipeline',     Icon: GitBranch,       roles: null, module: null },
  { to: '/reports',     label: 'Reports',      Icon: FileText,        roles: null, module: null },
  { to: '/process-log', label: 'Process Log',  Icon: History,         roles: null, module: null },
  { to: '/settings',    label: 'Settings',     Icon: Settings,        roles: ['admin', 'super_admin'] as const, module: null },
]

export function Sidebar() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const handleLogout = async () => {
    try { await api.post('/auth/logout') } catch {}
    logout()
    // The QueryClient is a singleton that outlives this SPA navigation - without
    // clearing it, the next user to log in on this tab (a different org) would
    // see this org's cached dashboard/risk/compliance/user data until every
    // query's staleTime expired and it happened to refetch.
    queryClient.clear()
    navigate('/login')
  }

  return (
    <aside className="w-64 h-screen flex flex-col bg-bg-surface border-r border-border-subtle sticky top-0">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-border-subtle">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-primary flex items-center justify-center shadow-glow-primary">
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <div className="font-bold text-text-primary tracking-tight">TBD2</div>
            <div className="text-[10px] text-text-muted uppercase tracking-widest">Risk Intelligence</div>
          </div>
        </div>
      </div>

      {/* Org badge */}
      <div className="px-5 py-3 border-b border-border-subtle">
        <div className="text-xs text-text-muted uppercase tracking-wider mb-0.5">Organisation</div>
        <div className="text-sm font-medium text-text-primary truncate">{user?.org_name}</div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="Main navigation">
        {NAV_ITEMS.filter((item) => {
          if (item.roles && !item.roles.includes(user?.role as any)) return false
          if (item.module && !hasModule(user, item.module)) return false
          return true
        }).map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(isActive ? 'nav-link-active' : 'nav-link')
            }
            aria-label={label}
          >
            <Icon size={18} aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User panel */}
      <div className="px-3 py-4 border-t border-border-subtle">
        <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-bg-elevated mb-2">
          <div className="w-8 h-8 rounded-full bg-gradient-primary flex items-center justify-center text-white text-sm font-bold">
            {user?.full_name?.[0] ?? 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-text-primary truncate">{user?.full_name}</div>
            <div className="text-xs text-text-muted capitalize">{user?.role}</div>
          </div>
        </div>
        <button
          className="btn-ghost w-full justify-start text-accent-danger hover:text-accent-danger"
          onClick={handleLogout}
          aria-label="Log out"
        >
          <LogOut size={16} />
          Log out
        </button>
      </div>
    </aside>
  )
}
