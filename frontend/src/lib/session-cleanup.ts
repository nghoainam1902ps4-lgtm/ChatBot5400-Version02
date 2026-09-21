import type { QueryClient } from '@tanstack/react-query'

import { useNavigationStore } from '@/lib/stores/navigation-store'

/**
 * Wipe every trace of the previous session's data so it can never leak into the
 * next user's screen. Called on both logout and login.
 *
 * - React Query cache holds all server data (notebooks, notes, chats, sources,
 *   recently-viewed …) — clearing it forces a fresh, correctly-scoped refetch.
 * - The navigation store holds session-scoped "return to" context.
 *
 * UI preferences (theme, language, sidebar collapse, notebook layout) are
 * intentionally preserved — they are per-browser conveniences, not per-account
 * data — so their stores are left untouched.
 */
export function clearSessionData(queryClient: QueryClient): void {
  try {
    queryClient.clear()
  } catch {
    // best-effort; never block auth transitions on cache teardown
  }
  try {
    useNavigationStore.getState().clearReturnTo()
  } catch {
    // best-effort
  }
}
