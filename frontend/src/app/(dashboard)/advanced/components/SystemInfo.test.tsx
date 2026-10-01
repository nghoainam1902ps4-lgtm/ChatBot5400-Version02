import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SystemInfo } from './SystemInfo'
import { fetchLatestVersion } from '@/lib/utils/version'
import { APP_VERSION } from '@/lib/constants/app'

// useTranslation is mocked globally in setup.ts (t returns the key string)

vi.mock('@/lib/utils/version', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/version')>()),
  fetchLatestVersion: vi.fn(),
}))

const area = () => document.querySelector('[data-slot="admin-area"]') as HTMLElement

describe('SystemInfo (P1C)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('is a readonly AdminArea titled advanced.systemInfo', async () => {
    vi.mocked(fetchLatestVersion).mockResolvedValue(APP_VERSION)
    render(<SystemInfo />)
    await screen.findByText('advanced.upToDate')
    expect(area()).toHaveAttribute('data-level', 'readonly')
    expect(screen.getByRole('heading', { name: 'advanced.systemInfo' })).toBeInTheDocument()
  })

  it('up to date uses the teal/info hue (not fern, not success)', async () => {
    vi.mocked(fetchLatestVersion).mockResolvedValue(APP_VERSION)
    render(<SystemInfo />)
    const badge = await screen.findByText('advanced.upToDate')
    expect(badge.className).toContain('text-teal')
    expect(badge.className).not.toMatch(/fern|success/)
    expect(area().innerHTML).not.toMatch(/fern/)
  })

  it('update available stays warn', async () => {
    vi.mocked(fetchLatestVersion).mockResolvedValue('999.0.0')
    render(<SystemInfo />)
    const badge = await screen.findByText('advanced.updateAvailable')
    expect(badge.className).toContain('text-warn')
  })

  it('connection error stays destructive', async () => {
    vi.mocked(fetchLatestVersion).mockRejectedValue(new Error('offline'))
    render(<SystemInfo />)
    const badge = await screen.findByText('advanced.connectionError')
    expect(badge.className).toContain('text-destructive')
  })
})
