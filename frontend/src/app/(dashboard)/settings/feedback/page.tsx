'use client'

import { useEffect, useMemo, useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { Toolbar } from '@/components/common/Toolbar'
import { SearchInput } from '@/components/common/SearchInput'
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
import { EmptyState } from '@/components/common/EmptyState'
import { AccessDenied } from '@/components/common/AccessDenied'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'
import {
  useAdminFeedbackList,
  useAdminFeedbackStats,
} from '@/lib/hooks/use-feedback'
import type { AdminFeedbackItem } from '@/lib/types/api'
import {
  ChevronLeft,
  ChevronRight,
  Flag,
  MessageSquareWarning,
  SearchX,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'

const PAGE_SIZE = 30

type TypeFilter = 'all' | 'like' | 'dislike' | 'report'
type ContextFilter = 'all' | 'notebook' | 'source'

export default function FeedbackPage() {
  const { t, language } = useTranslation()
  const { isAdmin, isLoading: authLoading } = useAuth()

  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [type, setType] = useState<TypeFilter>('all')
  const [context, setContext] = useState<ContextFilter>('all')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<AdminFeedbackItem | null>(null)

  // Debounce the search box into the query param (no debounce hook in repo).
  useEffect(() => {
    const id = setTimeout(() => setQ(searchInput.trim()), 300)
    return () => clearTimeout(id)
  }, [searchInput])

  // Any filter change returns to the first page.
  useEffect(() => {
    setPage(1)
  }, [q, type, context])

  const params = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      q: q || undefined,
      type: type === 'all' ? undefined : type,
      context: context === 'all' ? undefined : context,
      sort: 'created',
      direction: 'desc' as const,
    }),
    [page, q, type, context]
  )

  const stats = useAdminFeedbackStats(isAdmin)
  const list = useAdminFeedbackList(params, isAdmin)

  const items = list.data?.items ?? []
  const totalPages = list.data?.total_pages ?? 0
  const hasFilter = Boolean(q) || type !== 'all' || context !== 'all'

  const formatTime = (value?: string | null) => {
    if (!value) return '—'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '—'
    return new Intl.DateTimeFormat(language, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date)
  }

  const contextLabel = (item: AdminFeedbackItem) => {
    const base =
      item.context_type === 'notebook'
        ? t('feedback.contextNotebook')
        : t('feedback.contextSource')
    return item.context_title_snapshot
      ? `${base} · ${item.context_title_snapshot}`
      : base
  }

  const reactionBadges = (item: AdminFeedbackItem) => (
    <div className="flex flex-wrap items-center gap-1">
      {item.reaction === 'like' && (
        <Badge variant="outline" className="gap-1 border-teal/40 text-teal">
          <ThumbsUp className="h-3 w-3" />
          {t('feedback.like')}
        </Badge>
      )}
      {item.reaction === 'dislike' && (
        <Badge variant="outline" className="gap-1 border-warn/40 text-warn">
          <ThumbsDown className="h-3 w-3" />
          {t('feedback.dislike')}
        </Badge>
      )}
      {item.reported && (
        <Badge variant="outline" className="gap-1 border-destructive/40 text-destructive">
          <Flag className="h-3 w-3" />
          {t('feedback.reportedBadge')}
        </Badge>
      )}
    </div>
  )

  const statCards = (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[
        { label: t('feedback.statTotal'), value: stats.data?.total },
        { label: t('feedback.statLikes'), value: stats.data?.likes },
        { label: t('feedback.statDislikes'), value: stats.data?.dislikes },
        { label: t('feedback.statReports'), value: stats.data?.reports },
      ].map((card) => (
        <div key={card.label} className="rounded-lg border bg-card px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {card.label}
          </div>
          <div className="mt-1 font-mono text-2xl font-semibold text-foreground">
            {stats.isLoading ? '—' : card.value ?? 0}
          </div>
        </div>
      ))}
    </div>
  )

  const renderData = () => {
    if (list.isLoading) {
      return (
        <>
          <LoadingSkeleton
            variant="table"
            rows={6}
            columns={6}
            aria-label={t('common.loading')}
            className="hidden rounded-lg border sm:block"
          />
          <LoadingSkeleton variant="list" items={6} aria-label={t('common.loading')} className="sm:hidden" />
        </>
      )
    }
    if (list.isError) {
      return (
        <ErrorState
          title={t('feedback.loadError')}
          description={t('feedback.loadErrorDesc')}
          onRetry={() => void list.refetch()}
          className="rounded-lg border"
        />
      )
    }
    if (items.length === 0) {
      return hasFilter ? (
        <div role="status" className="rounded-lg border">
          <EmptyState variant="search" icon={SearchX} title={t('common.noMatches')} />
        </div>
      ) : (
        <EmptyState icon={MessageSquareWarning} title={t('feedback.empty')} description={t('feedback.emptyDesc')} />
      )
    }

    return (
      <>
        {/* >=640px: table */}
        <div className="hidden rounded-lg border sm:block">
          <DataTable className="table-fixed">
            <colgroup>
              <col className="w-[140px]" />
              <col className="w-[120px]" />
              <col className="w-[140px]" />
              <col className="w-[140px]" />
              <col className="w-auto" />
              <col className="w-auto" />
              <col className="w-auto" />
            </colgroup>
            <DataTableHeader>
              <tr>
                <DataTableHead>{t('feedback.colTime')}</DataTableHead>
                <DataTableHead>{t('feedback.colUser')}</DataTableHead>
                <DataTableHead>{t('feedback.colReaction')}</DataTableHead>
                <DataTableHead>{t('feedback.colContext')}</DataTableHead>
                <DataTableHead>{t('feedback.colQuestion')}</DataTableHead>
                <DataTableHead>{t('feedback.colAnswer')}</DataTableHead>
                <DataTableHead>{t('feedback.colReport')}</DataTableHead>
              </tr>
            </DataTableHeader>
            <DataTableBody>
              {items.map((item) => (
                <DataTableRow
                  key={item.id}
                  className="cursor-pointer last:border-b-0"
                  title={t('feedback.details')}
                  onClick={() => setSelected(item)}
                >
                  <DataTableCell className="whitespace-nowrap text-muted-foreground">
                    {formatTime(item.created)}
                  </DataTableCell>
                  <DataTableCell className="truncate">
                    {item.user_name_snapshot || item.username_snapshot}
                  </DataTableCell>
                  <DataTableCell>{reactionBadges(item)}</DataTableCell>
                  <DataTableCell className="truncate text-muted-foreground" title={contextLabel(item)}>
                    {contextLabel(item)}
                  </DataTableCell>
                  <DataTableCell className="truncate" title={item.question_snapshot}>
                    {item.question_snapshot || '—'}
                  </DataTableCell>
                  <DataTableCell className="truncate text-muted-foreground" title={item.answer_snapshot}>
                    {item.answer_snapshot || '—'}
                  </DataTableCell>
                  <DataTableCell className="truncate text-muted-foreground" title={item.report_reason ?? ''}>
                    {item.report_reason || '—'}
                  </DataTableCell>
                </DataTableRow>
              ))}
            </DataTableBody>
          </DataTable>
        </div>

        {/* <640px: list */}
        <DataList className="rounded-lg border sm:hidden">
          {items.map((item) => (
            <DataListItem
              key={item.id}
              className="cursor-pointer px-3"
              onClick={() => setSelected(item)}
              title={<span className="truncate">{item.question_snapshot || contextLabel(item)}</span>}
              meta={`${item.user_name_snapshot || item.username_snapshot} · ${formatTime(item.created)}`}
              actions={reactionBadges(item)}
            />
          ))}
        </DataList>
      </>
    )
  }

  const renderBody = () => {
    if (authLoading) {
      return <LoadingSkeleton variant="table" rows={6} columns={6} aria-label={t('common.loading')} />
    }
    if (!isAdmin) {
      return <AccessDenied />
    }
    return (
      <div className="space-y-4">
        {statCards}
        <Toolbar>
          <SearchInput
            value={searchInput}
            onChange={setSearchInput}
            placeholder={t('feedback.searchPlaceholder')}
            ariaLabel={t('feedback.searchPlaceholder')}
            clearLabel={t('common.clearSearch')}
            className="flex-1 basis-60 sm:max-w-sm"
          />
          <Select value={type} onValueChange={(v) => setType(v as TypeFilter)}>
            <SelectTrigger className="w-full sm:w-40" aria-label={t('feedback.filterType')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('feedback.typeAll')}</SelectItem>
              <SelectItem value="like">{t('feedback.typeLike')}</SelectItem>
              <SelectItem value="dislike">{t('feedback.typeDislike')}</SelectItem>
              <SelectItem value="report">{t('feedback.typeReport')}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={context} onValueChange={(v) => setContext(v as ContextFilter)}>
            <SelectTrigger className="w-full sm:w-40" aria-label={t('feedback.filterContext')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('feedback.contextAll')}</SelectItem>
              <SelectItem value="notebook">{t('feedback.contextNotebook')}</SelectItem>
              <SelectItem value="source">{t('feedback.contextSource')}</SelectItem>
            </SelectContent>
          </Select>
        </Toolbar>

        {renderData()}

        {/* Numbered server-side pagination (page size 30) */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-4 py-1 text-sm">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || list.isFetching}
            >
              <ChevronLeft className="h-4 w-4" />
              {t('feedback.prevPage')}
            </Button>
            <span className="text-muted-foreground tabular-nums">
              {t('feedback.pageInfo', { page, total: totalPages })}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => (totalPages ? Math.min(totalPages, p + 1) : p + 1))}
              disabled={page >= totalPages || list.isFetching}
            >
              {t('feedback.nextPage')}
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="wide">
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                <MessageSquareWarning aria-hidden className="h-5 w-5 text-muted-foreground" />
                {t('feedback.adminTitle')}
              </span>
            }
            description={t('feedback.adminDescription')}
          />
          {renderBody()}
        </PageShell>
      </div>

      {/* Detail dialog: fixed header, scrollable body */}
      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent size="lg" className="max-h-[85vh]">
          <DialogHeader>
            <DialogTitle>{t('feedback.detailTitle')}</DialogTitle>
          </DialogHeader>
          {selected && (
            <DialogBody className="space-y-5 overflow-y-auto">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                <span className="font-medium">
                  {selected.user_name_snapshot || selected.username_snapshot}
                </span>
                <span className="text-muted-foreground">{formatTime(selected.created)}</span>
                <span className="text-muted-foreground">{contextLabel(selected)}</span>
                {reactionBadges(selected)}
              </div>

              <section className="space-y-1.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t('feedback.question')}
                </h3>
                <p className="whitespace-pre-wrap break-words text-sm">
                  {selected.question_snapshot || '—'}
                </p>
              </section>

              <section className="space-y-1.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t('feedback.aiAnswer')}
                </h3>
                <div className="rounded-md border bg-muted/40 p-3">
                  <MarkdownRenderer>{selected.answer_snapshot || '—'}</MarkdownRenderer>
                </div>
              </section>

              {selected.reported && (
                <section className="space-y-1.5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-destructive">
                    {t('feedback.reportContent')}
                  </h3>
                  <p className="whitespace-pre-wrap break-words text-sm">
                    {selected.report_reason || '—'}
                  </p>
                </section>
              )}

              <p className="text-xs text-muted-foreground">
                {t('feedback.sessionLabel')}: <span className="font-mono">{selected.session_id}</span>
              </p>
            </DialogBody>
          )}
        </DialogContent>
      </Dialog>
    </AppShell>
  )
}
