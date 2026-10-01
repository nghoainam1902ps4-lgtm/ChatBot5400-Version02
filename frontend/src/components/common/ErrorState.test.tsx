import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { readFileSync } from 'fs'
import { ErrorState } from './ErrorState'

// useTranslation is mocked globally in setup.ts (t returns the key string)

describe('ErrorState', () => {
  it('renders title and description as an inline alert', () => {
    render(<ErrorState title="Could not load" description="Network error" onRetry={vi.fn()} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not load')
    expect(alert).toHaveTextContent('Network error')
  })

  it('retry button calls the callback (default label common.retry)', () => {
    const onRetry = vi.fn()
    render(<ErrorState title="x" onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('uses a custom retry label when given and hides retry without a callback', () => {
    const { rerender } = render(<ErrorState title="x" onRetry={vi.fn()} retryLabel="Load again" />)
    expect(screen.getByRole('button', { name: 'Load again' })).toBeInTheDocument()
    rerender(<ErrorState title="x" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('does not redirect or toast', () => {
    const src = readFileSync('src/components/common/ErrorState.tsx', 'utf8')
    expect(src).not.toMatch(/useRouter|router\.|location\.|redirect\(/)
    expect(src).not.toMatch(/from 'sonner'|useToast|toast\(/)
  })
})
