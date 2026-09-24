import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const toastInfo = vi.fn()
const fetchLatestVersion = vi.fn()

vi.mock('sonner', () => ({ toast: { info: (...args: unknown[]) => toastInfo(...args) } }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string, opts?: { version?: string }) => `${key}:${opts?.version ?? ''}` }),
}))
vi.mock('@/lib/constants/app', () => ({ APP_VERSION: '0.0.3' }))
vi.mock('@/lib/utils/version', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/version')>()),
  fetchLatestVersion: () => fetchLatestVersion(),
}))

import { UPDATE_NOTIFIED_KEY, useVersionCheck } from './use-version-check'

describe('useVersionCheck', () => {
  beforeEach(() => {
    sessionStorage.clear()
    toastInfo.mockReset()
    fetchLatestVersion.mockReset()
  })
  afterEach(() => sessionStorage.clear())

  it('shows a bottom-right toast once when a newer release exists', async () => {
    fetchLatestVersion.mockResolvedValue('0.0.4')
    renderHook(() => useVersionCheck(true))

    await waitFor(() => expect(toastInfo).toHaveBeenCalledTimes(1))
    expect(toastInfo.mock.calls[0][0]).toBe('advanced.updateToast:0.0.4')
    expect(toastInfo.mock.calls[0][1]).toMatchObject({ position: 'bottom-right' })
    expect(sessionStorage.getItem(UPDATE_NOTIFIED_KEY)).toBe('true')
  })

  it('does not check again once notified in this session', async () => {
    sessionStorage.setItem(UPDATE_NOTIFIED_KEY, 'true')
    renderHook(() => useVersionCheck(true))
    await new Promise((r) => setTimeout(r, 0))
    expect(fetchLatestVersion).not.toHaveBeenCalled()
    expect(toastInfo).not.toHaveBeenCalled()
  })

  it('stays silent when up to date, on error, or when disabled', async () => {
    fetchLatestVersion.mockResolvedValue('0.0.3')
    renderHook(() => useVersionCheck(true))
    await waitFor(() => expect(fetchLatestVersion).toHaveBeenCalledTimes(1))

    fetchLatestVersion.mockRejectedValue(new Error('offline'))
    renderHook(() => useVersionCheck(true))
    await waitFor(() => expect(fetchLatestVersion).toHaveBeenCalledTimes(2))

    renderHook(() => useVersionCheck(false))
    await new Promise((r) => setTimeout(r, 0))

    expect(fetchLatestVersion).toHaveBeenCalledTimes(2)
    expect(toastInfo).not.toHaveBeenCalled()
    expect(sessionStorage.getItem(UPDATE_NOTIFIED_KEY)).toBeNull()
  })
})
