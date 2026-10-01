'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useDebounce } from 'use-debounce'
import { sourcesApi, type SourceSortField } from '@/lib/api/sources'
import { SourceListResponse } from '@/lib/types/api'
import { EmptyState } from '@/components/common/EmptyState'
import { AppShell } from '@/components/layout/AppShell'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { Toolbar } from '@/components/common/Toolbar'
import { PrimaryAction } from '@/components/common/PrimaryAction'
import {
  DataTable,
  DataTableBody,
  DataTableCell,
  DataTableHead,
  DataTableHeader,
  DataTableRow,
} from '@/components/common/DataTable'
import { DataList, DataListItem } from '@/components/common/DataList'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { InfiniteIndicator } from '@/components/common/Pagination'
import { FileText, Trash2, ArrowDown, ArrowUp, ArrowUpDown, Plus, MoreHorizontal, SearchX } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getDateLocale } from '@/lib/utils/date-locale'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { getApiErrorKey } from '@/lib/utils/error-handler'
import { AddSourceDialog } from '@/components/sources/AddSourceDialog'
import { SourceSearchInput } from '@/components/sources/SourceSearchInput'
import { useAuth } from '@/lib/hooks/use-auth'

export default function SourcesPage() {
  const { t, language } = useTranslation()
  const { isAdmin } = useAuth()
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const failedToLoadMessage = t('sources.failedToLoad')
  const [sources, setSources] = useState<SourceListResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [sortBy, setSortBy] = useState<SourceSortField>('updated')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  // Server-side title/file-name search. Typing is debounced; clearing applies
  // immediately. Local UI state only (not persisted).
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery] = useDebounce(searchQuery.trim(), 300)
  const activeQuery = searchQuery.trim() ? debouncedQuery : ''
  // The query the currently shown `sources` were fetched with
  const [loadedQuery, setLoadedQuery] = useState('')
  const [deleteDialog, setDeleteDialog] = useState<{ open: boolean; source: SourceListResponse | null }>({
    open: false,
    source: null
  })
  const router = useRouter()
  const tableRef = useRef<HTMLTableElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const offsetRef = useRef(0)
  const loadingMoreRef = useRef(false)
  const hasMoreRef = useRef(true)
  // Identifies the current result set; a response for an older one (superseded
  // sort/search) is dropped instead of overwriting or appending.
  const requestIdRef = useRef(0)
  const abortRef = useRef<AbortController | null>(null)
  const PAGE_SIZE = 30

  const fetchSources = useCallback(async (reset = false) => {
    // Check flags before proceeding
    if (!reset && (loadingMoreRef.current || !hasMoreRef.current)) {
      return
    }
    if (reset) {
      requestIdRef.current += 1
      abortRef.current?.abort()
      abortRef.current = new AbortController()
    }
    const requestId = requestIdRef.current
    const signal = abortRef.current?.signal

    try {
      if (reset) {
        setLoading(true)
        setError(null)
        offsetRef.current = 0
        setSources([])
        hasMoreRef.current = true
      } else {
        loadingMoreRef.current = true
        setLoadingMore(true)
      }

      const data = await sourcesApi.list({
        limit: PAGE_SIZE,
        offset: offsetRef.current,
        sort_by: sortBy,
        sort_order: sortOrder,
        ...(activeQuery ? { q: activeQuery } : {}),
      }, { signal })
      if (requestId !== requestIdRef.current) return

      if (reset) {
        setSources(data)
      } else {
        setSources(prev => [...prev, ...data])
      }

      // Check if we have more data
      const hasMoreData = data.length === PAGE_SIZE
      hasMoreRef.current = hasMoreData
      offsetRef.current += data.length
      setLoadedQuery(activeQuery)
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      console.error('Failed to fetch sources:', err)
      setError(failedToLoadMessage)
      toast.error(failedToLoadMessage)
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
        setLoadingMore(false)
        loadingMoreRef.current = false
      }
    }
  }, [sortBy, sortOrder, activeQuery, failedToLoadMessage])

  // Initial load and when sort or search changes (back to page 1)
  useEffect(() => {
    setSelectedIndex(0)
    fetchSources(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortBy, sortOrder, activeQuery])

  // Abort an in-flight request on unmount
  useEffect(() => () => abortRef.current?.abort(), [])

  useEffect(() => {
    // Focus the table when component mounts or sources change — unless the
    // user is typing somewhere (e.g. the search box).
    const active = document.activeElement
    if (sources.length > 0 && tableRef.current && (!active || active === document.body)) {
      tableRef.current.focus()
    }
  }, [sources])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (sources.length === 0) return
      // Leave arrow/Home/End/Enter to text fields (search box)
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
      // ...and to the row action menu / delete dialog (Radix handles its own keys)
      if (e.defaultPrevented || target?.closest?.('[role="menu"], [role="dialog"], [role="alertdialog"]')) return

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex((prev) => {
            const newIndex = Math.min(prev + 1, sources.length - 1)
            // Scroll to keep selected row visible
            setTimeout(() => scrollToSelectedRow(newIndex), 0)
            return newIndex
          })
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex((prev) => {
            const newIndex = Math.max(prev - 1, 0)
            // Scroll to keep selected row visible
            setTimeout(() => scrollToSelectedRow(newIndex), 0)
            return newIndex
          })
          break
        case 'Enter':
          e.preventDefault()
          if (sources[selectedIndex]) {
            router.push(`/sources/${sources[selectedIndex].id}`)
          }
          break
        case 'Home':
          e.preventDefault()
          setSelectedIndex(0)
          setTimeout(() => scrollToSelectedRow(0), 0)
          break
        case 'End':
          e.preventDefault()
          const lastIndex = sources.length - 1
          setSelectedIndex(lastIndex)
          setTimeout(() => scrollToSelectedRow(lastIndex), 0)
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [sources, selectedIndex, router])

  const scrollToSelectedRow = (index: number) => {
    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    // Find the selected row element
    const rows = scrollContainer.querySelectorAll('tbody tr')
    const selectedRow = rows[index] as HTMLElement
    if (!selectedRow) return

    const containerRect = scrollContainer.getBoundingClientRect()
    const rowRect = selectedRow.getBoundingClientRect()

    // Check if row is above visible area
    if (rowRect.top < containerRect.top) {
      selectedRow.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
    // Check if row is below visible area
    else if (rowRect.bottom > containerRect.bottom) {
      selectedRow.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }

  // Set up scroll listener after sources are loaded
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    let scrollTimeout: NodeJS.Timeout | null = null

    const handleScroll = () => {
      if (scrollTimeout) {
        clearTimeout(scrollTimeout)
      }

      scrollTimeout = setTimeout(() => {
        if (!scrollContainerRef.current) return

        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight

        // Load more when within 200px of the bottom
        if (distanceFromBottom < 200 && !loadingMoreRef.current && hasMoreRef.current) {
          fetchSources(false)
        }
      }, 100)
    }

    scrollContainer.addEventListener('scroll', handleScroll)
    handleScroll() // Check on mount

    return () => {
      scrollContainer.removeEventListener('scroll', handleScroll)
      if (scrollTimeout) {
        clearTimeout(scrollTimeout)
      }
    }
  }, [fetchSources, sources.length])

  const toggleSort = (field: SourceSortField) => {
    setSelectedIndex(0)
    if (sortBy === field) {
      // Toggle order if clicking the same field
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      // Switch to new field with default desc order
      setSortBy(field)
      setSortOrder('desc')
    }
  }

  const renderSortableHeader = (
    field: SourceSortField,
    label: string,
    align: 'left' | 'center' = 'left'
  ) => {
    const active = sortBy === field
    const SortIcon = active ? (sortOrder === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown

    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={() => toggleSort(field)}
        className={cn(
          "h-8 px-2 hover:bg-muted",
          // Narrow trailing columns: the label may wrap to two lines inside
          // the 48px header instead of spilling over the next column.
          align === 'center' && "mx-auto h-auto min-h-8 max-w-full whitespace-normal px-1 py-1 leading-tight"
        )}
      >
        {label}
        <SortIcon className={cn(
          "h-3 w-3",
          active ? 'opacity-100' : 'opacity-30'
        )} />
      </Button>
    )
  }

  // Content-type pebble — type hues live in dots, never washes
  const getSourceTypeDotClass = (source: SourceListResponse) => {
    if (source.asset?.url) return 'bg-type-web'
    if (source.asset?.file_path) return 'bg-type-pdf'
    return 'bg-type-note'
  }

  const getSourceType = (source: SourceListResponse) => {
    if (source.asset?.url) return t('sources.type.link')
    if (source.asset?.file_path) return t('sources.type.file')
    return t('sources.type.text')
  }

  const handleRowClick = useCallback((index: number, sourceId: string) => {
    setSelectedIndex(index)
    router.push(`/sources/${sourceId}`)
  }, [router])

  // Row actions (admin): delete lives in a "..." menu instead of a permanent
  // red trash button. Clicks inside never reach the row (no navigation).
  const renderRowActions = (source: SourceListResponse) => {
    if (!isAdmin) return null
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('common.actions')}
            onClick={(e) => e.stopPropagation()}
            className="relative size-11 sm:size-8"
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => setDeleteDialog({ open: true, source })}
          >
            <Trash2 className="h-4 w-4" />
            {t('common.delete')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }

  const formatRelative = (value: string) =>
    formatDistanceToNow(new Date(value), {
      addSuffix: true,
      locale: getDateLocale(language),
    })

  const handleDeleteConfirm = async () => {
    if (!deleteDialog.source) return

    try {
      await sourcesApi.delete(deleteDialog.source.id)
      toast.success(t('sources.deleteSuccess'))
      // Remove the deleted source from the list
      setSources(prev => prev.filter(s => s.id !== deleteDialog.source?.id))
      setDeleteDialog({ open: false, source: null })
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }, message?: string };
      console.error('Failed to delete source:', error)
      toast.error(t(getApiErrorKey(error.response?.data?.detail || error.message)))
    }
  }

  const renderContent = () => {
    const isSearching = searchQuery.trim() !== ''

    // Initial load / reload (sort, search, retry): geometry-preserving
    // skeleton — a table from 640px, a list below.
    if (loading) {
      return (
        <div className="min-h-0 flex-1 overflow-hidden rounded-md border">
          <LoadingSkeleton
            variant="table"
            rows={8}
            columns={7}
            aria-label={t('common.loading')}
            className="hidden sm:block"
          />
          <LoadingSkeleton
            variant="list"
            items={8}
            aria-label={t('common.loading')}
            className="px-3 sm:hidden"
          />
        </div>
      )
    }

    if (error) {
      return (
        <div className="rounded-md border">
          <ErrorState title={error} onRetry={() => fetchSources(true)} />
        </div>
      )
    }

    if (sources.length === 0) {
      // "No sources yet" only when an unfiltered fetch came back empty — never
      // for an empty search result (or the frame right after clearing one).
      if (!isSearching && loadedQuery === '') {
        return (
          <EmptyState
            icon={FileText}
            title={t('sources.noSourcesYet')}
            description={t('sources.allSourcesDescShort')}
            action={
              isAdmin ? (
                <Button onClick={() => setSourceDialogOpen(true)} variant="outline" className="mt-4">
                  <Plus className="h-4 w-4 mr-2" />
                  {t('sources.newSource')}
                </Button>
              ) : undefined
            }
          />
        )
      }
      return (
        <div role="status" className="rounded-md border">
          <EmptyState
            variant="search"
            icon={SearchX}
            title={t('sources.noMatchingSources')}
            description={t('sources.noMatchingSourcesDesc')}
          />
        </div>
      )
    }

    // One scroll container (infinite scroll + keyboard scrollIntoView) holding
    // the table (>=640px) and the equivalent list (<640px).
    return (
      <div ref={scrollContainerRef} className="min-h-0 flex-1 overflow-auto rounded-md border">
        <DataTable
          ref={tableRef}
          tabIndex={0}
          className="group/table hidden min-w-[920px] table-fixed outline-none sm:table"
        >
          <colgroup>
            <col className="w-[120px]" />
            <col className="w-auto" />
            <col className="w-[140px]" />
            <col className="w-[140px]" />
            <col className="w-[136px]" />
            <col className="w-[120px]" />
            <col className="w-[64px]" />
          </colgroup>
          <DataTableHeader className="sticky top-0 z-10 bg-background">
            <tr className="border-b">
              <DataTableHead className="px-2">
                {renderSortableHeader('type', t('common.type'))}
              </DataTableHead>
              <DataTableHead className="px-2">
                {renderSortableHeader('title', t('common.title'))}
              </DataTableHead>
              <DataTableHead className="px-2">
                {renderSortableHeader('created', t('common.created_label'))}
              </DataTableHead>
              <DataTableHead className="px-2">
                {renderSortableHeader('updated', t('common.updated_label'))}
              </DataTableHead>
              <DataTableHead className="px-2 text-center">
                {renderSortableHeader('insights_count', t('sources.insights'), 'center')}
              </DataTableHead>
              <DataTableHead className="px-2 text-center">
                {renderSortableHeader('embedded', t('sources.embedded'), 'center')}
              </DataTableHead>
              <DataTableHead className="px-2 text-right">
                {t('common.actions')}
              </DataTableHead>
            </tr>
          </DataTableHeader>
          <DataTableBody>
            {sources.map((source, index) => (
              <DataTableRow
                key={source.id}
                selected={selectedIndex === index}
                onClick={() => handleRowClick(index, source.id)}
                className="cursor-pointer group-focus-visible/table:data-[selected=true]:outline-2 group-focus-visible/table:data-[selected=true]:-outline-offset-2 group-focus-visible/table:data-[selected=true]:outline-ring"
              >
                <DataTableCell>
                  <div className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className={cn('h-2 w-2 shrink-0 rounded-full', getSourceTypeDotClass(source))}
                    />
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {getSourceType(source)}
                    </span>
                  </div>
                </DataTableCell>
                <DataTableCell>
                  <div className="flex flex-col overflow-hidden">
                    <span className="font-medium truncate">
                      {source.title || t('sources.untitledSource')}
                    </span>
                    {source.asset?.url && (
                      <span className="text-xs text-muted-foreground truncate">
                        {source.asset.url}
                      </span>
                    )}
                  </div>
                </DataTableCell>
                <DataTableCell className="text-muted-foreground">
                  {formatRelative(source.created)}
                </DataTableCell>
                <DataTableCell className="text-muted-foreground">
                  {formatRelative(source.updated)}
                </DataTableCell>
                <DataTableCell className="text-center">
                  <span className="font-medium">{source.insights_count || 0}</span>
                </DataTableCell>
                <DataTableCell className="text-center">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-medium",
                      source.embedded
                        ? "bg-teal-tint text-teal"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {source.embedded ? t('sources.yes') : t('sources.no')}
                  </span>
                </DataTableCell>
                <DataTableCell className="px-2 text-right">
                  {renderRowActions(source)}
                </DataTableCell>
              </DataTableRow>
            ))}
          </DataTableBody>
        </DataTable>

        <DataList className="sm:hidden">
          {sources.map((source, index) => (
            <DataListItem
              key={source.id}
              className="relative px-3 hover:bg-muted"
              title={
                <button
                  type="button"
                  onClick={() => handleRowClick(index, source.id)}
                  className="block w-full truncate text-left before:absolute before:inset-0 before:content-[''] focus-visible:outline-none focus-visible:before:ring-2 focus-visible:before:ring-inset focus-visible:before:ring-ring"
                >
                  {source.title || t('sources.untitledSource')}
                </button>
              }
              meta={
                <span className="flex min-w-0 items-center gap-1.5">
                  <span
                    aria-hidden
                    className={cn('h-2 w-2 shrink-0 rounded-full', getSourceTypeDotClass(source))}
                  />
                  <span className="truncate">
                    {getSourceType(source)} · {formatRelative(source.updated)}
                  </span>
                </span>
              }
              actions={renderRowActions(source)}
            />
          ))}
        </DataList>

        <InfiniteIndicator loading={loadingMore} loadingLabel={t('sources.loadingMore')} />
      </div>
    )
  }

  return (
    <AppShell>
      <PageShell width="full" className="flex min-h-0 flex-1 flex-col">
        <PageHeader
          title={t('sources.allSources')}
          description={t('sources.allSourcesDesc')}
          className="flex-shrink-0"
        />

        <Toolbar className="flex-shrink-0">
          <SourceSearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            className="flex-1 basis-60 lg:max-w-md"
          />
          {isAdmin && (
            <PrimaryAction icon={Plus} onClick={() => setSourceDialogOpen(true)} className="sm:ml-auto">
              {t('sources.addSource')}
            </PrimaryAction>
          )}
        </Toolbar>

        {renderContent()}
      </PageShell>

      <ConfirmDialog
        open={deleteDialog.open}
        onOpenChange={(open) => setDeleteDialog({ open, source: deleteDialog.source })}
        title={t('sources.delete')}
        description={t('sources.deleteConfirmWithTitle', { title: deleteDialog.source?.title || t('sources.untitledSource') })}
        confirmText={t('common.delete')}
        confirmVariant="destructive"
        onConfirm={handleDeleteConfirm}
      />
      <AddSourceDialog
        open={sourceDialogOpen}
        onOpenChange={(open) => {
          setSourceDialogOpen(open)
          if (!open) fetchSources(true)
        }}
      />
    </AppShell>
  )
}
