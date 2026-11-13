'use client'

/**
 * Settings → Content Processing → OCR Engine Manager.
 *
 * Every badge, progress bar and button reflects the backend's real state
 * (GET /api/ocr/engines). Nothing is simulated: progress comes from the worker's
 * download manifest, and actions call the admin-only OCR API. Runtime installs
 * that need OS privileges are shown as instructions, never executed from here.
 */

import { useEffect, useState } from 'react'
import { CloudDownload, Cpu, Download, FlaskConical, Loader2, PlayCircle, RotateCcw, ShieldCheck, Terminal, Trash2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  useActivateOcrEngine,
  useInstallOcrEngine,
  useOcrEngines,
  useOcrJob,
  useOcrReadinessCheck,
  usePrepareOcrEngine,
  useRemoveOcrModel,
  useTestOcrEngine,
  useUpdateOcrConfig,
} from '@/lib/hooks/use-ocr'
import type { OcrEngineId, OcrEngineStatus, OcrGeneralInfo, OcrTestResult } from '@/lib/types/api'

// Static key maps (the locale test requires literal keys in source).
const STATE_KEYS: Record<string, string> = {
  not_installed: 'ocr.state.notInstalled',
  pending: 'ocr.state.pending',
  downloading: 'ocr.state.downloading',
  installing: 'ocr.state.installing',
  requires_restart: 'ocr.state.requiresRestart',
  ready: 'ocr.state.ready',
  failed: 'ocr.state.failed',
  incompatible: 'ocr.state.incompatible',
}
const RUNTIME_KEYS: Record<string, string> = {
  ready: 'ocr.runtimeStatus.ready',
  missing: 'ocr.runtimeStatus.missing',
  incompatible: 'ocr.runtimeStatus.incompatible',
  requires_restart: 'ocr.runtimeStatus.requiresRestart',
}
const MODEL_KEYS: Record<string, string> = {
  builtin: 'ocr.modelStatus.builtin',
  not_installed: 'ocr.modelStatus.notInstalled',
  partial: 'ocr.modelStatus.partial',
  corrupted: 'ocr.modelStatus.corrupted',
  installed: 'ocr.modelStatus.installed',
}
const DESC_KEYS: Record<OcrEngineId, string> = {
  rapidocr: 'ocr.engineDesc.rapidocr',
  tesseract_fast: 'ocr.engineDesc.tesseractFast',
  tesseract_best: 'ocr.engineDesc.tesseractBest',
  easyocr: 'ocr.engineDesc.easyocr',
}
const BUSY = new Set(['pending', 'downloading', 'installing'])
const READINESS_KEYS: Record<string, string> = {
  runtime_missing: 'ocr.readiness.state.runtimeMissing',
  model_missing: 'ocr.readiness.state.modelMissing',
  model_incomplete: 'ocr.readiness.state.modelIncomplete',
  incompatible: 'ocr.readiness.state.incompatible',
  pipeline_not_verified: 'ocr.readiness.state.pipelineNotVerified',
  offline_ready: 'ocr.readiness.state.offlineReady',
  not_offline_ready: 'ocr.readiness.state.notOfflineReady',
}
const CHECK_MODE_KEYS: Record<string, string> = {
  online: 'ocr.readiness.mode.online',
  local_only: 'ocr.readiness.mode.localOnly',
  offline: 'ocr.readiness.mode.offline',
}

function YesNo({ ok }: { ok: boolean }) {
  const { t } = useTranslation()
  return <span className={ok ? 'text-primary' : 'text-muted-foreground'}>{ok ? t('ocr.readiness.yes') : t('ocr.readiness.no')}</span>
}

/**
 * Offline-readiness panel for the ACTIVE engine. Values come only from real
 * pipeline runs recorded by the backend (never inferred from files on disk).
 */
