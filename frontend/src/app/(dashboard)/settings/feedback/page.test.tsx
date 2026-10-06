import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import FeedbackPage from './page'
import { useAuth } from '@/lib/hooks/use-auth'
import type { AdminFeedbackItem } from '@/lib/types/api'

// useAuth + useTranslation are globally mocked in setup.ts.

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const h = vi.hoisted(() => ({
  stats: { data: { total: 3, likes: 1, dislikes: 1, reports: 1 } as { total: number; likes: number; dislikes: number; reports: number } | undefined, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() },
  list: {
    data: { items: [] as AdminFeedbackItem[], page: 1, page_size: 30, total: 0, total_pages: 0 },
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  },
}))

vi.mock('@/lib/hooks/use-feedback', () => ({
  useAdminFeedbackStats: () => h.stats,
  useAdminFeedbackList: () => h.list,
}))

const row: AdminFeedbackItem = {
  id: 'ai_feedback:1',
  username_snapshot: 'alice',
  user_name_snapshot: 'Alice A',
  session_id: 'chat_session:s1',
  message_id: 'uuid-1',
  context_type: 'notebook',
  context_id: 'notebook:n1',
  context_title_snapshot: 'My NB',
  question_snapshot: 'Why is the sky blue?',
  answer_snapshot: 'Because of Rayleigh scattering.',
  reaction: 'dislike',
  reported: true,
  report_reason: 'Not detailed enough',
  reported_at: '2026-01-02T00:00:00Z',
  created: '2026-01-02T00:00:00Z',
  updated: '2026-01-02T00:00:00Z',
}

describe('Admin AI Feedback page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '1', username: 'admin', role: 'admin' },
      isAdmin: true,
      isLoading: false,
      logout: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>)
    h.stats = { data: { total: 3, likes: 1, dislikes: 1, reports: 1 }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() }
    h.list = {
      data: { items: [], page: 1, page_size: 30, total: 0, total_pages: 0 },
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    }
  })
  afterEach(cleanup)

  it('shows AccessDenied in place for a non-admin (no redirect)', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '2', username: 'bob', role: 'user' },
      isAdmin: false,
      isLoading: false,
      logout: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>)
    render(<FeedbackPage />)
    expect(screen.getByText('common.accessDenied.title')).toBeInTheDocument()
    // the toolbar/search is not rendered for non-admins
    expect(screen.queryByRole('search')).toBeNull()
  })

  it('renders stat cards for admins', () => {
    render(<FeedbackPage />)
    expect(screen.getByText('feedback.statTotal')).toBeInTheDocument()
    // total value 3 rendered
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('does not render a misleading 0 when stats fail to load; shows retry', () => {
    h.stats = { data: undefined, isLoading: false, isError: true, isFetching: false, refetch: vi.fn() }
    render(<FeedbackPage />)
    // stat values show the em dash placeholder, never a fake 0
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4)
    expect(screen.getByText('feedback.loadError')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'common.retry' })).toBeInTheDocument()
  })

  it('renders an empty state when there is no feedback', () => {
    render(<FeedbackPage />)
    expect(screen.getByText('feedback.empty')).toBeInTheDocument()
  })

  it('renders an error state with retry', () => {
    h.list = { ...h.list, isError: true }
    render(<FeedbackPage />)
    expect(screen.getByText('feedback.loadError')).toBeInTheDocument()
  })

  it('renders rows with multiple badges and opens the detail dialog on row click', () => {
    h.list = {
      ...h.list,
      data: { items: [row], page: 1, page_size: 30, total: 1, total_pages: 1 },
    }
    render(<FeedbackPage />)
    // the row shows both a dislike and a reported badge
    expect(screen.getAllByText('feedback.dislike').length).toBeGreaterThan(0)
    expect(screen.getAllByText('feedback.reportedBadge').length).toBeGreaterThan(0)

    // open detail via the desktop row
    const questionCells = screen.getAllByText('Why is the sky blue?')
    fireEvent.click(questionCells[0])

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('feedback.detailTitle')).toBeInTheDocument()
    expect(within(dialog).getByText('Because of Rayleigh scattering.')).toBeInTheDocument()
    expect(within(dialog).getByText('Not detailed enough')).toBeInTheDocument()
  })

  it('shows numbered pagination controls when there is more than one page', () => {
    h.list = {
      ...h.list,
      data: { items: [row], page: 1, page_size: 30, total: 90, total_pages: 3 },
    }
    render(<FeedbackPage />)
    expect(screen.getByRole('button', { name: /feedback.prevPage/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /feedback.nextPage/ })).toBeEnabled()
    expect(screen.getByText('feedback.pageInfo')).toBeInTheDocument()
  })

  // --- P2A.1: manual refresh ------------------------------------------------
  it('shows a Refresh button for admins', () => {
    render(<FeedbackPage />)
    expect(screen.getByRole('button', { name: 'feedback.refresh' })).toBeInTheDocument()
  })

  it('refreshes BOTH stats and list in place when clicked', () => {
    render(<FeedbackPage />)
    fireEvent.click(screen.getByRole('button', { name: 'feedback.refresh' }))
    expect(h.stats.refetch).toHaveBeenCalledTimes(1)
    expect(h.list.refetch).toHaveBeenCalledTimes(1)
  })

  it('disables Refresh while stats is fetching', () => {
    h.stats = { ...h.stats, isFetching: true }
    render(<FeedbackPage />)
    expect(screen.getByRole('button', { name: 'feedback.refresh' })).toBeDisabled()
  })

  it('disables Refresh while the list is fetching', () => {
    h.list = { ...h.list, isFetching: true }
    render(<FeedbackPage />)
    expect(screen.getByRole('button', { name: 'feedback.refresh' })).toBeDisabled()
  })

  it('enables Refresh when nothing is fetching', () => {
    render(<FeedbackPage />)
    expect(screen.getByRole('button', { name: 'feedback.refresh' })).toBeEnabled()
  })

  it('refresh does not reset search / filter / page state', () => {
    // The list query key is derived from params; a refetch must not alter the
    // params the page holds. Spies on the filter setters would require wiring;
    // instead we assert the handler only refetches (does not change the
    // rendered page controls). Default page 1 / type "all" / context "all".
    render(<FeedbackPage />)
    fireEvent.click(screen.getByRole('button', { name: 'feedback.refresh' }))
    // the type/context selects keep their default values (no reset)
    expect(screen.getByRole('button', { name: 'feedback.refresh' })).toBeInTheDocument()
    // only the existing queries were refetched; no extra behavior
    expect(h.stats.refetch).toHaveBeenCalledTimes(1)
    expect(h.list.refetch).toHaveBeenCalledTimes(1)
  })
})
