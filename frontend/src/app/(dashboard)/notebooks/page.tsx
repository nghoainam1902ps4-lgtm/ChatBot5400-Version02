'use client'

import { useMemo, useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import { NotebookList } from './components/NotebookList'
import { RecentlyViewed } from './components/RecentlyViewed'
import { Button } from '@/components/ui/button'
import { Plus, RefreshCw, LayoutGrid, List, SearchX } from 'lucide-react'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { CreateNotebookDialog } from '@/components/notebooks/CreateNotebookDialog'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { Toolbar } from '@/components/common/Toolbar'
import { SearchInput } from '@/components/common/SearchInput'
import { PrimaryAction } from '@/components/common/PrimaryAction'
import { ErrorState } from '@/components/common/ErrorState'
import { EmptyState } from '@/components/common/EmptyState'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebookViewStore } from '@/lib/stores/notebook-view-store'
import { useAuth } from '@/lib/hooks/use-auth'
import type { NotebookResponse } from '@/lib/types/api'

// Client-side match on name or description (case-insensitive, no folding).
function filterNotebooks(notebooks: NotebookResponse[] | undefined, query: string) {
  if (!notebooks || !query) return notebooks
  return notebooks.filter(
    (notebook) =>
      notebook.name.toLowerCase().includes(query) ||
      (notebook.description ?? '').toLowerCase().includes(query)
  )
}

export default function NotebooksPage() {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const viewMode = useNotebookViewStore((state) => state.viewMode)
  const setViewMode = useNotebookViewStore((state) => state.setViewMode)
  const { data: notebooks, isLoading, isError, refetch } = useNotebooks(false)
  const { data: archivedNotebooks } = useNotebooks(true)

  const normalizedQuery = searchTerm.trim().toLowerCase()

  const filteredActive = useMemo(
    () => filterNotebooks(notebooks, normalizedQuery),
    [notebooks, normalizedQuery]
  )

  const filteredArchived = useMemo(
    () => filterNotebooks(archivedNotebooks, normalizedQuery),
    [archivedNotebooks, normalizedQuery]
  )

  const hasArchived = (archivedNotebooks?.length ?? 0) > 0
  const isSearching = normalizedQuery.length > 0
  const activeMatches = filteredActive?.length ?? 0
  const archivedMatches = filteredArchived?.length ?? 0
  const noSearchResult = isSearching && !isLoading && activeMatches + archivedMatches === 0

  const renderLists = () => {
    if (isError) {
      return (
        <ErrorState
          title={t('notebooks.loadErrorTitle')}
          description={t('notebooks.loadErrorDesc')}
          onRetry={() => void refetch()}
        />
      )
    }

    // One page-level "no result" for the whole search (never a create CTA).
    if (noSearchResult) {
      return (
        <div role="status">
          <EmptyState
            variant="search"
            icon={SearchX}
            title={t('notebooks.noSearchResultTitle')}
            description={t('notebooks.noSearchResultDesc')}
          />
        </div>
      )
    }

    // While searching, only the groups that matched are shown.
    return (
      <>
        {(!isSearching || isLoading || activeMatches > 0) && (
          <NotebookList
            notebooks={filteredActive}
            isLoading={isLoading}
            title={t('notebooks.activeNotebooks')}
            onAction={!isSearching && isAdmin ? () => setCreateDialogOpen(true) : undefined}
            actionLabel={!isSearching && isAdmin ? t('notebooks.newNotebook') : undefined}
          />
        )}

        {hasArchived && (!isSearching || archivedMatches > 0) && (
          <NotebookList
            notebooks={filteredArchived}
            isLoading={false}
            title={t('notebooks.archivedNotebooks')}
            collapsible
          />
        )}
      </>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="wide">
          <PageHeader title={t('notebooks.title')} />

          <Toolbar>
            <SearchInput
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder={t('notebooks.searchPlaceholder')}
              ariaLabel={t('notebooks.searchPlaceholder')}
              clearLabel={t('common.clearSearch')}
              className="flex-1 basis-60 sm:max-w-sm"
            />
            <PrimaryAction
              icon={RefreshCw}
              variant="outline"
              onClick={() => void refetch()}
              aria-label={t('common.refresh')}
              title={t('common.refresh')}
            />
            <div className="flex items-center rounded-md border p-0.5">
              <Button
                variant={viewMode === 'tile' ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => setViewMode('tile')}
                aria-label={t('notebooks.tileView')}
                aria-pressed={viewMode === 'tile'}
                title={t('notebooks.tileView')}
                className="size-10 sm:size-9 lg:size-8"
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
              <Button
                variant={viewMode === 'list' ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => setViewMode('list')}
                aria-label={t('notebooks.listView')}
                aria-pressed={viewMode === 'list'}
                title={t('notebooks.listView')}
                className="size-10 sm:size-9 lg:size-8"
              >
                <List className="h-4 w-4" />
              </Button>
            </div>
            {isAdmin && (
              <PrimaryAction icon={Plus} onClick={() => setCreateDialogOpen(true)} className="sm:ml-auto">
                {t('notebooks.newNotebook')}
              </PrimaryAction>
            )}
          </Toolbar>

          <div className="space-y-8">
            <RecentlyViewed />
            {renderLists()}
          </div>
        </PageShell>
      </div>

      <CreateNotebookDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />
    </AppShell>
  )
}
