'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogBody,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { AlertTriangle, ExternalLink } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'

interface EmbeddingModelChangeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  oldModelName?: string
  newModelName?: string
}

export function EmbeddingModelChangeDialog({
  open,
  onOpenChange,
  onConfirm,
  oldModelName,
  newModelName
}: EmbeddingModelChangeDialogProps) {
  const { t } = useTranslation()
  const router = useRouter()
  const [isConfirming, setIsConfirming] = useState(false)

  const handleConfirmAndRebuild = () => {
    setIsConfirming(true)
    onConfirm()
    // Give a moment for the model to update, then redirect
    setTimeout(() => {
      router.push('/advanced')
      onOpenChange(false)
      setIsConfirming(false)
    }, 500)
  }

  const handleConfirmOnly = () => {
    onConfirm()
    onOpenChange(false)
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      {/* B2 Long content: LG, body scrolls, header/footer fixed, three
          actions on one row. */}
      <AlertDialogContent size="lg">
        <AlertDialogHeader icon={<AlertTriangle />} iconTone="warn">
          <AlertDialogTitle>{t('models.embeddingChangeTitle')}</AlertDialogTitle>
        </AlertDialogHeader>
        <AlertDialogBody>
          <AlertDialogDescription asChild>
            <div className="space-y-3 text-base text-muted-foreground">
              <p>
                {t('models.embeddingChangeConfirm', { from: oldModelName || '...', to: newModelName || '...' })}
              </p>

              <div className="bg-muted p-4 rounded-md space-y-2">
                <p className="font-semibold text-foreground">{t('models.rebuildRequired')}</p>
                <p className="text-sm">
                  {t('models.rebuildReason')}
                </p>
              </div>

              <div className="space-y-2 text-sm">
                <p className="font-medium text-foreground">{t('models.whatHappensNext')}</p>
                <ul className="list-disc list-inside space-y-1 ml-2">
                  <li>{t('models.step1')}</li>
                  <li>{t('models.step2')}</li>
                  <li>{t('models.step3')}</li>
                  <li>{t('models.step4')}</li>
                </ul>
              </div>

              <p className="text-sm font-medium text-foreground">
                {t('models.proceedToRebuildPrompt')}
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogBody>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isConfirming}>
            {t('common.cancel')}
          </AlertDialogCancel>
          <Button
            variant="outline"
            onClick={handleConfirmOnly}
            disabled={isConfirming}
          >
            {t('models.changeModelOnly')}
          </Button>
          <AlertDialogAction
            onClick={handleConfirmAndRebuild}
            disabled={isConfirming}
          >
            <ExternalLink className="mr-2 h-4 w-4" />
            {t('models.changeAndRebuild')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
