import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NotebooksPage from './page'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import type { NotebookResponse } from '@/lib/types/api'

// useTranslation is mocked globally in setup.ts (t returns the key string);
// useAuth is mocked globally as an admin.

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('./components/RecentlyViewed', () => ({ RecentlyViewed: () => null }))
vi.mock('./components/NotebookRow', () => ({
  NotebookRow: ({ notebook }: { notebook: NotebookResponse }) => <div data-testid="nb">{notebook.name}</div>,
}))
vi.mock('./components/NotebookCard', () => ({
  NotebookCard: ({ notebook }: { notebook: NotebookResponse }) => <div data-testid="nb">{notebook.name}</div>,
}))
vi.mock('@/components/notebooks/CreateNotebookDialog', () => ({ CreateNotebookDialog: () => null }))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebooks: vi.fn() }))

const mockUseNotebooks = vi.mocked(useNotebooks)

function nb(id: string, name: string, description = '', archived = false): NotebookResponse {
  return {
    id,
    name,
    description,
    archived,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
    source_count: 0,
    note_count: 0,
  }
}

type QueryState = { data?: NotebookResponse[]; isLoading?: boolean; isError?: boolean; refetch?: () => void }

function setup(active: QueryState, archived: QueryState = { data: [] }) {
  mockUseNotebooks.mockImplementation((isArchived?: boolean) => {
    const state = isArchived ? archived : active
    return {
      data: state.data,
      isLoading: state.isLoading ?? false,
      isError: state.isError ?? false,
      refetch: state.refetch ?? vi.fn(),
    } as unknown as ReturnType<typeof useNotebooks>
  })
  return render(<NotebooksPage />)
}

const searchBox = () => screen.getByRole('textbox', { name: 'notebooks.searchPlaceholder' })
const names = () => screen.queryAllByTestId('nb').map((el) => el.textContent)
// Toggle button of the archived group header (only present when collapsible)
const archivedToggle = () =>
  within(screen.getByText('notebooks.archivedNotebooks').parentElement as HTMLElement).queryByRole('button')

function expectHeaderAndToolbar() {
  expect(screen.getByRole('heading', { level: 1, name: 'notebooks.title' })).toBeInTheDocument()
  expect(screen.getByRole('search')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'common.refresh' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'notebooks.listView' })).toBeInTheDocument()
}

