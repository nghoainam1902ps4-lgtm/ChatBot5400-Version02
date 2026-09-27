'use client'

import { useState } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogBody,
} from '@/components/ui/dialog'
import { Loader2, AlertCircle, Trash2 } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useDeleteCredential } from '@/lib/hooks/use-credentials'
import { Credential } from '@/lib/api/credentials'

interface DeleteCredentialDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  credential: Credential
  allCredentials: Credential[]
}

export function DeleteCredentialDialog({
  open,
  onOpenChange,
  credential,
  allCredentials,
}: DeleteCredentialDialogProps) {
  const { t } = useTranslation()
  const deleteCredential = useDeleteCredential()
  const [migrateToId, setMigrateToId] = useState<string>('')

  const otherCredentials = allCredentials.filter(
    c => c.id !== credential.id && c.provider === credential.provider
  )

  const handleDeleteWithModels = () => {
    deleteCredential.mutate(
      { credentialId: credential.id, options: { delete_models: true } },
      { onSuccess: () => onOpenChange(false) }
    )
  }

  const handleMigrate = () => {
    if (!migrateToId) return
    deleteCredential.mutate(
      { credentialId: credential.id, options: { migrate_to: migrateToId } },
      { onSuccess: () => onOpenChange(false) }
    )
  }

  const handleDeleteOnly = () => {
    deleteCredential.mutate(
      { credentialId: credential.id },
      { onSuccess: () => onOpenChange(false) }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* B2 Destructive: SM, no close button (leave via Cancel or the action). */}
      <DialogContent size="sm" showCloseButton={false}>
        <DialogHeader icon={<Trash2 />} iconTone="danger" className="pr-6">
          <DialogTitle>{t('apiKeys.deleteConfig')}</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <DialogDescription>
            {t('apiKeys.deleteConfigConfirm', { name: credential.name })}
          </DialogDescription>

          {credential.model_count > 0 && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {t('apiKeys.linkedModelsCount', { count: credential.model_count })}
                {otherCredentials.length > 0 && (
                  <div className="mt-2">
                    <Label>{t('apiKeys.migrateModelsTo')}</Label>
                    <Select value={migrateToId} onValueChange={setMigrateToId}>
                      <SelectTrigger className="mt-1 w-full">
                        <SelectValue placeholder={t('apiKeys.selectCredential')} />
                      </SelectTrigger>
                      <SelectContent>
                        {otherCredentials.map(c => (
                          <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </AlertDescription>
            </Alert>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          {credential.model_count > 0 && migrateToId && (
            <Button variant="destructive" onClick={handleMigrate} disabled={deleteCredential.isPending}>
              {deleteCredential.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              {t('apiKeys.migrateAndDelete')}
            </Button>
          )}
          <Button
            variant="destructive"
            onClick={credential.model_count > 0 ? handleDeleteWithModels : handleDeleteOnly}
            disabled={deleteCredential.isPending}
          >
            {deleteCredential.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            {credential.model_count > 0 ? t('apiKeys.deleteWithModels') : t('common.delete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
