'use client'

import { FileText, Lightbulb, StickyNote } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'

interface ContextIndicatorProps {
  sourcesInsights: number
  sourcesFull: number
  notesCount: number
  tokenCount?: number
  charCount?: number
  className?: string
  /** `bar` (default): the existing context summary. `chip`: M1 composer chip
   * ("n sources · m notes") followed by the token count. */
  variant?: 'bar' | 'chip'
}

// Helper function to format large numbers with K/M suffixes
function formatNumber(num: number): string {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}K`
  }
  return num.toString()
}

export function ContextIndicator({
  sourcesInsights,
  sourcesFull,
  notesCount,
  tokenCount,
  charCount,
  className,
  variant = 'bar'
}: ContextIndicatorProps) {
  const { t } = useTranslation()

  if (variant === 'chip') {
    return (
      <>
        <span
          className={cn(
            'inline-flex h-[26px] min-w-0 flex-shrink items-center gap-[5px] truncate rounded-full bg-muted/60 px-[9px] text-[11.5px] text-muted-foreground',
            className
          )}
        >
          <FileText className="size-3 flex-shrink-0" />
          <span className="truncate">
            {t('chat.contextChip', { sources: sourcesInsights + sourcesFull, notes: notesCount })}
          </span>
        </span>
        {tokenCount !== undefined && tokenCount > 0 && (
          <span className={cn('ml-auto flex-shrink-0 pl-1 font-mono text-xs text-muted-foreground', className)}>
            {formatNumber(tokenCount)}
          </span>
        )}
      </>
    )
  }

  const hasContext = (sourcesInsights + sourcesFull) > 0 || notesCount > 0

  if (!hasContext) {
    return (
      <div className={cn('flex-shrink-0 text-xs text-muted-foreground py-2 px-3 border-t', className)}>
        No sources or notes included in context. Toggle icons on cards to include them.
      </div>
    )
  }

  return (
    <div className={cn('flex-shrink-0 flex items-center justify-between gap-2 py-2 px-3 border-t bg-muted/30', className)}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Context:</span>

        <div className="flex items-center gap-1.5">
          {sourcesInsights > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-xs flex items-center gap-1 px-1.5 py-0.5 text-ctx-insights border-ctx-insights/50 cursor-default">
                  <Lightbulb className="h-3 w-3" />
                  <span>{sourcesInsights}</span>
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>Insights for {sourcesInsights} source{sourcesInsights !== 1 ? 's' : ''}</p>
              </TooltipContent>
            </Tooltip>
          )}

          {sourcesFull > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-xs flex items-center gap-1 px-1.5 py-0.5 text-ctx-full border-ctx-full/50 cursor-default">
                  <FileText className="h-3 w-3" />
                  <span>{sourcesFull}</span>
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>{sourcesFull} full source{sourcesFull !== 1 ? 's' : ''}</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        {notesCount > 0 && (
          <>
            {(sourcesInsights > 0 || sourcesFull > 0) && (
              <span className="text-muted-foreground">•</span>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-xs flex items-center gap-1 px-1.5 py-0.5 text-ctx-full border-ctx-full/50 cursor-default">
                  <StickyNote className="h-3 w-3" />
                  <span>{notesCount}</span>
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>{notesCount} full note{notesCount !== 1 ? 's' : ''}</p>
              </TooltipContent>
            </Tooltip>
          </>
        )}
      </div>

      {(tokenCount !== undefined || charCount !== undefined) && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {tokenCount !== undefined && tokenCount > 0 && (
            <span>{formatNumber(tokenCount)} tokens</span>
          )}
          {tokenCount !== undefined && charCount !== undefined && tokenCount > 0 && charCount > 0 && (
            <span>/</span>
          )}
          {charCount !== undefined && charCount > 0 && (
            <span>{formatNumber(charCount)} chars</span>
          )}
        </div>
      )}
    </div>
  )
}
