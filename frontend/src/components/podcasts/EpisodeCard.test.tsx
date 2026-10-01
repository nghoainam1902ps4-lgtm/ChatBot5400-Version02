import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { EpisodeCard } from './EpisodeCard'
import type { PodcastEpisode } from '@/lib/types/podcasts'
import apiClient from '@/lib/api/client'
import { resolvePodcastAssetUrl } from '@/lib/api/podcasts'

// t returns the key string, as in the global mock, but with a stable identity
// like the real hook (the audio effect depends on it).
vi.mock('@/lib/hooks/use-translation', () => {
  const t = (key: string) => key
  return { useTranslation: () => ({ t, language: 'en-US', setLanguage: vi.fn() }) }
})

vi.mock('@/lib/api/client', () => ({
  default: { get: vi.fn() },
}))

vi.mock('@/lib/api/podcasts', () => ({
  resolvePodcastAssetUrl: vi.fn(async () => undefined),
}))

function makeEpisode(overrides: Partial<PodcastEpisode> = {}): PodcastEpisode {
  return {
    id: 'episode:1',
    name: 'Test Episode',
    episode_profile: {
      id: 'episode_profile:1',
      name: 'default',
      description: '',
      speaker_config: null,
      default_briefing: '',
      num_segments: 5,
    },
    speaker_profile: {
      id: 'speaker_profile:1',
      name: 'default',
      description: '',
      speakers: [],
    },
    briefing: 'briefing',
    job_status: 'completed',
    ...overrides,
  }
}

function renderAndOpenDetails(episode: PodcastEpisode) {
  render(<EpisodeCard episode={episode} onDelete={vi.fn()} />)
  fireEvent.click(screen.getByText('podcasts.details'))
}

describe('EpisodeCard model details', () => {
  it('renders API-resolved model display fields for new episodes', () => {
    renderAndOpenDetails(
      makeEpisode({
        episode_profile: {
          id: 'episode_profile:1',
          name: 'modern',
          description: '',
          speaker_config: null,
          default_briefing: '',
          num_segments: 5,
          outline_llm: 'model:outline',
          transcript_llm: 'model:transcript',
          outline_model_provider: 'openai',
          outline_model_name: 'gpt-4o',
          transcript_model_provider: 'anthropic',
          transcript_model_name: 'claude-sonnet',
        },
        speaker_profile: {
          id: 'speaker_profile:1',
          name: 'modern',
          description: '',
          speakers: [],
          voice_model: 'model:voice',
          voice_model_provider: 'elevenlabs',
          voice_model_name: 'eleven_turbo',
        },
      })
    )

    expect(screen.getByText('openai / gpt-4o')).toBeInTheDocument()
    expect(screen.getByText('anthropic / claude-sonnet')).toBeInTheDocument()
    expect(screen.getByText('elevenlabs / eleven_turbo')).toBeInTheDocument()
  })

  it('falls back to legacy snapshot strings for old episodes', () => {
    renderAndOpenDetails(
      makeEpisode({
        episode_profile: {
          id: 'episode_profile:1',
          name: 'legacy',
          description: '',
          speaker_config: null,
          default_briefing: '',
          num_segments: 5,
          outline_provider: 'openai',
          outline_model: 'gpt-3.5-turbo',
          transcript_provider: 'openai',
          transcript_model: 'gpt-4',
        },
        speaker_profile: {
          id: 'speaker_profile:1',
          name: 'legacy',
          description: '',
          speakers: [],
          tts_provider: 'openai',
          tts_model: 'tts-1',
        },
      })
    )

    expect(screen.getByText('openai / gpt-3.5-turbo')).toBeInTheDocument()
    expect(screen.getByText('openai / gpt-4')).toBeInTheDocument()
    expect(screen.getByText('openai / tts-1')).toBeInTheDocument()
  })

  it('degrades to dashes when references are unresolvable and no legacy strings exist', () => {
    renderAndOpenDetails(
      makeEpisode({
        episode_profile: {
          id: 'episode_profile:1',
          name: 'orphaned',
          description: '',
          speaker_config: null,
          default_briefing: '',
          num_segments: 5,
          outline_llm: 'model:deleted',
          transcript_llm: 'model:deleted',
        },
        speaker_profile: {
          id: 'speaker_profile:1',
          name: 'orphaned',
          description: '',
          speakers: [],
          voice_model: 'model:deleted',
        },
      })
    )

    expect(screen.getAllByText('— / —')).toHaveLength(3)
  })
})

describe('EpisodeCard status badge', () => {
  it('renders a completed badge with success semantics (not fern)', () => {
    render(<EpisodeCard episode={makeEpisode({ job_status: 'completed' })} onDelete={vi.fn()} />)
    const badge = screen.getByText('podcasts.completedLabel')
    expect(badge.className).toContain('bg-success-tint')
    expect(badge.className).toContain('text-success')
    expect(badge.className).toContain('border-success/30')
    expect(badge.className).not.toMatch(/fern/)
  })

  it.each([
    ['pending', 'podcasts.pendingLabel', 'text-teal'],
    ['running', 'podcasts.processingLabel', 'text-warn'],
    ['processing', 'podcasts.processingLabel', 'text-warn'],
    ['failed', 'podcasts.failedLabel', 'text-destructive'],
    ['error', 'podcasts.failedLabel', 'text-destructive'],
  ] as const)('status %s keeps its existing group (%s, %s)', (status, label, cls) => {
    render(<EpisodeCard episode={makeEpisode({ job_status: status })} onDelete={vi.fn()} />)
    expect(screen.getByText(label).className).toContain(cls)
  })
})

describe('EpisodeCard audio player (P1A)', () => {
  it('renders exactly one <audio>, also with the details dialog open, from a single fetch', async () => {
    vi.mocked(resolvePodcastAssetUrl).mockResolvedValueOnce('http://api.test/podcasts/episodes/1/audio')
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: new Blob(['x']) })
    const createObjectURL = vi.fn(() => 'blob:episode-audio')
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() })

    render(
      <EpisodeCard
        episode={makeEpisode({ audio_url: '/api/podcasts/episodes/1/audio' })}
        onDelete={vi.fn()}
      />
    )
    await waitFor(() => expect(document.querySelectorAll('audio')).toHaveLength(1))

    fireEvent.click(screen.getByText('podcasts.details'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(document.querySelectorAll('audio')).toHaveLength(1)
    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('shows the audio error once (not duplicated in the dialog)', async () => {
    vi.mocked(resolvePodcastAssetUrl).mockResolvedValueOnce('http://api.test/podcasts/episodes/1/audio')
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('403'))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <EpisodeCard
        episode={makeEpisode({ audio_url: '/api/podcasts/episodes/1/audio' })}
        onDelete={vi.fn()}
      />
    )
    await screen.findByText('podcasts.audioUnavailable')
    fireEvent.click(screen.getByText('podcasts.details'))
    expect(screen.getAllByText('podcasts.audioUnavailable')).toHaveLength(1)
  })

  it('an episode without a status shows the common.unknown badge', () => {
    render(<EpisodeCard episode={makeEpisode({ job_status: null })} onDelete={vi.fn()} />)
    expect(screen.getByText('common.unknown')).toBeInTheDocument()
  })

  it('an unlisted job status (e.g. "new") falls back to the unknown badge instead of crashing', () => {
    render(
      <EpisodeCard
        episode={makeEpisode({ job_status: 'new' as PodcastEpisode['job_status'] })}
        onDelete={vi.fn()}
      />
    )
    expect(screen.getByText('common.unknown')).toBeInTheDocument()
  })
})
