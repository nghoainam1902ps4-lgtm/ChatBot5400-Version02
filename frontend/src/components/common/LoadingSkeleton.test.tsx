import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { LoadingSkeleton } from './LoadingSkeleton'

describe('LoadingSkeleton', () => {
  it('table: 48px header and the requested number of 48px rows', () => {
    const { container } = render(<LoadingSkeleton variant="table" rows={5} />)
    const header = container.querySelector('[data-slot="skeleton-header"]')!
    const rows = container.querySelectorAll('[data-slot="skeleton-row"]')
    expect(header.className).toContain('h-12')
    expect(rows).toHaveLength(5)
    rows.forEach((r) => expect(r.className.split(/\s+/)).toContain('h-12'))
  })

  it('table: column count is respected', () => {
    const { container } = render(<LoadingSkeleton variant="table" rows={2} columns={4} />)
    const firstRow = container.querySelector('[data-slot="skeleton-row"]')!
    expect(firstRow.children).toHaveLength(4)
  })

  it.each(['card', 'list'] as const)('%s: item count and placeholder lines per item', (variant) => {
    const { container } = render(<LoadingSkeleton variant={variant} items={3} lines={4} />)
    const items = container.querySelectorAll('[data-slot="skeleton-item"]')
    expect(items).toHaveLength(3)
    items.forEach((item) => expect(item.querySelectorAll('span[aria-hidden]')).toHaveLength(4))
  })

  it('announces a busy status region', () => {
    const { getByRole } = render(<LoadingSkeleton variant="list" items={1} aria-label="Loading" />)
    const region = getByRole('status', { name: 'Loading' })
    expect(region).toHaveAttribute('aria-busy', 'true')
  })
})
