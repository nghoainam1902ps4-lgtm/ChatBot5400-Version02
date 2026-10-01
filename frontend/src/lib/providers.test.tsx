import { render } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { getTypeIcon, getTypeColor, getTypeLabel } from './providers'

describe('model type presentation helpers', () => {
  it('maps known modalities to their icons', () => {
    const { container } = render(<>{getTypeIcon('language')}</>)
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(container.querySelector('.lucide-box')).not.toBeInTheDocument()
  })

  it('falls back to a generic icon for unknown modalities', () => {
    // Provider modalities are runtime data from GET /api/providers: a new
    // backend modality must still render instead of breaking the UI.
    const { container } = render(<>{getTypeIcon('holograms')}</>)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders different markup for known vs unknown modalities', () => {
    const known = render(<>{getTypeIcon('embedding')}</>)
    const unknown = render(<>{getTypeIcon('not-a-modality')}</>)
    expect(known.container.innerHTML).not.toEqual(unknown.container.innerHTML)
  })

  it('falls back to the raw modality name as label', () => {
    expect(getTypeLabel('language')).toBe('Language')
    expect(getTypeLabel('holograms')).toBe('holograms')
  })

  it('translates the four known modalities when given a translator', () => {
    const t = (key: string) => `T(${key})`
    expect(getTypeLabel('language', t)).toBe('T(models.type.language)')
    expect(getTypeLabel('embedding', t)).toBe('T(models.type.embedding)')
    expect(getTypeLabel('text_to_speech', t)).toBe('T(models.type.textToSpeech)')
    expect(getTypeLabel('speech_to_text', t)).toBe('T(models.type.speechToText)')
  })

  it('never translates an unknown modality: raw name, not a raw i18n key, no throw', () => {
    const t = vi.fn((key: string) => key)
    expect(getTypeLabel('holograms', t)).toBe('holograms')
    expect(getTypeLabel('constructor', t)).toBe('constructor')
    expect(getTypeLabel('toString', t)).toBe('toString')
    expect(t).not.toHaveBeenCalled()
  })

  it('falls back to a neutral color for unknown modalities', () => {
    expect(getTypeColor('holograms')).toBeTruthy()
    expect(getTypeColor('holograms')).not.toEqual(getTypeColor('language'))
  })
})
