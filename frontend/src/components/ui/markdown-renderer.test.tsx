import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'

import { MarkdownRenderer } from './markdown-renderer'

describe('MarkdownRenderer', () => {
  it('renders basic markdown', () => {
    const { container } = render(<MarkdownRenderer>{'# Title\n\nSome **bold** text'}</MarkdownRenderer>)
    expect(container.querySelector('h1')?.textContent).toBe('Title')
    expect(container.querySelector('strong')?.textContent).toBe('bold')
  })

  it('highlights fenced code blocks for registered languages', () => {
    const { container } = render(
      <MarkdownRenderer>{'```python\ndef hello():\n    return 42\n```'}</MarkdownRenderer>
    )
    // PrismLight emits token spans when the grammar is registered; a plain
    // fallback would leave the code block without any token markup.
    expect(container.querySelectorAll('span[class*="token"]').length).toBeGreaterThan(0)
  })

  it('falls back to plain text for unknown languages without crashing', () => {
    const { container } = render(
      <MarkdownRenderer>{'```notalanguage\nsome content\n```'}</MarkdownRenderer>
    )
    expect(container.textContent).toContain('some content')
  })

  it('renders inline code without a highlighter block', () => {
    const { container } = render(<MarkdownRenderer>{'Use `npm ci` here'}</MarkdownRenderer>)
    expect(container.querySelector('code')?.textContent).toBe('npm ci')
    expect(container.querySelectorAll('span[class*="token"]').length).toBe(0)
  })

  // Phase 12A root-cause evidence (docs/ocr/PHASE12A_ROOT_CAUSE_REPORT.md, layer I).
  it('shows a Docling image placeholder as literal text (no rehype-raw): the "<!-- image -->" users see', () => {
    const { container } = render(<MarkdownRenderer>{'Trước\n\n<!-- image -->\n\nSau'}</MarkdownRenderer>)
    expect(container.textContent).toContain('<!-- image -->')
    expect(container.querySelector('script')).toBeNull()
  })

  it('renumbers a standard ordered list: source "5. 7. 13." is drawn as 5, 6, 7', () => {
    const { container } = render(
      <MarkdownRenderer>{'5. Một\n7. Hai\n13. Ba'}</MarkdownRenderer>
    )
    const ol = container.querySelector('ol')
    expect(ol?.getAttribute('start')).toBe('5')
    expect(ol?.querySelectorAll('li')).toHaveLength(3) // browser numbers 5, 6, 7
  })

  it('Legal Document output keeps the original clause numbers as text', () => {
    const { container } = render(
      <MarkdownRenderer>{'5\\. Một\n\n7\\. Hai\n\n13\\. Ba\n\nđ) Bốn\n\n\\- Năm'}</MarkdownRenderer>
    )
    expect(container.querySelector('ol')).toBeNull()
    expect(container.querySelector('ul')).toBeNull()
    const paragraphs = Array.from(container.querySelectorAll('p')).map((p) => p.textContent)
    expect(paragraphs).toEqual(['5. Một', '7. Hai', '13. Ba', 'đ) Bốn', '- Năm'])
  })
})
