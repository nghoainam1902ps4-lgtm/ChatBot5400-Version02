import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/**
 * Grid container for summary cards. Gap: 12px on mobile, 16px from 640px.
 * The caller decides the column count via `className` (e.g. `sm:grid-cols-2`).
 */
export function CardGrid({ className, ...props }: ComponentProps<'div'>) {
  return <div data-slot="card-grid" className={cn('grid gap-3 sm:gap-4', className)} {...props} />
}
