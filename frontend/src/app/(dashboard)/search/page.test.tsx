import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SearchPage from './page'
import { useSearch } from '@/lib/hooks/use-search'
import { useModalManager } from '@/lib/hooks/use-modal-manager'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/search',
  useSearchParams: () => new URLSearchParams('mode=search'),
}))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/search/NotebookScopeSelector', () => ({
  NotebookScopeSelector: () => null,
}))

vi.mock('@/components/search/StreamingResponse', () => ({
  StreamingResponse: () => null,
}))

vi.mock('@/components/search/AdvancedModelsDialog', () => ({
  AdvancedModelsDialog: () => null,
}))

vi.mock('@/components/search/SaveToNotebooksDialog', () => ({
  SaveToNotebooksDialog: () => null,
}))

vi.mock('@/lib/hooks/use-search', () => ({
  useSearch: vi.fn(),
}))

vi.mock('@/lib/hooks/use-ask', () => ({
  useAsk: () => ({
    sendAsk: vi.fn(),
    isStreaming: false,
    strategy: null,
    answers: [],
    finalAnswer: '',
  }),
}))

vi.mock('@/lib/hooks/use-models', () => ({
  useModelDefaults: () => ({ data: null, isLoading: false }),
  useModels: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/lib/hooks/use-modal-manager', () => ({
  useModalManager: vi.fn(),
}))

const mockUseSearch = vi.mocked(useSearch)
const mockUseModalManager = vi.mocked(useModalManager)
const openModal = vi.fn()
const mutate = vi.fn()

function mockSearchState(state: Record<string, unknown>) {
  mockUseSearch.mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    mutate,
    ...state,
  } as unknown as ReturnType<typeof useSearch>)
}

const queryBox = () => screen.getByRole('textbox', { name: 'common.accessibility.enterSearch' })

describe('SearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseSearch.mockReturnValue({
      data: {
        results: [{
          id: 'source_insight:matched-insight',
          parent_id: 'source:parent-source',
          title: 'Matched insight',
          final_score: 0.9,
          created: '2026-01-01T00:00:00Z',
          updated: '2026-01-01T00:00:00Z',
        }],
        total_count: 1,
        search_type: 'text',
      },
      isPending: false,
      mutate: vi.fn(),
    } as unknown as ReturnType<typeof useSearch>)
    mockUseModalManager.mockReturnValue({ openModal } as unknown as ReturnType<typeof useModalManager>)
  })

  it('opens the record that matched instead of its parent source', () => {
    render(<SearchPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Matched insight' }))

    expect(openModal).toHaveBeenCalledWith('insight', 'matched-insight')
  })

  it('keeps the unified PageHeader and no Card around the form', () => {
    render(<SearchPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'searchPage.askAndSearch' })).toBeInTheDocument()
    for (const form of document.querySelectorAll('[data-slot="query-form"]')) {
      expect(form.closest('[data-slot="card"]')).toBeNull()
    }
  })

  it('reading width 880 with a 680 form on the same left edge (no own mx-auto)', () => {
    render(<SearchPage />)
    const shell = document.querySelector('[data-slot="page-shell"]') as HTMLElement
    expect(shell).toHaveAttribute('data-width', 'reading')
    const forms = document.querySelectorAll('[data-slot="query-form"]')
    expect(forms.length).toBeGreaterThan(0)
    for (const form of forms) {
      expect(form.className).toContain('max-w-[680px]')
      expect(form.className).not.toContain('mx-auto')
    }
  })

  it('Enter (keydown) submits with limit 100 / minimum_score 0.2; IME composition Enter does not', () => {
    mockSearchState({})
    render(<SearchPage />)
    fireEvent.change(queryBox(), { target: { value: 'tín dụng' } })

    fireEvent.keyDown(queryBox(), { key: 'Enter', isComposing: true })
    expect(mutate).not.toHaveBeenCalled()

    fireEvent.keyDown(queryBox(), { key: 'Enter' })
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ query: 'tín dụng', limit: 100, minimum_score: 0.2 })
    )
  })

  it('search error: inline ErrorState, retry re-runs the same query, query kept', () => {
    mockSearchState({ isError: true })
    render(<SearchPage />)
    fireEvent.change(queryBox(), { target: { value: 'agribank' } })

    const alert = screen.getByText('apiErrors.searchFailed').closest('[role="alert"]') as HTMLElement
    expect(within(alert).getByText('searchPage.searchErrorDesc')).toBeInTheDocument()

    fireEvent.click(within(alert).getByRole('button', { name: 'common.retry' }))
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ query: 'agribank', limit: 100, minimum_score: 0.2 })
    )
    expect(queryBox()).toHaveValue('agribank')
  })

  it('shows the result limit note next to the summary, score as a separate badge', () => {
    render(<SearchPage />)
    expect(screen.getByText('searchPage.resultLimitNote')).toBeInTheDocument()

    const title = screen.getByRole('button', { name: 'Matched insight' })
    expect(title).not.toHaveTextContent('0.90')
    const score = screen.getByText('0.90')
    expect(title.contains(score)).toBe(false)
    expect(score.className).toContain('shrink-0')
  })

  it('no result: search empty state, no create action, no limit note', () => {
    mockSearchState({ data: { results: [], total_count: 0, search_type: 'text' } })
    render(<SearchPage />)

    const empty = document.querySelector('[data-slot="empty-state"]') as HTMLElement
    expect(empty).toHaveAttribute('data-variant', 'search')
    expect(within(empty).getByText('searchPage.noResultsFor')).toBeInTheDocument()
    expect(within(empty).queryByRole('button')).toBeNull()
    expect(screen.queryByText('searchPage.resultLimitNote')).toBeNull()
  })

  it('both tabs use the same Alert for the missing embedding model', () => {
    render(<SearchPage />)
    const warning = screen.getByText('searchPage.vectorSearchWarning').closest('[role="alert"]') as HTMLElement
    expect(warning).not.toBeNull()
    expect(warning.className).toContain('bg-warn-tint')
  })

  it('mobile: options collapsed behind "more options", always shown from sm, state kept', () => {
    render(<SearchPage />)
    const toggle = screen.getByRole('button', { name: 'common.moreOptions' })
    const options = document.getElementById('search-options') as HTMLElement

    expect(toggle.className).toContain('sm:hidden')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(options.className).toMatch(/(^| )hidden( |$)/)
    expect(options.className).toContain('sm:block')

    const notes = within(options).getByRole('checkbox', { name: 'searchPage.searchNotes' })
    fireEvent.click(notes)
    expect(notes).toHaveAttribute('aria-checked', 'false')

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(options.className).toMatch(/(^| )block( |$)/)

    fireEvent.click(toggle)
    expect(within(options).getByRole('checkbox', { name: 'searchPage.searchNotes' })).toHaveAttribute('aria-checked', 'false')
  })
})
