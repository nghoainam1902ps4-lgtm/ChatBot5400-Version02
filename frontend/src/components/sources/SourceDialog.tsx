'use client'

import { useRouter } from 'next/navigation'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { MOBILE_SHEET_CLASSES, SheetGrip } from '@/components/ui/mobile-sheet'
import { SourceDetailContent } from './SourceDetailContent'
import { useTranslation } from '@/lib/hooks/use-translation'

interface SourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sourceId: string | null
}

/**
 * Source Dialog Component
 *
 * Displays source details in a modal dialog.
 * Includes a "Chat with source" button that navigates to the full source page in-app.
 */
export function SourceDialog({ open, onOpenChange, sourceId }: SourceDialogProps) {
  const { t } = useTranslation()
  const router = useRouter()
  // Ensure source ID has 'source:' prefix for API calls and routing
  const sourceIdWithPrefix = sourceId
    ? (sourceId.includes(':') ? sourceId : `source:${sourceId}`)
    : null

  const handleChatClick = () => {
    if (sourceIdWithPrefix) {
      onOpenChange(false)
      router.push(`/sources/${sourceIdWithPrefix}`)
    }
  }

  const handleClose = () => {
    onOpenChange(false)
  }

  if (!sourceIdWithPrefix) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Wide (xl), tall reading modal for long legal documents. Fixed height so
          SourceDetailContent (flex-col h-full) can pin its header and scroll
          only the body — the inner content owns its own scroll. */}
      {/* < lg: bottom sheet at 88dvh (M1); lg+: unchanged B2 dialog */}
      <DialogContent size="xl" className={`h-[88vh] max-lg:h-[88dvh] ${MOBILE_SHEET_CLASSES}`}>
        <SheetGrip />
        {/* Accessibility title (hidden visually but read by screen readers) */}
        <DialogTitle className="sr-only">{t('sources.detailsTitle')}</DialogTitle>

        {/* Source detail content — header pinned, body scrolls internally */}
        <div className="flex-1 min-h-0 px-6 pt-6 max-lg:px-4 max-lg:pt-2 max-lg:overscroll-contain">
          <SourceDetailContent
            sourceId={sourceIdWithPrefix}
            showChatButton={true}
            onChatClick={handleChatClick}
            onClose={handleClose}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
