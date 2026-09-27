import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Zap, Loader2 } from 'lucide-react'
import api from '@/lib/axios'
import { useAuthStore } from '@/store/auth'

export default function RegisterPage() {
  const navigate  = useNavigate()
  const setAuth   = useAuthStore((s) => s.setAuth)
  const setTokens = useAuthStore((s) => s.setTokens)

  const [form, setForm] = useState({ email:'', full_name:'', password:'', organisation_slug:'' })
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  const set = (field: string, val: string) => setForm((f) => ({ ...f, [field]: val }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const { data: registered } = await api.post('/auth/register', form)
      // Real backend's POST /auth/register returns UserOut only - no tokens,
      // registration does not log the user in. The mock returns
      // { ...tokens, user } and skips this. Either way, log in with the same
      // credentials right after to get a real token pair.
      let user = registered.user
      let data = registered
      if (!user) {
        const loginRes = await api.post('/auth/login', { email: form.email, password: form.password })
        data = loginRes.data
        setTokens(data.access_token, data.refresh_token)
        const me   = await api.get('/auth/me')
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
      const mods = user.module_access ?? []
      const canEsgrc = user.role === 'super_admin' || mods.length === 0 || mods.includes('esgrc')
      navigate(canEsgrc ? '/dashboard' : '/pipeline', { replace: true })
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-base relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 right-1/3 w-96 h-96 bg-accent-secondary/10 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md mx-4">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-primary shadow-glow-primary mb-4">
            <Zap size={26} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-text-primary">Create account</h1>
          <p className="text-text-secondary mt-1 text-sm">Join your organisation on TBD2</p>
        </div>

        <div className="card p-8">
          {error && (
            <div className="bg-accent-danger/10 border border-accent-danger/30 rounded-lg px-4 py-3 mb-5 text-sm text-accent-danger">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {[
              { id:'reg-name',     field:'full_name', label:'Full name',          type:'text',  placeholder:'Alex Morgan' },
              { id:'reg-email',    field:'email',     label:'Work email',         type:'email', placeholder:'alex@company.com' },
              { id:'reg-password', field:'password',  label:'Password',           type:'password', placeholder:'Min 8 characters' },
              { id:'reg-org',      field:'organisation_slug',  label:'Organisation slug',  type:'text',  placeholder:'acme-corp' },
            ].map(({ id, field, label, type, placeholder }) => (
              <div key={field}>
                <label htmlFor={id} className="label">{label}</label>
                <input
                  id={id}
                  type={type}
                  placeholder={placeholder}
                  value={(form as any)[field]}
                  onChange={(e) => set(field, e.target.value)}
                  required
                  className="w-full"
                />
              </div>
            ))}

            <button
              type="submit"
              id="register-submit-btn"
              className="btn-primary w-full justify-center py-3 text-base"
              disabled={loading || Object.values(form).some((v) => !v)}
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : 'Create account'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-text-muted">
            Already have an account?{' '}
            <Link to="/login" className="text-accent-primary hover:underline">Sign in</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
