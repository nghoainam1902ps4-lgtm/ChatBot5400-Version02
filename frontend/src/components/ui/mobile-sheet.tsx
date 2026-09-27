import { cn } from '@/lib/utils'

/**
 * M1 bottom-sheet presentation for a B2 `DialogContent`, below 1024px only.
 * Pass `MOBILE_SHEET_CLASSES` in the consumer's `className`: every rule is
 * `max-lg:`-scoped, so from lg up the dialog renders exactly as in B2. This is
 * opt-in per consumer — the shared Dialog itself is not turned into a sheet.
 */
export const MOBILE_SHEET_CLASSES = cn(
  'max-lg:top-auto max-lg:bottom-0 max-lg:left-0 max-lg:mx-0 max-lg:translate-x-0 max-lg:translate-y-0',
  'max-lg:!w-full max-lg:!max-w-none max-lg:max-h-[88dvh]',
  'max-lg:rounded-b-none max-lg:rounded-t-2xl max-lg:border-x-0 max-lg:border-b-0',
  'max-lg:pb-[env(safe-area-inset-bottom)]',
  'max-lg:data-[state=open]:zoom-in-100 max-lg:data-[state=closed]:zoom-out-100',
  'max-lg:data-[state=open]:slide-in-from-bottom max-lg:data-[state=closed]:slide-out-to-bottom',
  // the body scrolls without dragging the page behind it
  'max-lg:[&_[data-slot=dialog-body]]:overscroll-contain'
)

/** Drag-handle affordance at the top of the sheet (hidden from lg up). */
export function SheetGrip({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn('mx-auto mt-2 mb-1 block h-1 w-9 flex-shrink-0 rounded-full bg-border lg:hidden', className)}
    />
  )
}
