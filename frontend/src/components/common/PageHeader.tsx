import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { PageDescription } from './PageDescription'

interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Right-aligned actions; wraps below the title when space runs out. */
  actions?: ReactNode
  className?: string
}

/**
 * Page title block: title + optional description on the left, actions on the
 * right. Not sticky, no breadcrumb, no tabs, no default icon.
 */
export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <header
      data-slot="page-header"
      className={cn('flex flex-wrap items-start justify-between gap-x-4 gap-y-3', className)}
    >
      <div className="min-w-0 flex-1 basis-64">
        <h1 className="font-display text-2xl font-bold tracking-tight">{title}</h1>
        {description && <PageDescription>{description}</PageDescription>}
      </div>
      {actions && <div className="flex flex-shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}
