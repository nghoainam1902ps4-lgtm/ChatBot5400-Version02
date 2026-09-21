'use client'

import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/lib/stores/auth-store'
import { clearSessionData } from '@/lib/session-cleanup'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export function useAuth() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const {
    isAuthenticated,
    isLoading,
    user,
    login,
    logout,
    checkAuth,
    checkAuthRequired,
    error,
    hasHydrated,
    authRequired,
  } = useAuthStore()

  useEffect(() => {
    if (hasHydrated) {
      if (authRequired === null) {
        checkAuthRequired()
          .then(() => {
            checkAuth()
          })
          .catch(() => {
            // connection error already recorded in the store
          })
      } else {
        checkAuth()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHydrated, authRequired])

  const handleLogin = async (username: string, password: string) => {
    const success = await login(username, password)
    if (success) {
      // Start the new session from a clean cache so nothing from a previous
      // account (e.g. switching users without a full reload) can flash in.
      clearSessionData(queryClient)
      const redirectPath = sessionStorage.getItem('redirectAfterLogin')
      if (redirectPath) {
        sessionStorage.removeItem('redirectAfterLogin')
        router.push(redirectPath)
      } else {
        router.push('/notebooks')
      }
    }
    return success
  }

  const handleLogout = async () => {
    await logout()
    // Drop the previous user's cached notebooks/notes/chats/sources and
    // navigation context before leaving the authenticated area.
    clearSessionData(queryClient)
    router.replace('/login')
  }

  return {
    isAuthenticated,
    isLoading: isLoading || !hasHydrated,
    error,
    user,
    isAdmin: user?.role === 'admin',
    login: handleLogin,
    logout: handleLogout,
  }
}
