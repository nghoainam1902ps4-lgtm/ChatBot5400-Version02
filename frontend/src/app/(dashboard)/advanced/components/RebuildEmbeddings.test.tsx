import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RebuildEmbeddings } from './RebuildEmbeddings'
import { embeddingApi, type RebuildStatusResponse } from '@/lib/api/embedding'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const toast = vi.fn()
vi.mock('@/lib/hooks/use-toast', () => ({ useToast: () => ({ toast }) }))
vi.mock('@/lib/api/embedding', () => ({
  embeddingApi: { rebuildEmbeddings: vi.fn(), getRebuildStatus: vi.fn() },
}))

const rebuild = vi.mocked(embeddingApi.rebuildEmbeddings)
const getStatus = vi.mocked(embeddingApi.getRebuildStatus)

function renderRebuild() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RebuildEmbeddings />
    </QueryClientProvider>
  )
}

const status = (over: Partial<RebuildStatusResponse>): RebuildStatusResponse =>
  ({ command_id: 'command:1', status: 'running', ...over }) as RebuildStatusResponse

async function startAndPoll(next: RebuildStatusResponse) {
  rebuild.mockResolvedValue({ command_id: 'command:1' } as never)
  getStatus.mockResolvedValue(next)
  renderRebuild()
  fireEvent.click(screen.getByRole('button', { name: 'advanced.rebuild.startBtn' }))
  await until(() => expect(rebuild).toHaveBeenCalled())
  await act(async () => {
    vi.advanceTimersByTime(5000)
  })
  await until(() => expect(getStatus).toHaveBeenCalled())
}

// setInterval is faked (5 s polling), and RTL's waitFor polls with setInterval,
// so wait with real setTimeout ticks instead.
async function until(check: () => unknown) {
  for (let i = 0; i < 100; i++) {
    try {
      return check()
    } catch {
      await act(() => new Promise((r) => setTimeout(r, 10)))
    }
  }
  return check()
}

const tone = () => document.querySelector('[data-tone]')?.getAttribute('data-tone')

