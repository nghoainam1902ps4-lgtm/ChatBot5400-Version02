import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SourcesPage from './page'
import { sourcesApi } from '@/lib/api/sources'
import type { SourceListResponse } from '@/lib/types/api'

// useTranslation is mocked globally in setup.ts (t returns the key string);
// useAuth is mocked globally as an admin.

const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/sources',
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/sources/AddSourceDialog', () => ({
  AddSourceDialog: () => null,
}))

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: { list: vi.fn(), delete: vi.fn() },
}))

const list = vi.mocked(sourcesApi.list)

function makeSource(n: number, overrides: Partial<SourceListResponse> = {}): SourceListResponse {
  return {
    id: `source:${n}`,
    title: `Source ${n}`,
    topics: [],
    asset: null,
    embedded: false,
    embedded_chunks: 0,
    insights_count: 0,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-02T00:00:00Z',
    ...overrides,
  } as SourceListResponse
}

const rows = () => Array.from(document.querySelectorAll('[data-slot="data-table-row"]'))
const selectedRows = () => rows().filter((r) => r.getAttribute('data-selected') === 'true')

function expectHeaderAndSearch() {
  expect(screen.getByRole('heading', { level: 1, name: 'sources.allSources' })).toBeInTheDocument()
  expect(screen.getByRole('search')).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'sources.searchSourcesPlaceholder' })).toBeInTheDocument()
}

