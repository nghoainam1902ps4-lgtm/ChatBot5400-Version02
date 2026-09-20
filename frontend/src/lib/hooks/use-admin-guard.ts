'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/hooks/use-auth'

/**
 * Redirects non-admin users away from an admin-only page. Returns auth state so
 * the page can render a placeholder while the check/redirect settles.
 */
export function useAdminGuard() {
  const { isAdmin, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && !isAdmin) {
      router.replace('/notebooks')
    }
  }, [isLoading, isAdmin, router])

  return { isAdmin, isLoading }
}
