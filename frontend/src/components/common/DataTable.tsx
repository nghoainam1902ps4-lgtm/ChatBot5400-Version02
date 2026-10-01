import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/**
 * Presentation table (SPS). Header and rows are 48px. Row states:
 * - default: surface;
 * - hover: recessed surface (never overrides selected);
 * - selected (`selected` prop): accent background + 2px primary bar on the
 *   leading edge, independent of the pointer;
 * - focus: 2px outline with 2px offset, visible on top of selected.
 * No sorting, paging, selection index or keyboard handling — callers own state.
 */
export function DataTable({ className, ...props }: ComponentProps<'table'>) {
  return <table data-slot="data-table" className={cn('w-full border-collapse text-sm', className)} {...props} />
}

/**
 * Optional state container around a table (data / loading / no-result) that
 * keeps a 240px minimum height so the page does not jump. Adds no scrolling.
 */
export function DataTableContainer({ className, ...props }: ComponentProps<'div'>) {
  return <div data-slot="data-table-container" className={cn('min-h-[240px]', className)} {...props} />
}

export function DataTableHeader({ className, ...props }: ComponentProps<'thead'>) {
  return <thead data-slot="data-table-header" className={cn('border-b', className)} {...props} />
}

export function DataTableBody(props: ComponentProps<'tbody'>) {
  return <tbody data-slot="data-table-body" {...props} />
}

export function DataTableHead({ className, ...props }: ComponentProps<'th'>) {
  return (
    <th
      data-slot="data-table-head"
      className={cn('h-12 px-4 text-left align-middle font-medium text-muted-foreground', className)}
      {...props}
    />
  )
}

interface DataTableRowProps extends ComponentProps<'tr'> {
  selected?: boolean
}

export function DataTableRow({ selected = false, className, ...props }: DataTableRowProps) {
  return (
    <tr
      data-slot="data-table-row"
      data-selected={selected ? 'true' : undefined}
      aria-selected={selected || undefined}
      className={cn(
        'h-12 border-b bg-card transition-colors hover:bg-muted',
        'data-[selected=true]:bg-accent data-[selected=true]:hover:bg-accent',
        'data-[selected=true]:[&>*:first-child]:shadow-[inset_2px_0_0_var(--primary)]',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        className
      )}
      {...props}
    />
  )
}

export function DataTableCell({ className, ...props }: ComponentProps<'td'>) {
  return <td data-slot="data-table-cell" className={cn('h-12 px-4 align-middle', className)} {...props} />
}
