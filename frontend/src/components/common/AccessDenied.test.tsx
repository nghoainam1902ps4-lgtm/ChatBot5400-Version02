import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { readFileSync } from 'fs'
import { AccessDenied } from './AccessDenied'

// useTranslation is mocked globally in setup.ts (t returns the key string)

describe('AccessDenied', () => {
  it('renders the default translated copy', () => {
    render(<AccessDenied />)
    expect(screen.getByRole('heading', { name: 'common.accessDenied.title' })).toBeInTheDocument()
    expect(screen.getByText('common.accessDenied.desc')).toBeInTheDocument()
  })

  it('is neutral: no destructive / warning semantics, no alert role', () => {
    const { container } = render(<AccessDenied onAction={vi.fn()} />)
    // Semantic color utilities only — the shared Button's form-validation
    // styles (aria-invalid:ring-destructive/…) are not a semantic choice.
    const semantic = [...container.querySelectorAll('*')]
      .flatMap((el) => (el.getAttribute('class') ?? '').split(/\s+/))
      .filter((c) => !c.includes('aria-invalid:'))
    expect(semantic.filter((c) => /destructive|warn|danger/.test(c))).toEqual([])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(container.querySelector('svg')?.getAttribute('class')).toContain('text-muted-foreground')
  })

  it('action is optional and uses the default backToNotebooks label', () => {
    const { rerender } = render(<AccessDenied />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    const onAction = vi.fn()
    rerender(<AccessDenied onAction={onAction} />)
    fireEvent.click(screen.getByRole('button', { name: 'common.accessDenied.backToNotebooks' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('accepts caller copy', () => {
    render(<AccessDenied title="Admins only" description="Ask your admin" onAction={vi.fn()} actionLabel="Go home" />)
    expect(screen.getByRole('heading', { name: 'Admins only' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go home' })).toBeInTheDocument()
  })

  it('never navigates or redirects by itself', () => {
    const src = readFileSync('src/components/common/AccessDenied.tsx', 'utf8')
    expect(src).not.toMatch(/useRouter|router\.|location\.|redirect\(|<Link|href=/)
  })
})
