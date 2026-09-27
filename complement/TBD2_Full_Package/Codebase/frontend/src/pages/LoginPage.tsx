import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, Zap, Loader2 } from 'lucide-react'
import api from '@/lib/axios'
import { useAuthStore } from '@/store/auth'

export default function LoginPage() {
  const navigate   = useNavigate()
  const setAuth    = useAuthStore((s) => s.setAuth)
  const setTokens  = useAuthStore((s) => s.setTokens)

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [showPw,   setShowPw]   = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const { data } = await api.post('/auth/login', { email, password })
      // The real backend returns only tokens (no user object); the mock returns
      // { ...tokens, user }. Handle both: if no user, fetch it from /auth/me.
      let user = data.user
      if (!user) {
        setTokens(data.access_token, data.refresh_token) // so the interceptor attaches it to /auth/me
        const me = await api.get('/auth/me')
        const snap = await api.get('/org/snapshot').catch(() => ({ data: {} }))
        user = {
          id:        me.data.id,
          email:     me.data.email,
          full_name: me.data.full_name,
          role:      me.data.role,
          org_id:    me.data.organisation_id ?? me.data.org_id,
          org_name:  snap.data?.org_name ?? '',
          module_access: me.data.module_access ?? [],
        }
      }
      setAuth(user, data.access_token, data.refresh_token)
      // Land on a page the user's module scope allows (an Apex-only user has no
      // ESGRC dashboard/risk/compliance access → send them to Pipeline).
      const mods = user.module_access ?? []
      const canEsgrc = user.role === 'super_admin' || mods.length === 0 || mods.includes('esgrc')
      navigate(canEsgrc ? '/dashboard' : '/pipeline', { replace: true })
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Login failed. Check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-base relative overflow-hidden">
      {/* Animated background glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-accent-primary/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-accent-secondary/10 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md mx-4">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-primary shadow-glow-primary mb-4">
            <Zap size={30} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold text-text-primary">TBD2</h1>
          <p className="text-text-secondary mt-1 text-sm">AI-Powered Enterprise Risk Intelligence</p>
        </div>

        {/* Card */}
        <div className="card p-8">
          <h2 className="text-xl font-bold text-text-primary mb-6">Sign in</h2>

          {error && (
            <div className="bg-accent-danger/10 border border-accent-danger/30 rounded-lg px-4 py-3 mb-5 text-sm text-accent-danger">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="login-email" className="label">Email address</label>
              <input
                id="login-email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full"
                aria-describedby={error ? 'login-error' : undefined}
              />
            </div>

            <div>
              <label htmlFor="login-password" className="label">Password</label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pr-10"
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                  onClick={() => setShowPw((v) => !v)}
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              id="login-submit-btn"
              className="btn-primary w-full justify-center py-3 text-base"
              disabled={loading || !email || !password}
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : 'Sign in'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-text-muted">
            Don't have an account?{' '}
            <Link to="/register" className="text-accent-primary hover:underline">Create one</Link>
          </div>
        </div>

        <p className="text-center text-xs text-text-muted mt-6">
          © 2026 TBD2 · Enterprise Risk Intelligence Platform
        </p>
      </div>
    </div>
  )
}
