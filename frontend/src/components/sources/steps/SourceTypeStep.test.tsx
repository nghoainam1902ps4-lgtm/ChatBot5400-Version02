import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useForm } from 'react-hook-form'

// useTranslation is mocked globally in setup.ts (t returns the key string).

vi.mock('@/lib/hooks/use-capabilities', () => ({
  useCapabilities: vi.fn(),
}))

import { useCapabilities } from '@/lib/hooks/use-capabilities'
import { SourceTypeStep } from './SourceTypeStep'

function mockCapabilities(data: unknown) {
  ;(useCapabilities as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data })
}

function Harness() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const form = useForm<any>({ defaultValues: { type: 'upload', embed: false, async_processing: true } })
  return (
    <SourceTypeStep
      control={form.control}
      register={form.register}
      setValue={form.setValue}
      errors={{}}
    />
  )
}

const tab = (name: string) => screen.getByRole('tab', { name: new RegExp(name) })

describe('SourceTypeStep — URL ingestion switch', () => {
  beforeEach(() => vi.clearAllMocks())

  it('disables only the URL tab and explains why when the backend reports it off', () => {
    mockCapabilities({ docling_available: true, crawl4ai_available: false, crawl4ai_remote_configured: false, url_ingestion_enabled: false })
    render(<Harness />)
    expect(tab('sources.addUrl')).toBeDisabled()
    expect(tab('sources.uploadFile')).not.toBeDisabled()
    expect(tab('sources.enterText')).not.toBeDisabled()
    expect(screen.getByTestId('url-ingestion-disabled')).toHaveTextContent('sources.urlIngestionDisabled')
  })

  it('keeps the URL tab available when the backend reports it on', () => {
    mockCapabilities({ docling_available: true, crawl4ai_available: false, crawl4ai_remote_configured: false, url_ingestion_enabled: true })
    render(<Harness />)
    expect(tab('sources.addUrl')).not.toBeDisabled()
    expect(screen.queryByTestId('url-ingestion-disabled')).toBeNull()
  })

  it('is closed by default: unknown state (loading, older backend) keeps the URL tab disabled', () => {
    mockCapabilities(undefined)
    render(<Harness />)
    expect(tab('sources.addUrl')).toBeDisabled()
    expect(tab('sources.uploadFile')).not.toBeDisabled()
    mockCapabilities({ docling_available: true, crawl4ai_available: false, crawl4ai_remote_configured: false })
    render(<Harness />)
    expect(screen.getAllByRole('tab', { name: /sources.addUrl/ }).every(el => (el as HTMLButtonElement).disabled)).toBe(true)
  })
})
