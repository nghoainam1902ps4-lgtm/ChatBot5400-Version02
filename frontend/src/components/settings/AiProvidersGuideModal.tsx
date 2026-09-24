'use client'

import { useEffect, useState } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import { useTranslation } from '@/lib/hooks/use-translation'

interface AiProvidersGuideModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// The translated guide lives as a static Markdown asset under /public so it can
// be updated without a rebuild and rendered by the existing MarkdownRenderer.
const GUIDE_URL = '/docs/ai-providers.vi.md'

// Agribank bordeaux for headings and links inside the guide.
const BORDEAUX = '#8B1538'

// Render headings and links in the guide with the Agribank bordeaux, and open
// external provider links (openai.com, etc.) in a new tab.
const guideComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="mb-4 mt-6 text-2xl font-bold" style={{ color: BORDEAUX }}>
      {children}
    </h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="mb-3 mt-6 text-xl font-semibold" style={{ color: BORDEAUX }}>
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mb-2 mt-4 text-lg font-semibold" style={{ color: BORDEAUX }}>
      {children}
    </h3>
  ),
  a: ({ children, href }: { children?: React.ReactNode; href?: string }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium underline underline-offset-2 hover:opacity-80"
      style={{ color: BORDEAUX }}
    >
      {children}
    </a>
  ),
}

export function AiProvidersGuideModal({
  open,
  onOpenChange,
}: AiProvidersGuideModalProps) {
  const { t } = useTranslation()
  const [content, setContent] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')

  // Fetch the guide the first time the modal is opened; cache it afterwards.
  // Use an AbortController (not a `cancelled` flag) so React 18 Strict Mode's
  // double-invoke in dev works: the first run's cleanup aborts its fetch, and
  // the second run — content still null — issues a fresh one that resolves.
  // (A `cancelled` flag would discard the resolved response and leave the modal
  // stuck on the loading spinner.)
  useEffect(() => {
    if (!open || content !== null) return
    const controller = new AbortController()
    setStatus('loading')
    fetch(GUIDE_URL, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.text()
      })
      .then((text) => {
        setContent(text)
        setStatus('idle')
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setStatus('error')
      })
    return () => controller.abort()
  }, [open, content])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[92vw] max-w-4xl sm:max-w-4xl h-[85vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="shrink-0 border-b border-border px-6 py-4 pr-12">
          <DialogTitle style={{ color: BORDEAUX }}>
            {t('apiKeys.guideTitle')}
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5">
          {status === 'loading' && (
            <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>{t('common.loading')}</span>
            </div>
          )}
          {status === 'error' && (
            <div className="flex items-center justify-center gap-2 py-12 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <span>{t('apiKeys.guideError')}</span>
            </div>
          )}
          {content !== null && status !== 'error' && (
            <MarkdownRenderer components={guideComponents}>
              {content}
            </MarkdownRenderer>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