function ReadinessPanel({ engine, general }: { engine?: OcrEngineStatus; general: OcrGeneralInfo }) {
  const { t } = useTranslation()
  const prepare = usePrepareOcrEngine()
  const check = useOcrReadinessCheck()
  if (!engine) return null
  const r = engine.readiness
  const last = r?.last_check
  const pending = !!engine.readiness_job
  const verifiedLayout = last?.pipeline_ok ? last.layout_model : null
  const verifiedTable = last?.pipeline_ok ? `${last.table_model ?? ''} (${last.table_mode ?? ''})` : null
  return (
    <section aria-labelledby="ocr-readiness" className="space-y-2 rounded-lg border p-4" data-slot="ocr-readiness">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="ocr-readiness" className="text-sm font-semibold">{t('ocr.readiness.title')}</h3>
        {r && (
          <Badge variant={r.state === 'offline_ready' ? 'default' : r.state === 'not_offline_ready' ? 'destructive' : 'secondary'}>
            {t(READINESS_KEYS[r.state] ?? 'ocr.readiness.state.pipelineNotVerified')}
          </Badge>
        )}
      </div>
      <p className="text-sm text-muted-foreground">{t('ocr.readiness.desc')}</p>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.readiness.doclingRuntime')}:</dt><dd><YesNo ok={general.docling_available} /></dd></div>
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.readiness.activeEngine')}:</dt><dd>{engine.display_name}</dd></div>
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.layoutModel')}:</dt><dd>{verifiedLayout ?? `${general.layout_model ?? '—'} · ${t('ocr.readiness.notVerified')}`}</dd></div>
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.tableModel')}:</dt><dd>{verifiedTable ?? `${general.table_model ?? '—'} · ${t('ocr.readiness.notVerified')}`}</dd></div>
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.readiness.ocrModel')}:</dt><dd>{engine.model_name} · {engine.model.status}</dd></div>
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.readiness.fullPipeline')}:</dt><dd><YesNo ok={!!r?.pipeline_ok} /></dd></div>
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.readiness.localOnly')}:</dt><dd><YesNo ok={!!r?.local_only_verified} /></dd></div>
        <div className="flex gap-2"><dt className="text-muted-foreground">{t('ocr.readiness.offlineVerified')}:</dt><dd><YesNo ok={!!r?.offline_verified} /></dd></div>
        <div className="flex gap-2 sm:col-span-2">
          <dt className="text-muted-foreground">{t('ocr.readiness.lastCheck')}:</dt>
          <dd>
            {last?.checked_at
              ? `${new Date(last.checked_at * 1000).toLocaleString()} · ${t(CHECK_MODE_KEYS[last.mode] ?? 'ocr.readiness.mode.online')}`
              : '—'}
            {r?.stale ? ` · ${t('ocr.readiness.stale')}` : ''}
          </dd>
        </div>
      </dl>
      {last?.error && !last.pipeline_ok && (
        <Alert variant="destructive"><AlertDescription className="break-words">{last.error}</AlertDescription></Alert>
      )}
      <p className="text-xs text-muted-foreground">{t('ocr.readiness.hint')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={() => prepare.mutate(engine.id)} disabled={pending || prepare.isPending}>
          <CloudDownload className="h-4 w-4" aria-hidden />
          {t('ocr.readiness.prepare')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => check.mutate(engine.id)} disabled={pending || check.isPending}>
          <ShieldCheck className="h-4 w-4" aria-hidden />
          {t('ocr.readiness.check')}
        </Button>
        {pending && (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            {engine.readiness_job === 'prepare' ? t('ocr.readiness.preparing') : t('ocr.readiness.checking')}
          </span>
        )}
      </div>
    </section>
  )
}

function formatBytes(n?: number | null): string {
  if (!n) return '0 MB'
  return `${(n / (1024 * 1024)).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`
}

function stateVariant(state: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (state === 'ready') return 'default'
  if (state === 'failed' || state === 'incompatible') return 'destructive'
  if (BUSY.has(state) || state === 'requires_restart') return 'outline'
  return 'secondary'
}

function RuntimeGuide({ engine }: { engine: OcrEngineStatus }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const rt = engine.runtime
  if (rt.status === 'ready') return null
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="h-8 px-2">
          <Terminal className="h-4 w-4" aria-hidden />
          {t('ocr.runtimeGuide')}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-2 rounded-md border bg-muted/40 p-3 text-sm">
        <p className="text-muted-foreground">{t('ocr.runtimeGuideDesc')}</p>
        {rt.detail && <p className="text-muted-foreground">{rt.detail}</p>}
        {rt.install_env_var && (
          <div>
            <p className="font-medium">{t('ocr.runtimeGuideEnv')}</p>
            <code className="block break-all rounded bg-background px-2 py-1 text-xs">{`${rt.install_env_var}=true`}</code>
          </div>
        )}
        {rt.install_cli && (
          <div>
            <p className="font-medium">{t('ocr.runtimeGuideCli')}</p>
            <code className="block break-all rounded bg-background px-2 py-1 text-xs">
              {`docker compose exec open_notebook uv run --no-sync ${rt.install_cli}`}
            </code>
          </div>
        )}
        <p className="text-muted-foreground">{t('ocr.runtimeGuideRestart')}</p>
      </CollapsibleContent>
    </Collapsible>
  )
}

