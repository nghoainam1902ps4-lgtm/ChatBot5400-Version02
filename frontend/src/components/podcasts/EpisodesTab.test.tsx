import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EpisodesTab } from './EpisodesTab'
import { usePodcastEpisodes } from '@/lib/hooks/use-podcasts'
import type { PodcastEpisode } from '@/lib/types/podcasts'

// useTranslation is mocked globally in setup.ts (t returns the key string)

vi.mock('@/lib/hooks/use-podcasts', () => ({
  usePodcastEpisodes: vi.fn(),
  useDeletePodcastEpisode: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRetryPodcastEpisode: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/components/podcasts/EpisodeCard', () => ({
  EpisodeCard: ({ episode }: { episode: PodcastEpisode }) => <div data-testid="episode">{episode.name}</div>,
}))
vi.mock('@/components/podcasts/GeneratePodcastDialog', () => ({ GeneratePodcastDialog: () => null }))

const mockEpisodes = vi.mocked(usePodcastEpisodes)

const ep = (id: string, job_status: PodcastEpisode['job_status']) =>
  ({ id, name: id, job_status }) as PodcastEpisode

function setup(state: Partial<ReturnType<typeof usePodcastEpisodes>>) {
  const groups = { running: [], completed: [], failed: [], pending: [], ...(state.statusGroups ?? {}) }
  mockEpisodes.mockReturnValue({
    episodes: [],
    statusCounts: {
      total: 0,
      running: groups.running.length,
      completed: groups.completed.length,
      failed: groups.failed.length,
      pending: groups.pending.length,
    },
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
    ...state,
    statusGroups: groups,
  } as unknown as ReturnType<typeof usePodcastEpisodes>)
  return render(<EpisodesTab />)
}

describe('EpisodesTab (P1A)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('summary badges: Total, then pending → processing → completed → failed', () => {
    setup({ episodes: [ep('a', 'completed')] })
    const labels = ['podcasts.total', 'podcasts.pendingLabel', 'podcasts.processingLabel', 'podcasts.completedLabel', 'podcasts.failedLabel']
    const nodes = labels.map((l) => screen.getByText(l))
    for (let i = 1; i < nodes.length; i++) {
      expect(nodes[i - 1].compareDocumentPosition(nodes[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })

  it('sections use the same order and carry the pending/completed notes', () => {
    const statusGroups = {
      running: [ep('r', 'running')],
      completed: [ep('c', 'completed')],
      failed: [ep('f', 'failed')],
      pending: [ep('p', 'pending'), ep('u', null)],
    }
    setup({ episodes: Object.values(statusGroups).flat(), statusGroups })

    const order = Array.from(document.querySelectorAll('[data-status-group]')).map((s) => s.getAttribute('data-status-group'))
    expect(order).toEqual(['pending', 'running', 'completed', 'failed'])

    const pending = document.querySelector('[data-status-group="pending"]') as HTMLElement
    expect(within(pending).getByText('podcasts.statusPendingDesc')).toBeInTheDocument()
    expect(within(pending).getByText('podcasts.statusPendingNote')).toBeInTheDocument()
    // Unknown status stays in the pending group
    expect(within(pending).getByText('u')).toBeInTheDocument()

    const completed = document.querySelector('[data-status-group="completed"]') as HTMLElement
    expect(within(completed).getByText('podcasts.statusCompletedDesc')).toBeInTheDocument()
    expect(within(completed).getByText('podcasts.statusCompletedNote')).toBeInTheDocument()
  })

  it('error: ErrorState whose retry calls refetch(); no empty state', () => {
    const refetch = vi.fn()
    setup({ isError: true, refetch })

    const alert = screen.getByRole('alert')
    expect(within(alert).getByText('podcasts.loadErrorTitle')).toBeInTheDocument()
    expect(within(alert).getByText('podcasts.loadErrorDesc')).toBeInTheDocument()
    fireEvent.click(within(alert).getByRole('button', { name: 'common.retry' }))
    expect(refetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('podcasts.noEpisodesYet')).toBeNull()
  })

  it('loading: card skeleton, no fake progress', () => {
    setup({ isLoading: true })
    const skeleton = document.querySelector('[data-slot="loading-skeleton"]') as HTMLElement
    expect(skeleton).toHaveAttribute('data-variant', 'card')
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('empty: empty state, generate action still available', () => {
    setup({})
    expect(screen.getByText('podcasts.noEpisodesYet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'podcasts.generateBtn' })).toBeInTheDocument()
  })
})
