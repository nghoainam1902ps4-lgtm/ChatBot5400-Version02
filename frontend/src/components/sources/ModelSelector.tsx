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
  DialogBody,
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

  // Closing without saving (Hủy, X, Esc, overlay) discards the draft selection
  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setSelectedModel(currentModel || 'default')
    }
    setOpen(next)
  }

  const handleReset = () => {
    setSelectedModel('default')
    onModelChange(undefined)
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          className="h-7 gap-1.5 rounded-full px-2.5 text-xs text-muted-foreground hover:text-foreground max-lg:h-[26px] max-lg:max-w-[46vw] max-lg:flex-shrink-0 max-lg:gap-[5px] max-lg:bg-muted/60 max-lg:px-[9px] max-lg:text-[11.5px]"
        >
          <Settings2 className="h-3.5 w-3.5" />
          <span className="text-xs max-lg:min-w-0 max-lg:truncate max-lg:text-[11.5px]">
            {currentModelName}
          </span>
        </Button>
      </DialogTrigger>
      {/* md (560px) leaves room for long model names; below sm the base
          DialogContent keeps max-w-[calc(100%-2rem)], so it never overflows. */}
      <DialogContent size="md">
        <DialogHeader icon={<Sparkles />}>
          <DialogTitle>
            {t('common.modelConfiguration')}
          </DialogTitle>
          <DialogDescription>
            {t('transformations.overrideModelDesc')}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="grid min-w-0 gap-4">
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
        </DialogBody>
        <DialogFooter className="sm:justify-between">
          <Button variant="ghost" onClick={handleReset}>
            {t('common.resetToDefault')}
          </Button>
          <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <Button variant="outline" onClick={() => handleOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSave}>
              {t('common.saveChanges')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
