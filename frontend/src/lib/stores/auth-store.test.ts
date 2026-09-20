import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useAuthStore } from './auth-store'

// The store resolves the API base URL via this helper.
vi.mock('@/lib/config', () => ({
  getApiUrl: vi.fn().mockResolvedValue('http://api.test'),
}))

function mockFetchOnce(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
}

const adminUser = {
  id: 'user:admin',
  username: 'admin',
  role: 'admin' as const,
  name: 'Administrator',
}

describe('auth-store', () => {
  beforeEach(() => {
    useAuthStore.setState({
      isAuthenticated: false,
      token: null,
      user: null,
      error: null,
      isLoading: false,
      lastAuthCheck: null,
      isCheckingAuth: false,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('login', () => {
    it('stores token and user on success', async () => {
      vi.stubGlobal(
        'fetch',
        mockFetchOnce(200, {
          access_token: 'jwt-token',
          token_type: 'bearer',
          user: adminUser,
        })
      )

      const ok = await useAuthStore.getState().login('admin', 'admin')

      expect(ok).toBe(true)
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(true)
      expect(state.token).toBe('jwt-token')
      expect(state.user?.username).toBe('admin')
      expect(state.user?.role).toBe('admin')
      expect(state.error).toBeNull()
    })

    it('sets an error and stays logged out on invalid credentials', async () => {
      vi.stubGlobal('fetch', mockFetchOnce(401, { detail: 'bad' }))

      const ok = await useAuthStore.getState().login('admin', 'wrong')

      expect(ok).toBe(false)
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.token).toBeNull()
      expect(state.user).toBeNull()
      expect(state.error).toBeTruthy()
    })

    it('reports a connection error when the server is unreachable', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
      )

      const ok = await useAuthStore.getState().login('admin', 'admin')

      expect(ok).toBe(false)
      expect(useAuthStore.getState().error).toMatch(/connect/i)
    })
  })

  describe('logout', () => {
    it('clears auth state', async () => {
      useAuthStore.setState({
        isAuthenticated: true,
        token: 'jwt-token',
        user: adminUser,
      })
      vi.stubGlobal('fetch', mockFetchOnce(200, { success: true }))

      await useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.token).toBeNull()
      expect(state.user).toBeNull()
    })
  })

  describe('checkAuth', () => {
    it('returns false without a token', async () => {
      expect(await useAuthStore.getState().checkAuth()).toBe(false)
    })

    it('validates the token and refreshes the user via /me', async () => {
      useAuthStore.setState({ token: 'jwt-token' })
      vi.stubGlobal('fetch', mockFetchOnce(200, adminUser))

      const ok = await useAuthStore.getState().checkAuth()

      expect(ok).toBe(true)
      expect(useAuthStore.getState().user?.username).toBe('admin')
    })

    it('clears state when the token is rejected', async () => {
      useAuthStore.setState({ token: 'stale', isAuthenticated: true })
      vi.stubGlobal('fetch', mockFetchOnce(401, { detail: 'expired' }))

      const ok = await useAuthStore.getState().checkAuth()

      expect(ok).toBe(false)
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.token).toBeNull()
    })
  })

  describe('updatePreferences', () => {
    it('optimistically updates the user and persists to the backend', async () => {
      useAuthStore.setState({
        isAuthenticated: true,
        token: 'jwt-token',
        user: { ...adminUser, language: 'en-US', theme: 'light' },
      })
      const fetchMock = mockFetchOnce(200, {
        ...adminUser,
        language: 'vi-VN',
        theme: 'dark',
      })
      vi.stubGlobal('fetch', fetchMock)

      await useAuthStore
        .getState()
        .updatePreferences({ language: 'vi-VN', theme: 'dark' })

      // Persisted to /api/auth/preferences
      expect(fetchMock).toHaveBeenCalledTimes(1)
      const [url, init] = fetchMock.mock.calls[0]
      expect(String(url)).toMatch(/\/api\/auth\/preferences$/)
      expect(init.method).toBe('PUT')

      const state = useAuthStore.getState()
      expect(state.user?.language).toBe('vi-VN')
      expect(state.user?.theme).toBe('dark')
    })

    it('no-ops when not authenticated', async () => {
      const fetchMock = mockFetchOnce(200, {})
      vi.stubGlobal('fetch', fetchMock)

      await useAuthStore.getState().updatePreferences({ language: 'vi-VN' })

      expect(fetchMock).not.toHaveBeenCalled()
    })
  })
})