describe('SourcesPage (P1A)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('keeps header + search + add action while loading, with a skeleton', () => {
    list.mockReturnValue(new Promise(() => {}))
    render(<SourcesPage />)

    expectHeaderAndSearch()
    expect(screen.getByRole('button', { name: 'sources.addSource' })).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"][data-variant="table"]')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"][data-variant="list"]')).toBeInTheDocument()
    // Server pagination unchanged
    expect(list).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 30, offset: 0, sort_by: 'updated', sort_order: 'desc' }),
      expect.anything()
    )
  })

  it('shows an inline ErrorState whose retry really refetches; header stays', async () => {
    list.mockRejectedValueOnce(new Error('boom'))
    render(<SourcesPage />)

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('sources.failedToLoad')).toBeInTheDocument()
    expectHeaderAndSearch()

    list.mockResolvedValueOnce([makeSource(1)])
    fireEvent.click(within(alert).getByRole('button', { name: 'common.retry' }))

    await waitFor(() => expect(rows()).toHaveLength(1))
    expect(list).toHaveBeenCalledTimes(2)
    expect(list.mock.calls[1][0]).toMatchObject({ offset: 0 })
  })

  it('no data (empty query): empty state with the create CTA', async () => {
    list.mockResolvedValue([])
    render(<SourcesPage />)

    const empty = await waitFor(() => {
      const el = document.querySelector('[data-slot="empty-state"]')
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    expect(empty).toHaveAttribute('data-variant', 'empty')
    expect(within(empty).getByText('sources.noSourcesYet')).toBeInTheDocument()
    expect(within(empty).getByRole('button', { name: 'sources.newSource' })).toBeInTheDocument()
    expectHeaderAndSearch()
  })

  it('search no-result: search empty state, no create CTA, header + search kept', async () => {
    list.mockResolvedValueOnce([makeSource(1)])
    render(<SourcesPage />)
    await waitFor(() => expect(rows()).toHaveLength(1))

    list.mockResolvedValue([])
    fireEvent.change(screen.getByRole('textbox', { name: 'sources.searchSourcesPlaceholder' }), {
      target: { value: 'zzz' },
    })

    const empty = await waitFor(
      () => {
        const el = document.querySelector('[data-slot="empty-state"]')
        expect(el).not.toBeNull()
        return el as HTMLElement
      },
      { timeout: 2000 }
    )
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'zzz', offset: 0 }), expect.anything())
    expect(empty).toHaveAttribute('data-variant', 'search')
    expect(within(empty).getByText('sources.noMatchingSources')).toBeInTheDocument()
    expect(within(empty).getByText('sources.noMatchingSourcesDesc')).toBeInTheDocument()
    expect(within(empty).queryByRole('button')).toBeNull()
    expect(screen.queryByText('sources.noSourcesYet')).toBeNull()
    expectHeaderAndSearch()
  })

  it('hover does not change the selected row; keyboard and click still do', async () => {
    list.mockResolvedValue([makeSource(1), makeSource(2), makeSource(3)])
    render(<SourcesPage />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    expect(selectedRows()).toEqual([rows()[0]])

    fireEvent.mouseEnter(rows()[2])
    fireEvent.mouseOver(rows()[2])
    expect(selectedRows()).toEqual([rows()[0]])

    act(() => {
      fireEvent.keyDown(window, { key: 'ArrowDown' })
    })
    expect(selectedRows()).toEqual([rows()[1]])

    act(() => {
      fireEvent.keyDown(window, { key: 'End' })
    })
    expect(selectedRows()).toEqual([rows()[2]])

    act(() => {
      fireEvent.keyDown(window, { key: 'Home' })
    })
    expect(selectedRows()).toEqual([rows()[0]])

    act(() => {
      fireEvent.keyDown(window, { key: 'Enter' })
    })
    expect(push).toHaveBeenLastCalledWith('/sources/source:1')

    fireEvent.click(rows()[2])
    expect(push).toHaveBeenLastCalledWith('/sources/source:3')
    expect(selectedRows()).toEqual([rows()[2]])
  })

  it('selected rows use the SPS selected state (accent + primary bar + focus outline)', async () => {
    list.mockResolvedValue([makeSource(1)])
    render(<SourcesPage />)
    await waitFor(() => expect(rows()).toHaveLength(1))

    const row = rows()[0]
    expect(row.className).toContain('data-[selected=true]:bg-accent')
    expect(row.className).toContain('shadow-[inset_2px_0_0_var(--primary)]')
    expect(row.className).toContain('group-focus-visible/table:data-[selected=true]:outline-2')
  })

  it('delete lives in the row "..." menu; opening it never navigates', async () => {
    list.mockResolvedValue([makeSource(1)])
    render(<SourcesPage />)
    await waitFor(() => expect(rows()).toHaveLength(1))

    // No permanent destructive button on the row
    expect(within(rows()[0] as HTMLElement).queryByRole('button', { name: 'common.delete' })).toBeNull()

    const trigger = within(rows()[0] as HTMLElement).getByRole('button', { name: 'common.actions' })
    fireEvent.click(trigger)
    fireEvent.keyDown(trigger, { key: 'Enter' })

    const item = await screen.findByRole('menuitem', { name: 'common.delete' })
    expect(item).toHaveAttribute('data-variant', 'destructive')
    fireEvent.keyDown(item, { key: 'Enter' })

    expect(await screen.findByText('sources.deleteConfirmWithTitle')).toBeInTheDocument()
    expect(push).not.toHaveBeenCalled()
  })

  it('embedded chip uses the teal/info hue, not fern/success', async () => {
    list.mockResolvedValue([makeSource(1, { embedded: true })])
    render(<SourcesPage />)
    await waitFor(() => expect(rows()).toHaveLength(1))

    const chip = within(rows()[0] as HTMLElement).getByText('sources.yes')
    expect(chip.className).toContain('bg-teal-tint')
    expect(chip.className).toContain('text-teal')
    expect(chip.className).not.toMatch(/fern|success/)
  })

  it('renders the mobile list next to the table (<640: list, >=640: table)', async () => {
    list.mockResolvedValue([makeSource(1, { title: 'A very long source title' })])
    render(<SourcesPage />)
    await waitFor(() => expect(rows()).toHaveLength(1))

    const table = document.querySelector('[data-slot="data-table"]') as HTMLElement
    expect(table.className).toMatch(/(^| )hidden( |$)/)
    expect(table.className).toContain('sm:table')
    expect(table.className).toContain('min-w-[920px]')

    const dataList = document.querySelector('[data-slot="data-list"]') as HTMLElement
    expect(dataList.className).toContain('sm:hidden')
    const item = within(dataList).getByRole('button', { name: 'A very long source title' })
    expect(item.className).toContain('truncate')
    fireEvent.click(item)
    expect(push).toHaveBeenLastCalledWith('/sources/source:1')
  })

  it('keeps 7 columns / min 920 and lets the narrow trailing headers wrap instead of overlapping', async () => {
    list.mockResolvedValue([makeSource(1)])
    render(<SourcesPage />)
    await waitFor(() => expect(rows()).toHaveLength(1))

    const cols = Array.from(document.querySelectorAll('[data-slot="data-table"] col')).map((c) => c.className)
    expect(cols).toEqual(['w-[120px]', 'w-auto', 'w-[140px]', 'w-[140px]', 'w-[136px]', 'w-[120px]', 'w-[64px]'])
    const heads = Array.from(document.querySelectorAll('[data-slot="data-table-head"]'))
    expect(heads).toHaveLength(7)
    for (const name of ['sources.insights', 'sources.embedded']) {
      const btn = screen.getByRole('button', { name })
      expect(btn.className).toContain('whitespace-normal')
      expect(btn.className).toContain('max-w-full')
    }
  })
})
