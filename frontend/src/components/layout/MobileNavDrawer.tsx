'use client'

import * as DialogPrimitive from '@radix-ui/react-dialog'
import { AppSidebar } from './AppSidebar'
import { useTranslation } from '@/lib/hooks/use-translation'

interface MobileNavDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * M1 navigation drawer (< 1024px): a 296px left panel that renders the same
 * AppSidebar as the desktop rail, in its `drawer` variant. Content unmounts
 * when closed; all navigation/create/account actions come from AppSidebar.
 */
export function MobileNavDrawer({ open, onOpenChange }: MobileNavDrawerProps) {
  const { t } = useTranslation()
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/45 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 lg:hidden" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 flex w-[296px] max-w-[85vw] flex-col shadow-overlay outline-none duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left lg:hidden"
        >
          <DialogPrimitive.Title className="sr-only">{t('common.navigationMenu')}</DialogPrimitive.Title>
          <AppSidebar variant="drawer" onRequestClose={() => onOpenChange(false)} />
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
