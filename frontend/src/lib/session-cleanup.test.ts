import { describe, it, expect, vi } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'

import { clearSessionData } from './session-cleanup'
import { useNavigationStore } from '@/lib/stores/navigation-store'

describe('clearSessionData', () => {
  it('clears the React Query cache and the navigation context', () => {
    const clear = vi.fn()
    const clearReturnTo = vi.spyOn(
      useNavigationStore.getState(),
      'clearReturnTo'
    )

    clearSessionData({ clear } as unknown as QueryClient)

    expect(clear).toHaveBeenCalledTimes(1)
    expect(clearReturnTo).toHaveBeenCalledTimes(1)
  })

  it('does not throw if the query cache teardown fails', () => {
    const clear = vi.fn(() => {
      throw new Error('boom')
    })

    expect(() =>
      clearSessionData({ clear } as unknown as QueryClient)
    ).not.toThrow()
  })
})
