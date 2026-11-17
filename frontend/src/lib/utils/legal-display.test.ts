import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { legalDisplayMarkdown, legalParagraphKind, normalizationState } from './legal-display'

// The same vectors as the Python reference (tests/test_ocr_legal_normalizer.py).
const cases: Array<{ input: string; display: string }> = JSON.parse(
  readFileSync(resolve(__dirname, '../../../../tests/fixtures/legal/display_escape_cases.json'), 'utf-8')
)

describe('legalDisplayMarkdown', () => {
  it('matches every shared vector and is idempotent', () => {
    expect(cases.length).toBeGreaterThanOrEqual(20)
    for (const c of cases) {
      expect(legalDisplayMarkdown(c.input), JSON.stringify(c.input)).toBe(c.display)
      expect(legalDisplayMarkdown(c.display), JSON.stringify(c.display)).toBe(c.display)
    }
  })

  it('does not touch tables, headings, lettered points or text inside a line', () => {
    const md = '## Điều 5. Phạm vi\n\n| 1. | a |\n\nđ) điểm đ\n\nnăm 2024. Hết'
    expect(legalDisplayMarkdown(md)).toBe(md)
  })
})

describe('normalizationState', () => {
  it('reads the record stored with the Source', () => {
    expect(normalizationState(null)).toBe('standard')
    expect(normalizationState(undefined)).toBe('standard')
    expect(normalizationState({})).toBe('standard')
    expect(normalizationState({ mode: 'legal', status: 'applied' })).toBe('legal_applied')
    expect(normalizationState({ mode: 'legal', status: 'failed' })).toBe('legal_failed')
    expect(normalizationState({ mode: 'legal', status: 'skipped' })).toBe('legal_skipped')
    expect(normalizationState({ mode: 'legal', status: 'something-new' })).toBe('legal_skipped')
  })
})

describe('legalParagraphKind', () => {
  it('classifies by the leading marker only', () => {
    const kinds: Array<[string, string]> = [
      ['Điều 5. Phạm vi', 'article'],
      ['1. Khoản một', 'clause'],
      ['1.1 Tiểu khoản', 'clause'],
      ['13. Khoản mười ba', 'clause'],
      ['a) điểm a', 'point'],
      ['đ) điểm đ', 'point'],
      ['a. điểm a', 'point'],
      ['a/ điểm a', 'point'],
      ['(a) điểm a', 'point'],
      ['a.1) tiết', 'subpoint'],
      ['- gạch đầu dòng', 'bullet'],
      ['Nội dung thường', 'plain'],
      ['2024 là năm kế hoạch', 'plain'],
      ['2) khoản hai', 'clause'],
      ['Căn cứ Thông tư số 39', 'plain'],
    ]
    for (const [text, kind] of kinds) expect(legalParagraphKind(text), text).toBe(kind)
  })
})