function TestResultView({ result }: { result: OcrTestResult }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2 text-sm">
      <p className={result.success ? 'font-medium text-primary' : 'font-medium text-destructive'}>
        {result.success ? t('ocr.testSuccess') : t('ocr.testFailed')}
      </p>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
        <dt className="text-muted-foreground">{t('ocr.testEngine')}</dt>
        <dd>{result.display_name ?? result.engine}</dd>
        <dt className="text-muted-foreground">{t('ocr.testModel')}</dt>
        <dd>{result.model}</dd>
        <dt className="text-muted-foreground">{t('ocr.testLanguages')}</dt>
        <dd>{(result.languages ?? []).join(', ')}</dd>
        <dt className="text-muted-foreground">{t('ocr.testDevice')}</dt>
        <dd>{result.device}</dd>
        <dt className="text-muted-foreground">{t('ocr.testDoclingModels')}</dt>
        <dd>{(result.ocr_models ?? []).join(', ') || '—'}</dd>
        <dt className="text-muted-foreground">{t('ocr.testElapsed')}</dt>
        <dd>{result.elapsed_seconds ?? '—'} s</dd>
        {typeof result.cer === 'number' && (
          <>
            <dt className="text-muted-foreground">{t('ocr.testCer')}</dt>
            <dd>{(result.cer * 100).toFixed(1)}%</dd>
          </>
        )}
      </dl>
      {result.error && <p className="break-words text-destructive">{result.error}</p>}
      {result.text && (
        <div>
          <p className="font-medium">{t('ocr.testText')}</p>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded border bg-muted/40 p-2 text-xs">{result.text}</pre>
        </div>
      )}
      <p className="text-xs text-muted-foreground">{t('ocr.sampleNote')}</p>
    </div>
  )
}

