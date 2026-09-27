import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore, isAdmin, isAnalyst, isSuperAdmin, hasModule, type AuthUser } from './auth'

const demoUser: AuthUser = {
  id: 1, email: 'admin@demo.com', full_name: 'Admin', role: 'admin', org_id: 1, org_name: 'Demo',
  module_access: ['esgrc', 'apex'],
}

describe('hasModule (mirrors backend module scope)', () => {
  const mk = (role: AuthUser['role'], mods: string[]): AuthUser => ({
    id: 1, email: 'u@x', full_name: 'U', role, org_id: 1, org_name: 'O', module_access: mods,
  })
  it('grants when the module is in module_access', () => {
    expect(hasModule(mk('admin', ['esgrc']), 'esgrc')).toBe(true)
    expect(hasModule(mk('admin', ['apex']), 'apex')).toBe(true)
  })
  it('denies a module the user does not have', () => {
    expect(hasModule(mk('admin', ['apex']), 'esgrc')).toBe(false)
    expect(hasModule(mk('viewer', ['esgrc']), 'apex')).toBe(false)
  })
  it('super_admin sees every module regardless of the list', () => {
    expect(hasModule(mk('super_admin', []), 'esgrc')).toBe(true)
    expect(hasModule(mk('super_admin', []), 'apex')).toBe(true)
  })
  it('null user has no access', () => {
    expect(hasModule(null, 'esgrc')).toBe(false)
  })
})

describe('role checkers (mirror the backend RBAC hierarchy)', () => {
  it('isAdmin: admin and super_admin only', () => {
    expect(isAdmin('admin')).toBe(true)
    expect(isAdmin('super_admin')).toBe(true)
    expect(isAdmin('analyst')).toBe(false)
    expect(isAdmin('viewer')).toBe(false)
    expect(isAdmin(undefined)).toBe(false)
  })

  it('isAnalyst: analyst and above (admin, super_admin)', () => {
    expect(isAnalyst('analyst')).toBe(true)
    expect(isAnalyst('admin')).toBe(true)
    expect(isAnalyst('super_admin')).toBe(true)
    expect(isAnalyst('viewer')).toBe(false) // viewer cannot write - matches the live 403 we verified
    expect(isAnalyst(undefined)).toBe(false)
  })

  it('isSuperAdmin: super_admin only', () => {
    expect(isSuperAdmin('super_admin')).toBe(true)
    expect(isSuperAdmin('admin')).toBe(false)
    expect(isSuperAdmin('analyst')).toBe(false)
    expect(isSuperAdmin('viewer')).toBe(false)
  })
})

describe('useAuthStore', () => {
  beforeEach(() => {
    useAuthStore.getState().logout()
  })

  it('starts unauthenticated', () => {
    const s = useAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.token).toBeNull()
    expect(s.refreshToken).toBeNull()
  })

  it('setAuth stores user + token + refresh token', () => {
    useAuthStore.getState().setAuth(demoUser, 'tok-123', 'refresh-123')
    const s = useAuthStore.getState()
    expect(s.user).toEqual(demoUser)
    expect(s.token).toBe('tok-123')
    expect(s.refreshToken).toBe('refresh-123')
    expect(sessionStorage.getItem('tbd2_refresh_token')).toBe('refresh-123')
  })

  it('setTokens rotates both tokens without touching the user', () => {
    useAuthStore.getState().setAuth(demoUser, 'tok-123', 'refresh-123')
    useAuthStore.getState().setTokens('tok-456', 'refresh-456')
    const s = useAuthStore.getState()
    expect(s.token).toBe('tok-456')
    expect(s.refreshToken).toBe('refresh-456')
    expect(s.user).toEqual(demoUser)
    expect(sessionStorage.getItem('tbd2_refresh_token')).toBe('refresh-456')
  })

  it('logout clears everything, including sessionStorage', () => {
    useAuthStore.getState().setAuth(demoUser, 'tok-123', 'refresh-123')
    useAuthStore.getState().logout()
    const s = useAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.token).toBeNull()
    expect(s.refreshToken).toBeNull()
    expect(sessionStorage.getItem('tbd2_refresh_token')).toBeNull()
  })
})
