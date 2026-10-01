import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { PageShell } from './PageShell'

const shell = (el: HTMLElement) => el.querySelector('[data-slot="page-shell"]') as HTMLElement

describe('PageShell', () => {
  it.each([
    ['full', 'max-w-none'],
    ['wide', 'max-w-[1200px]'],
    ['config', 'max-w-[1000px]'],
    ['reading', 'max-w-[880px]'],
  ] as const)('width "%s" → %s', (width, cls) => {
    const { container } = render(<PageShell width={width}>x</PageShell>)
    expect(shell(container).className).toContain(cls)
  })

  it('defaults to full width and never uses a 896px / max-w-4xl variant', () => {
    const { container } = render(<PageShell>x</PageShell>)
    expect(shell(container).className).toContain('max-w-none')
    expect(shell(container).className).not.toContain('max-w-4xl')
  })

  it('is centered and full width', () => {
    const { container } = render(<PageShell width="reading">x</PageShell>)
    expect(shell(container).className).toMatch(/(^|\s)mx-auto(\s|$)/)
    expect(shell(container).className).toMatch(/(^|\s)w-full(\s|$)/)
  })

  it('applies the responsive page padding 16 / 20 / 24px', () => {
    const { container } = render(<PageShell>x</PageShell>)
    const cls = shell(container).className.split(/\s+/)
    expect(cls).toEqual(expect.arrayContaining(['p-4', 'sm:p-5', 'lg:p-6']))
  })
})
