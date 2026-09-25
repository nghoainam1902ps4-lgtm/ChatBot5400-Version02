"use client"

import { useThemeStore } from "@/lib/stores/theme-store"
import { Toaster as Sonner, ToasterProps } from "sonner"

const Toaster = ({ ...props }: ToasterProps) => {
  const theme = useThemeStore((state) => state.theme)
  const systemTheme = useThemeStore((state) => state.getSystemTheme())
  const effectiveTheme = theme === 'system' ? systemTheme : theme

  return (
    <Sonner
      theme={effectiveTheme as ToasterProps["theme"]}
      richColors
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          // Success/status toasts use the Agribank bordeaux with high-contrast
          // white text (richColors makes Sonner read these per-type vars).
          "--success-bg": "#8B1538",
          "--success-text": "#ffffff",
          "--success-border": "#6f1029",
          // Info toasts (e.g. update available) share the same Agribank look.
          "--info-bg": "#8B1538",
          "--info-text": "#ffffff",
          "--info-border": "#6f1029",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
