import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Semantic level of an admin section:
 * - `readonly`: neutral surface and border;
 * - `maintenance`: teal / info (e.g. rebuild jobs) — never red;
 * - `danger`: destructive, for irreversible actions only.
 */
export type AdminAreaLevel = 'readonly' | 'maintenance' | 'danger'

const LEVEL_CLASS: Record<AdminAreaLevel, { box: string; title: string }> = {
  readonly: { box: 'border-border bg-card', title: 'text-foreground' },
  maintenance: { box: 'border-teal/30 bg-teal-tint', title: 'text-teal' },
  danger: { box: 'border-destructive/30 bg-destructive-tint', title: 'text-destructive' },
}

interface AdminAreaProps {
  level: AdminAreaLevel
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
  className?: string
}

/** Admin section box. Section names and copy always come from the caller. */
export function AdminArea({ level, title, description, actions, children, className }: AdminAreaProps) {
  const tone = LEVEL_CLASS[level]
  return (
    <section
      data-slot="admin-area"
      data-level={level}
      className={cn('rounded-lg border px-4 py-3.5 sm:px-[18px] sm:py-4 lg:px-5', tone.box, className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-56">
          <h2 className={cn('text-base font-semibold', tone.title)}>{title}</h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children && <div className="mt-4">{children}</div>}
    </section>
  )
}
