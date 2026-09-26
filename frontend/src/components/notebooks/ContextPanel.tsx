'use client'

import { ReactNode, useMemo, useState } from 'react'
import { Layers } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CollapsibleColumn, createCollapseButton } from '@/components/notebooks/CollapsibleColumn'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useTranslation } from '@/lib/hooks/use-translation'

interface ContextPanelProps {
  sourcesCount: number
  notesCount: number
  /** Tab bodies — the existing SourcesColumn / NotesColumn rendered `embedded`. */
  sources: ReactNode
  notes: ReactNode
  footer?: ReactNode
}

/**
 * Desktop context panel (design B): one 340px panel with Sources / Notes tabs
 * instead of two side-by-side columns. Presentation only — the tab bodies own
 * all data, dialogs and context-selection callbacks. Collapse reuses the
 * existing `sourcesCollapsed` flag of the notebook-columns store.
 */
export function ContextPanel({ sourcesCount, notesCount, sources, notes, footer }: ContextPanelProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<'sources' | 'notes'>('sources')
  const { sourcesCollapsed, toggleSources } = useNotebookColumnsStore()
  const panelLabel = t('notebooks.contextPanel')
  const collapseButton = useMemo(
    () => createCollapseButton(toggleSources, panelLabel),
    [toggleSources, panelLabel]
  )

  return (
    <CollapsibleColumn
      isCollapsed={sourcesCollapsed}
      onToggle={toggleSources}
      collapsedIcon={Layers}
      collapsedLabel={panelLabel}
    >
      <aside
        aria-label={panelLabel}
        className="flex h-full min-h-0 flex-col border-r bg-sidebar/40"
      >
        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as 'sources' | 'notes')}
          className="flex min-h-0 flex-1 flex-col gap-0"
        >
          <div className="flex flex-shrink-0 items-center gap-2 px-3 pt-3">
            <TabsList className="grid flex-1 grid-cols-2">
              <TabsTrigger value="sources" className="gap-1.5">
                {t('navigation.sources')}
                <span className="text-xs tabular-nums text-muted-foreground">{sourcesCount}</span>
              </TabsTrigger>
              <TabsTrigger value="notes" className="gap-1.5">
                {t('common.notes')}
                <span className="text-xs tabular-nums text-muted-foreground">{notesCount}</span>
              </TabsTrigger>
            </TabsList>
            {collapseButton}
          </div>
          {/* forceMount keeps each list's scroll position, pagination listener
              and open dialogs alive while the other tab is shown. */}
          <TabsContent value="sources" forceMount className="min-h-0 data-[state=inactive]:hidden">
            {sources}
          </TabsContent>
          <TabsContent value="notes" forceMount className="min-h-0 data-[state=inactive]:hidden">
            {notes}
          </TabsContent>
        </Tabs>
        {footer}
      </aside>
    </CollapsibleColumn>
  )
}
