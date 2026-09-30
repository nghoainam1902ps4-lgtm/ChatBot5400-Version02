"use client"

import { useThemeStore } from "@/lib/stores/theme-store"
import { Toaster as Sonner, ToasterProps } from "sonner"

// Semantic toast palette: every variant sits on the popover surface with a
// hairline border tinted by its hue; only the icon and the title carry the
// semantic color (richColors reads these per-type vars). The description stays
// neutral ink via `classNames.description`.
const tintedBorder = (hue: string) => `color-mix(in oklab, var(${hue}) 35%, var(--border))`

// Bottom offset, shared by every breakpoint: the larger of the edge margin
// (+ bottom safe area) and the M1/desktop composer height published by
// ChatPanel as --composer-h (it already includes the composer's own safe-area
// padding, so the two are never added together), plus the software keyboard
// height below lg (--vvh/--vv-top from useVisualViewportVars; 0 elsewhere).
const TOAST_BOTTOM =
  'calc(max(var(--toast-edge) + env(safe-area-inset-bottom), var(--composer-h, 0px) + 12px) + var(--toast-kb))'

const Toaster = ({ ...props }: ToasterProps) => {
  const theme = useThemeStore((state) => state.theme)
  const systemTheme = useThemeStore((state) => state.getSystemTheme())
  const effectiveTheme = theme === 'system' ? systemTheme : theme

  return (
    <Sonner
      theme={effectiveTheme as ToasterProps["theme"]}
      richColors
      closeButton
      // Desktop: bottom-right, 24px. Tablet/mobile: right-aligned, 16px
      // (Sonner switches to full width at <=600px via mobileOffset).
      position="bottom-right"
      duration={5000}
      offset={{ right: 'var(--toast-edge)', bottom: TOAST_BOTTOM }}
      mobileOffset={{ bottom: TOAST_BOTTOM }}
      className="toaster group [--toast-edge:16px] lg:[--toast-edge:24px]"
      toastOptions={{
        classNames: {
          description: "text-muted-foreground!",
          // Warn hue on the icon; the title uses --warn-deep (see --warning-text).
          warning: "[&_[data-icon]]:text-warn",
          // 20px visual, ~44px hit area on touch screens.
          closeButton: "before:absolute before:-inset-3 before:content-['']",
          actionButton: "pointer-coarse:h-9! pointer-coarse:px-3!",
        },
      }}
      style={
        {
          "--toast-kb": "max(0px, calc(100dvh - var(--vv-top, 0px) - var(--vvh, 100dvh)))",
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--success-bg": "var(--popover)",
          "--success-text": "var(--success)",
          "--success-border": tintedBorder("--success"),
          "--error-bg": "var(--popover)",
          "--error-text": "var(--destructive)",
          "--error-border": tintedBorder("--destructive"),
          // Title text uses --warn-deep: light --warn on the popover is 4.44:1,
          // below AA for 13px text; the icon keeps --warn (UI contrast).
          "--warning-bg": "var(--popover)",
          "--warning-text": "var(--warn-deep)",
          "--warning-border": tintedBorder("--warn"),
          "--info-bg": "var(--popover)",
          "--info-text": "var(--teal)",
          "--info-border": tintedBorder("--teal"),
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
