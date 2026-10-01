'use client'

import type { ReactNode } from 'react'
import { Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

interface AccessDeniedProps {
  /** Defaults to `common.accessDenied.title`. */
  title?: ReactNode
  /** Defaults to `common.accessDenied.desc`. */
  description?: ReactNode
  /** Optional lightweight action; the caller decides what it does. */
  onAction?: () => void
  /** Defaults to `common.accessDenied.backToNotebooks`. */
  actionLabel?: string
  className?: string
}

/**
 * Shown when the account lacks permission for a page or section. Neutral, not
 * an error or a warning. It never navigates or redirects by itself; the
 * backend remains the authority. Not for authentication failures or expired
 * sessions.
 */
export function AccessDenied({ title, description, onAction, actionLabel, className }: AccessDeniedProps) {
  const { t } = useTranslation()
  return (
    <div data-slot="access-denied" className={cn('flex flex-col items-center px-4 py-12 text-center', className)}>
      <Lock aria-hidden className="mb-3 size-10 text-muted-foreground" />
      <h2 className="text-lg font-medium text-foreground">{title ?? t('common.accessDenied.title')}</h2>
      <p className="mt-1.5 max-w-[60ch] text-sm text-muted-foreground">{description ?? t('common.accessDenied.desc')}</p>
      {onAction && (
        <Button variant="outline" className="mt-4 h-11 sm:h-10 lg:h-9" onClick={onAction}>
          {actionLabel ?? t('common.accessDenied.backToNotebooks')}
        </Button>
      )}
    </div>
  )
}
