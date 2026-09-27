import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('axios', () => ({ default: { post: vi.fn() } }))
vi.mock('@/lib/axios', () => ({ default: { get: vi.fn() } }))

import axios from 'axios'
import api from '@/lib/axios'
import { restoreSession, restoreSessionOnce, resetRestoreState, landingPathFor } from '@/lib/session'
import { useAuthStore, type AuthUser } from '@/store/auth'

const post = axios.post as unknown as ReturnType<typeof vi.fn>
const get = api.get as unknown as ReturnType<typeof vi.fn>

const ME = {
  id: 7,
  email: 'a@b.com',
  full_name: 'A B',
  role: 'admin',
  organisation_id: 3,
  module_access: ['esgrc'],
}

const STORED_REFRESH_TOKEN = 'stored-refresh-token'

function seedStoredRefreshToken() {
  sessionStorage.setItem('tbd2_refresh_token', STORED_REFRESH_TOKEN)
}

function mockHappyPath() {
  post.mockResolvedValue({ data: { access_token: 'fresh-token', refresh_token: 'rotated-refresh-token' } })
  get.mockImplementation((url: string) =>
    url === '/auth/me'
      ? Promise.resolve({ data: ME })
      : Promise.resolve({ data: { org_name: 'Acme' } }),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  resetRestoreState()
  useAuthStore.getState().logout()
  sessionStorage.clear()
})

describe('restoreSession', () => {
  it('rebuilds the session from the stored refresh token', async () => {
    seedStoredRefreshToken()
    mockHappyPath()

    await expect(restoreSession()).resolves.toBe(true)

    const state = useAuthStore.getState()
    expect(state.token).toBe('fresh-token')
    expect(state.refreshToken).toBe('rotated-refresh-token')
    expect(state.user).toMatchObject({ id: 7, org_id: 3, org_name: 'Acme' })
    // The old token was single-use; only the rotated one should remain.
    expect(sessionStorage.getItem('tbd2_refresh_token')).toBe('rotated-refresh-token')
    expect(post).toHaveBeenCalledWith('/api/auth/refresh', { refresh_token: STORED_REFRESH_TOKEN })
  })

  it('reports no session without a network call when there is no stored refresh token', async () => {
    // The normal first-time-visitor path: must not surface as an error, and
    // must not spend a round-trip trying to refresh a token that never existed.
    await expect(restoreSession()).resolves.toBe(false)
    expect(useAuthStore.getState().user).toBeNull()
    expect(post).not.toHaveBeenCalled()
  })

  it('reports no session instead of throwing when the stored token is rejected', async () => {
    seedStoredRefreshToken()
    post.mockRejectedValue({ response: { status: 401 } })

    await expect(restoreSession()).resolves.toBe(false)
    expect(useAuthStore.getState().user).toBeNull()
    expect(sessionStorage.getItem('tbd2_refresh_token')).toBeNull()
  })

  it('still restores when the org snapshot is unavailable', async () => {
    seedStoredRefreshToken()
    post.mockResolvedValue({ data: { access_token: 'fresh-token', refresh_token: 'rotated-refresh-token' } })
    get.mockImplementation((url: string) =>
      url === '/auth/me'
        ? Promise.resolve({ data: ME })
        : Promise.reject(new Error('snapshot down')),
    )

    await expect(restoreSession()).resolves.toBe(true)
    expect(useAuthStore.getState().user?.org_name).toBe('')
  })
})

describe('restoreSessionOnce', () => {
  it('spends the refresh token exactly once per page load', async () => {
    // Refresh tokens are single-use and rotate, and StrictMode double-invokes
    // effects. A second exchange would look like a replayed token to the server
    // and log the user straight back out.
    seedStoredRefreshToken()
    mockHappyPath()

    await Promise.all([restoreSessionOnce(), restoreSessionOnce()])

    expect(post).toHaveBeenCalledTimes(1)
  })
})

describe('landingPathFor', () => {
  const base: AuthUser = {
    id: 1, email: 'x@y.z', full_name: 'X', role: 'analyst',
    org_id: 1, org_name: 'O', module_access: [],
  }

  it('sends an apex-only user to pipeline, not a dashboard that would 403', () => {
    expect(landingPathFor({ ...base, module_access: ['apex'] })).toBe('/pipeline')
  })

  it('sends an esgrc user to the dashboard', () => {
    expect(landingPathFor({ ...base, module_access: ['esgrc'] })).toBe('/dashboard')
  })

  it('lets a super_admin through regardless of module list', () => {
    expect(landingPathFor({ ...base, role: 'super_admin', module_access: ['apex'] }))
      .toBe('/dashboard')
  })
})
