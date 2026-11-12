'use client'

import { useMemo } from 'react'
import { NotebookResponse } from '@/lib/types/api'
import { NotebookCard } from './NotebookCard'
import { NotebookRow } from './NotebookRow'
import { useNotebookViewStore } from '@/lib/stores/notebook-view-store'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { Book, FolderTree, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotebookHierarchyProps {
  notebooks?: NotebookResponse[]
  isLoading: boolean
  title: string
  onAction?: () => void
  actionLabel?: string
}

/**
 * Renders notebooks as a category → sub-notebook tree. Top-level notebooks
 * (no `parent`) are categories; notebooks whose `parent` points at one of them
 * are nested beneath it. Children whose parent isn't in the current set (e.g.
 * an archived or filtered-out category) fall back to a flat trailing group.
 */
export function NotebookHierarchy({
  notebooks,
  isLoading,
  title,
  onAction,
  actionLabel,
}: NotebookHierarchyProps) {
  const { t } = useTranslation()
  const viewMode = useNotebookViewStore((state) => state.viewMode)

  const { categories, childrenByParent, orphans } = useMemo(() => {
    const list = notebooks ?? []
    const ids = new Set(list.map((n) => n.id))
    const categories = list.filter((n) => !n.parent)
    const childrenByParent = new Map<string, NotebookResponse[]>()
    const orphans: NotebookResponse[] = []
    for (const nb of list) {
      if (!nb.parent) continue
      if (ids.has(nb.parent)) {
        const arr = childrenByParent.get(nb.parent) ?? []
        arr.push(nb)
        childrenByParent.set(nb.parent, arr)
      } else {
        orphans.push(nb)
      }
    }
    return { categories, childrenByParent, orphans }
  }, [notebooks])

  if (isLoading) {
    return viewMode === 'list' ? (
      <LoadingSkeleton variant="list" items={6} aria-label={t('common.loading')} />
    ) : (
      <LoadingSkeleton
        variant="card"
        items={6}
        aria-label={t('common.loading')}
        className="grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
      />
    )
  }

  if (!notebooks || notebooks.length === 0) {
    return (
      <EmptyState
        icon={Book}
        title={t('common.noResults')}
        description={t('chat.startByCreating')}
        action={
          onAction && actionLabel ? (
            <Button onClick={onAction} variant="outline" className="mt-4">
              <Plus className="mr-2 h-4 w-4" />
              {actionLabel}
            </Button>
          ) : undefined
        }
      />
    )
  }

  const renderItem = (nb: NotebookResponse) =>
    viewMode === 'list' ? (
      <NotebookRow key={nb.id} notebook={nb} />
    ) : (
      <NotebookCard key={nb.id} notebook={nb} />
    )

  const renderChildGrid = (children: NotebookResponse[]) =>
    viewMode === 'list' ? (
      <div className="flex flex-col gap-2">{children.map(renderItem)}</div>
    ) : (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {children.map(renderItem)}
      </div>
    )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="font-display text-lg font-semibold tracking-tight">{title}</h2>
        <span className="text-sm text-muted-foreground">({notebooks.length})</span>
      </div>

      <div className="space-y-5">
        {categories.map((category) => {
          const children = childrenByParent.get(category.id) ?? []
          return (
            <div key={category.id} className="space-y-2">
              {renderItem(category)}
              {children.length > 0 && (
                <div className="ml-3 space-y-2 border-l-2 border-border pl-3 sm:ml-5 sm:pl-5">
                  <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    <FolderTree className="h-3.5 w-3.5" />
                    {t('notebooks.subNotebooks')} ({children.length})
                  </p>
                  {renderChildGrid(children)}
                </div>
              )}
            </div>
          )
        })}

        {orphans.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('notebooks.otherNotebooks')} ({orphans.length})
            </p>
            {renderChildGrid(orphans)}
          </div>
        )}
      </div>
    </div>
  )
}