function TestDialog({
  jobId,
  engineName,
  onClose,
}: {
  jobId: string | null
  engineName: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { data } = useOcrJob(jobId)
  const finished = data?.status === 'completed' || data?.status === 'failed'
  const result = data?.result?.result
  return (
    <Dialog open={!!jobId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="md">
        <DialogHeader icon={<FlaskConical />}>
          <DialogTitle>{t('ocr.testResult')}</DialogTitle>
          <DialogDescription>{engineName}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          {!finished && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              {t('ocr.testRunning')}
            </p>
          )}
          {finished && result && <TestResultView result={result} />}
          {finished && !result && (
            <p className="text-sm text-destructive">{data?.error_message || data?.result?.error_message || t('ocr.testFailed')}</p>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EngineRow({
  engine,
  onTest,
  onRemove,
}: {
  engine: OcrEngineStatus
  onTest: (engine: OcrEngineStatus) => void
  onRemove: (engine: OcrEngineStatus) => void
}) {
  const { t } = useTranslation()
  const install = useInstallOcrEngine()
  const activate = useActivateOcrEngine()
  const busy = BUSY.has(engine.state)
  const progress = engine.job?.progress
  const pct =
    progress?.bytes_total ? Math.min(100, Math.round(((progress.bytes_done ?? 0) / progress.bytes_total) * 100)) : 0
  // Retry is also offered when files verify but the install failed (e.g. smoke
  // check); never when the runtime is incompatible (the API would refuse).
  const canInstall =
    !engine.builtin &&
    !busy &&
    engine.runtime.status !== 'incompatible' &&
    (engine.model.status !== 'installed' || engine.state === 'failed')
  const canTest = engine.runtime.status === 'ready' && (engine.builtin || engine.ready)
  const canUse = !engine.active && (engine.builtin ? engine.runtime.status === 'ready' : engine.ready)
  const canRemove = !engine.builtin && !engine.active && !busy && engine.model.status !== 'not_installed'

  return (
    <li className="space-y-3 rounded-lg border p-4" data-engine={engine.id}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="font-medium">{engine.display_name}</h4>
            {engine.active && <Badge>{t('ocr.inUse')}</Badge>}
            <Badge variant={stateVariant(engine.state)}>{t(STATE_KEYS[engine.state] ?? 'ocr.state.notInstalled')}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">{t(DESC_KEYS[engine.id])}</p>
        </div>
      </div>

      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        <div className="flex gap-2">
          <dt className="text-muted-foreground">{t('ocr.languages')}:</dt>
          <dd>{engine.languages.join(', ')}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-muted-foreground">{t('ocr.version')}:</dt>
          <dd className="break-all">{engine.model_name} · {engine.model_version}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-muted-foreground">{t('ocr.size')}:</dt>
          <dd>
            {engine.builtin
              ? t('ocr.builtinModel')
              : `${formatBytes(engine.installed_size_bytes)} / ${formatBytes(engine.size_bytes)}`}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-muted-foreground">{t('ocr.runtime')}:</dt>
          <dd>
            {t(RUNTIME_KEYS[engine.runtime.status] ?? 'ocr.runtimeStatus.missing')}
            {engine.runtime.version ? ` (${engine.runtime.version})` : ''}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-muted-foreground">{t('ocr.model')}:</dt>
          <dd>{t(MODEL_KEYS[engine.model.status] ?? 'ocr.modelStatus.notInstalled')}</dd>
        </div>
      </dl>

      {busy && (
        <div className="space-y-1" aria-live="polite">
          <Progress value={pct} aria-label={t('ocr.progress')} />
          <p className="text-xs text-muted-foreground">
            {t('ocr.progress')}: {formatBytes(progress?.bytes_done)} / {formatBytes(progress?.bytes_total)}
          </p>
        </div>
      )}

      {engine.error && !busy && (
        <Alert variant="destructive">
          <AlertDescription className="break-words">{engine.error}</AlertDescription>
        </Alert>
      )}

      {engine.readiness && (
        <p className="text-xs text-muted-foreground" data-slot="engine-readiness">
          {t('ocr.readiness.title')}: {t(READINESS_KEYS[engine.readiness.state] ?? 'ocr.readiness.state.pipelineNotVerified')}
        </p>
      )}

      {engine.last_test && (
        <p className="text-xs text-muted-foreground">
          {t('ocr.lastTest')}: {engine.last_test.success ? t('ocr.testSuccess') : t('ocr.testFailed')}
          {typeof engine.last_test.cer === 'number' ? ` · CER ${(engine.last_test.cer * 100).toFixed(1)}%` : ''}
          {engine.last_test.elapsed_seconds ? ` · ${engine.last_test.elapsed_seconds}s` : ''}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {canInstall && (
          <Button
            type="button"
            size="sm"
            onClick={() => install.mutate(engine.id)}
            disabled={install.isPending}
          >
            {engine.state === 'failed' ? <RotateCcw className="h-4 w-4" aria-hidden /> : <Download className="h-4 w-4" aria-hidden />}
            {engine.state === 'failed' ? t('ocr.retry') : t('ocr.install')}
          </Button>
        )}
        {canUse && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => activate.mutate(engine.id)}
            disabled={activate.isPending}
          >
            <PlayCircle className="h-4 w-4" aria-hidden />
            {t('ocr.use')}
          </Button>
        )}
        {canTest && (
          <Button type="button" size="sm" variant="outline" onClick={() => onTest(engine)}>
            <FlaskConical className="h-4 w-4" aria-hidden />
            {t('ocr.test')}
          </Button>
        )}
        {canRemove && (
          <Button type="button" size="sm" variant="ghost" onClick={() => onRemove(engine)}>
            <Trash2 className="h-4 w-4" aria-hidden />
            {t('ocr.removeModel')}
          </Button>
        )}
        {busy && (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            {t(STATE_KEYS[engine.state])}
          </span>
        )}
      </div>
      <RuntimeGuide engine={engine} />
    </li>
  )
}

export function OcrEngineManager() {
  const { t } = useTranslation()
  const { data, isLoading, error, refetch } = useOcrEngines()
  const test = useTestOcrEngine()
  const remove = useRemoveOcrModel()
  const updateConfig = useUpdateOcrConfig()
  const [testJob, setTestJob] = useState<{ id: string; name: string } | null>(null)
  const [removing, setRemoving] = useState<OcrEngineStatus | null>(null)
  const [enabled, setEnabled] = useState(true)
  const [threads, setThreads] = useState('')
  const [fullPage, setFullPage] = useState(false)

  // Sync the form from the server config only when that config changes —
  // not on every progress poll — so in-progress edits are not overwritten.
  const serverEnabled = data?.config.docling_ocr
  const serverThreads = data?.config.docling_ocr_num_threads
  const serverFullPage = data?.config.docling_ocr_force_full_page
  useEffect(() => {
    if (serverEnabled === undefined) return
    setEnabled(serverEnabled)
    setThreads(serverThreads ? String(serverThreads) : '')
    setFullPage(!!serverFullPage)
  }, [serverEnabled, serverThreads, serverFullPage])

  if (isLoading) {
    return <LoadingSkeleton variant="card" items={1} lines={4} aria-label={t('common.loading')} />
  }
  if (error || !data) {
    return (
      <ErrorState
        title={t('ocr.loadFailed')}
        description={t('settings.loadFailedDesc')}
        onRetry={() => void refetch()}
        className="rounded-lg border"
      />
    )
  }

  const { general, config, engines } = data
  const threadsValue = threads.trim() === '' ? 0 : Number(threads)
  const threadsValid = threads.trim() === '' || (Number.isInteger(threadsValue) && threadsValue >= 1 && threadsValue <= 64)
  const configDirty =
    enabled !== config.docling_ocr ||
    fullPage !== config.docling_ocr_force_full_page ||
    (threadsValue || null) !== (config.docling_ocr_num_threads ?? null)

  const startTest = async (engine: OcrEngineStatus) => {
    try {
      const job = await test.mutateAsync(engine.id)
      setTestJob({ id: job.job_id, name: engine.display_name })
    } catch {
      // toast already shown by the hook
    }
  }

  return (
    <Card id="ocr-engine-manager">
      <CardHeader>
        <CardTitle>{t('ocr.title')}</CardTitle>
        <CardDescription>{t('ocr.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section aria-labelledby="ocr-general" className="space-y-2">
          <h3 id="ocr-general" className="text-sm font-semibold">{t('ocr.generalInfo')}</h3>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
            <div className="flex gap-2">
              <dt className="text-muted-foreground">{t('ocr.documentEngine')}:</dt>
              <dd>{general.document_engine}{general.docling_version ? ` ${general.docling_version}` : ''}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground">{t('ocr.layoutModel')}:</dt>
              <dd>{general.layout_model ?? '—'}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground">{t('ocr.tableModel')}:</dt>
              <dd>{general.table_model ?? '—'}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground">{t('ocr.ocrDevice')}:</dt>
              <dd className="flex items-center gap-1"><Cpu className="h-3.5 w-3.5" aria-hidden />CPU</dd>
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <dt className="text-muted-foreground">{t('ocr.modelsDir')}:</dt>
              <dd className="break-all">{general.models_dir}{general.offline_mode ? ` · ${t('ocr.offlineMode')}` : ''}</dd>
            </div>
          </dl>
          <p className="text-xs text-muted-foreground">{t('ocr.readOnlyInfo')}</p>
          {!general.docling_available && (
            <Alert><AlertDescription>{t('ocr.doclingUnavailable')}</AlertDescription></Alert>
          )}
          {(general.dependency_problems?.length ?? 0) > 0 && (
            <Alert variant={general.dependency_override ? 'default' : 'destructive'}>
              <AlertDescription className="break-words">
                {t('ocr.dependencyProblems')} {general.dependency_problems?.join('; ')}
              </AlertDescription>
            </Alert>
          )}
          {general.docling_available && general.docling_api_compatible === false && (
            <Alert variant="destructive">
              <AlertDescription>
                {t('ocr.doclingIncompatible')} {general.docling_missing_api.join(', ')}
              </AlertDescription>
            </Alert>
          )}
        </section>

        <ReadinessPanel engine={engines.find((e) => e.active)} general={general} />

        <section aria-labelledby="ocr-engines" className="space-y-2">
          <h3 id="ocr-engines" className="text-sm font-semibold">{t('ocr.engines')}</h3>
          <p className="text-sm text-muted-foreground">{t('ocr.enginesDesc')}</p>
          <ul className="space-y-3">
            {engines.map((engine) => (
              <EngineRow key={engine.id} engine={engine} onTest={startTest} onRemove={setRemoving} />
            ))}
          </ul>
        </section>

        <section aria-labelledby="ocr-config" className="space-y-4">
          <div>
            <h3 id="ocr-config" className="text-sm font-semibold">{t('ocr.config')}</h3>
            <p className="text-sm text-muted-foreground">{t('ocr.configDesc')}</p>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="ocr_enabled" checked={enabled} onCheckedChange={(v) => setEnabled(v === true)} />
            <Label htmlFor="ocr_enabled">{t('ocr.enableOcr')}</Label>
          </div>
          <div className="space-y-1">
            <Label>{t('ocr.activeEngine')}</Label>
            <p className="text-sm">{engines.find((e) => e.active)?.display_name ?? config.docling_ocr_engine}</p>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ocr_threads">{t('ocr.threads')}</Label>
            <Input
              id="ocr_threads"
              inputMode="numeric"
              className="w-40"
              value={threads}
              placeholder={t('ocr.threadsPlaceholder')}
              onChange={(e) => setThreads(e.target.value)}
              aria-invalid={!threadsValid}
            />
            <p className="text-sm text-muted-foreground">{t('ocr.threadsHelp')}</p>
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Checkbox id="ocr_full_page" checked={fullPage} onCheckedChange={(v) => setFullPage(v === true)} />
              <Label htmlFor="ocr_full_page">{t('ocr.forceFullPage')}</Label>
            </div>
            <p className="text-sm text-muted-foreground">{t('ocr.forceFullPageHelp')}</p>
          </div>
          <Button
            type="button"
            disabled={!configDirty || !threadsValid || updateConfig.isPending}
            onClick={() =>
              updateConfig.mutate({
                docling_ocr: enabled,
                docling_ocr_force_full_page: fullPage,
                docling_ocr_num_threads: threadsValue,
              })
            }
          >
            {updateConfig.isPending ? t('common.saving') : t('ocr.saveConfig')}
          </Button>
        </section>
      </CardContent>

      <TestDialog jobId={testJob?.id ?? null} engineName={testJob?.name ?? ''} onClose={() => setTestJob(null)} />

      <Dialog open={!!removing} onOpenChange={(open) => !open && setRemoving(null)}>
        <DialogContent size="sm" showCloseButton={false}>
          <DialogHeader icon={<Trash2 />} iconTone="danger">
            <DialogTitle>{t('ocr.removeConfirmTitle')}</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <DialogDescription>{t('ocr.removeConfirm', { name: removing?.display_name ?? '' })}</DialogDescription>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoving(null)}>{t('common.cancel')}</Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                removing && remove.mutate(removing.id, { onSettled: () => setRemoving(null) })
              }
            >
              {remove.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {t('ocr.removeModel')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
