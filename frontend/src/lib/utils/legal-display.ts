/**
 * Display of a Source whose text went through Legal Document normalization
 * (docs/ocr D-34; Phase 12D3 findings F-07, F-16, F-17; Phase 12D5 R2-02).
 *
 * The stored text is the PRINTED text: clause markers ("9. …", "10) …",
 * "- …"), "*", "_", "`", "$", "[", "]", "~", "<", "&", "|" and "\\" exactly as on
 * paper, so chunks, embeddings, copy and display all see the same characters.
 * Markdown (with GFM and remark-math) would read them as lists - renumbered by
 * the browser -, emphasis, code, links, strikethrough, formulas or HTML, so each
 * such character of a text line is escaped HERE, at render time only. Table rows
 * keep their "|" separators, headings their "#" prefix; the serializer's own
 * "<!-- image -->" placeholders and fenced code are left alone. Idempotent.
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
const HEADING = /^(\s{0,3}#{1,6}\s+)(.*)$/
const THEMATIC_DASHES = /^(\s{0,3})-(?:\s*-){2,}\s*$/
const SERIALIZER_COMMENT = /^\s*<!--[^<>]*-->\s*$/
const ASCII_PUNCT = new Set('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'.split(''))
const INLINE_SPECIAL = new Set('`*_[]~$<|'.split(''))
// Entities the Legal serializer itself writes ("&lt;": a "<" that would open
// HTML; "&#124;": a "|" inside a table cell): rendered as "<" / "|".
const KEPT_ENTITIES = ['&lt;', '&#124;']

// A bare URL: GFM turns it into a link VERBATIM (escapes inside it would be
// displayed), so it is copied as it is; "_" / "&" inside it are literal anyway.
const URL_AT = /^(?:https?:\/\/|www\.)[^\s<>]*/i

function escapeInline(text: string, table = false): string {
  let out = ''
  let i = 0
  while (i < text.length) {
    if ('hHwW'.includes(text[i]) && (i === 0 || !/[\p{L}\p{N}]/u.test(text[i - 1]))) {
      const url = URL_AT.exec(text.slice(i))
      if (url && url[0].length > 0) {
        out += url[0]
        i += url[0].length
        continue
      }
    }
    const c = text[i]
    if (c === '\\') {
      if (i + 1 < text.length && ASCII_PUNCT.has(text[i + 1])) {
        out += text.slice(i, i + 2) // already an escape: idempotent
        i += 2
        continue
      }
      out += '\\\\'
    } else if (c === '&') {
      out += KEPT_ENTITIES.some((e) => text.startsWith(e, i)) ? '&' : '\\&'
    } else if (c === '|' && table) {
      out += c
    } else if (INLINE_SPECIAL.has(c)) {
      out += '\\' + c
    } else {
      out += c
    }
    i += 1
  }
  return out
}

/** Escape every Markdown-significant character of each text line (outside fenced code). Idempotent. */
export function legalDisplayMarkdown(markdown: string): string {
  let inFence = false
  return markdown
    .split('\n')
    .map((line) => {
      if (FENCE.test(line)) {
        inFence = !inFence
        return line
      }
      if (inFence || !line.trim() || SERIALIZER_COMMENT.test(line)) return line
      if (line.trimStart().startsWith('|')) return escapeInline(line, true)
      const heading = HEADING.exec(line)
      if (heading) return heading[1] + escapeInline(heading[2])
      const ordered = ORDERED.exec(line)
      if (ordered) {
        return `${ordered[1]}${ordered[2]}\\${ordered[3]}` + escapeInline(line.slice(ordered[0].length))
      }
      const bullet = BULLET.exec(line)
      if (bullet) return `${bullet[1]}\\${bullet[2]}` + escapeInline(line.slice(bullet[0].length))
      const dashes = THEMATIC_DASHES.exec(line)
      if (dashes) return `${dashes[1]}\\${line.slice(dashes[1].length)}`
      return escapeInline(line)
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
