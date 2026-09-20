import axios from 'axios'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { getApiUrl } from '@/lib/config'
import i18n from '@/lib/i18n'
import { useThemeStore, type Theme } from '@/lib/stores/theme-store'
import type { LoginResponse, User } from '@/lib/types/auth'

const DEFAULT_LANGUAGE = 'vi-VN'

/**
 * Apply a user's saved UI preferences (language + theme) after login / auth
 * check, so settings are restored per-account. Missing values fall back to the
 * app defaults (Vietnamese; existing theme).
 */
function applyUserPreferences(user: User | null): void {
  try {
    const lang = user?.language || DEFAULT_LANGUAGE
    if (i18n.language !== lang) {
      void i18n.changeLanguage(lang)
    }
    if (user?.theme) {
      useThemeStore.getState().setTheme(user.theme as Theme)
    }
  } catch {
    // preferences are best-effort; never block auth on them
  }
}

interface AuthState {
  isAuthenticated: boolean
  token: string | null
  user: User | null
  isLoading: boolean
  error: string | null
  lastAuthCheck: number | null
  isCheckingAuth: boolean
  hasHydrated: boolean
  authRequired: boolean | null
  setHasHydrated: (state: boolean) => void
  checkAuthRequired: () => Promise<boolean>
  login: (username: string, password: string) => Promise<boolean>
  logout: () => Promise<void>
  checkAuth: () => Promise<boolean>
  updatePreferences: (prefs: {
    language?: string
    theme?: string
  }) => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      token: null,
      user: null,
      isLoading: false,
      error: null,
      lastAuthCheck: null,
      isCheckingAuth: false,
      hasHydrated: false,
      authRequired: null,

      setHasHydrated: (state: boolean) => {
        set({ hasHydrated: state })
      },

      // Authentication is always required in ChatBot5400. This still probes the
      // server so a connection error can be surfaced distinctly from "logged
      // out", which the login screen relies on.
      checkAuthRequired: async () => {
        try {
          const apiUrl = await getApiUrl()
          const response = await fetch(`${apiUrl}/api/auth/status`, {
            headers: { 'Cache-Control': 'no-store' },
          })
          if (!response.ok) {
            throw new Error(`auth status ${response.status}`)
          }
          set({ authRequired: true })
          return true
        } catch (error) {
          console.error('Failed to check auth status:', error)
          if (axios.isAxiosError(error) && !error.response) {
            set({
              error:
                'Unable to connect to server. Please check if the API is running.',
              authRequired: null,
            })
          } else if (error instanceof TypeError) {
            // fetch network failure
            set({
              error:
                'Unable to connect to server. Please check if the API is running.',
              authRequired: null,
            })
          } else {
            set({ authRequired: true })
          }
          throw error
        }
      },

      login: async (username: string, password: string) => {
        set({ isLoading: true, error: null })
        try {
          const apiUrl = await getApiUrl()

          // Deliberately raw fetch (not apiClient): a failed login returns 401,
          // and the apiClient response interceptor would clear storage and
          // hard-redirect on 401 — wrong behaviour while probing credentials.
          const response = await fetch(`${apiUrl}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
          })

          if (response.ok) {
            const data: LoginResponse = await response.json()
            set({
              isAuthenticated: true,
              token: data.access_token,
              user: data.user,
              isLoading: false,
              lastAuthCheck: Date.now(),
              error: null,
            })
            applyUserPreferences(data.user)
            return true
          }

          let errorMessage = 'Authentication failed'
          if (response.status === 401) {
            errorMessage = 'Invalid username or password'
          } else if (response.status >= 500) {
            errorMessage = 'Server error. Please try again later.'
          } else {
            errorMessage = `Authentication failed (${response.status})`
          }
          set({
            error: errorMessage,
            isLoading: false,
            isAuthenticated: false,
            token: null,
            user: null,
          })
          return false
        } catch (error) {
          console.error('Network error during auth:', error)
          let errorMessage = 'Authentication failed'
          if (
            error instanceof TypeError &&
            error.message.includes('Failed to fetch')
          ) {
            errorMessage =
              'Unable to connect to server. Please check if the API is running.'
          } else if (error instanceof Error) {
            errorMessage = `Network error: ${error.message}`
          }
          set({
            error: errorMessage,
            isLoading: false,
            isAuthenticated: false,
            token: null,
            user: null,
          })
          return false
        }
      },

      logout: async () => {
        const { token } = get()
        // Best-effort server notification; token is stateless so local clear is
        // what actually logs the user out.
        try {
          if (token) {
            const apiUrl = await getApiUrl()
            await fetch(`${apiUrl}/api/auth/logout`, {
              method: 'POST',
              headers: { Authorization: `Bearer ${token}` },
            })
          }
        } catch {
          // ignore network errors on logout
        }
        set({
          isAuthenticated: false,
          token: null,
          user: null,
          error: null,
          lastAuthCheck: null,
        })
      },

      checkAuth: async () => {
        const state = get()
        const { token, lastAuthCheck, isCheckingAuth, isAuthenticated } = state

        if (isCheckingAuth) {
          return isAuthenticated
        }
        if (!token) {
          return false
        }
        const now = Date.now()
        if (isAuthenticated && lastAuthCheck && now - lastAuthCheck < 30000) {
          return true
        }

        set({ isCheckingAuth: true })
        try {
          const apiUrl = await getApiUrl()
          // Raw fetch: a 401 here must update store state, not trigger the
          // interceptor's storage-clear/redirect.
          const response = await fetch(`${apiUrl}/api/auth/me`, {
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          })
          if (response.ok) {
            const user: User = await response.json()
            set({
              isAuthenticated: true,
              user,
              lastAuthCheck: now,
              isCheckingAuth: false,
            })
            applyUserPreferences(user)
            return true
          }
          set({
            isAuthenticated: false,
            token: null,
            user: null,
            lastAuthCheck: null,
            isCheckingAuth: false,
          })
          return false
        } catch (error) {
          console.error('checkAuth error:', error)
          set({
            isAuthenticated: false,
            token: null,
            user: null,
            lastAuthCheck: null,
            isCheckingAuth: false,
          })
          return false
        }
      },

      updatePreferences: async (prefs) => {
        const { token, user } = get()
        if (!token || !user) {
          return
        }
        // Optimistically update local state so the UI reflects the choice
        // immediately, then persist to the account.
        set({ user: { ...user, ...prefs } })
        try {
          const apiUrl = await getApiUrl()
          const response = await fetch(`${apiUrl}/api/auth/preferences`, {
            method: 'PUT',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(prefs),
          })
          if (response.ok) {
            const updated: User = await response.json()
            set({ user: updated })
          }
        } catch {
          // best-effort; local state already reflects the choice
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true)
      },
    }
  )
)
