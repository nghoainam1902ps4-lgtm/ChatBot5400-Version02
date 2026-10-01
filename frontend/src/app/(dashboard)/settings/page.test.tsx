import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsPage from './page'
import { useAuth } from '@/lib/hooks/use-auth'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const replace = vi.fn()
const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/settings',
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('./components/SettingsForm', () => ({ SettingsForm: () => <div data-testid="settings-form" /> }))
const refetch = vi.fn()
vi.mock('@/lib/hooks/use-settings', () => ({ useSettings: () => ({ refetch }) }))

const header = () => screen.getByRole('heading', { level: 1, name: 'settings.pageTitle' })

describe('SettingsPage (P1C)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ isAdmin: true, isLoading: false } as ReturnType<typeof useAuth>)
  })

  it('admin: config PageShell, settings.pageTitle/pageDesc header (not navigation.settings), form', () => {
    render(<SettingsPage />)
    expect(header()).toBeInTheDocument()
    expect(screen.getByText('settings.pageDesc')).toBeInTheDocument()
    expect(screen.queryByText('navigation.settings')).toBeNull()
    expect(document.querySelector('[data-slot="page-shell"]')).toHaveAttribute('data-width', 'config')
    expect(screen.getByTestId('settings-form')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="toolbar"]')).toBeNull()
  })

  it('refresh lives in the header with a visible label and refetches', () => {
    render(<SettingsPage />)
    const head = document.querySelector('[data-slot="page-header"]') as HTMLElement
    const refresh = within(head).getByRole('button', { name: 'common.refresh' })
    expect(refresh).toHaveTextContent('common.refresh')
    fireEvent.click(refresh)
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('auth loading: header + skeleton, not blank', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: true } as ReturnType<typeof useAuth>)
    render(<SettingsPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
    expect(screen.queryByTestId('settings-form')).toBeNull()
  })

  it('non-admin: header + AccessDenied, no redirect, no form', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: false } as ReturnType<typeof useAuth>)
    render(<SettingsPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="access-denied"]')).toBeInTheDocument()
    expect(screen.queryByTestId('settings-form')).toBeNull()
    expect(replace).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })
})
