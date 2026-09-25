/* eslint-disable @typescript-eslint/no-explicit-any */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { usePathname } from 'next/navigation'
import { AppSidebar } from './AppSidebar'
import { useSidebarStore } from '@/lib/stores/sidebar-store'

// Mock Tooltip components to avoid Radix UI async issues in tests
vi.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

// AppSidebar renders <ChangePasswordDialog>, which calls useChangePassword()
// (a TanStack useMutation). Mock it so the test needs no QueryClientProvider.
vi.mock('@/lib/hooks/use-users', () => ({
  useChangePassword: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

describe('AppSidebar', () => {
  afterEach(() => {
    vi.mocked(usePathname).mockReturnValue('')
  })

  it('highlights only Models (not Settings) on the Models page', () => {
    vi.mocked(usePathname).mockReturnValue('/settings/models')

    const { container } = render(<AppSidebar />)

    const modelsButton = container.querySelector('a[href="/settings/models"] button')
    const settingsButton = container.querySelector('a[href="/settings"] button')

    expect(modelsButton?.className).toContain('font-semibold')
    expect(settingsButton?.className).toContain('font-medium')
    expect(settingsButton?.className).not.toContain('font-semibold')
  })

  it('renders correctly when expanded', () => {
    render(<AppSidebar />)

    // Brand: logo mark + "Agribank Lâm Đồng" wordmark shown when expanded.
    expect(screen.getByText('Agribank Lâm Đồng')).toBeDefined()
    expect(screen.getByAltText('Agribank Lâm Đồng')).toBeDefined()
    expect(screen.getByText('navigation.sources')).toBeDefined()
    expect(screen.getByText('navigation.notebooks')).toBeDefined()
  })

  it('uses consistent spacing for expanded footer actions', () => {
    render(<AppSidebar />)

    const themeButton = screen.getByText('common.theme').closest('button')
    const languageButton = screen.getByText('common.language').closest('button')
    const signOutButton = screen.getByRole('button', { name: 'common.signOut' })

    expect(themeButton?.className.split(/\s+/)).toContain('px-3')

    for (const button of [themeButton, languageButton, signOutButton]) {
      expect(button?.className.split(/\s+/)).toContain('gap-2')
    }

    expect(themeButton?.querySelector(':scope > span.relative.size-4')).not.toBeNull()
    expect(signOutButton.className.split(/\s+/)).not.toContain('gap-3')
  })

  it('toggles collapse state when clicking handle', () => {
    const toggleCollapse = vi.fn()
    vi.mocked(useSidebarStore).mockReturnValue({
      isCollapsed: false,
      toggleCollapse,
    } as any)

    render(<AppSidebar />)

    fireEvent.click(screen.getByTestId('sidebar-toggle'))

    expect(toggleCollapse).toHaveBeenCalled()
  })

  it('shows collapsed view when isCollapsed is true', () => {
    vi.mocked(useSidebarStore).mockReturnValue({
      isCollapsed: true,
      toggleCollapse: vi.fn(),
    } as any)

    render(<AppSidebar />)

    // In collapsed mode the wordmark text is hidden; only the logo mark shows.
    expect(screen.queryByText('Agribank Lâm Đồng')).toBeNull()
    expect(screen.getByAltText('Agribank Lâm Đồng')).toBeDefined()
  })

  it('rail exposes every icon-only action by the same t() key via aria-label', () => {
    vi.mocked(useSidebarStore).mockReturnValue({
      isCollapsed: true,
      toggleCollapse: vi.fn(),
    } as any)

    render(<AppSidebar />)

    // Nav links: labels are hidden in the rail but still reachable by name.
    expect(screen.getByRole('link', { name: 'navigation.sources' }).getAttribute('href')).toBe('/sources')
    expect(screen.getByRole('link', { name: 'navigation.notebooks' }).getAttribute('href')).toBe('/notebooks')

    // Footer actions (labels hidden in the rail).
    expect(screen.getByRole('group', { name: 'common.theme' })).toBeDefined()
    expect(screen.getByRole('group', { name: 'common.language' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'common.signOut' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'common.create' })).toBeDefined()
  })

  it('shows a visible expand toggle in the rail that flips the stored state', () => {
    const toggleCollapse = vi.fn()
    vi.mocked(useSidebarStore).mockReturnValue({
      isCollapsed: true,
      toggleCollapse,
    } as any)

    render(<AppSidebar />)

    fireEvent.click(screen.getByRole('button', { name: 'common.expandSidebar' }))

    expect(toggleCollapse).toHaveBeenCalled()
  })
})
