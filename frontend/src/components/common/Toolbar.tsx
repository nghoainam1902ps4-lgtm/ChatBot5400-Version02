import { Children, type ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/**
 * Page toolbar row (search, filters, actions): 44px base row, no decorative
 * border, wraps when narrow. Spacing: description → toolbar 14/18/20px
 * (mobile/tablet/desktop), toolbar → content 12/16/16px. Renders nothing when
 * it has no content.
 */
export function Toolbar({ className, children, ...props }: ComponentProps<'div'>) {
  if (Children.toArray(children).length === 0) return null
  return (
    <div
      data-slot="toolbar"
      className={cn(
        'mt-3.5 mb-3 flex min-h-11 flex-wrap items-center gap-2 sm:mt-[18px] sm:mb-4 lg:mt-5',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
