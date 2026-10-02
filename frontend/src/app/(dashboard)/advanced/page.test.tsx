import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdvancedPage from './page'
import { useAuth } from '@/lib/hooks/use-auth'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const replace = vi.fn()
const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/advanced',
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('./components/SystemInfo', () => ({ SystemInfo: () => <div data-testid="system-info" /> }))
vi.mock('./components/RebuildEmbeddings', () => ({ RebuildEmbeddings: () => <div data-testid="rebuild" /> }))

const header = () => screen.getByRole('heading', { level: 1, name: 'advanced.title' })

describe('AdvancedPage (P1C)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ isAdmin: true, isLoading: false } as ReturnType<typeof useAuth>)
  })

  it('admin: config PageShell, header with description, both admin areas', () => {
    render(<AdvancedPage />)
    expect(header()).toBeInTheDocument()
    expect(screen.getByText('advanced.desc')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="page-shell"]')).toHaveAttribute('data-width', 'config')
    expect(screen.getByTestId('system-info')).toBeInTheDocument()
    expect(screen.getByTestId('rebuild')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="toolbar"]')).toBeNull()
  })

  it('auth loading: header + skeleton', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: true } as ReturnType<typeof useAuth>)
    render(<AdvancedPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
  })

  it('non-admin: header + AccessDenied, no redirect, no admin content', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: false } as ReturnType<typeof useAuth>)
    render(<AdvancedPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="access-denied"]')).toBeInTheDocument()
    expect(screen.queryByTestId('rebuild')).toBeNull()
    expect(replace).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })
})
