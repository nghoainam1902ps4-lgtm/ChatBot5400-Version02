import type { ReactNode } from 'react'
import { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * - `empty` (default): nothing exists yet; may show a create action.
 * - `search`: a search/filter matched nothing; never shows a create action
 *   (`action` is ignored), so "no results" is not confused with "no data".
 */
export type EmptyStateVariant = 'empty' | 'search'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: ReactNode
  action?: ReactNode
  variant?: EmptyStateVariant
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, variant = 'empty', className }: EmptyStateProps) {
  const isSearch = variant === 'search'
  return (
    <div data-slot="empty-state" data-variant={variant} className={cn('text-center', isSearch ? 'py-10' : 'py-12', className)}>
      <Icon className={cn('mx-auto text-muted-foreground/60', isSearch ? 'mb-3 h-10 w-10' : 'mb-4 h-12 w-12')} />
      <h3 className="text-lg font-medium text-foreground mb-2">{title}</h3>
      {description && <p className="text-muted-foreground mb-4">{description}</p>}
      {!isSearch && action}
    </div>
  )
}
