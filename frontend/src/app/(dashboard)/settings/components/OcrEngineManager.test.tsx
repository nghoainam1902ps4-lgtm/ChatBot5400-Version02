import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { OcrCustomVersion, OcrEngineStatus, OcrEnginesResponse } from '@/lib/types/api'

// useTranslation is mocked globally in setup.ts (t returns the key string).

const install = vi.fn()
const activate = vi.fn()
const testMutate = vi.fn()
const remove = vi.fn()
const updateConfig = vi.fn()
const prepare = vi.fn()
const readinessCheck = vi.fn()
const switchVersion = vi.fn()
const rollbackVersion = vi.fn()
const verifyVersion = vi.fn()

vi.mock('@/lib/hooks/use-ocr', () => ({
  useOcrEngines: vi.fn(),
  useInstallOcrEngine: () => ({ mutate: install, isPending: false }),
  useActivateOcrEngine: () => ({ mutate: activate, isPending: false }),
  useTestOcrEngine: () => ({ mutateAsync: testMutate, isPending: false }),
  useRemoveOcrModel: () => ({ mutate: remove, isPending: false }),
  useUpdateOcrConfig: () => ({ mutate: updateConfig, isPending: false }),
  useOcrJob: () => ({ data: undefined }),
  usePrepareOcrEngine: () => ({ mutate: prepare, isPending: false }),
  useOcrReadinessCheck: () => ({ mutate: readinessCheck, isPending: false }),
  useActivateOcrCustomVersion: () => ({ mutate: switchVersion, isPending: false }),
  useRollbackOcrCustomVersion: () => ({ mutate: rollbackVersion, isPending: false }),
  useVerifyOcrCustomVersion: () => ({ mutate: verifyVersion, isPending: false }),
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

function mockEngines(engines: OcrEngineStatus[], general: Partial<OcrEnginesResponse['general']> = {}) {
  const payload = data(engines)
  ;(useOcrEngines as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    data: { ...payload, general: { ...payload.general, ...general } },
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

  it('no install button when the runtime is incompatible (API would refuse)', () => {
    mockEngines([rapid, engine({ state: 'incompatible', runtime: { kind: 'tesseract', status: 'incompatible', detail: 'too old' } })])
    render(<OcrEngineManager />)
    expect(within(row('tesseract_fast')).queryByRole('button', { name: /ocr.install|ocr.retry/ })).toBeNull()
  })

  it('failed install with verified files still offers retry and is not usable', () => {
    mockEngines([rapid, engine({ state: 'failed', error: 'Smoke check failed', model: { status: 'installed', installed_bytes: 1, files: [] } })])
    render(<OcrEngineManager />)
    const r = within(row('tesseract_fast'))
    expect(r.getByRole('button', { name: /ocr.retry/ })).toBeInTheDocument()
    expect(r.queryByRole('button', { name: /ocr.use/ })).toBeNull()
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

  it('readiness panel: never claims verification without a real pipeline check', () => {
    mockEngines([{ ...rapid, readiness: { state: 'pipeline_not_verified', ocr_ok: false, pipeline_ok: false, local_only_verified: false, offline_verified: false, stale: false, last_check: null } }])
    render(<OcrEngineManager />)
    const panel = document.querySelector('[data-slot="ocr-readiness"]') as HTMLElement
    expect(within(panel).getByText('ocr.readiness.state.pipelineNotVerified')).toBeInTheDocument()
    expect(within(panel).getAllByText(/ocr.readiness.notVerified/).length).toBe(2)
    fireEvent.click(within(panel).getByRole('button', { name: /ocr.readiness.prepare/ }))
    expect(prepare).toHaveBeenCalledWith('rapidocr')
    fireEvent.click(within(panel).getByRole('button', { name: /ocr.readiness.check/ }))
    expect(readinessCheck).toHaveBeenCalledWith('rapidocr')
  })

  it('readiness panel: shows verified Heron/TableFormer and failure details', () => {
    const ok = { mode: 'local_only' as const, success: true, pipeline_ok: true, checked_at: 1, layout_model: 'layout_heron', table_model: 'docling_tableformer', table_mode: 'accurate' }
    mockEngines([{ ...rapid, readiness: { state: 'offline_ready', ocr_ok: true, pipeline_ok: true, local_only_verified: true, offline_verified: false, stale: false, last_check: ok } }])
    render(<OcrEngineManager />)
    const panel = document.querySelector('[data-slot="ocr-readiness"]') as HTMLElement
    expect(within(panel).getByText('ocr.readiness.state.offlineReady')).toBeInTheDocument()
    expect(within(panel).getByText('layout_heron')).toBeInTheDocument()
    expect(within(panel).getByText('docling_tableformer (accurate)')).toBeInTheDocument()
  })

  it('readiness panel: pending job disables actions and failure is explained', () => {
    const bad = { mode: 'local_only' as const, success: false, pipeline_ok: false, checked_at: 1, error: 'Heron model not available locally' }
    mockEngines([{ ...rapid, readiness_job: 'check', readiness: { state: 'not_offline_ready', ocr_ok: false, pipeline_ok: false, local_only_verified: false, offline_verified: false, stale: false, last_check: bad } }])
    render(<OcrEngineManager />)
    const panel = document.querySelector('[data-slot="ocr-readiness"]') as HTMLElement
    expect(within(panel).getByText('Heron model not available locally')).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: /ocr.readiness.prepare/ })).toBeDisabled()
    expect(within(panel).getByText('ocr.readiness.checking')).toBeInTheDocument()
  })

  it('shows the quality qualification separately from the ready state', () => {
    mockEngines([
      { ...rapid, quality: 'compatibility' },
      engine({ id: 'tesseract_best', display_name: 'Tesseract Vietnamese Best', quality: 'recommended' }),
      engine({ id: 'easyocr', display_name: 'EasyOCR Vietnamese', quality: 'experimental', state: 'ready', ready: true }),
    ])
    render(<OcrEngineManager />)
    expect(within(row('tesseract_best')).getByText(/ocr\.quality\.tier\.recommended/)).toBeInTheDocument()
    // Ready AND experimental at the same time: the two states are not merged.
    expect(within(row('easyocr')).getByText(/ocr\.quality\.tier\.experimental/)).toBeInTheDocument()
    expect(within(row('easyocr')).getByText('ocr.quality.note.easyocr')).toBeInTheDocument()
    expect(screen.getByText('ocr.quality.legend')).toBeInTheDocument()
  })

  it('asks for confirmation before activating an experimental engine', () => {
    mockEngines([rapid, engine({ id: 'easyocr', display_name: 'EasyOCR Vietnamese', quality: 'experimental', state: 'ready', ready: true })])
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<OcrEngineManager />)
    fireEvent.click(within(row('easyocr')).getByRole('button', { name: /ocr\.use/ }))
    expect(confirmSpy).toHaveBeenCalledWith('ocr.quality.experimentalConfirm')
    expect(activate).not.toHaveBeenCalled()
    confirmSpy.mockReturnValue(true)
    fireEvent.click(within(row('easyocr')).getByRole('button', { name: /ocr\.use/ }))
    expect(activate).toHaveBeenCalledWith('easyocr')
    confirmSpy.mockRestore()
  })

  it('does not ask for confirmation for the other engines', () => {
    mockEngines([rapid, engine({ id: 'tesseract_best', display_name: 'Tesseract Vietnamese Best', quality: 'recommended', state: 'ready', ready: true })])
    const confirmSpy = vi.spyOn(window, 'confirm')
    render(<OcrEngineManager />)
    fireEvent.click(within(row('tesseract_best')).getByRole('button', { name: /ocr\.use/ }))
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(activate).toHaveBeenCalledWith('tesseract_best')
    confirmSpy.mockRestore()
  })

  it('reports whether page-orientation correction is really available', () => {
    mockEngines([rapid], { page_orientation: { enabled: true, available: false, reason: 'osd_data_missing' } })
    render(<OcrEngineManager />)
    expect(screen.getByTestId('ocr-page-orientation')).toHaveTextContent('ocr.pageOrientation.osd_data_missing')
  })


  // --- Phase 10: custom fine-tuned model (Tesseract Vietnamese Agri) --------------

  // Made-up values: no checksum or size of a real model belongs in the source tree.
  const SHA1 = '0123456789abcdef'.repeat(4)
  const SHA2 = 'fedcba9876543210'.repeat(4)

  function version(over: Partial<OcrCustomVersion>): OcrCustomVersion {
    return {
      version: 'v1',
      active: false,
      previous: false,
      sha256: SHA1,
      size: 12_300_000,
      imported_at: 1_794_000_000,
      notes: '',
      smoke: { ok: true, cer: 0.005 },
      verification: { status: 'verified' },
      file_ok: true,
      readiness_state: 'offline_ready',
      ...over,
    }
  }

  function agri(over: Partial<OcrEngineStatus> = {}, versions: OcrCustomVersion[] = []): OcrEngineStatus {
    const active = versions.find((v) => v.active)
    const previous = versions.find((v) => v.previous)
    return engine({
      id: 'tesseract_agri',
      display_name: 'Tesseract Vietnamese Agri',
      model_name: 'vie_agri (custom fine-tuned)',
      model_version: 'managed versions',
      quality: 'experimental',
      state: active ? 'ready' : 'not_installed',
      ready: !!active,
      model: { status: active ? 'installed' : 'not_installed', installed_bytes: 0, files: [] },
      custom: {
        family: 'agri',
        filename: 'vie_agri.traineddata',
        active_version: active?.version ?? null,
        previous_version: previous?.version ?? null,
        versions,
        with_english: false,
        english_ok: null,
        english_env: 'OCR_AGRI_WITH_ENGLISH',
        prerequisites_ok: true,
        models_dir: '/app/data/ocr/models/tesseract/custom/agri',
        manifests_dir: '/app/data/ocr/manifests/custom/agri',
        import_cli:
          'python -m open_notebook.ocr.cli custom import --file /app/data/ocr-import/vie_agri.traineddata --version <id>',
      },
      ...over,
    })
  }

  const agriRow = () => within(row('tesseract_agri'))

  it('Agri card: fifth engine, shows the active version, size, SHA-256, import date and states', () => {
    mockEngines([rapid, engine({}), agri({}, [version({ active: true })])])
    render(<OcrEngineManager />)
    expect(document.querySelectorAll('[data-engine]')).toHaveLength(3)
    const r = agriRow()
    expect(r.getByText('Tesseract Vietnamese Agri')).toBeInTheDocument()
    expect(r.getByText('ocr.custom.badge')).toBeInTheDocument()
    expect(r.getByTestId('custom-active-sha')).toHaveTextContent(SHA1)
    const activeBlock = within(row('tesseract_agri').querySelector('[data-slot="custom-active"]') as HTMLElement)
    expect(activeBlock.getByText('v1')).toBeInTheDocument()
    expect(activeBlock.getByText('12 MB')).toBeInTheDocument()
    expect(activeBlock.getByText('ocr.custom.verifyStatus.verified')).toBeInTheDocument()
    expect(activeBlock.getByText('ocr.readiness.state.offlineReady')).toBeInTheDocument()
    expect(activeBlock.getByText(new Date(1_794_000_000 * 1000).toLocaleString())).toBeInTheDocument()
    // Use / test come from the ordinary engine actions; no remove, no install.
    expect(r.getByRole('button', { name: /ocr.use/ })).toBeInTheDocument()
    expect(r.getByRole('button', { name: /ocr.test/ })).toBeInTheDocument()
    expect(r.queryByRole('button', { name: /ocr.removeModel/ })).toBeNull()
    expect(r.queryByRole('button', { name: /ocr.install/ })).toBeNull()
  })

  it('Agri card: without any version it cannot be used and explains the CLI import', () => {
    mockEngines([rapid, agri()])
    render(<OcrEngineManager />)
    const r = agriRow()
    expect(r.getByText('ocr.custom.noVersions')).toBeInTheDocument()
    expect(r.queryByRole('button', { name: /ocr.use/ })).toBeNull()
    expect(r.queryByRole('button', { name: /ocr.test/ })).toBeNull()
    const guide = row('tesseract_agri').querySelector('[data-slot="custom-cli-guide"]') as HTMLElement
    expect(guide).toHaveTextContent('custom import --file /app/data/ocr-import/vie_agri.traineddata --version <id>')
    expect(guide).toHaveTextContent('custom activate --version <id>')
    // No file input anywhere: models are never uploaded over HTTP.
    expect(document.querySelector('input[type="file"]')).toBeNull()
  })

  it('Agri card: switches to another verified version after confirmation', () => {
    mockEngines([
      rapid,
      agri({}, [version({ active: true }), version({ version: 'v2', sha256: SHA2, readiness_state: 'pipeline_not_verified' })]),
    ])
    render(<OcrEngineManager />)
    const v2 = within(row('tesseract_agri').querySelector('[data-version="v2"]') as HTMLElement)
    const v1 = within(row('tesseract_agri').querySelector('[data-version="v1"]') as HTMLElement)
    expect(v1.getByText('ocr.custom.activeBadge')).toBeInTheDocument()
    expect(v1.queryByRole('button', { name: /ocr.custom.switchTo/ })).toBeNull()
    expect(row('tesseract_agri').querySelector('[data-version="v2"]')).toHaveTextContent('ocr.readiness.state.pipelineNotVerified')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(v2.getByRole('button', { name: /ocr.custom.switchTo/ }))
    expect(switchVersion).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    fireEvent.click(v2.getByRole('button', { name: /ocr.custom.switchTo/ }))
    expect(switchVersion).toHaveBeenCalledWith({ id: 'tesseract_agri', version: 'v2' })
    confirm.mockRestore()
  })

  it('Agri card: rollback is offered only when there is a previous version', () => {
    mockEngines([rapid, agri({}, [version({ active: true })])])
    const { unmount } = render(<OcrEngineManager />)
    expect(agriRow().queryByRole('button', { name: /ocr.custom.rollback/ })).toBeNull()
    unmount()
    mockEngines([
      rapid,
      agri({}, [version({ previous: true }), version({ version: 'v2', sha256: SHA2, active: true })]),
    ])
    render(<OcrEngineManager />)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(agriRow().getByRole('button', { name: /ocr.custom.rollback/ }))
    expect(rollbackVersion).toHaveBeenCalledWith('tesseract_agri')
    confirm.mockRestore()
  })

  it('Agri card: a changed file is flagged and cannot be switched to; verify calls the backend', () => {
    mockEngines([
      rapid,
      agri({}, [
        version({ active: true }),
        version({ version: 'v2', sha256: SHA2, file_ok: false, file_detail: 'sha256 differs from the import manifest' }),
      ]),
    ])
    render(<OcrEngineManager />)
    const v2 = within(row('tesseract_agri').querySelector('[data-version="v2"]') as HTMLElement)
    expect(v2.getByText('ocr.custom.verifyStatus.changed')).toBeInTheDocument()
    expect(v2.getByText('sha256 differs from the import manifest')).toBeInTheDocument()
    expect(v2.queryByRole('button', { name: /ocr.custom.switchTo/ })).toBeNull()
    fireEvent.click(v2.getByRole('button', { name: /ocr.custom.verify/ }))
    expect(verifyVersion).toHaveBeenCalledWith({ id: 'tesseract_agri', version: 'v2' })
  })

  it('Agri card: a missing file is called missing even while the stored verdict still says verified', () => {
    mockEngines([
      rapid,
      agri({}, [
        version({ active: true }),
        version({ version: 'v2', sha256: SHA2, file_ok: false, file_present: false, file_detail: 'model file is missing' }),
      ]),
    ])
    render(<OcrEngineManager />)
    const v2 = within(row('tesseract_agri').querySelector('[data-version="v2"]') as HTMLElement)
    expect(v2.getByText('ocr.custom.verifyStatus.missing')).toBeInTheDocument()
    expect(v2.queryByText('ocr.custom.verifyStatus.changed')).toBeNull()
    expect(v2.getByText('model file is missing')).toBeInTheDocument()
  })

  it('Agri card: a failed install / check keeps a Retry, like the official engines', () => {
    // Prerequisites verify and a version is active, but the engine manifest
    // still holds the failure of an earlier install job.
    mockEngines([
      rapid,
      agri({ state: 'failed', ready: false, error: 'Download failed for tesseract/osd.traineddata' }, [
        version({ active: true }),
      ]),
    ])
    render(<OcrEngineManager />)
    const r = agriRow()
    expect(r.getByText('Download failed for tesseract/osd.traineddata')).toBeInTheDocument()
    expect(r.queryByRole('button', { name: /ocr.use/ })).toBeNull()
    fireEvent.click(r.getByRole('button', { name: /ocr.retry/ }))
    expect(install).toHaveBeenCalledWith('tesseract_agri')
  })

  it('Agri card: a ready engine offers no install or retry', () => {
    mockEngines([rapid, agri({}, [version({ active: true })])])
    render(<OcrEngineManager />)
    expect(agriRow().queryByRole('button', { name: /ocr.install|ocr.retry/ })).toBeNull()
  })

  it('Agri card: activating the engine asks for an informed confirmation; readiness check is real', () => {
    mockEngines([rapid, agri({}, [version({ active: true })])])
    render(<OcrEngineManager />)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(agriRow().getByRole('button', { name: /ocr.use/ }))
    expect(confirm).toHaveBeenCalledWith('ocr.custom.experimentalConfirm')
    expect(activate).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    fireEvent.click(agriRow().getByRole('button', { name: /ocr.use/ }))
    expect(activate).toHaveBeenCalledWith('tesseract_agri')
    confirm.mockRestore()
    const panel = within(row('tesseract_agri').querySelector('[data-slot="custom-model"]') as HTMLElement)
    fireEvent.click(panel.getByRole('button', { name: /ocr.readiness.check/ }))
    expect(readinessCheck).toHaveBeenCalledWith('tesseract_agri')
  })

  it('the four official engines get no custom panel and keep their actions', () => {
    mockEngines([
      rapid,
      engine({ state: 'ready', ready: true, model: { status: 'installed', installed_bytes: 1, files: [] } }),
      agri({}, [version({ active: true })]),
    ])
    render(<OcrEngineManager />)
    expect(row('tesseract_fast').querySelector('[data-slot="custom-model"]')).toBeNull()
    expect(row('rapidocr').querySelector('[data-slot="custom-model"]')).toBeNull()
    const fast = within(row('tesseract_fast'))
    expect(fast.getByRole('button', { name: /ocr.use/ })).toBeInTheDocument()
    expect(fast.getByRole('button', { name: /ocr.removeModel/ })).toBeInTheDocument()
    expect(fast.queryByText('ocr.custom.badge')).toBeNull()
  })
})
