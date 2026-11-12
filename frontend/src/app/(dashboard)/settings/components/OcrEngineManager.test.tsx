import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { OcrEngineStatus, OcrEnginesResponse } from '@/lib/types/api'

// useTranslation is mocked globally in setup.ts (t returns the key string).

const install = vi.fn()
const activate = vi.fn()
const testMutate = vi.fn()
const remove = vi.fn()
const updateConfig = vi.fn()

vi.mock('@/lib/hooks/use-ocr', () => ({
  useOcrEngines: vi.fn(),
  useInstallOcrEngine: () => ({ mutate: install, isPending: false }),
  useActivateOcrEngine: () => ({ mutate: activate, isPending: false }),
  useTestOcrEngine: () => ({ mutateAsync: testMutate, isPending: false }),
  useRemoveOcrModel: () => ({ mutate: remove, isPending: false }),
  useUpdateOcrConfig: () => ({ mutate: updateConfig, isPending: false }),
  useOcrJob: () => ({ data: undefined }),
}))

import { useOcrEngines } from '@/lib/hooks/use-ocr'
import { OcrEngineManager } from './OcrEngineManager'

function engine(over: Partial<OcrEngineStatus>): OcrEngineStatus {
  return {
    id: 'tesseract_fast',
    display_name: 'Tesseract Vietnamese Fast',
    description: '',
    languages: ['vie', 'eng'],
    model_name: 'tessdata_fast',
    model_version: '4.1.0',
    license: 'Apache-2.0',
    source_url: '',
    builtin: false,
    download_size_bytes: 15_000_000,
    size_bytes: 15_000_000,
    installed_size_bytes: 0,
    runtime: { kind: 'tesseract', status: 'ready', version: '5.3.4' },
    model: { status: 'not_installed', installed_bytes: 0, files: [] },
    state: 'not_installed',
    ready: false,
    active: false,
    options: {},
    ...over,
  }
}

function data(engines: OcrEngineStatus[]): OcrEnginesResponse {
  return {
    general: {
      document_engine: 'Docling',
      docling_available: true,
      docling_version: '2.129.0',
      docling_api_compatible: true,
      docling_missing_api: [],
      layout_model: 'layout_heron',
      table_model: 'docling_tableformer (accurate)',
      ocr_device: 'cpu',
      models_dir: '/app/data/ocr/models',
      offline_mode: false,
    },
    config: {
      docling_ocr: true,
      docling_ocr_engine: 'rapidocr',
      docling_ocr_device: 'cpu',
      docling_ocr_num_threads: null,
      docling_ocr_force_full_page: false,
    },
    engines,
  }
}

const rapid = engine({
  id: 'rapidocr',
  display_name: 'RapidOCR – PaddleOCR',
  builtin: true,
  runtime: { kind: 'builtin', status: 'ready' },
  model: { status: 'builtin', installed_bytes: 0, files: [] },
  state: 'ready',
  ready: true,
  active: true,
})

function mockEngines(engines: OcrEngineStatus[]) {
  ;(useOcrEngines as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    data: data(engines),
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })
}

const row = (id: string) => document.querySelector(`[data-engine="${id}"]`) as HTMLElement

