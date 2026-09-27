import axios from 'axios'
import { useAuthStore } from '@/store/auth'

// ── Axios instance pointing at /api proxy ────────────────────────────────────
// No cookie-based session: the backend takes the refresh token in the request
// body (POST /auth/refresh { refresh_token }) and never sets a cookie, so
// there is nothing for withCredentials to send.
export const api = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor: attach Bearer token ─────────────────────────────────
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor: refresh on 401 ─────────────────────────────────────

/**
 * Endpoints where a 401 means "these credentials are wrong", not "the access
 * token aged out" - refreshing would be pointless, or recursive in the case of
 * /auth/refresh itself.
 *
 * This used to match on '/auth/' as a whole, which also caught /auth/me and
 * /auth/users. The visible symptom: an admin sitting on Settings > Users past
 * the 30-minute token lifetime had the tab's background refetch 401, and was
 * thrown back to the login screen while holding a perfectly valid refresh
 * token.
 */
const NO_REFRESH_PATHS = [
  '/auth/login',
  '/auth/register',
  '/auth/refresh',
  '/auth/logout',
]

let isRefreshing = false
type Waiter = { resolve: (token: string) => void; reject: (reason: unknown) => void }
let waiters: Waiter[] = []

/**
 * Exchange the stored refresh token for a new access token, sharing the same
 * isRefreshing/waiters coordination the response interceptor below uses for
 * ordinary API calls. Exported so callers outside axios - the SSE hooks
 * (usePipelineSSE, useCopilotSSE), which connect via `fetch` and so never go
 * through this interceptor - can recover from an access-token expiry mid-
 * stream instead of treating any non-OK handshake as fatal. Without sharing
 * this queue, an SSE 401 and a concurrent axios 401 would each try to
 * exchange the same one-time-use refresh token, and the loser would replay
 * an already-rotated token and get logged out.
 *
 * Throws and calls logout() on failure, same as the interceptor's own catch
 * path - callers should treat a rejection as "the session is over," not
 * retry it themselves.
 */
export function refreshAccessToken(): Promise<string> {
  const refreshToken = useAuthStore.getState().refreshToken
  if (!refreshToken) {
    useAuthStore.getState().logout()
    return Promise.reject(new Error('No refresh token available'))
  }

  if (isRefreshing) {
    return new Promise((resolve, reject) => {
      waiters.push({ resolve, reject })
    })
  }

  isRefreshing = true
  return axios.post('/api/auth/refresh', { refresh_token: refreshToken })
    .then(({ data }) => {
      const newToken: string = data.access_token
      // Rotation: the server invalidated `refreshToken` the instant it read
      // it, so `data.refresh_token` must replace it in the store or the next
      // 401 on this tab exchanges an already-dead token and gets treated as
      // a replay.
      useAuthStore.getState().setTokens(newToken, data.refresh_token)

      const queued = waiters
      waiters = []
      queued.forEach((w) => w.resolve(newToken))
      return newToken
    })
    .catch((refreshErr) => {
      const queued = waiters
      waiters = []
      queued.forEach((w) => w.reject(refreshErr))

      useAuthStore.getState().logout()
      window.location.replace('/login')
      throw refreshErr
    })
    .finally(() => {
      isRefreshing = false
    })
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config

    // Only attempt refresh once per 401; guard against infinite loops
    if (err.response?.status !== 401 || original._retry) {
      return Promise.reject(err)
    }

    if (NO_REFRESH_PATHS.some((path) => original.url?.includes(path))) {
      useAuthStore.getState().logout()
      return Promise.reject(err)
    }

    if (!useAuthStore.getState().refreshToken) {
      // Nothing to exchange - this is a real logout, not a retryable 401.
      useAuthStore.getState().logout()
      return Promise.reject(err)
    }

    original._retry = true

    try {
      const newToken = await refreshAccessToken()
      original.headers.Authorization = `Bearer ${newToken}`
      return api(original)
    } catch {
      // refreshAccessToken() already logged out and redirected on failure.
      return Promise.reject(err)
    }
  },
)

export default api
