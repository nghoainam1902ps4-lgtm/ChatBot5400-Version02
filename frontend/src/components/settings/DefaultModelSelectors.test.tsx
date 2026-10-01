import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DefaultModelSelectors } from './DefaultModelSelectors'
import type { ModelDefaults } from '@/lib/types/models'

// useTranslation is mocked globally in setup.ts (t returns the key string)

vi.mock('@/lib/hooks/use-models', () => ({
  useUpdateModelDefaults: () => ({ mutate: vi.fn(), isPending: false }),
  useAutoAssignDefaults: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('./EmbeddingModelChangeDialog', () => ({ EmbeddingModelChangeDialog: () => null }))

const emptyDefaults = {
  default_chat_model: null,
  default_transformation_model: null,
  default_tools_model: null,
  large_context_model: null,
  default_embedding_model: null,
  default_text_to_speech_model: null,
  default_speech_to_text_model: null,
} as unknown as ModelDefaults

describe('DefaultModelSelectors (P1B)', () => {
  it('labels the advanced group with models.advancedGroup, not a navigation key', () => {
    render(<DefaultModelSelectors models={[]} defaults={emptyDefaults} />)
    expect(screen.getByText('models.advancedGroup')).toBeInTheDocument()
    expect(screen.queryByText('navigation.advanced')).toBeNull()
  })

  it('shows missing required defaults with the shared warn treatment', () => {
    render(<DefaultModelSelectors models={[]} defaults={emptyDefaults} />)
    const alert = screen.getByText('models.missingRequiredModels').closest('[role="alert"]') as HTMLElement
    expect(alert.className).toContain('border-warn/30')
    expect(alert.className).toContain('bg-warn-tint')
    expect(alert.className).toContain('text-warn')
    expect(screen.getByRole('button', { name: /models\.autoAssign/ })).toBeInTheDocument()
  })

  it('select triggers fill (and may shrink within) their grid cell so long labels never overlap', () => {
    render(<DefaultModelSelectors models={[]} defaults={emptyDefaults} />)
    const triggers = document.querySelectorAll('[data-slot="select-trigger"]')
    expect(triggers.length).toBe(7)
    triggers.forEach((trigger) => {
      expect(trigger.className).toContain('w-full')
      expect(trigger.className).toContain('min-w-0')
      expect((trigger.parentElement?.parentElement as HTMLElement).className).toContain('min-w-0')
    })
  })
})
