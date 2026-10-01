'use client'

import type { ReactNode } from 'react'
import { AlertCircle, RotateCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

interface ErrorStateProps {
  title: ReactNode
  description?: ReactNode
  /** Called by the retry button; the button is omitted without it. */
  onRetry?: () => void
  /** Defaults to `common.retry`. */
  retryLabel?: string
  className?: string
}

/**
 * Inline error for a content area that failed to load (a real error, so it
 * uses the destructive hue). Not a fatal screen: no redirect, no toast — the
 * retry button only calls `onRetry`. Permission problems use AccessDenied.
 */
export function ErrorState({ title, description, onRetry, retryLabel, className }: ErrorStateProps) {
  const { t } = useTranslation()
  return (
    <div data-slot="error-state" role="alert" className={cn('flex flex-col items-center px-4 py-10 text-center', className)}>
      <AlertCircle aria-hidden className="mb-3 size-10 text-destructive" />
      <h3 className="text-base font-medium text-foreground">{title}</h3>
      {description && <p className="mt-1.5 max-w-[60ch] text-sm text-muted-foreground">{description}</p>}
      {onRetry && (
        <Button variant="outline" className="mt-4 h-11 sm:h-10 lg:h-9" onClick={onRetry}>
          <RotateCw aria-hidden className="size-4" />
          {retryLabel ?? t('common.retry')}
        </Button>
      )}
    </div>
  )
}
