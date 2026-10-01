import { cn } from '@/lib/utils'

type LoadingSkeletonProps =
  | { variant: 'table'; rows: number; columns?: number; className?: string; 'aria-label'?: string }
  | { variant: 'card' | 'list'; items: number; lines?: number; className?: string; 'aria-label'?: string }

const Bar = ({ className }: { className?: string }) => (
  <span aria-hidden className={cn('block animate-pulse rounded bg-muted', className)} />
)

/**
 * Geometry-preserving placeholders so content does not jump when data
 * arrives. `table`: 48px header + 48px rows (caller sets the row count).
 * `card` / `list`: caller sets the item count and placeholder lines per item.
 * LoadingSpinner stays the choice for small areas and buttons.
 */
export function LoadingSkeleton(props: LoadingSkeletonProps) {
  const { className } = props
  const common = {
    role: 'status' as const,
    'aria-busy': true,
    'aria-label': props['aria-label'],
  }

  if (props.variant === 'table') {
    const columns = Math.max(1, props.columns ?? 3)
    const cells = (key: string, bar: string) =>
      Array.from({ length: columns }, (_, c) => (
        <div key={`${key}-${c}`} className="flex flex-1 items-center px-4">
          <Bar className={bar} />
        </div>
      ))
    return (
      <div data-slot="loading-skeleton" data-variant="table" className={cn('w-full', className)} {...common}>
        <div data-slot="skeleton-header" className="flex h-12 border-b">{cells('h', 'h-3 w-20')}</div>
        {Array.from({ length: Math.max(0, props.rows) }, (_, r) => (
          <div key={r} data-slot="skeleton-row" className="flex h-12 border-b">{cells(`r${r}`, 'h-3.5 w-full max-w-48')}</div>
        ))}
      </div>
    )
  }

  const lines = Math.max(1, props.lines ?? 2)
  const isCard = props.variant === 'card'
  return (
    <div
      data-slot="loading-skeleton"
      data-variant={props.variant}
      className={cn(isCard ? 'grid gap-3 sm:gap-4' : 'divide-y divide-border', className)}
      {...common}
    >
      {Array.from({ length: Math.max(0, props.items) }, (_, i) => (
        <div
          key={i}
          data-slot="skeleton-item"
          className={cn(
            'flex flex-col gap-2',
            isCard ? 'rounded-lg border px-4 py-3.5 sm:px-[18px] sm:py-4 lg:px-5' : 'py-3'
          )}
        >
          {Array.from({ length: lines }, (_, l) => (
            <Bar key={l} className={cn('h-3.5', l === 0 ? 'w-2/3' : 'w-1/2')} />
          ))}
        </div>
      ))}
    </div>
  )
}
