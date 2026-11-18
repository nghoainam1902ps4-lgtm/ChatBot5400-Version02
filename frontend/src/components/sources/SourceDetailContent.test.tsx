import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SourceDetailContent } from './SourceDetailContent'
import { sourcesApi } from '@/lib/api/sources'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { SourceDetailResponse } from '@/lib/types/api'
import type { SourceExtractionRecord } from '@/lib/utils/legal-display'

// useTranslation is mocked globally in setup.ts (t returns the key string)

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: {
    get: vi.fn(),
  },
}))

vi.mock('@/lib/api/insights', () => ({
  insightsApi: {
    listForSource: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/lib/api/transformations', () => ({
  transformationsApi: {
    list: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/lib/api/embedding', () => ({
  embeddingApi: {
    embedSource: vi.fn(),
  },
}))

vi.mock('@/components/sources/SourceInsightDialog', () => ({
  SourceInsightDialog: () => null,
}))

vi.mock('@/components/sources/NotebookAssociations', () => ({
  NotebookAssociations: () => null,
}))

const mockSourcesGet = vi.mocked(sourcesApi.get)

const notFoundError = Object.assign(new Error('Request failed with status code 404'), {
  isAxiosError: true,
  response: { status: 404 },
})

const networkError = Object.assign(new Error('Network Error'), {
  isAxiosError: true,
  response: undefined,
})

function renderContent(onClose?: () => void) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <SourceDetailContent sourceId="source:missing" onClose={onClose} />
    </QueryClientProvider>
  )
}

