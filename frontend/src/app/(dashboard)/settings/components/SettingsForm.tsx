'use client'

import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useSettings, useUpdateSettings } from '@/lib/hooks/use-settings'
import { useCapabilities } from '@/lib/hooks/use-capabilities'
import { useEffect, useState, type ReactNode } from 'react'
import { ChevronDownIcon } from 'lucide-react'
import type { SettingsResponse } from '@/lib/types/api'
import { useTranslation } from '@/lib/hooks/use-translation'

const settingsSchema = z.object({
  default_content_processing_engine_doc: z.enum(['auto', 'docling', 'simple']).optional(),
  default_content_processing_engine_url: z.enum(['auto', 'firecrawl', 'jina', 'crawl4ai', 'simple']).optional(),
  default_embedding_option: z.enum(['ask', 'always', 'never']).optional(),
  auto_delete_files: z.enum(['yes', 'no']).optional(),
  docling_ocr: z.boolean().optional(),
  docling_formulas: z.boolean().optional(),
  docling_vision: z.boolean().optional(),
})

type SettingsFormData = z.infer<typeof settingsSchema>

// Form values for the settings as currently stored on the server (also the
// target of "Undo changes").
function toFormData(settings: SettingsResponse): SettingsFormData {
  return {
    default_content_processing_engine_doc: settings.default_content_processing_engine_doc as 'auto' | 'docling' | 'simple',
    default_content_processing_engine_url: settings.default_content_processing_engine_url as 'auto' | 'firecrawl' | 'jina' | 'crawl4ai' | 'simple',
    default_embedding_option: settings.default_embedding_option as 'ask' | 'always' | 'never',
    auto_delete_files: settings.auto_delete_files as 'yes' | 'no',
    docling_ocr: settings.docling_ocr ?? true,
    docling_formulas: settings.docling_formulas ?? false,
    docling_vision: settings.docling_vision ?? false,
  }
}

/** One "Help me choose" disclosure (shared by the four setting blocks). */
function SettingsHelp({ open, onToggle, children }: { open: boolean; onToggle: () => void; children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <Collapsible open={open} onOpenChange={onToggle}>
      <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronDownIcon className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        {t('settings.helpMeChoose')}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 text-sm text-muted-foreground space-y-2">
        <p>{children}</p>
      </CollapsibleContent>
    </Collapsible>
  )
}

