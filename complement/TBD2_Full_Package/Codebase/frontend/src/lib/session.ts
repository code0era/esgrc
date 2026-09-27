import axios from 'axios'
import api from '@/lib/axios'
import { useAuthStore, getStoredRefreshToken, type AuthUser } from '@/store/auth'

/**
 * Session hydration shared by login, registration and page-load restore.
 *
 * The access token lives in memory only (deliberately - it never touches
 * storage), so a reload always starts with an empty store. The backend has no
 * cookie-based session (POST /auth/refresh takes { refresh_token } in the JSON
 * body and never sets a cookie - confirmed against ESGRC/app/routers/auth.py),
 * so the refresh token is mirrored to sessionStorage instead; restoreSession
 * spends it at boot to rebuild the session without forcing a re-login on every
 * page reload.
 */

/** Build the AuthUser from an access token. Caller must have already put the
 *  token (and refresh token) in the store so the request interceptor attaches it. */
export async function hydrateUser(): Promise<AuthUser> {
  const me = await api.get('/auth/me')
  // Snapshot is decoration (org display name); never fail the session over it.
  const snap = await api.get('/org/snapshot').catch(() => ({ data: {} }))

  return {
    id:        me.data.id,
    email:     me.data.email,
    full_name: me.data.full_name,
    role:      me.data.role,
    org_id:    me.data.organisation_id ?? me.data.org_id,
    org_name:  snap.data?.org_name ?? '',
    module_access: me.data.module_access ?? [],
  }
}

/**
 * Spend the sessionStorage-held refresh token to rebuild the session after a
 * reload. Resolves false when there is no usable session, which is the normal
 * path for a first-time visitor and must not surface as an error.
 *
 * Uses bare axios, not the api instance: a 401 here is the expected "not logged
 * in" answer, and routing it through the response interceptor would trigger a
 * refresh-on-refresh loop.
 */
export async function restoreSession(): Promise<boolean> {
  const refreshToken = getStoredRefreshToken()
  if (!refreshToken) return false // first-time visitor / already logged out

  try {
    const { data } = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
    if (!data?.access_token || !data?.refresh_token) return false
    // Rotation: the token we just spent is now dead. Store the new pair before
    // the /auth/me call below so the request interceptor attaches the right one.
    useAuthStore.getState().setTokens(data.access_token, data.refresh_token)
    const user = await hydrateUser()
    useAuthStore.getState().setAuth(user, data.access_token, data.refresh_token)
    return true
  } catch {
    useAuthStore.getState().logout()
    return false
  }
}

let restoreInFlight: Promise<boolean> | null = null

/**
 * restoreSession, guaranteed to run at most once per page load.
 *
 * This guard is load-bearing, not defensive tidiness. Refresh tokens are
 * single-use and rotate on every exchange, with replay detection on the server.
 * React StrictMode invokes effects twice in development, so an unguarded call
 * would spend the token, then immediately present the now-invalidated token
 * again - which the backend correctly reads as a replayed token and rejects,
 * logging the developer out on every single page load.
 */
export function restoreSessionOnce(): Promise<boolean> {
  if (!restoreInFlight) restoreInFlight = restoreSession()
  return restoreInFlight
}

/** Test seam: forget the memoised attempt. */
export function resetRestoreState(): void {
  restoreInFlight = null
}

/**
 * Where a user should land after authenticating.
 * An Apex-only user has no ESGRC dashboard/risk/compliance access, so sending
 * them to /dashboard would render a page whose every request 403s.
 */
export function landingPathFor(user: AuthUser): string {
  const mods = user.module_access ?? []
  const canEsgrc =
    user.role === 'super_admin' || mods.length === 0 || mods.includes('esgrc')
  return canEsgrc ? '/dashboard' : '/pipeline'
}
