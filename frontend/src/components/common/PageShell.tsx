import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/** Content width categories for page bodies (SPS). */
export type PageShellWidth = 'full' | 'wide' | 'config' | 'reading'

const WIDTH_CLASS: Record<PageShellWidth, string> = {
  full: 'max-w-none',
  wide: 'max-w-[1200px]',
  config: 'max-w-[1000px]',
  reading: 'max-w-[880px]',
}

interface PageShellProps extends ComponentProps<'div'> {
  width?: PageShellWidth
}

/**
 * Page content wrapper: one width category, centered, with the shared page
 * padding (16px <640, 20px 640–1023, 24px >=1024).
 */
export function PageShell({ width = 'full', className, ...props }: PageShellProps) {
  return (
    <div
      data-slot="page-shell"
      data-width={width}
      className={cn('mx-auto w-full p-4 sm:p-5 lg:p-6', WIDTH_CLASS[width], className)}
      {...props}
    />
  )
}
