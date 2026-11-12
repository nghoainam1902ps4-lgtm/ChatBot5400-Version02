'use client'

import { useState } from 'react'
import { Check, X } from 'lucide-react'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { MOBILE_SHEET_CLASSES, SheetGrip } from '@/components/ui/mobile-sheet'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { SourceDetailContent } from './SourceDetailContent'
import { useApproveSource, useRejectSource } from '@/lib/hooks/use-approvals'
import { useTranslation } from '@/lib/hooks/use-translation'

interface ReviewSourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sourceId: string | null
}

/**
 * Review window for a pending source: shows the full source detail (content,
 * insights, and the "Manage notebooks" details tab so a reviewer can change the
 * notebook/sub-notebook it belongs to) plus Approve / Reject actions.
 */
export function ReviewSourceDialog({
  open,
  onOpenChange,
  sourceId,
}: ReviewSourceDialogProps) {
  const { t } = useTranslation()
  const approve = useApproveSource()
  const reject = useRejectSource()
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')

  const idWithPrefix = sourceId
    ? sourceId.includes(':')
      ? sourceId
      : `source:${sourceId}`
    : null

  if (!idWithPrefix) return null

  const busy = approve.isPending || reject.isPending

  const handleApprove = async () => {
    await approve.mutateAsync(idWithPrefix)
    onOpenChange(false)
  }

  const handleReject = async () => {
    await reject.mutateAsync({
      sourceId: idWithPrefix,
      reason: reason || undefined,
    })
    setRejecting(false)
    setReason('')
    onOpenChange(false)
  }

  return (
    <>
      {/* Hidden while the reject-reason dialog is up to avoid stacked focus traps. */}
      <Dialog open={open && !rejecting} onOpenChange={onOpenChange}>
        <DialogContent
          size="xl"
          className={`h-[88vh] max-lg:h-[88dvh] ${MOBILE_SHEET_CLASSES}`}
        >
          <SheetGrip />
          <DialogTitle className="sr-only">{t('approvals.reviewTitle')}</DialogTitle>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 px-6 pt-6 max-lg:overscroll-contain max-lg:px-4 max-lg:pt-2">
              <SourceDetailContent
                sourceId={idWithPrefix}
                showChatButton={false}
                onClose={() => onOpenChange(false)}
                manageNotebooksAutoSave
              />
            </div>

            <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3 max-lg:px-4">
              <Button
                variant="outline"
                onClick={() => setRejecting(true)}
                disabled={busy}
              >
                <X className="h-4 w-4" />
                {t('approvals.reject')}
              </Button>
              <Button onClick={handleApprove} disabled={busy}>
                <Check className="h-4 w-4" />
                {t('approvals.approve')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Reject reason */}
      <Dialog open={rejecting} onOpenChange={(o) => !o && setRejecting(false)}>
        <DialogContent size="md">
          <DialogHeader>
            <DialogTitle>{t('approvals.rejectTitle')}</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-1.5">
            <Label htmlFor="review-reject-reason">{t('approvals.rejectReason')}</Label>
            <Textarea
              id="review-reject-reason"
              rows={3}
              value={reason}
              placeholder={t('approvals.rejectReasonPlaceholder')}
              onChange={(e) => setReason(e.target.value)}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleReject}
              disabled={reject.isPending}
            >
              {t('approvals.reject')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