describe('RebuildEmbeddings (P1C)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('is a maintenance AdminArea (never a danger zone) with the existing title/description', () => {
    renderRebuild()
    const area = document.querySelector('[data-slot="admin-area"]') as HTMLElement
    expect(area).toHaveAttribute('data-level', 'maintenance')
    expect(document.querySelector('[data-level="danger"]')).toBeNull()
    expect(screen.getByRole('heading', { name: 'advanced.rebuildEmbeddings' })).toBeInTheDocument()
    expect(screen.getByText('advanced.rebuildEmbeddingsDesc')).toBeInTheDocument()
  })

  it('labels the sources checkbox with advanced.rebuild.includeSources (not navigation.sources)', () => {
    renderRebuild()
    expect(screen.getByRole('checkbox', { name: 'advanced.rebuild.includeSources' })).toBeInTheDocument()
    expect(screen.queryByText('navigation.sources')).toBeNull()
    expect(screen.getByText('advanced.rebuild.existingDesc')).toBeInTheDocument()
  })

  it('sends the unchanged payload, keeps the INFO "submitted" toast and polls every 5 seconds', async () => {
    rebuild.mockResolvedValue({ command_id: 'command:1' } as never)
    getStatus.mockResolvedValue(status({ status: 'running' }))
    renderRebuild()
    fireEvent.click(screen.getByRole('button', { name: 'advanced.rebuild.startBtn' }))
    await until(() => expect(rebuild).toHaveBeenCalled())
    expect(rebuild.mock.calls[0][0]).toEqual({ mode: 'existing', include_sources: true, include_notes: true, include_insights: true })
    expect(toast).toHaveBeenCalledWith({ title: 'advanced.rebuild.submittedToastTitle', variant: 'info' })

    await act(async () => {
      vi.advanceTimersByTime(4999)
    })
    expect(getStatus).not.toHaveBeenCalled()
    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    await until(() => expect(getStatus).toHaveBeenCalledWith('command:1'))
  })

  it('queued is teal/info, not warn', async () => {
    await startAndPoll(status({ status: 'queued' }))
    await until(() => screen.getByText('advanced.rebuild.queued'))
    expect(tone()).toBe('info')
    expect(document.querySelector('[data-tone]')?.getAttribute('class')).toContain('text-teal')
  })

  it('running is teal/info', async () => {
    await startAndPoll(status({ status: 'running' }))
    await until(() => screen.getByText('advanced.rebuild.running'))
    expect(tone()).toBe('info')
  })

  it('completed with no failures is success; polling stops', async () => {
    await startAndPoll(status({ status: 'completed', stats: { failed_items: 0 } as never }))
    await until(() => screen.getByText('advanced.rebuild.completed'))
    expect(tone()).toBe('success')
    expect(screen.queryByText('advanced.rebuild.failedItems')).toBeNull()

    const calls = getStatus.mock.calls.length
    await act(async () => {
      vi.advanceTimersByTime(15000)
    })
    expect(getStatus.mock.calls.length).toBe(calls)
  })

  it('completed with failed items is ONE warning result (no success at the same time)', async () => {
    await startAndPoll(
      status({
        status: 'completed',
        progress: { total_items: 10, processed_items: 10, percentage: 100 } as never,
        stats: { sources_processed: 4, notes_processed: 3, insights_processed: 0, failed_items: 3, processing_time: 2.5 } as never,
      })
    )
    await until(() => screen.getByText('advanced.rebuild.completed'))
    const tones = Array.from(document.querySelectorAll('[data-tone]')).map((e) => e.getAttribute('data-tone'))
    expect(tones).toEqual(['warn'])
    expect(document.querySelector('.text-success')).toBeNull()
    expect(screen.getAllByText('advanced.rebuild.failedItems')).toHaveLength(1)
    expect(document.querySelector('[data-slot="rebuild-result"]')?.className).toContain('text-warn')
    expect(document.body.textContent).not.toContain('⚠')
  })

  it('failed is destructive', async () => {
    await startAndPoll(status({ status: 'failed', error_message: 'boom' }))
    await until(() => screen.getByText('advanced.rebuild.failed'))
    expect(tone()).toBe('destructive')
  })

  it('stats: four values at 17px (no KPI headline), sources label uses includeSources, progress unchanged', async () => {
    await startAndPoll(
      status({
        status: 'running',
        progress: { total_items: 8, processed_items: 2 } as never,
        stats: { sources_processed: 5, notes_processed: 6, insights_processed: 7, failed_items: 0 } as never,
      })
    )
    await until(() => screen.getByText('5'))
    for (const value of ['5', '6', '7']) {
      const el = screen.getByText(value)
      expect(el.className).toContain('text-[17px]')
      expect(el.className).not.toContain('text-2xl')
    }
    expect(screen.getByText('advanced.rebuild.includeSources', { selector: 'p' })).toBeInTheDocument()
    // Derived percentage fallback (2 / 8 = 25%) still drives the bar
    expect((document.querySelector('[data-slot="progress-indicator"]') as HTMLElement).style.transform).toBe('translateX(-75%)')
  })

  it('failed also stops polling, and unmount clears the interval', async () => {
    await startAndPoll(status({ status: 'failed' }))
    await until(() => screen.getByText('advanced.rebuild.failed'))
    const calls = getStatus.mock.calls.length
    await act(async () => {
      vi.advanceTimersByTime(15000)
    })
    expect(getStatus.mock.calls.length).toBe(calls)
  })

  it('unmount while running clears the interval (no further polls)', async () => {
    rebuild.mockResolvedValue({ command_id: 'command:1' } as never)
    getStatus.mockResolvedValue(status({ status: 'running' }))
    const view = renderRebuild()
    fireEvent.click(screen.getByRole('button', { name: 'advanced.rebuild.startBtn' }))
    await until(() => expect(rebuild).toHaveBeenCalled())
    view.unmount()
    await act(async () => {
      vi.advanceTimersByTime(15000)
    })
    expect(getStatus).not.toHaveBeenCalled()
  })
})

