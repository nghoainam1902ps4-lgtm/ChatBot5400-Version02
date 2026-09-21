/* eslint-disable @typescript-eslint/no-explicit-any */
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { CommandPalette } from './CommandPalette'
import { useAuth } from '@/lib/hooks/use-auth'

// use-translation is mocked globally (returns the key). Mock the remaining
// data/store hooks the palette pulls in so it renders in isolation.
vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => ({ data: [], isLoading: false }),
}))
vi.mock('@/lib/stores/theme-store', () => ({
  useTheme: () => ({ setTheme: vi.fn() }),
}))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

// Open the palette (it mounts closed and toggles on ⌘K / Ctrl+K).
const openPalette = () => {
  act(() => {
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
  })
}

describe('CommandPalette RBAC', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('hides admin-only navigation for regular users', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false } as any)
    render(<CommandPalette />)
    openPalette()

    // Public destinations remain
    expect(screen.getByText('navigation.sources')).toBeDefined()
    expect(screen.getByText('navigation.notebooks')).toBeDefined()

    // Admin-only destinations are gone
    expect(screen.queryByText('navigation.models')).toBeNull()
    expect(screen.queryByText('navigation.transformations')).toBeNull()
    expect(screen.queryByText('navigation.settings')).toBeNull()
    expect(screen.queryByText('navigation.advanced')).toBeNull()
  })

  it('shows admin-only navigation for admins', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: true } as any)
    render(<CommandPalette />)
    openPalette()

    expect(screen.getByText('navigation.models')).toBeDefined()
    expect(screen.getByText('navigation.settings')).toBeDefined()
    expect(screen.getByText('navigation.advanced')).toBeDefined()
  })
})