describe('SourceDetailContent', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the shared not-found state when the source returns 404', async () => {
    mockSourcesGet.mockRejectedValue(notFoundError)

    renderContent()

    await waitFor(() => {
      expect(screen.getByTestId('content-unavailable')).toBeInTheDocument()
    })
    expect(screen.getByText('common.contentUnavailable.notFoundTitle')).toBeInTheDocument()
    expect(screen.getByText('common.contentUnavailable.notFoundDescription')).toBeInTheDocument()
  })

  it('shows the shared load-error state for non-404 failures', async () => {
    mockSourcesGet.mockRejectedValue(networkError)

    renderContent()

    await waitFor(() => {
      expect(screen.getByTestId('content-unavailable')).toBeInTheDocument()
    })
    expect(screen.getByText('common.contentUnavailable.errorTitle')).toBeInTheDocument()
    expect(
      screen.queryByText('common.contentUnavailable.notFoundTitle')
    ).not.toBeInTheDocument()
  })

  it('shows the not-found state over stale cached data when a refetch returns 404', async () => {
    // Simulates the orphan-reference path: the source was viewed (cached),
    // then deleted; reopening it serves the retained cache while the
    // background refetch 404s. React Query keeps the previous data alongside
    // the error — the definitive 404 must still win over the stale render.
    mockSourcesGet.mockRejectedValue(notFoundError)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const cachedSource: SourceDetailResponse = {
      id: 'source:stale',
      title: 'Deleted but cached',
      asset: null,
      embedded: false,
      embedded_chunks: 0,
      insights_count: 0,
      created: '2026-01-01T00:00:00Z',
      updated: '2026-01-01T00:00:00Z',
      full_text: 'stale content',
    }
    // Mark the cached entry as stale (older than useSource's 30s staleTime)
    // so mounting triggers a refetch, which rejects with the 404 above.
    queryClient.setQueryData(QUERY_KEYS.source('source:stale'), cachedSource, {
      updatedAt: Date.now() - 60_000,
    })

    render(
      <QueryClientProvider client={queryClient}>
        <SourceDetailContent sourceId="source:stale" />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('content-unavailable')).toBeInTheDocument()
    })
    expect(screen.getByText('common.contentUnavailable.notFoundTitle')).toBeInTheDocument()
    expect(screen.queryByText('Deleted but cached')).not.toBeInTheDocument()
  })

  it('invokes onClose from the not-found close button', async () => {
    mockSourcesGet.mockRejectedValue(notFoundError)
    const onClose = vi.fn()

    renderContent(onClose)

    await waitFor(() => {
      expect(screen.getByText('common.close')).toBeInTheDocument()
    })
    screen.getByText('common.close').click()
    expect(onClose).toHaveBeenCalled()
  })

  // ---- Phase 12D3: F-07 (normalization status), F-16 (hierarchy), F-17 (markers) ----
  const legalText = [
    '## Điều 3. Giải thích từ ngữ',
    '5. Khoản năm của văn bản.',
    '7. Khoản bảy của văn bản.',
    '13. Khoản mười ba của văn bản.',
    'a) điểm a của khoản;',
    'đ) điểm đ của khoản;',
    'a.1) tiết của điểm;',
    '- gạch đầu dòng trong văn bản gốc.',
    'Đoạn văn thường.',
  ].join('\n\n')

  function source(extraction: SourceExtractionRecord | undefined): SourceDetailResponse {
    return {
      id: 'source:legal',
      title: 'Quy định',
      asset: { file_path: '/x.pdf', extraction },
      embedded: false,
      embedded_chunks: 0,
      insights_count: 0,
      created: '2026-01-01T00:00:00Z',
      updated: '2026-01-01T00:00:00Z',
      full_text: legalText,
    }
  }

  async function renderSource(data: SourceDetailResponse) {
    mockSourcesGet.mockResolvedValue(data)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(
      <QueryClientProvider client={queryClient}>
        <SourceDetailContent sourceId="source:legal" />
      </QueryClientProvider>
    )
    await waitFor(() => expect(screen.getByTestId('source-normalization')).toBeInTheDocument())
    return view
  }

  it('Legal source: shows the status, keeps the original numbers and the hierarchy', async () => {
    const { container } = await renderSource(
      source({ mode: 'legal', status: 'applied', version: '1.1.0', warnings: [{ code: 'page_number_kept' }] })
    )
    const badge = screen.getByTestId('source-normalization')
    expect(badge).toHaveAttribute('data-state', 'legal_applied')
    expect(badge).toHaveTextContent('sources.normalization.legalApplied')
    expect(badge).toHaveTextContent('v1.1.0')
    expect(screen.getByTestId('source-normalization-warnings')).toBeInTheDocument()
    const prose = container.querySelector('.source-prose') as HTMLElement
    expect(prose.querySelector('ol')).toBeNull()
    expect(prose.querySelector('ul')).toBeNull()
    const paragraphs = Array.from(prose.querySelectorAll('p')).map((p) => [p.textContent, p.getAttribute('data-legal-kind')])
    expect(paragraphs).toEqual([
      ['5. Khoản năm của văn bản.', 'clause'],
      ['7. Khoản bảy của văn bản.', 'clause'],
      ['13. Khoản mười ba của văn bản.', 'clause'],
      ['a) điểm a của khoản;', 'point'],
      ['đ) điểm đ của khoản;', 'point'],
      ['a.1) tiết của điểm;', 'subpoint'],
      ['- gạch đầu dòng trong văn bản gốc.', 'bullet'],
      ['Đoạn văn thường.', 'plain'],
    ])
    expect(prose.textContent).not.toContain('\\') // no escape character is ever displayed
    const clause = prose.querySelector('p[data-legal-kind="clause"]') as HTMLElement
    const point = prose.querySelector('p[data-legal-kind="point"]') as HTMLElement
    expect(clause.style.paddingLeft).toBe('2em')
    expect(point.style.paddingLeft).toBe('3.5em')
    expect(clause.style.textIndent).toBe('0')
  })

  // ---- Phase 12D5: R2-02 / F-17 - the page shows the printed characters ----
  it('Legal source: Markdown-significant characters are displayed as printed', async () => {
    const printed = [
      'Lãi suất = 5*3% (tối đa 15*2)',
      'Mức phí (*) áp dụng theo biểu phí (*) hiện hành',
      'Mã `TK01` dùng cho tài khoản thanh toán',
      'Phí 5$ và 10$ cho mỗi giao dịch quốc tế',
      'Tỷ lệ 1:2 và công thức a_1 + b_2 = c_3',
      'Mã sản phẩm TK_VND_01 và file bao_cao_2024.xlsx',
      'Email: ho_tro@agribank.com.vn; website https://agribank.com.vn/a_b?x=1&y=2',
      'Họ tên: <Tên khách hàng> & <Số CMND>',
      'Ký hiệu ~50 triệu đồng và ~[chưa xác nhận]~',
      'Đường dẫn C:\\Bieu\\phi.xlsx trên máy trạm',
      '9. Khoản có ký hiệu 5*3% và mã TK_01',
    ]
    const data = source({ mode: 'legal', status: 'applied', version: '1.2.0' })
    data.full_text = printed.join('\n\n')
    const { container } = await renderSource(data)
    const prose = container.querySelector('.source-prose') as HTMLElement
    const shown = Array.from(prose.querySelectorAll('p')).map((p) => p.textContent)
    expect(shown).toEqual(printed)
    // nothing was turned into emphasis, code, strikethrough, a formula or a list
    for (const selector of ['em', 'strong', 'code', 'del', '.katex', 'ol', 'ul']) {
      expect(prose.querySelector(selector), selector).toBeNull()
    }
  })

  it('Standard source: rendered exactly as before, labelled Standard', async () => {
    const { container } = await renderSource(source(undefined))
    expect(screen.getByTestId('source-normalization')).toHaveAttribute('data-state', 'standard')
    const prose = container.querySelector('.source-prose') as HTMLElement
    expect(prose.querySelector('ol')).not.toBeNull() // Markdown list, as in v1.2.0
    expect(prose.querySelector('p[data-legal-kind]')).toBeNull()
  })

  it('Failed / skipped normalization is visible and rendered as a standard source', async () => {
    const failed = await renderSource(source({ mode: 'legal', status: 'failed', error: 'NormalizationLimitError' }))
    const badge = screen.getByTestId('source-normalization')
    expect(badge).toHaveAttribute('data-state', 'legal_failed')
    expect(badge).toHaveTextContent('sources.normalization.legalFailed')
    expect(failed.container.querySelector('.source-prose ol')).not.toBeNull()
    failed.unmount()
    await renderSource(source({ mode: 'legal', status: 'skipped', reason: 'not a PDF' }))
    expect(screen.getByTestId('source-normalization')).toHaveAttribute('data-state', 'legal_skipped')
  })
})
