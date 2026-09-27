import { create } from 'zustand'

export type UserRole = 'super_admin' | 'admin' | 'analyst' | 'viewer'

export interface AuthUser {
  id:       number
  email:    string
  full_name: string
  role:     UserRole
  org_id:   number
  org_name: string
  module_access: string[]   // module keys this user may access, e.g. ['esgrc']
}

// Refresh tokens rotate on every exchange (server-side single-use + replay
// detection), so sessionStorage - not the access token's memory-only rule -
// is what lets a reload survive without re-authenticating. It's scoped to the
// tab and gone on close, unlike localStorage.
const REFRESH_TOKEN_KEY = 'tbd2_refresh_token'

export function getStoredRefreshToken(): string | null {
  try {
    return sessionStorage.getItem(REFRESH_TOKEN_KEY)
  } catch {
    return null // storage unavailable (private mode, SSR, etc.) - treat as logged out
  }
}

function persistRefreshToken(refreshToken: string | null): void {
  try {
    if (refreshToken) sessionStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    else sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  } catch {
    // storage unavailable - session simply won't survive a reload
  }
}

interface AuthState {
  user:         AuthUser | null
  token:        string | null   // access token - MEMORY ONLY, never persisted
  refreshToken: string | null   // mirrored to sessionStorage so a reload can restore it
  setAuth:   (user: AuthUser, token: string, refreshToken: string) => void
  setTokens: (token: string, refreshToken: string) => void
  logout:    () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  user:         null,
  token:        null,
  refreshToken: getStoredRefreshToken(),

  setAuth: (user, token, refreshToken) => {
    persistRefreshToken(refreshToken)
    set({ user, token, refreshToken })
  },
  setTokens: (token, refreshToken) => {
    persistRefreshToken(refreshToken)
    set({ token, refreshToken })
  },
  logout: () => {
    persistRefreshToken(null)
    set({ user: null, token: null, refreshToken: null })
  },
}))

// Convenience role checkers
export const isAdmin    = (role?: UserRole) => role === 'admin'    || role === 'super_admin'
export const isAnalyst  = (role?: UserRole) => isAdmin(role) || role === 'analyst'
export const isSuperAdmin = (role?: UserRole) => role === 'super_admin'

// Module-scoped access (mirrors the backend). super_admin sees every module.
export const hasModule = (user: AuthUser | null, module: string): boolean =>
  !!user && (user.role === 'super_admin' || (user.module_access ?? []).includes(module))
