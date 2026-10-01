import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const sonner = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  loading: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: sonner }))

import { useToast } from './use-toast'

const toastFn = () => renderHook(() => useToast()).result.current.toast

// Exactly one Sonner method must fire per call; returns which one.
const firedMethods = () =>
  (Object.keys(sonner) as (keyof typeof sonner)[]).filter((k) => sonner[k].mock.calls.length > 0)

describe('useToast runtime variants (N2)', () => {
  beforeEach(() => {
    Object.values(sonner).forEach((fn) => fn.mockReset())
  })

  it.each([
    ['success', 'success'],
    ['error', 'error'],
    ['warn', 'warning'],
    ['info', 'info'],
  ] as const)('variant "%s" → sonner.%s with title and description', (variant, method) => {
    toastFn()({ title: 'Title', description: 'Desc', variant })

    expect(firedMethods()).toEqual([method])
    expect(sonner[method]).toHaveBeenCalledWith('Title', { description: 'Desc' })
  })

  it('keeps the legacy names: "default" → success, "destructive" → error', () => {
    toastFn()({ title: 'Saved', variant: 'default' })
    expect(firedMethods()).toEqual(['success'])

    sonner.success.mockReset()
    toastFn()({ title: 'Failed', variant: 'destructive' })
    expect(firedMethods()).toEqual(['error'])
  })

  it('defaults to success when no variant is given (unchanged legacy behaviour)', () => {
    toastFn()({ title: 'Done', description: 'd' })
    expect(firedMethods()).toEqual(['success'])
    expect(sonner.success).toHaveBeenCalledWith('Done', { description: 'd' })
  })

  it('falls back to the localized common title when none is given', () => {
    toastFn()({ description: 'a', variant: 'success' })
    toastFn()({ description: 'b', variant: 'error' })
    toastFn()({ description: 'c', variant: 'warn' })

    expect(sonner.success).toHaveBeenCalledWith('common.success', { description: 'a' })
    expect(sonner.error).toHaveBeenCalledWith('common.error', { description: 'b' })
    expect(sonner.warning).toHaveBeenCalledWith('common.warning', { description: 'c' })
  })

  it('info without a title shows the description as the message (no generic info title exists)', () => {
    toastFn()({ description: 'Request received', variant: 'info' })
    expect(sonner.info).toHaveBeenCalledWith('Request received')
  })

  it('never uses a loading/pending toast', () => {
    for (const variant of ['success', 'error', 'warn', 'info', 'default', 'destructive'] as const) {
      toastFn()({ title: 't', variant })
    }
    expect(sonner.loading).not.toHaveBeenCalled()
  })
})
