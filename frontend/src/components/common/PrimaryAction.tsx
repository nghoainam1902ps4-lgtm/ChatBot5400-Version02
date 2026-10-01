import type { ComponentProps, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type BaseProps = Omit<ComponentProps<typeof Button>, 'size' | 'children'>

/**
 * Icon + label, or icon-only. Icon-only actions (e.g. refresh) must carry an
 * aria-label — enforced by the type.
 */
type PrimaryActionProps = BaseProps &
  (
    | { icon?: LucideIcon; children: ReactNode }
    | { icon: LucideIcon; children?: undefined; 'aria-label': string }
  )

/**
 * Primary page action on the existing Button. Height: 44px <640, 40px
 * 640–1023, 36px >=1024. Text always comes from the caller.
 */
export function PrimaryAction({ icon: Icon, children, className, ...props }: PrimaryActionProps) {
  const iconOnly = children === undefined || children === null
  return (
    <Button
      data-slot="primary-action"
      className={cn('h-11 sm:h-10 lg:h-9', iconOnly && 'w-11 px-0 sm:w-10 lg:w-9', className)}
      {...props}
    >
      {Icon && <Icon aria-hidden className="size-4" />}
      {children}
    </Button>
  )
}
