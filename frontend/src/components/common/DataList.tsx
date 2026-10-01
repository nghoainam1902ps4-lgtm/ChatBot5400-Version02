import type { ComponentProps, ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Vertical list for long-title items (list / mobile list). */
export function DataList({ className, ...props }: ComponentProps<'ul'>) {
  return <ul data-slot="data-list" className={cn('divide-y divide-border', className)} {...props} />
}

interface DataListItemProps extends Omit<ComponentProps<'li'>, 'title'> {
  title: ReactNode
  /** Light secondary line (counts, dates…). */
  meta?: ReactNode
  /** Optional trailing slot; never shrinks, so long titles cannot push it. */
  actions?: ReactNode
  /** Title classes; defaults to single-line truncation. */
  titleClassName?: string
}

/**
 * One list row: title + light metadata on the left, optional actions on the
 * right. The text column is `min-w-0` so a one-line title truncates instead of
 * moving the metadata or the trailing slot. No domain fields.
 */
export function DataListItem({ title, meta, actions, titleClassName, className, ...props }: DataListItemProps) {
  return (
    <li data-slot="data-list-item" className={cn('flex min-h-11 items-center gap-3 py-3', className)} {...props}>
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-sm font-medium', titleClassName)}>{title}</div>
        {meta && <div className="mt-0.5 truncate text-xs text-muted-foreground">{meta}</div>}
      </div>
      {actions && <div className="flex flex-shrink-0 items-center gap-1">{actions}</div>}
    </li>
  )
}
