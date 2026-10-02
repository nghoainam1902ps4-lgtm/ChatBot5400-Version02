import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

// Radix Select measures its trigger via ResizeObserver, which jsdom lacks.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub)

import { SettingsForm } from './SettingsForm'

// useTranslation is mocked globally in setup.ts (t returns the key string),
// so hint keys render as their literal key names below.

const mutateAsync = vi.fn()
vi.mock('@/lib/hooks/use-settings', () => ({
  useSettings: vi.fn(),
  useUpdateSettings: vi.fn(() => ({ mutateAsync, isPending: false })),
}))

vi.mock('@/lib/hooks/use-capabilities', () => ({
  useCapabilities: vi.fn(),
}))

import { useSettings } from '@/lib/hooks/use-settings'
import { useCapabilities } from '@/lib/hooks/use-capabilities'

const settingsData = {
  default_content_processing_engine_doc: 'auto',
  default_content_processing_engine_url: 'auto',
  default_embedding_option: 'ask',
  auto_delete_files: 'no',
  docling_ocr: true,
}

function mockCapabilities(caps: unknown, { isError = false } = {}) {
  ;(useSettings as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    data: settingsData,
    isLoading: false,
    error: null,
  })
  ;(useCapabilities as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    data: caps,
    isError,
  })
}

describe('SettingsForm engine gating', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('disables OCR and shows env hints when the runtimes are unavailable', () => {
    mockCapabilities({
      docling_available: false,
      crawl4ai_available: false,
      crawl4ai_remote_configured: false,
    })
    render(<SettingsForm />)

    expect(screen.getByText('settings.enableDoclingHint')).toBeInTheDocument()
    expect(screen.getByText('settings.enableCrawl4aiHint')).toBeInTheDocument()
    // Target the OCR toggle by its accessible name (from the associated Label).
    expect(
      screen.getByRole('checkbox', { name: 'settings.ocrEnabled' })
    ).toBeDisabled()
  })

  it('enables OCR and hides the hints when the runtimes are available', () => {
    mockCapabilities({
      docling_available: true,
      crawl4ai_available: true,
      crawl4ai_remote_configured: false,
    })
    render(<SettingsForm />)

    expect(screen.queryByText('settings.enableDoclingHint')).not.toBeInTheDocument()
    expect(screen.queryByText('settings.enableCrawl4aiHint')).not.toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: 'settings.ocrEnabled' })
    ).not.toBeDisabled()
  })

  it('treats runtimes as available while the capability probe is still loading', () => {
    mockCapabilities(undefined)
    render(<SettingsForm />)

    // Optimistic default avoids a flash of disabled controls on a working setup.
    expect(screen.queryByText('settings.enableDoclingHint')).not.toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: 'settings.ocrEnabled' })
    ).not.toBeDisabled()
  })

  it('fails closed when the capability probe errors', () => {
    mockCapabilities(undefined, { isError: true })
    render(<SettingsForm />)

    // A failed probe must not advertise engines the backend couldn't verify.
    expect(screen.getByText('settings.enableDoclingHint')).toBeInTheDocument()
    expect(screen.getByText('settings.enableCrawl4aiHint')).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: 'settings.ocrEnabled' })
    ).toBeDisabled()
  })
})

const available = { docling_available: true, crawl4ai_available: true, crawl4ai_remote_configured: false }
const saveBar = () => document.querySelector('[data-slot="settings-save-bar"]')
const ocr = () => screen.getByRole('checkbox', { name: 'settings.ocrEnabled' })

describe('SettingsForm (P1C)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loading: skeleton instead of a full-area spinner', () => {
    ;(useSettings as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: undefined, isLoading: true, error: null })
    ;(useCapabilities as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: available, isError: false })
    render(<SettingsForm />)
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
  })

  it('error: readable ErrorState (never the raw error message) whose retry refetches', () => {
    const refetch = vi.fn()
    ;(useSettings as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Request failed with status code 500 at axios'),
      refetch,
    })
    ;(useCapabilities as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: available, isError: false })
    render(<SettingsForm />)
    expect(screen.getByText('settings.loadFailed')).toBeInTheDocument()
    expect(screen.getByText('settings.loadFailedDesc')).toBeInTheDocument()
    expect(screen.queryByText(/status code 500/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('renders the four "Help me choose" blocks through one helper, each independently toggled', () => {
    mockCapabilities(available)
    render(<SettingsForm />)
    const triggers = screen.getAllByRole('button', { name: 'settings.helpMeChoose' })
    expect(triggers).toHaveLength(4)
    expect(screen.queryByText('settings.urlHelp')).toBeNull()
    fireEvent.click(triggers[1])
    expect(screen.getByText('settings.urlHelp')).toBeInTheDocument()
    expect(screen.queryByText('settings.docHelp')).toBeNull()
  })

  it('no save bar while clean; a sticky bar with Undo + Save appears once dirty', async () => {
    mockCapabilities(available)
    render(<SettingsForm />)
    await waitFor(() => expect(ocr()).toBeChecked())
    expect(saveBar()).toBeNull()

    fireEvent.click(ocr())
    await waitFor(() => expect(saveBar()).not.toBeNull())
    expect((saveBar() as HTMLElement).className).toContain('sticky')
    expect((saveBar() as HTMLElement).className).toContain('bottom-0')
    expect(screen.getByRole('button', { name: 'settings.undoChanges' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'common.save' })).toBeInTheDocument()
  })

  it('Undo restores the values loaded from the server (not product defaults) and clears dirty', async () => {
    mockCapabilities(available)
    render(<SettingsForm />)
    await waitFor(() => expect(ocr()).toBeChecked())

    fireEvent.click(ocr())
    await waitFor(() => expect(ocr()).not.toBeChecked())
    fireEvent.click(screen.getByRole('button', { name: 'settings.undoChanges' }))

    await waitFor(() => expect(saveBar()).toBeNull())
    expect(ocr()).toBeChecked()
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it('a successful save sends the same 7-field payload and clears the dirty bar', async () => {
    mutateAsync.mockResolvedValue({})
    mockCapabilities(available)
    render(<SettingsForm />)
    await waitFor(() => expect(ocr()).toBeChecked())

    fireEvent.click(ocr())
    await waitFor(() => expect(saveBar()).not.toBeNull())
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    })

    await waitFor(() => expect(saveBar()).toBeNull())
    expect(mutateAsync).toHaveBeenCalledTimes(1)
    expect(mutateAsync.mock.calls[0][0]).toEqual({
      default_content_processing_engine_doc: 'auto',
      default_content_processing_engine_url: 'auto',
      default_embedding_option: 'ask',
      auto_delete_files: 'no',
      docling_ocr: false,
      docling_formulas: false,
      docling_vision: false,
    })
  })

  it('a failed save keeps the unsaved changes (bar stays)', async () => {
    mutateAsync.mockRejectedValue(new Error('boom'))
    mockCapabilities(available)
    render(<SettingsForm />)
    await waitFor(() => expect(ocr()).toBeChecked())
    fireEvent.click(ocr())
    await waitFor(() => expect(saveBar()).not.toBeNull())
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    })
    expect(saveBar()).not.toBeNull()
  })
})