describe('NotebooksPage (P1A)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses the generic SearchInput (placeholder/aria-label/clear label)', () => {
    setup({ data: [nb('n1', 'Alpha')] })
    expectHeaderAndToolbar()
    fireEvent.change(searchBox(), { target: { value: 'al' } })
    expect(screen.getByRole('button', { name: 'common.clearSearch' })).toBeInTheDocument()
  })

  it('matches name OR description, case-insensitive, across active + archived', () => {
    setup(
      { data: [nb('n1', 'Alpha'), nb('n2', 'Beta', 'Quarterly CREDIT report'), nb('n3', 'Gamma')] },
      { data: [nb('a1', 'Old credit notes', '', true), nb('a2', 'Archive', '', true)] }
    )

    fireEvent.change(searchBox(), { target: { value: 'credit' } })
    expect(names()).toEqual(['Beta', 'Old credit notes'])
  })

  it('only renders the groups that matched (no per-group empty state)', () => {
    setup({ data: [nb('n1', 'Alpha')] }, { data: [nb('a1', 'Zeta', '', true)] })

    fireEvent.change(searchBox(), { target: { value: 'zeta' } })
    expect(names()).toEqual(['Zeta'])
    expect(screen.queryByText('notebooks.activeNotebooks')).toBeNull()
    expect(screen.getByText('notebooks.archivedNotebooks')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="empty-state"]')).toBeNull()
  })

  it('no result: ONE page-level search empty state without CTA; Escape restores the full list', () => {
    setup({ data: [nb('n1', 'Alpha')] }, { data: [nb('a1', 'Zeta', '', true)] })

    fireEvent.change(searchBox(), { target: { value: 'nothing-matches' } })

    const empties = document.querySelectorAll('[data-slot="empty-state"]')
    expect(empties).toHaveLength(1)
    expect(empties[0]).toHaveAttribute('data-variant', 'search')
    expect(within(empties[0] as HTMLElement).getByText('notebooks.noSearchResultTitle')).toBeInTheDocument()
    expect(within(empties[0] as HTMLElement).getByText('notebooks.noSearchResultDesc')).toBeInTheDocument()
    expect(within(empties[0] as HTMLElement).queryByRole('button')).toBeNull()
    expect(screen.queryByRole('button', { name: 'notebooks.newNotebook' })).toBeInTheDocument() // toolbar only
    expectHeaderAndToolbar()

    fireEvent.keyDown(searchBox(), { key: 'Escape' })
    expect(searchBox()).toHaveValue('')
    expect(names()).toEqual(['Alpha'])
  })

  it('clear (X) returns to the full list immediately', () => {
    setup({ data: [nb('n1', 'Alpha'), nb('n2', 'Beta')] })
    fireEvent.change(searchBox(), { target: { value: 'beta' } })
    expect(names()).toEqual(['Beta'])

    fireEvent.click(screen.getByRole('button', { name: 'common.clearSearch' }))
    expect(names()).toEqual(['Alpha', 'Beta'])
  })

  it('no data (empty query): regular empty state keeps the create CTA', () => {
    setup({ data: [] })
    const empty = document.querySelector('[data-slot="empty-state"]') as HTMLElement
    expect(empty).toHaveAttribute('data-variant', 'empty')
    expect(within(empty).getByRole('button', { name: 'notebooks.newNotebook' })).toBeInTheDocument()
  })

  it('error: ErrorState with a real retry; header + toolbar stay', () => {
    const refetch = vi.fn()
    setup({ data: undefined, isError: true, refetch })

    const alert = screen.getByRole('alert')
    expect(within(alert).getByText('notebooks.loadErrorTitle')).toBeInTheDocument()
    expect(within(alert).getByText('notebooks.loadErrorDesc')).toBeInTheDocument()
    expectHeaderAndToolbar()

    fireEvent.click(within(alert).getByRole('button', { name: 'common.retry' }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('loading: skeleton instead of a full-area spinner; header + toolbar stay', () => {
    setup({ data: undefined, isLoading: true })
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
    expectHeaderAndToolbar()
  })

  it('loading while searching does not flash the no-result state', () => {
    setup({ data: undefined, isLoading: true })
    fireEvent.change(searchBox(), { target: { value: 'x' } })
    expect(document.querySelector('[data-slot="empty-state"]')).toBeNull()
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
  })

  it('archived-only match is shown expanded while searching (no extra click)', () => {
    setup({ data: [nb('n1', 'Alpha')] }, { data: [nb('a1', 'Zeta', 'Old archive', true)] })

    // Default (no query): archived group collapsed, toggle present
    expect(names()).toEqual(['Alpha'])
    expect(archivedToggle()).not.toBeNull()

    fireEvent.change(searchBox(), { target: { value: 'old archive' } })
    expect(names()).toEqual(['Zeta'])
    expect(archivedToggle()).toBeNull()
  })

  it('clearing the query returns the archived group to its normal collapsed state', () => {
    setup({ data: [nb('n1', 'Alpha')] }, { data: [nb('a1', 'Zeta', '', true)] })

    fireEvent.change(searchBox(), { target: { value: 'zeta' } })
    expect(names()).toEqual(['Zeta'])

    fireEvent.keyDown(searchBox(), { key: 'Escape' })
    expect(names()).toEqual(['Alpha'])
    expect(archivedToggle()).not.toBeNull()
    expect(screen.queryByText('Zeta')).toBeNull()

    // Still the regular collapsible behaviour
    fireEvent.click(archivedToggle() as HTMLElement)
    expect(names()).toEqual(['Alpha', 'Zeta'])
  })
})
