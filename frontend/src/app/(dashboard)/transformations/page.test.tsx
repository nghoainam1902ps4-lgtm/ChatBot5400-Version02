import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TransformationsPage from './page'
import { useAuth } from '@/lib/hooks/use-auth'
import { useTransformations } from '@/lib/hooks/use-transformations'
import type { Transformation } from '@/lib/types/transformations'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const replace = vi.fn()
const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/transformations',
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/lib/hooks/use-transformations', () => ({ useTransformations: vi.fn() }))
vi.mock('./components/DefaultPromptEditor', () => ({ DefaultPromptEditor: () => <div data-testid="default-prompt" /> }))
vi.mock('./components/TransformationsList', () => ({
  TransformationsList: ({ isLoading, onPlayground, transformations }: { isLoading: boolean; onPlayground: (t: Transformation) => void; transformations?: Transformation[] }) => (
    <div data-testid="list" data-loading={String(isLoading)}>
      {transformations?.map((tr) => (
        <button key={tr.id} onClick={() => onPlayground(tr)}>play {tr.name}</button>
      ))}
    </div>
  ),
}))
vi.mock('./components/TransformationPlayground', () => ({
  TransformationPlayground: ({ selectedTransformation }: { selectedTransformation?: Transformation }) => (
    <div data-testid="playground">{selectedTransformation?.name ?? 'none'}</div>
  ),
}))

const refetch = vi.fn()
const tr = { id: 'transformation:1', name: 'summarize' } as Transformation

function setup(query: Partial<ReturnType<typeof useTransformations>>) {
  vi.mocked(useTransformations).mockReturnValue({
    data: [tr],
    isLoading: false,
    isError: false,
    refetch,
    ...query,
  } as unknown as ReturnType<typeof useTransformations>)
  return render(<TransformationsPage />)
}

const header = () => screen.getByRole('heading', { level: 1, name: 'transformations.title' })

describe('TransformationsPage (P1B)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ isAdmin: true, isLoading: false } as ReturnType<typeof useAuth>)
  })

  it('normal: PageHeader with description in a config PageShell', () => {
    setup({})
    expect(header()).toBeInTheDocument()
    expect(screen.getByText('transformations.desc')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="page-shell"]')).toHaveAttribute('data-width', 'config')
    expect(screen.getByTestId('list')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="toolbar"]')).toBeNull()
  })

  it('refresh lives in the header actions with a visible label and refetches', () => {
    setup({})
    const actions = document.querySelector('[data-slot="page-header"]') as HTMLElement
    const refresh = within(actions).getByRole('button', { name: 'common.refresh' })
    expect(refresh).toHaveTextContent('common.refresh')
    expect(refresh.querySelector('.lucide-refresh-cw')).not.toBeNull()
    fireEvent.click(refresh)
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('error: ErrorState (not the empty state) whose retry really refetches; header stays', () => {
    setup({ data: undefined, isError: true })
    expect(header()).toBeInTheDocument()
    const state = document.querySelector('[data-slot="error-state"]') as HTMLElement
    expect(within(state).getByText('transformations.loadErrorTitle')).toBeInTheDocument()
    expect(within(state).getByText('transformations.loadErrorDesc')).toBeInTheDocument()
    expect(screen.queryByTestId('list')).toBeNull()
    fireEvent.click(within(state).getByRole('button', { name: 'common.retry' }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('list loading is passed down (skeleton in the list); header stays', () => {
    setup({ data: undefined, isLoading: true })
    expect(header()).toBeInTheDocument()
    expect(screen.getByTestId('list')).toHaveAttribute('data-loading', 'true')
  })

  it('auth loading: header + skeleton, not blank', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: true } as ReturnType<typeof useAuth>)
    setup({})
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
  })

  it('non-admin: header + AccessDenied, no redirect, no tabs/data', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: false } as ReturnType<typeof useAuth>)
    setup({})
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="access-denied"]')).toBeInTheDocument()
    expect(screen.queryByTestId('list')).toBeNull()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(replace).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('opening Playground from a card switches tab and preselects that transformation', () => {
    setup({})
    fireEvent.click(screen.getByRole('button', { name: 'play summarize' }))
    expect(screen.getByTestId('playground')).toHaveTextContent('summarize')
  })
})
