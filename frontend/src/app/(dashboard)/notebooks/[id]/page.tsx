'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { NotebookHeader } from '../components/NotebookHeader'
import { SourcesColumn } from '../components/SourcesColumn'
import { NotesColumn } from '../components/NotesColumn'
import { ChatColumn } from '../components/ChatColumn'
import { ContextPanel } from '@/components/notebooks/ContextPanel'
import { ContextIndicator } from '@/components/common/ContextIndicator'
import { useNotebook } from '@/lib/hooks/use-notebooks'
import { useNotebookSources } from '@/lib/hooks/use-sources'
import { useNotes } from '@/lib/hooks/use-notes'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useIsDesktop } from '@/lib/hooks/use-media-query'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  applyBulkSourceContext,
  applyBulkNoteContext,
  computeSourceSelections,
  computeNoteSelections,
  type SourceContextDefault,
  type SourceBulkAction,
  type NoteContextDefault,
} from '@/lib/utils/source-context'

// Re-exported from the shared types module for backward compatibility; several
// components historically import these from this route file.
import type { ContextMode, ContextSelections, NoteContextMode } from '@/lib/types/notebook-context'
export type { ContextMode, ContextSelections, NoteContextMode }

export default function NotebookPage() {
  const { t } = useTranslation()
  const params = useParams()

  // Ensure the notebook ID is properly decoded from URL
  const notebookId = params?.id ? decodeURIComponent(params.id as string) : ''

  const { data: notebook, isLoading: notebookLoading } = useNotebook(notebookId)
  const {
    sources,
    isLoading: sourcesLoading,
    refetch: refetchSources,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useNotebookSources(notebookId)
  const { data: notes, isLoading: notesLoading } = useNotes(notebookId)

  // Collapse state for the desktop context panel (design B: one panel, one flag)
  const { sourcesCollapsed } = useNotebookColumnsStore()

  // Detect desktop to avoid double-mounting ChatColumn
  const isDesktop = useIsDesktop()

  // Mobile tab state (Sources, Notes, or Chat)
  const [mobileActiveTab, setMobileActiveTab] = useState<'sources' | 'notes' | 'chat'>('chat')

  // Context selection state
  const [contextSelections, setContextSelections] = useState<ContextSelections>({
    sources: {},
    notes: {}
  })

  // The default context mode applied to sources as they load. A bulk
  // include/exclude updates this so sources loaded later via pagination follow
  // the same intent instead of reverting to "included" (#223/#915).
  const [sourceContextDefault, setSourceContextDefault] = useState<SourceContextDefault>('include')

  // Same idea for notes loaded later (notes are binary: included/off).
  const [noteContextDefault, setNoteContextDefault] = useState<NoteContextDefault>('include')

  // Initialize and update selections when sources load or change
  useEffect(() => {
    if (sources && sources.length > 0) {
      setContextSelections(prev => ({
        ...prev,
        sources: computeSourceSelections(prev.sources, sources, sourceContextDefault),
      }))
    }
  }, [sources, sourceContextDefault])

  useEffect(() => {
    if (notes && notes.length > 0) {
      setContextSelections(prev => ({
        ...prev,
        notes: computeNoteSelections(prev.notes, notes, noteContextDefault),
      }))
    }
  }, [notes, noteContextDefault])

  const handleSourceContextModeChange = (sourceId: string, mode: ContextMode) => {
    setContextSelections(prev => ({
      ...prev,
      sources: {
        ...prev.sources,
        [sourceId]: mode
      }
    }))
  }

  const handleNoteContextModeChange = (noteId: string, mode: NoteContextMode) => {
    setContextSelections(prev => ({
      ...prev,
      notes: {
        ...prev.notes,
        [noteId]: mode
      }
    }))
  }

  // Bulk-apply a context action (insights-only / full / exclude) to every
  // source at once (#223). Also records the action as the default for sources
  // loaded later (#915).
  const handleBulkSourceContext = (action: SourceBulkAction) => {
    setSourceContextDefault(action)
    setContextSelections(prev => ({
      ...prev,
      sources: applyBulkSourceContext(prev.sources, sources ?? [], action),
    }))
  }

  // Bulk include/exclude every note from the chat context at once (#223).
  const handleBulkNoteContext = (action: NoteContextDefault) => {
    setNoteContextDefault(action)
    setContextSelections(prev => ({
      ...prev,
      notes: applyBulkNoteContext(prev.notes, notes ?? [], action),
    }))
  }

  if (notebookLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!notebook) {
    return (
      <AppShell>
        <div className="p-6">
          <h1 className="text-2xl font-bold mb-4">{t('notebooks.notFound')}</h1>
          <p className="text-muted-foreground">{t('notebooks.notFoundDesc')}</p>
        </div>
      </AppShell>
    )
  }

  const mobileTabClass =
    'h-[46px] gap-1.5 whitespace-nowrap border-b-0 px-1 text-[13.5px] font-medium text-muted-foreground shadow-[inset_0_-2px_0_transparent] data-[state=active]:font-semibold data-[state=active]:text-foreground data-[state=active]:shadow-[inset_0_-2px_0_var(--primary)] sm:text-[14.5px]'
  const mobileTabCount = 'font-mono text-[11px] tabular-nums text-muted-foreground group-data-[state=active]:text-primary'

  return (
    <AppShell hideMobileTopBar>
      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex-shrink-0 lg:p-0">
          <NotebookHeader notebook={notebook} />
        </div>

        <div className="flex-1 flex flex-col min-h-0 overflow-hidden lg:p-0 lg:overflow-hidden">
          {/* Mobile: Tabbed interface - only render on mobile to avoid double-mounting */}
          {!isDesktop && (
            <>
              {/* M1: three equal tabs, no icons, counts, burgundy underline */}
              <div className="flex-shrink-0 border-b bg-card sm:px-11 lg:hidden">
                <Tabs value={mobileActiveTab} onValueChange={(value) => setMobileActiveTab(value as 'sources' | 'notes' | 'chat')} className="gap-0">
                  <TabsList className="grid w-full grid-cols-3 gap-0 border-b-0">
                    <TabsTrigger value="sources" className={`group ${mobileTabClass}`}>
                      {t('navigation.sources')}
                      <span className={mobileTabCount}>{sources?.length ?? 0}</span>
                    </TabsTrigger>
                    <TabsTrigger value="notes" className={`group ${mobileTabClass}`}>
                      {t('common.notes')}
                      <span className={mobileTabCount}>{notes?.length ?? 0}</span>
                    </TabsTrigger>
                    <TabsTrigger value="chat" className={mobileTabClass}>
                      {t('common.chat')}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              {/* Mobile: Show only active tab */}
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:hidden">
                {mobileActiveTab === 'sources' && (
                  <SourcesColumn
                    mobile
                    sources={sources}
                    isLoading={sourcesLoading}
                    notebookId={notebookId}
                    notebookName={notebook?.name}
                    onRefresh={refetchSources}
                    contextSelections={contextSelections.sources}
                    onContextModeChange={handleSourceContextModeChange}
                    onBulkContextModeChange={handleBulkSourceContext}
                    hasNextPage={hasNextPage}
                    isFetchingNextPage={isFetchingNextPage}
                    fetchNextPage={fetchNextPage}
                  />
                )}
                {mobileActiveTab === 'notes' && (
                  <NotesColumn
                    mobile
                    notes={notes}
                    isLoading={notesLoading}
                    notebookId={notebookId}
                    contextSelections={contextSelections.notes}
                    onContextModeChange={handleNoteContextModeChange}
                    onBulkContextModeChange={handleBulkNoteContext}
                  />
                )}
                {mobileActiveTab === 'chat' && (
                  <ChatColumn
                    sessionInMobileTopBar
                    notebookId={notebookId}
                    contextSelections={contextSelections}
                    sources={sources}
                    sourcesLoading={sourcesLoading}
                  />
                )}
              </div>
            </>
          )}

          {/* Desktop (design B): context panel (Sources / Notes tabs) + chat */}
          <div className="hidden lg:flex h-full min-h-0 flex-row">
            <div className={cn(
              'flex-shrink-0 min-h-0 transition-all duration-150',
              sourcesCollapsed ? 'w-[60px] border-r p-1.5' : 'w-[340px]'
            )}>
              <ContextPanel
                sourcesCount={sources?.length ?? 0}
                notesCount={notes?.length ?? 0}
                sources={
                  <SourcesColumn
                    embedded
                    sources={sources}
                    isLoading={sourcesLoading}
                    notebookId={notebookId}
                    notebookName={notebook?.name}
                    onRefresh={refetchSources}
                    contextSelections={contextSelections.sources}
                    onContextModeChange={handleSourceContextModeChange}
                    onBulkContextModeChange={handleBulkSourceContext}
                    hasNextPage={hasNextPage}
                    isFetchingNextPage={isFetchingNextPage}
                    fetchNextPage={fetchNextPage}
                  />
                }
                notes={
                  <NotesColumn
                    embedded
                    notes={notes}
                    isLoading={notesLoading}
                    notebookId={notebookId}
                    contextSelections={contextSelections.notes}
                    onContextModeChange={handleNoteContextModeChange}
                    onBulkContextModeChange={handleBulkNoteContext}
                  />
                }
                footer={
                  <ContextIndicator
                    sourcesInsights={(sources ?? []).filter(source => contextSelections.sources[source.id] === 'insights').length}
                    sourcesFull={(sources ?? []).filter(source => contextSelections.sources[source.id] === 'full').length}
                    notesCount={(notes ?? []).filter(note => contextSelections.notes[note.id] === 'full').length}
                  />
                }
              />
            </div>

            {/* Chat - takes remaining space */}
            <div className="flex-1 min-w-0 min-h-0">
              <ChatColumn
                notebookId={notebookId}
                contextSelections={contextSelections}
                sources={sources}
                sourcesLoading={sourcesLoading}
              />
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
