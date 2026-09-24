import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const toastInfo = vi.fn()
const fetchLatestVersion = vi.fn()

vi.mock('sonner', () => ({ toast: { info: (...args: unknown[]) => toastInfo(...args) } }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string, opts?: { version?: string }) => `${key}:${opts?.version ?? ''}` }),
}))
vi.mock('@/lib/constants/app', () => ({ APP_VERSION: '0.0.4' }))
vi.mock('@/lib/utils/version', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/version')>()),
  fetchLatestVersion: () => fetchLatestVersion(),
}))

import { resetVersionCheck, useVersionCheck } from './use-version-check'

describe('useVersionCheck', () => {
  beforeEach(() => {
    resetVersionCheck()
    toastInfo.mockReset()
    fetchLatestVersion.mockReset()
  })

  it('shows a bottom-right toast with title and description when a newer release exists', async () => {
    fetchLatestVersion.mockResolvedValue('0.0.5')
    renderHook(() => useVersionCheck(true))

    await waitFor(() => expect(toastInfo).toHaveBeenCalledTimes(1))
    expect(toastInfo.mock.calls[0][0]).toBe('advanced.updateToastTitle:0.0.5')
    expect(toastInfo.mock.calls[0][1]).toMatchObject({
      position: 'bottom-right',
      description: 'advanced.updateToastDesc:',
    })
  })

  it('checks only once per app load (no repeat on page navigation)', async () => {
    fetchLatestVersion.mockResolvedValue('0.0.5')
    const first = renderHook(() => useVersionCheck(true))
    await waitFor(() => expect(toastInfo).toHaveBeenCalledTimes(1))
    first.unmount()

    // Layout remount (e.g. navigation) in the same load: no new check
    renderHook(() => useVersionCheck(true))
    await new Promise((r) => setTimeout(r, 0))
    expect(fetchLatestVersion).toHaveBeenCalledTimes(1)
    expect(toastInfo).toHaveBeenCalledTimes(1)
  })

  it('shows again on a new app load', async () => {
    fetchLatestVersion.mockResolvedValue('0.0.5')
    renderHook(() => useVersionCheck(true))
    await waitFor(() => expect(toastInfo).toHaveBeenCalledTimes(1))

    resetVersionCheck() // simulates a fresh page load
    renderHook(() => useVersionCheck(true))
    await waitFor(() => expect(toastInfo).toHaveBeenCalledTimes(2))
  })

  it('stays silent when up to date, on error, or when disabled', async () => {
    fetchLatestVersion.mockResolvedValue('0.0.4')
    renderHook(() => useVersionCheck(true))
    await waitFor(() => expect(fetchLatestVersion).toHaveBeenCalledTimes(1))

    resetVersionCheck()
    fetchLatestVersion.mockRejectedValue(new Error('offline'))
    renderHook(() => useVersionCheck(true))
    await waitFor(() => expect(fetchLatestVersion).toHaveBeenCalledTimes(2))

    resetVersionCheck()
    renderHook(() => useVersionCheck(false))
    await new Promise((r) => setTimeout(r, 0))

    expect(fetchLatestVersion).toHaveBeenCalledTimes(2)
    expect(toastInfo).not.toHaveBeenCalled()
  })
})
