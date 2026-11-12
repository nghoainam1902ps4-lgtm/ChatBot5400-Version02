'use client'

import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/lib/stores/auth-store'
import { clearSessionData } from '@/lib/session-cleanup'
import { approvalsApi } from '@/lib/api/approvals'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export function useAuth() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
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
      // Notify reviewers (approver/admin) at login if documents await approval.
      const loggedIn = useAuthStore.getState().user
      if (loggedIn && (loggedIn.role === 'admin' || loggedIn.role === 'approver')) {
        approvalsApi
          .count()
          .then(({ count }) => {
            if (count > 0) {
              toast({
                title: t('approvals.title'),
                description: t('approvals.pendingNotice', { count }),
              })
            }
          })
          .catch(() => {
            // Non-critical: a failed badge check never blocks login.
          })
      }
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

  const role = user?.role
  return {
    isAuthenticated,
    isLoading: isLoading || !hasHydrated,
    error,
    user,
    isAdmin: role === 'admin',
    isApprover: role === 'approver',
    isContributor: role === 'contributor',
    // Approvers and admins can review pending submissions and manage categories.
    canReview: role === 'admin' || role === 'approver',
    // Only admins and contributors add new sources/văn bản. Approvers are
    // checkers (maker-checker separation) and do not submit content.
    canSubmit: role === 'admin' || role === 'contributor',
    login: handleLogin,
    logout: handleLogout,
  }
}
