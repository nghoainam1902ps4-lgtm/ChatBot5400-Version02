/**
 * Display of a Source whose text went through Legal Document normalization
 * (docs/ocr D-34; Phase 12D3 findings F-07, F-16, F-17).
 *
 * The stored text keeps every clause marker exactly as printed ("9. …",
 * "10) …", "- …"): chunks, embeddings, copy and display all see the same
 * characters. Markdown would turn such lines into lists and a browser would
 * renumber them (5. 7. 13. is drawn 5, 6, 7), so the marker of each line is
 * escaped HERE, at render time only. Nothing is stored escaped.
 *
 * Reference implementation and shared test vectors:
 * scripts/ocr/phase12_metrics.py::legal_display_markdown,
 * tests/fixtures/legal/display_escape_cases.json.
 */

export interface SourceExtractionRecord {
  mode?: string
  status?: 'applied' | 'failed' | 'skipped' | string
  version?: string
  error?: string
  reason?: string
  counts?: Record<string, number>
  warnings?: Array<{ code: string; pages?: number[]; count?: number; reason?: string }>
  operations?: Array<{ op: string; pages?: number[]; sha256?: string }>
  truncated?: boolean
}

export type NormalizationState = 'standard' | 'legal_applied' | 'legal_failed' | 'legal_skipped'

/** What the Source page says about how the text was produced. */
export function normalizationState(record: SourceExtractionRecord | null | undefined): NormalizationState {
  if (!record || record.mode !== 'legal') return 'standard'
  if (record.status === 'applied') return 'legal_applied'
  if (record.status === 'failed') return 'legal_failed'
  return 'legal_skipped'
}

const ORDERED = /^(\s{0,3})(\d{1,9})([.)])(?=\s|$)/
const BULLET = /^(\s{0,3})([-+*])(?=\s|$)/
const FENCE = /^\s{0,3}(```|~~~)/

/** Escape the leading clause marker of every line (outside fenced code). Idempotent. */
export function legalDisplayMarkdown(markdown: string): string {
  let inFence = false
  return markdown
    .split('\n')
    .map((line) => {
      if (FENCE.test(line)) {
        inFence = !inFence
        return line
      }
      if (inFence) return line
      const ordered = ORDERED.exec(line)
      if (ordered) {
        return `${ordered[1]}${ordered[2]}\\${ordered[3]}${line.slice(ordered[0].length)}`
      }
      const bullet = BULLET.exec(line)
      if (bullet) {
        return `${bullet[1]}\\${line.slice(bullet[1].length)}`
      }
      return line
    })
    .join('\n')
}

export type LegalParagraphKind = 'article' | 'clause' | 'point' | 'subpoint' | 'bullet' | 'plain'

/**
 * The level of a Legal paragraph from its own first characters (never changes
 * the text): Điều n. / 1. 1.1 / a) đ) a. a/ (a) / a.1) / - bullets.
 */
export function legalParagraphKind(text: string): LegalParagraphKind {
  const lead = text.trimStart()
  if (/^Điều\s+\d+/.test(lead)) return 'article'
  if (/^[a-zđ]\.\d+[.)]/i.test(lead)) return 'subpoint'
  if (/^(?:[a-zđ][.)/]|\([a-zđ0-9]{1,3}\))(?:\s|$)/i.test(lead)) return 'point'
  if (/^\d+(?:\.\d+)*[.)](?:\s|$)/.test(lead) || /^\d+(?:\.\d+)+(?:\s|$)/.test(lead)) return 'clause'
  if (/^[-+*•–](?:\s|$)/.test(lead)) return 'bullet'
  return 'plain'
}