export function SettingsForm() {
  const { t } = useTranslation()
  const { data: settings, isLoading, error, refetch } = useSettings()
  const { data: capabilities, isError: capabilitiesError } = useCapabilities()
  const updateSettings = useUpdateSettings()
  // Opt-in heavy runtimes are installed on demand at container startup, so an
  // engine is only offered when the backend probe confirms it's actually
  // available. While the probe is still loading, default to available to avoid a
  // flash of disabled controls on a correctly-configured install; but if the
  // probe *fails*, fail closed (treat as unavailable) rather than advertising an
  // engine the backend couldn't verify.
  const doclingAvailable = capabilities?.docling_available ?? !capabilitiesError
  const crawl4aiAvailable = capabilities?.crawl4ai_available ?? !capabilitiesError
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    doc: false,
    url: false,
    embedding: false,
    files: false
  })
  const [hasResetForm, setHasResetForm] = useState(false)
  
  
  const {
    control,
    handleSubmit,
    reset,
    formState: { isDirty }
  } = useForm<SettingsFormData>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      default_content_processing_engine_doc: undefined,
      default_content_processing_engine_url: undefined,
      default_embedding_option: undefined,
      auto_delete_files: undefined,
      docling_ocr: undefined,
      docling_formulas: undefined,
      docling_vision: undefined,
    }
  })


  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  useEffect(() => {
    if (settings && settings.default_content_processing_engine_doc && !hasResetForm) {
      reset(toFormData(settings))
      setHasResetForm(true)
    }
  }, [hasResetForm, reset, settings])

  const onSubmit = async (data: SettingsFormData) => {
    try {
      await updateSettings.mutateAsync(data)
    } catch {
      // The hook already shows the error toast; keep the unsaved edits.
      return
    }
    // Saved: these values are now the server state, so the form is clean.
    reset(data)
  }

  // Undo = drop unsaved edits and go back to the settings loaded from the server
  // (not the product defaults).
  const handleUndo = () => {
    if (settings) reset(toFormData(settings))
  }

  if (isLoading) {
    return <LoadingSkeleton variant="card" items={3} lines={3} aria-label={t('common.loading')} />
  }

  if (error) {
    // Readable copy only; the raw error message is never shown.
    return (
      <ErrorState
        title={t('settings.loadFailed')}
        description={t('settings.loadFailedDesc')}
        onRetry={() => void refetch()}
        className="rounded-lg border"
      />
    )
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.contentProcessing')}</CardTitle>
          <CardDescription>
            {t('settings.contentProcessingDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <Label htmlFor="doc_engine">{t('settings.docEngine')}</Label>
            <Controller
              name="default_content_processing_engine_doc"
              control={control}
              render={({ field }) => (
                  <Select
                    key={field.value}
                    name={field.name}
                    value={field.value || ''}
                    onValueChange={field.onChange}
                    disabled={field.disabled || isLoading}
                  >
                      <SelectTrigger id="doc_engine" className="w-full">
                        <SelectValue placeholder={t('settings.docEnginePlaceholder')} />
                      </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">{t('settings.autoRecommended')}</SelectItem>
                      <SelectItem value="docling" disabled={!doclingAvailable}>{t('settings.docling')}</SelectItem>
                      <SelectItem value="simple">{t('settings.simple')}</SelectItem>
                    </SelectContent>
                  </Select>
              )}
            />
            {!doclingAvailable && (
              <p className="text-sm text-muted-foreground">{t('settings.enableDoclingHint')}</p>
            )}
            <SettingsHelp open={expandedSections.doc} onToggle={() => toggleSection('doc')}>
              {t('settings.docHelp')}
            </SettingsHelp>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Controller
                name="docling_ocr"
                control={control}
                render={({ field }) => (
                  <Checkbox
                    id="docling_ocr"
                    checked={field.value ?? true}
                    onCheckedChange={field.onChange}
                    disabled={field.disabled || isLoading || !doclingAvailable}
                  />
                )}
              />
              <Label htmlFor="docling_ocr">{t('settings.ocrEnabled')}</Label>
            </div>
            <p className="text-sm text-muted-foreground">{t('settings.ocrHelp')}</p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Controller
                name="docling_formulas"
                control={control}
                render={({ field }) => (
                  <Checkbox
                    id="docling_formulas"
                    checked={field.value ?? false}
                    onCheckedChange={field.onChange}
                    disabled={field.disabled || isLoading || !doclingAvailable}
                  />
                )}
              />
              <Label htmlFor="docling_formulas">{t('settings.formulasEnabled')}</Label>
            </div>
            <p className="text-sm text-muted-foreground">{t('settings.formulasHelp')}</p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Controller
                name="docling_vision"
                control={control}
                render={({ field }) => (
                  <Checkbox
                    id="docling_vision"
                    checked={field.value ?? false}
                    onCheckedChange={field.onChange}
                    disabled={field.disabled || isLoading || !doclingAvailable}
                  />
                )}
              />
              <Label htmlFor="docling_vision">{t('settings.visionEnabled')}</Label>
            </div>
            <p className="text-sm text-muted-foreground">{t('settings.visionHelp')}</p>
          </div>

          <div className="space-y-3">
            <Label htmlFor="url_engine">{t('settings.urlEngine')}</Label>
            <Controller
              name="default_content_processing_engine_url"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="url_engine" className="w-full">
                    <SelectValue placeholder={t('settings.urlEnginePlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">{t('settings.autoRecommended')}</SelectItem>
                    <SelectItem value="firecrawl">{t('settings.firecrawl')}</SelectItem>
                    <SelectItem value="jina">{t('settings.jina')}</SelectItem>
                    <SelectItem value="crawl4ai" disabled={!crawl4aiAvailable}>{t('settings.crawl4ai')}</SelectItem>
                    <SelectItem value="simple">{t('settings.simple')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
            {!crawl4aiAvailable && (
              <p className="text-sm text-muted-foreground">{t('settings.enableCrawl4aiHint')}</p>
            )}
            <SettingsHelp open={expandedSections.url} onToggle={() => toggleSection('url')}>
              {t('settings.urlHelp')}
            </SettingsHelp>
          </div>
        </CardContent>
      </Card>

       <Card>
        <CardHeader>
          <CardTitle>{t('settings.embeddingAndSearch')}</CardTitle>
          <CardDescription>
            {t('settings.embeddingAndSearchDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
           <div className="space-y-3">
            <Label htmlFor="embedding">{t('settings.defaultEmbeddingOption')}</Label>
            <Controller
              name="default_embedding_option"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="embedding" className="w-full">
                    <SelectValue placeholder={t('settings.embeddingOptionPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ask">{t('settings.ask')}</SelectItem>
                    <SelectItem value="always">{t('settings.always')}</SelectItem>
                    <SelectItem value="never">{t('settings.never')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
            <SettingsHelp open={expandedSections.embedding} onToggle={() => toggleSection('embedding')}>
              {t('settings.embeddingHelp')}
            </SettingsHelp>
          </div>
        </CardContent>
      </Card>

       <Card>
        <CardHeader>
          <CardTitle>{t('settings.fileManagement')}</CardTitle>
          <CardDescription>
            {t('settings.fileManagementDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
           <div className="space-y-3">
            <Label htmlFor="auto_delete">{t('settings.autoDeleteFiles')}</Label>
            <Controller
              name="auto_delete_files"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="auto_delete" className="w-full">
                    <SelectValue placeholder={t('settings.autoDeletePlaceholder')} />
                  </SelectTrigger>
                   <SelectContent>
                    <SelectItem value="yes">{t('common.yes')}</SelectItem>
                    <SelectItem value="no">{t('common.no')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
            <SettingsHelp open={expandedSections.files} onToggle={() => toggleSection('files')}>
              {t('settings.filesHelp')}
            </SettingsHelp>
          </div>
        </CardContent>
      </Card>

      {/* Unsaved changes: sticky (within the page scroll) so Save is always
          reachable; in normal flow at the end, so it never hides the last card. */}
      {isDirty && (
        <div
          data-slot="settings-save-bar"
          className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center justify-end gap-2 rounded-lg border bg-background/95 px-3 py-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/80"
        >
          <Button
            type="button"
            variant="outline"
            onClick={handleUndo}
            disabled={updateSettings.isPending}
            className="h-11 sm:h-10 lg:h-9"
          >
            {t('settings.undoChanges')}
          </Button>
          <Button
            type="submit"
            disabled={updateSettings.isPending}
            className="h-11 sm:h-10 lg:h-9"
          >
            {updateSettings.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      )}
    </form>
  )
}
