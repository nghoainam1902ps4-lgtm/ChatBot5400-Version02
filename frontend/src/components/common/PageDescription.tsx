import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/**
 * Page-level description under the title: 14px muted text, at most 80ch.
 * Title → description spacing: 6px on mobile, 8px from 640px.
 */
export function PageDescription({ className, ...props }: ComponentProps<'p'>) {
  return (
    <p
      data-slot="page-description"
      className={cn('mt-1.5 max-w-[80ch] text-sm text-muted-foreground sm:mt-2', className)}
      {...props}
    />
  )
}
