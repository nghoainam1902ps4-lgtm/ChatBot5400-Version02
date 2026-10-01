import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CredentialItem } from './CredentialItem'
import type { Credential } from '@/lib/api/credentials'
import type { Model, ModelDefaults } from '@/lib/types/models'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const testCredential = vi.fn()
let testResults: Record<string, { success: boolean; message?: string }> = {}
vi.mock('@/lib/hooks/use-credentials', () => ({
  useTestCredential: () => ({ testCredential, isPending: false, testResults }),
  useCredential: () => ({ data: undefined }),
}))
vi.mock('@/lib/hooks/use-models', () => ({
  useTestModel: () => ({
    testModel: vi.fn(),
    isPending: false,
    testingModelId: null,
    testResult: null,
    testedModelName: '',
    clearResult: vi.fn(),
  }),
  useDeleteModel: () => ({ mutate: vi.fn() }),
}))
vi.mock('./CredentialFormDialog', () => ({
  CredentialFormDialog: ({ open }: { open: boolean }) => (open ? <div data-testid="edit-dialog" /> : null),
}))
vi.mock('./DeleteCredentialDialog', () => ({
  DeleteCredentialDialog: ({ open }: { open: boolean }) => (open ? <div data-testid="delete-dialog" /> : null),
}))
vi.mock('./DiscoverModelsDialog', () => ({
  DiscoverModelsDialog: ({ open }: { open: boolean }) => (open ? <div data-testid="discover-dialog" /> : null),
}))
vi.mock('./ModelTestResultDialog', () => ({ ModelTestResultDialog: () => null }))

const credential: Credential = {
  id: 'credential:1',
  name: 'OpenAI Prod',
  provider: 'openai',
  modalities: ['language', 'embedding'],
  has_api_key: true,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
  model_count: 2,
}

const model = (id: string, type: string): Model =>
  ({ id, name: id.replace('model:', ''), provider: 'openai', type, credential: 'credential:1' }) as unknown as Model

function renderItem(overrides: Partial<Credential> = {}, models: Model[] = [], defaults: ModelDefaults | null = null) {
  return render(
    <CredentialItem credential={{ ...credential, ...overrides }} models={models} defaults={defaults} allCredentials={[]} />
  )
}

const openMenu = () => {
  const trigger = screen.getByRole('button', { name: 'common.actions' })
  fireEvent.keyDown(trigger, { key: 'Enter' })
  return screen.getByRole('menu')
}

describe('CredentialItem (P1B)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    testResults = {}
  })

  it('keeps Test connection and Sync models as direct, labelled actions', () => {
    renderItem()
    const test = screen.getByRole('button', { name: /apiKeys\.testConnection/ })
    fireEvent.click(test)
    expect(testCredential).toHaveBeenCalledWith('credential:1')

    fireEvent.click(screen.getByRole('button', { name: /apiKeys\.syncModels/ }))
    expect(screen.getByTestId('discover-dialog')).toBeInTheDocument()

    // No hardcoded English labels
    expect(screen.queryByText('Test')).toBeNull()
    expect(screen.queryByText('Models')).toBeNull()
  })

  it('moves Edit and Delete into the "..." menu (no direct buttons)', () => {
    renderItem()
    expect(screen.queryByRole('button', { name: 'common.edit' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'common.delete' })).toBeNull()

    const menu = openMenu()
    expect(within(menu).getByRole('menuitem', { name: 'common.edit' })).toBeInTheDocument()
    const del = within(menu).getByRole('menuitem', { name: 'common.delete' })
    expect(del).toHaveAttribute('data-variant', 'destructive')
  })

  it('menu Delete opens the existing delete dialog; Edit opens the edit dialog', () => {
    renderItem()
    fireEvent.keyDown(within(openMenu()).getByRole('menuitem', { name: 'common.delete' }), { key: 'Enter' })
    expect(screen.getByTestId('delete-dialog')).toBeInTheDocument()
    expect(screen.queryByTestId('edit-dialog')).toBeNull()

    fireEvent.keyDown(within(openMenu()).getByRole('menuitem', { name: 'common.edit' }), { key: 'Enter' })
    expect(screen.getByTestId('edit-dialog')).toBeInTheDocument()
  })

  it('keeps the decryption guards: Test/Sync/Edit disabled, Delete still allowed, warn alert', () => {
    renderItem({ decryption_error: 'bad key' })
    expect(screen.getByRole('button', { name: /apiKeys\.testConnection/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /apiKeys\.syncModels/ })).toBeDisabled()

    const menu = openMenu()
    expect(within(menu).getByRole('menuitem', { name: 'common.edit' })).toHaveAttribute('data-disabled')
    expect(within(menu).getByRole('menuitem', { name: 'common.delete' })).not.toHaveAttribute('data-disabled')

    const alert = screen.getByText('apiKeys.decryptionError').closest('[role="alert"]') as HTMLElement
    expect(alert.className).toContain('bg-warn-tint')
    expect(alert.className).toContain('text-warn')
  })

  it('a successful connection test uses the success hue (not fern); failure stays destructive', () => {
    testResults = { 'credential:1': { success: true } }
    const { container, unmount } = renderItem()
    expect(container.querySelector('.lucide-check')?.getAttribute('class')).toContain('text-success')
    expect(container.innerHTML).not.toMatch(/text-fern/)
    unmount()

    testResults = { 'credential:1': { success: false } }
    const failed = renderItem()
    expect(failed.container.querySelector('.lucide-x')?.getAttribute('class')).toContain('text-destructive')
  })

  it('labels default slots through i18n with the same model → slot mapping', () => {
    const models = [
      model('model:chat', 'language'),
      model('model:transform', 'language'),
      model('model:tools', 'language'),
      model('model:large', 'language'),
      model('model:embed', 'embedding'),
      model('model:tts', 'text_to_speech'),
      model('model:stt', 'speech_to_text'),
      model('model:plain', 'language'),
    ]
    const defaults = {
      default_chat_model: 'model:chat',
      default_transformation_model: 'model:transform',
      default_tools_model: 'model:tools',
      large_context_model: 'model:large',
      default_embedding_model: 'model:embed',
      default_text_to_speech_model: 'model:tts',
      default_speech_to_text_model: 'model:stt',
    } as ModelDefaults
    renderItem({ modalities: ['language', 'embedding', 'text_to_speech', 'speech_to_text'] }, models, defaults)

    const slotOf = (name: string) => screen.getByText(name).closest('[data-slot="badge"]')?.textContent
    expect(slotOf('chat')).toContain('(models.slot.chat)')
    expect(slotOf('transform')).toContain('(models.slot.transform)')
    expect(slotOf('tools')).toContain('(models.slot.tools)')
    expect(slotOf('large')).toContain('(models.slot.largeContext)')
    expect(slotOf('embed')).toContain('(models.slot.embedding)')
    expect(slotOf('tts')).toContain('(models.slot.tts)')
    expect(slotOf('stt')).toContain('(models.slot.stt)')
    expect(slotOf('plain')).not.toContain('models.slot')

    // Modality group labels are localized too
    expect(screen.getAllByText('models.type.language').length).toBeGreaterThan(0)
  })

  it('the action menu is non-modal: opening it never locks body pointer events', () => {
    renderItem()
    openMenu()
    expect(document.body.style.pointerEvents).not.toBe('none')
  })
})
