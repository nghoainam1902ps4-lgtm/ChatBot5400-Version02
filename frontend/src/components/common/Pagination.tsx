import type { ComponentProps, ReactNode } from 'react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { cn } from '@/lib/utils'

/**
 * Presentation row at the end of a list (status / "load more" area). It does
 * not page, fetch or know a page size — callers keep their existing infinite
 * scroll and only render this row.
 */
export function Pagination({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="pagination"
      className={cn('flex min-h-12 items-center justify-center gap-2 py-3 text-sm text-muted-foreground', className)}
      {...props}
    />
  )
}

interface InfiniteIndicatorProps {
  /** A next page is being fetched by the caller. */
  loading: boolean
  /** The caller has nothing more to load. */
  done?: boolean
  loadingLabel?: ReactNode
  doneLabel?: ReactNode
  className?: string
}

/** Infinite-scroll status: spinner + label while loading, optional end label. */
export function InfiniteIndicator({ loading, done = false, loadingLabel, doneLabel, className }: InfiniteIndicatorProps) {
  if (loading) {
    return (
      <Pagination role="status" aria-live="polite" className={className}>
        <LoadingSpinner size="sm" />
        {loadingLabel}
      </Pagination>
    )
  }
  if (done && doneLabel) return <Pagination className={className}>{doneLabel}</Pagination>
  return null
}
