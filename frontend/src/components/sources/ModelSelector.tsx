'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Settings2, Sparkles } from 'lucide-react'
import { useModelDefaults, useModels } from '@/lib/hooks/use-models'
import { useTranslation } from '@/lib/hooks/use-translation'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'

interface ModelSelectorProps {
  currentModel?: string
  onModelChange: (model?: string) => void
  disabled?: boolean
}

export function ModelSelector({ 
  currentModel, 
  onModelChange,
  disabled = false 
}: ModelSelectorProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [selectedModel, setSelectedModel] = useState(currentModel || 'default')
  const { data: models, isLoading } = useModels()
  const { data: defaults } = useModelDefaults()

  useEffect(() => {
    setSelectedModel(currentModel || 'default')
  }, [currentModel])

  // Filter for language models only and sort by name
  const languageModels = useMemo(() => {
    if (!models) {
      return []
    }
    return [...models]
      .filter((model) => model.type === 'language')
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [models])

  const defaultModel = useMemo(() => {
    if (!defaults?.default_chat_model) return undefined
    return languageModels.find(model => model.id === defaults.default_chat_model)
  }, [defaults?.default_chat_model, languageModels])

  const currentModelName = useMemo(() => {
    if (currentModel) {
      return languageModels.find(model => model.id === currentModel)?.name || currentModel
    }
    if (defaultModel) {
      return defaultModel.name
    }
    return t('common.default')
  }, [currentModel, languageModels, defaultModel, t('common.default')])

  const handleSave = () => {
    onModelChange(selectedModel === 'default' ? undefined : selectedModel)
    setOpen(false)
  }

  const handleReset = () => {
    setSelectedModel('default')
    onModelChange(undefined)
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          className="h-7 gap-1.5 rounded-full px-2.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Settings2 className="h-3.5 w-3.5" />
          <span className="text-xs">
            {currentModelName}
          </span>
        </Button>
      </DialogTrigger>
      {/* Room for long model names (e.g. "Mặc định (google/gemini-3-flash-preview)").
          The base DialogContent keeps max-w-[calc(100%-2rem)] below sm, so it never
          overflows the viewport. */}
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            {t('common.modelConfiguration')}
          </DialogTitle>
          <DialogDescription>
            {t('transformations.overrideModelDesc')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid min-w-0 gap-4 py-4">
          <div className="grid min-w-0 gap-2">
            <Label htmlFor="model">{t('common.model')}</Label>
            <Select value={selectedModel} onValueChange={setSelectedModel}>
              {/* Full width of the dialog; a long selected name truncates in the
                  trigger (full name in the title tooltip and in the open list). */}
              <SelectTrigger
                id="model"
                className="w-full min-w-0 *:data-[slot=select-value]:min-w-0 *:data-[slot=select-value]:flex-1 [&_[data-slot=select-value]_span]:truncate"
                title={selectedModel === 'default'
                  ? (defaultModel ? `${t('common.default')} (${defaultModel.name})` : t('transformations.systemDefault'))
                  : languageModels.find(m => m.id === selectedModel)?.name || selectedModel}
              >
                <SelectValue placeholder={t('models.selectModelPlaceholder')} />
              </SelectTrigger>
              <SelectContent className="max-w-[var(--radix-select-content-available-width)]">
                <SelectItem value="default">
                  <div className="flex min-w-0 items-center justify-between w-full">
                    <span className="min-w-0 [overflow-wrap:anywhere]">
                      {defaultModel 
                        ? `${t('common.default')} (${defaultModel.name})` 
                        : t('transformations.systemDefault')}
                    </span>
                    {defaultModel?.provider && (
                      <span className="flex-shrink-0 text-xs text-muted-foreground ml-2">
                        {defaultModel.provider}
                      </span>
                    )}
                  </div>
                </SelectItem>
                {isLoading ? (
                  <div className="flex items-center justify-center py-2">
                    <LoadingSpinner size="sm" />
                  </div>
                ) : (
                  languageModels.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      <div className="flex min-w-0 items-center justify-between w-full">
                        <span className="min-w-0 [overflow-wrap:anywhere]" title={model.name}>{model.name}</span>
                        <span className="flex-shrink-0 text-xs text-muted-foreground ml-2">
                          {model.provider}
                        </span>
                      </div>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>
          {selectedModel && selectedModel !== 'default' && (
            <div className="rounded-lg bg-muted p-3">
              <p className="text-sm text-muted-foreground break-words">
                {t('transformations.sessionUseReplacement', { name: languageModels.find(m => m.id === selectedModel)?.name || selectedModel })}
              </p>
            </div>
          )}
        </div>
        <DialogFooter className="flex justify-between">
          <Button variant="outline" onClick={handleReset}>
            {t('common.resetToDefault')}
          </Button>
          <Button onClick={handleSave}>
            {t('common.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
