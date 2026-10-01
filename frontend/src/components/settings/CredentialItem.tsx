'use client'

import { useState } from 'react'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import {
  Key,
  AlertTriangle,
  Edit,
  Trash2,
  Plug,
  Loader2,
  Check,
  X,
  Bot,
  MoreHorizontal,
} from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useDeleteModel, useTestModel } from '@/lib/hooks/use-models'
import { useCredential, useTestCredential } from '@/lib/hooks/use-credentials'
import { Credential } from '@/lib/api/credentials'
import { Model, ModelDefaults } from '@/lib/types/models'
import {
  MODEL_TYPES,
  getTypeIcon,
  getTypeColor,
  getTypeLabel,
  TYPE_COLOR_INACTIVE,
} from '@/lib/providers'
import { ModelTestResultDialog } from './ModelTestResultDialog'
import { CredentialFormDialog } from './CredentialFormDialog'
import { DeleteCredentialDialog } from './DeleteCredentialDialog'
import { DiscoverModelsDialog } from './DiscoverModelsDialog'

interface CredentialItemProps {
  credential: Credential
  models: Model[]
  defaults: ModelDefaults | null
  allCredentials: Credential[]
}

export function CredentialItem({
  credential,
  models,
  defaults,
  allCredentials,
}: CredentialItemProps) {
  const { t } = useTranslation()
  const { testCredential, isPending: isTestPending, testResults } = useTestCredential()
  const { testModel, isPending: isModelTestPending, testingModelId, testResult: modelTestResult, testedModelName, clearResult: clearModelTestResult } = useTestModel()
  const deleteModel = useDeleteModel()
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  // Full credential data needed for edit form
  const { data: fullCredential } = useCredential(editOpen ? credential.id : '')

  const linkedModels = models.filter(m => m.credential === credential.id)
  const activeTypes = new Set<string>(linkedModels.map(m => m.type))
  const testResult = testResults[credential.id]

  // Check which models are defaults (model id → slot label i18n key)
  const defaultSlots: Record<string, string> = {}
  if (defaults) {
    const slotMap: Record<string, string | null | undefined> = {
      'models.slot.chat': defaults.default_chat_model,
      'models.slot.transform': defaults.default_transformation_model,
      'models.slot.tools': defaults.default_tools_model,
      'models.slot.largeContext': defaults.large_context_model,
      'models.slot.embedding': defaults.default_embedding_model,
      'models.slot.tts': defaults.default_text_to_speech_model,
      'models.slot.stt': defaults.default_speech_to_text_model,
    }
    for (const [slot, modelId] of Object.entries(slotMap)) {
      if (modelId) defaultSlots[modelId] = slot
    }
  }

  return (
    <>
      <div className="border rounded-lg p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-medium truncate">{credential.name}</span>
            <div className="flex gap-1">
              {credential.modalities.map(mod => (
                <Badge
                  key={mod}
                  variant="secondary"
                  className={`text-[10px] gap-0.5 px-1 py-0 ${activeTypes.has(mod) ? getTypeColor(mod) : TYPE_COLOR_INACTIVE}`}
                >
                  {getTypeIcon(mod)}
                  <span className="hidden sm:inline">{getTypeLabel(mod, t)}</span>
                </Badge>
              ))}
            </div>
            {credential.has_api_key && (
              <Badge variant="outline" className="text-[10px]">
                <Key className="h-2.5 w-2.5 mr-0.5" />
                Key
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {testResult && (
              testResult.success
                ? <Check className="h-4 w-4 text-success" />
                : <X className="h-4 w-4 text-destructive" />
            )}
            <Button
              variant="ghost" size="sm"
              onClick={() => testCredential(credential.id)}
              disabled={isTestPending || !!credential.decryption_error}
              title={t('apiKeys.testConnection')}
            >
              {isTestPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
              <span className="hidden sm:inline text-xs">{t('apiKeys.testConnection')}</span>
            </Button>
            <Button
              variant="ghost" size="sm"
              onClick={() => setDiscoverOpen(true)}
              disabled={!!credential.decryption_error}
              title={t('apiKeys.syncModels')}
            >
              <Bot className="h-4 w-4" />
              <span className="hidden sm:inline text-xs">{t('apiKeys.syncModels')}</span>
            </Button>
            {/* Edit / Delete live in the "..." menu; same guards and dialogs.
                Non-modal so the dialog it opens does not inherit the menu's
                body pointer-events lock. */}
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" aria-label={t('common.actions')} title={t('common.actions')}>
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => setEditOpen(true)}
                  disabled={!!credential.decryption_error}
                >
                  <Edit className="h-4 w-4" />
                  {t('common.edit')}
                </DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onSelect={() => setDeleteOpen(true)}>
                  <Trash2 className="h-4 w-4" />
                  {t('common.delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Decryption error warning */}
        {credential.decryption_error && (
          <Alert className="border-warn/30 bg-warn-tint text-warn [&>svg]:text-warn">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>{t('apiKeys.decryptionError')}</AlertTitle>
            <AlertDescription className="text-sm">
              {t('apiKeys.decryptionErrorDescription')}
            </AlertDescription>
          </Alert>
        )}

        {/* Linked models grouped by type */}
        {linkedModels.length > 0 && (
          <div className="space-y-1.5 pt-1">
            {MODEL_TYPES
              .filter(type => linkedModels.some(m => m.type === type))
              .map(type => (
                <div key={type} className="flex items-start gap-1.5">
                  <Badge
                    variant="outline"
                    className={`text-[10px] gap-0.5 px-1 py-0 shrink-0 mt-0.5 ${getTypeColor(type)}`}
                  >
                    {getTypeIcon(type)}
                    {getTypeLabel(type, t)}
                  </Badge>
                  <div className="flex flex-wrap gap-1">
                    {linkedModels.filter(m => m.type === type).map(model => {
                      const defaultSlot = defaultSlots[model.id]
                      return (
                        <Badge
                          key={model.id}
                          variant={defaultSlot ? 'default' : 'secondary'}
                          className="font-mono text-[11px] gap-1 pr-0.5 group/model"
                        >
                          {model.name}
                          {defaultSlot && <span className="ml-0.5 opacity-75">({t(defaultSlot)})</span>}
                          <button
                            className="ml-0.5 opacity-0 group-hover/model:opacity-60 hover:!opacity-100 transition-opacity"
                            onClick={() => testModel(model.id, model.name)}
                            disabled={isModelTestPending && testingModelId === model.id}
                            title={t('models.testModel')}
                          >
                            {isModelTestPending && testingModelId === model.id
                              ? <Loader2 className="h-3 w-3 animate-spin" />
                              : <Plug className="h-3 w-3" />
                            }
                          </button>
                          <button
                            className="opacity-0 group-hover/model:opacity-60 hover:!opacity-100 hover:text-destructive transition-opacity"
                            onClick={() => deleteModel.mutate(model.id)}
                            title={t('models.deleteModel')}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      )
                    })}
                  </div>
                </div>
              ))}
          </div>
        )}


      </div>

      {/* Edit dialog */}
      {editOpen && (
        <CredentialFormDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          provider={credential.provider}
          credential={fullCredential || credential}
        />
      )}

      {/* Delete dialog */}
      {deleteOpen && (
        <DeleteCredentialDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          credential={credential}
          allCredentials={allCredentials}
        />
      )}

      {/* Discover models dialog */}
      {discoverOpen && (
        <DiscoverModelsDialog
          open={discoverOpen}
          onOpenChange={setDiscoverOpen}
          credential={credential}
        />
      )}

      {/* Model test result dialog */}
      <ModelTestResultDialog
        open={modelTestResult !== null}
        onOpenChange={(open) => { if (!open) clearModelTestResult() }}
        result={modelTestResult}
        modelName={testedModelName}
      />
    </>
  )
}
