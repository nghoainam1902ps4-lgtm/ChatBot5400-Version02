"use client"

import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import { useTranslation } from "@/lib/hooks/use-translation"

import { cn } from "@/lib/utils"

function Dialog({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

function DialogTrigger({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Portal>) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

function DialogOverlay({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:pointer-events-none fixed inset-0 z-50 bg-black/50",
        className
      )}
      {...props}
    />
  )
}

// B2 modal sizes — max-widths on ≥sm; below 640px every dialog is
// viewport - 32px (16px gutter each side). Height is capped at 88vh for all.
const DIALOG_SIZES = {
  sm: "sm:max-w-[420px]",
  md: "sm:max-w-[560px]",
  lg: "sm:max-w-[760px]",
  xl: "sm:max-w-[1040px]",
} as const

type DialogSize = keyof typeof DIALOG_SIZES

// Semantic header icon tones (use only when the icon carries meaning).
const DIALOG_ICON_TONES = {
  primary: "bg-fern-tint text-primary",
  danger: "bg-destructive-tint text-destructive",
  warn: "bg-gold-tint text-gold-deep",
  info: "bg-teal-tint text-teal-deep",
} as const

type DialogIconTone = keyof typeof DIALOG_ICON_TONES

const DialogContent = ({
  className,
  children,
  showCloseButton = true,
  size = "md",
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & {
  showCloseButton?: boolean
  size?: DialogSize
}) => {
  const { t } = useTranslation()
  return (
    <DialogPortal data-slot="dialog-portal">
      <DialogOverlay />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        className={cn(
          // Column shell: DialogHeader and DialogFooter stay put, DialogBody is
          // the only scrolling region. Padding lives on the parts, not here.
          "bg-card data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:pointer-events-none fixed top-[50%] left-[50%] z-50 flex flex-col w-full max-w-[calc(100%-2rem)] max-h-[88vh] translate-x-[-50%] translate-y-[-50%] mx-auto rounded-xl border shadow-overlay duration-200 overflow-hidden",
          DIALOG_SIZES[size],
          className
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <DialogPrimitive.Close className="absolute right-4 top-4 inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none">
            <X className="h-4 w-4" />
            <span className="sr-only">{t('common.close')}</span>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
}

function DialogHeader({
  className,
  children,
  icon,
  iconTone = "primary",
  ...props
}: React.ComponentProps<"div"> & {
  /** Optional semantic icon, shown in a tinted box left of the titles. */
  icon?: React.ReactNode
  iconTone?: DialogIconTone
}) {
  return (
    <div
      data-slot="dialog-header"
      className={cn(
        "flex-shrink-0 flex items-start gap-3 border-b border-border/70 py-4 pl-6 pr-14 text-left",
        className
      )}
      {...props}
    >
      {icon && (
        <span
          aria-hidden
          className={cn(
            "flex size-[34px] flex-shrink-0 items-center justify-center rounded-md [&_svg]:size-[17px]",
            DIALOG_ICON_TONES[iconTone]
          )}
        >
          {icon}
        </span>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1">{children}</div>
    </div>
  )
}

/** The single scrolling region between header and footer. */
function DialogBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-body"
      className={cn("min-h-0 flex-1 overflow-y-auto px-6 py-5", className)}
      {...props}
    />
  )
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "flex-shrink-0 flex flex-col-reverse gap-2 border-t border-border/70 px-6 py-3.5 sm:flex-row sm:items-center sm:justify-end",
        className
      )}
      {...props}
    />
  )
}

function DialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("font-display text-lg leading-6 font-semibold tracking-[-0.015em]", className)}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-muted-foreground text-sm", className)}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
  DIALOG_ICON_TONES,
}
export type { DialogSize, DialogIconTone }