describe('OcrEngineManager', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows general info (Docling, Heron, TableFormer, CPU) and the 4 engines', () => {
    mockEngines([
      rapid,
      engine({}),
      engine({ id: 'tesseract_best', display_name: 'Tesseract Vietnamese Best' }),
      engine({ id: 'easyocr', display_name: 'EasyOCR Vietnamese', runtime: { kind: 'easyocr', status: 'missing', install_env_var: 'OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR', install_cli: 'python -m open_notebook.ocr.cli runtime install easyocr' } }),
    ])
    render(<OcrEngineManager />)
    expect(screen.getByText('Docling 2.129.0')).toBeInTheDocument()
    expect(screen.getByText('layout_heron')).toBeInTheDocument()
    expect(screen.getByText('docling_tableformer (accurate)')).toBeInTheDocument()
    expect(document.querySelectorAll('[data-engine]')).toHaveLength(4)
    expect(within(row('rapidocr')).getByText('ocr.inUse')).toBeInTheDocument()
  })

  it('builtin active RapidOCR cannot be installed, used again or removed; can be tested', () => {
    mockEngines([rapid])
    render(<OcrEngineManager />)
    const r = within(row('rapidocr'))
    expect(r.queryByRole('button', { name: /ocr.install/ })).toBeNull()
    expect(r.queryByRole('button', { name: /ocr.use/ })).toBeNull()
    expect(r.queryByRole('button', { name: /ocr.removeModel/ })).toBeNull()
    expect(r.getByRole('button', { name: /ocr.test/ })).toBeInTheDocument()
  })

  it('install button calls the real install mutation; not-ready engine cannot be used', () => {
    mockEngines([rapid, engine({})])
    render(<OcrEngineManager />)
    const r = within(row('tesseract_fast'))
    expect(r.queryByRole('button', { name: /ocr.use/ })).toBeNull()
    fireEvent.click(r.getByRole('button', { name: /ocr.install/ }))
    expect(install).toHaveBeenCalledWith('tesseract_fast')
  })

  it('downloading shows real progress and hides install/remove', () => {
    mockEngines([
      rapid,
      engine({ state: 'downloading', job: { state: 'downloading', progress: { bytes_done: 5 * 1024 * 1024, bytes_total: 10 * 1024 * 1024 } } }),
    ])
    render(<OcrEngineManager />)
    const r = within(row('tesseract_fast'))
    expect(r.getByRole('progressbar')).toBeInTheDocument()
    expect(r.queryByRole('button', { name: /ocr.install/ })).toBeNull()
    expect(r.queryByRole('button', { name: /ocr.removeModel/ })).toBeNull()
  })

  it('failed install offers retry and shows the error', () => {
    mockEngines([rapid, engine({ state: 'failed', error: 'Download failed after 3 attempts' })])
    render(<OcrEngineManager />)
    const r = within(row('tesseract_fast'))
    expect(r.getByText('Download failed after 3 attempts')).toBeInTheDocument()
    fireEvent.click(r.getByRole('button', { name: /ocr.retry/ }))
    expect(install).toHaveBeenCalledWith('tesseract_fast')
  })

  it('ready engine can be used, tested and its model removed', () => {
    mockEngines([
      rapid,
      engine({ state: 'ready', ready: true, model: { status: 'installed', installed_bytes: 1, files: [] } }),
    ])
    render(<OcrEngineManager />)
    const r = within(row('tesseract_fast'))
    fireEvent.click(r.getByRole('button', { name: /ocr.use/ }))
    expect(activate).toHaveBeenCalledWith('tesseract_fast')
    expect(r.getByRole('button', { name: /ocr.test/ })).toBeInTheDocument()
    expect(r.getByRole('button', { name: /ocr.removeModel/ })).toBeInTheDocument()
  })

  it('active engine model cannot be removed', () => {
    mockEngines([
      { ...rapid, active: false },
      engine({ state: 'ready', ready: true, active: true, model: { status: 'installed', installed_bytes: 1, files: [] } }),
    ])
    render(<OcrEngineManager />)
    expect(within(row('tesseract_fast')).queryByRole('button', { name: /ocr.removeModel/ })).toBeNull()
  })

  it('missing runtime shows install instructions instead of running anything', () => {
    mockEngines([
      rapid,
      engine({
        id: 'easyocr',
        runtime: { kind: 'easyocr', status: 'missing', install_env_var: 'OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR', install_cli: 'python -m open_notebook.ocr.cli runtime install easyocr' },
      }),
    ])
    render(<OcrEngineManager />)
    const r = within(row('easyocr'))
    fireEvent.click(r.getByRole('button', { name: /ocr.runtimeGuide/ }))
    expect(r.getByText('OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true')).toBeInTheDocument()
  })

  it('saves OCR config with validated thread count', () => {
    mockEngines([rapid])
    render(<OcrEngineManager />)
    const save = screen.getByRole('button', { name: 'ocr.saveConfig' })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText('ocr.threads'), { target: { value: '99' } })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText('ocr.threads'), { target: { value: '2' } })
    fireEvent.click(save)
    expect(updateConfig).toHaveBeenCalledWith({
      docling_ocr: true,
      docling_ocr_force_full_page: false,
      docling_ocr_num_threads: 2,
    })
  })
})
