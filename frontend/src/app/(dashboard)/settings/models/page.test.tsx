import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ApiKeysPage from './page'
import { useAuth } from '@/lib/hooks/use-auth'
import { ProviderInfo } from '@/lib/api/providers'
import { Credential } from '@/lib/api/credentials'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const replace = vi.fn()
const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/settings/models',
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('@/components/settings/AiProvidersGuideModal', () => ({ AiProvidersGuideModal: () => null }))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/settings', () => ({
  MigrationBanner: () => null,
  DefaultModelSelectors: () => null,
  ProviderSection: ({ provider }: { provider: ProviderInfo }) => (
    <div data-testid="provider-section">{provider.display_name}</div>
  ),
}))

vi.mock('@/lib/hooks/use-models', () => ({
  useModels: vi.fn(() => ({ data: [], isLoading: false })),
  useModelDefaults: vi.fn(() => ({ data: null, isLoading: false })),
}))

const mockUseCredentials = vi.fn()
vi.mock('@/lib/hooks/use-credentials', () => ({
  useCredentials: () => mockUseCredentials(),
  useCredentialStatus: vi.fn(() => ({
    data: { configured: {}, source: {}, encryption_configured: true },
  })),
  useEnvStatus: vi.fn(() => ({ data: {} })),
}))

const mockUseProviders = vi.fn()
const refetchProviders = vi.fn()
vi.mock('@/lib/hooks/use-providers', () => ({
  useProviders: () => mockUseProviders(),
}))

const providers: ProviderInfo[] = [
  {
    name: 'openai',
    display_name: 'OpenAI',
    modalities: ['language'],
    docs_url: null,
    env_configured: false,
  },
  {
    name: 'anthropic',
    display_name: 'Anthropic',
    modalities: ['language'],
    docs_url: null,
    env_configured: false,
  },
]

const anthropicCredential = {
  id: 'credential:1',
  name: 'Anthropic Prod',
  provider: 'anthropic',
  modalities: ['language'],
  has_api_key: true,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
  model_count: 0,
} as Credential

describe('ApiKeysPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ isAdmin: true, isLoading: false } as ReturnType<typeof useAuth>)
    mockUseCredentials.mockReturnValue({ data: [], isLoading: false })
    mockUseProviders.mockReturnValue({
      data: providers,
      isLoading: false,
      isError: false,
      refetch: refetchProviders,
    })
  })

  it('renders one section per provider from GET /api/providers', () => {
    render(<ApiKeysPage />)
    const sections = screen.getAllByTestId('provider-section')
    expect(sections.map(s => s.textContent)).toEqual(['OpenAI', 'Anthropic'])
  })

  it('sorts configured providers first, keeping backend order otherwise', () => {
    mockUseCredentials.mockReturnValue({
      data: [anthropicCredential],
      isLoading: false,
    })
    render(<ApiKeysPage />)
    const sections = screen.getAllByTestId('provider-section')
    expect(sections.map(s => s.textContent)).toEqual(['Anthropic', 'OpenAI'])
  })

  it('shows a loading state while the provider list loads', () => {
    mockUseProviders.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })
    render(<ApiKeysPage />)
    expect(screen.queryAllByTestId('provider-section')).toHaveLength(0)
  })

  it('shows an error state when the provider list fails to load', () => {
    mockUseProviders.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    })
    render(<ApiKeysPage />)
    expect(screen.getByText('apiKeys.providersLoadFailed')).toBeInTheDocument()
    expect(
      screen.getByText('apiKeys.providersLoadFailedDescription')
    ).toBeInTheDocument()
    expect(screen.queryAllByTestId('provider-section')).toHaveLength(0)
  })

  const header = () => screen.getByRole('heading', { level: 1, name: /apiKeys\.title/ })

  it('keeps the PageHeader in the config PageShell for the normal state', () => {
    render(<ApiKeysPage />)
    expect(header()).toBeInTheDocument()
    expect(screen.getByText('apiKeys.description')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="page-shell"]')).toHaveAttribute('data-width', 'config')
  })

  it('auth loading: header + skeleton, not a blank page', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: true } as ReturnType<typeof useAuth>)
    render(<ApiKeysPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="access-denied"]')).toBeNull()
  })

  it('non-admin: header + AccessDenied in place, no redirect, no provider content', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: false } as ReturnType<typeof useAuth>)
    render(<ApiKeysPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="access-denied"]')).toBeInTheDocument()
    expect(screen.queryAllByTestId('provider-section')).toHaveLength(0)
    expect(replace).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('admin + data loading: header + skeleton (no full-page spinner)', () => {
    mockUseProviders.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: refetchProviders })
    render(<ApiKeysPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
  })

  it('provider error: ErrorState whose retry really refetches providers; header stays', () => {
    mockUseProviders.mockReturnValue({ data: undefined, isLoading: false, isError: true, refetch: refetchProviders })
    render(<ApiKeysPage />)
    expect(header()).toBeInTheDocument()
    const state = document.querySelector('[data-slot="error-state"]') as HTMLElement
    expect(within(state).getByText('apiKeys.providersLoadFailed')).toBeInTheDocument()
    fireEvent.click(within(state).getByRole('button', { name: 'common.retry' }))
    expect(refetchProviders).toHaveBeenCalledTimes(1)
  })
})
