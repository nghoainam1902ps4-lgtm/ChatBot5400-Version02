'use client'

import { useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DataTable,
  DataTableBody,
  DataTableCell,
  DataTableHead,
  DataTableHeader,
  DataTableRow,
} from '@/components/common/DataTable'
import { DataList, DataListItem } from '@/components/common/DataList'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { EmptyState } from '@/components/common/EmptyState'
import { AccessDenied } from '@/components/common/AccessDenied'
import { ReviewSourceDialog } from '@/components/sources/ReviewSourceDialog'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'
import {
  usePendingApprovals,
  useApproveSource,
  useRejectSource,
} from '@/lib/hooks/use-approvals'
import type { ApprovalItem } from '@/lib/api/approvals'
import { Check, ClipboardCheck, X } from 'lucide-react'

export default function ApprovalsPage() {
  const { t, language } = useTranslation()
  const { canReview, isLoading: authLoading } = useAuth()

  const { data: items, isLoading, isError, refetch } = usePendingApprovals(canReview)
  const approve = useApproveSource()
  const reject = useRejectSource()

  const [rejecting, setRejecting] = useState<ApprovalItem | null>(null)
  const [reason, setReason] = useState('')
  const [reviewingId, setReviewingId] = useState<string | null>(null)

  const formatDate = (value?: string | null) => {
    if (!value) return '—'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '—'
    return new Intl.DateTimeFormat(language, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date)
  }

  const typeLabel = (type?: string | null) => {
    switch (type) {
      case 'link':
        return t('sources.type.link')
      case 'upload':
        return t('sources.type.file')
      case 'text':
        return t('sources.type.text')
      default:
        return type || '—'
    }
  }

  const handleApprove = (item: ApprovalItem) => {
    approve.mutate(item.id)
  }

  const submitReject = async () => {
    if (!rejecting) return
    await reject.mutateAsync({ sourceId: rejecting.id, reason: reason || undefined })
    setRejecting(null)
    setReason('')
  }

  const renderActions = (item: ApprovalItem) => (
    <div className="flex items-center justify-end gap-2">
      <Button
        size="sm"
        onClick={() => handleApprove(item)}
        disabled={approve.isPending}
      >
        <Check className="h-4 w-4" />
        {t('approvals.approve')}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          setRejecting(item)
          setReason('')
        }}
      >
        <X className="h-4 w-4" />
        {t('approvals.reject')}
      </Button>
    </div>
  )

  const renderNotebooks = (item: ApprovalItem) =>
    item.notebooks.length > 0 ? (
      <div className="flex flex-wrap gap-1">
        {item.notebooks.map((nb) => (
          <Badge key={nb.id} variant="secondary" className="font-normal">
            {nb.name}
          </Badge>
        ))}
      </div>
    ) : (
      <span className="text-muted-foreground">—</span>
    )

  const renderData = () => {
    if (isLoading) {
      return (
        <>
          <LoadingSkeleton
            variant="table"
            rows={5}
            columns={5}
            aria-label={t('common.loading')}
            className="hidden rounded-lg border sm:block"
          />
          <LoadingSkeleton
            variant="list"
            items={5}
            aria-label={t('common.loading')}
            className="sm:hidden"
          />
        </>
      )
    }

    if (isError) {
      return (
        <ErrorState
          title={t('approvals.loadErrorTitle')}
          description={t('approvals.loadErrorDesc')}
          onRetry={() => void refetch()}
          className="rounded-lg border"
        />
      )
    }

    if (!items || items.length === 0) {
      return (
        <EmptyState
          icon={ClipboardCheck}
          title={t('approvals.empty')}
          description={t('approvals.emptyDesc')}
        />
      )
    }

    return (
      <>
        {/* >=640px: table */}
        <div className="hidden rounded-lg border sm:block">
          <DataTable className="table-fixed">
            <colgroup>
              <col className="w-auto" />
              <col className="w-[110px]" />
              <col className="w-auto" />
              <col className="w-[160px]" />
              <col className="w-[200px]" />
            </colgroup>
            <DataTableHeader>
              <tr>
                <DataTableHead>{t('approvals.colTitle')}</DataTableHead>
                <DataTableHead>{t('approvals.colType')}</DataTableHead>
                <DataTableHead>{t('approvals.colNotebooks')}</DataTableHead>
                <DataTableHead>{t('approvals.colSubmitted')}</DataTableHead>
                <DataTableHead className="text-right">
                  {t('approvals.colActions')}
                </DataTableHead>
              </tr>
            </DataTableHeader>
            <DataTableBody>
              {items.map((item) => (
                <DataTableRow key={item.id} className="last:border-b-0">
                  <DataTableCell className="font-medium">
                    <button
                      type="button"
                      onClick={() => setReviewingId(item.id)}
                      className="block max-w-full truncate text-left text-fern hover:underline"
                      title={t('approvals.openReview')}
                    >
                      {item.title || t('approvals.untitled')}
                    </button>
                  </DataTableCell>
                  <DataTableCell>{typeLabel(item.type)}</DataTableCell>
                  <DataTableCell>{renderNotebooks(item)}</DataTableCell>
                  <DataTableCell className="text-muted-foreground">
                    <div className="flex flex-col">
                      <span className="truncate">
                        {item.submitted_by_name || '—'}
                      </span>
                      <span className="text-xs">{formatDate(item.submitted_at)}</span>
                    </div>
                  </DataTableCell>
                  <DataTableCell className="text-right">
                    {renderActions(item)}
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
              className="px-3"
              title={
                <button
                  type="button"
                  onClick={() => setReviewingId(item.id)}
                  className="truncate text-left text-fern hover:underline"
                >
                  {item.title || t('approvals.untitled')}
                </button>
              }
              meta={[
                typeLabel(item.type),
                item.submitted_by_name,
                formatDate(item.submitted_at),
              ]
                .filter(Boolean)
                .join(' · ')}
              actions={renderActions(item)}
            />
          ))}
        </DataList>
      </>
    )
  }

  const renderBody = () => {
    if (authLoading) {
      return (
        <LoadingSkeleton
          variant="table"
          rows={5}
          columns={5}
          aria-label={t('common.loading')}
        />
      )
    }
    if (!canReview) {
      return <AccessDenied />
    }
    return renderData()
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="wide">
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                <ClipboardCheck aria-hidden className="h-5 w-5 text-muted-foreground" />
                {t('approvals.title')}
              </span>
            }
            description={t('approvals.subtitle')}
          />
          {renderBody()}
        </PageShell>
      </div>

      {/* Reject dialog */}
      <Dialog
        open={rejecting !== null}
        onOpenChange={(open) => !open && setRejecting(null)}
      >
        <DialogContent size="md">
          <DialogHeader>
            <DialogTitle>{t('approvals.rejectTitle')}</DialogTitle>
            <DialogDescription>
              {rejecting?.title || t('approvals.untitled')}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-1.5">
            <Label htmlFor="reject-reason">{t('approvals.rejectReason')}</Label>
            <Textarea
              id="reject-reason"
              value={reason}
              placeholder={t('approvals.rejectReasonPlaceholder')}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={submitReject}
              disabled={reject.isPending}
            >
              {t('approvals.reject')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Full review window: content + manage-notebooks + approve/reject */}
      <ReviewSourceDialog
        open={reviewingId !== null}
        onOpenChange={(o) => !o && setReviewingId(null)}
        sourceId={reviewingId}
      />
    </AppShell>
  )
}
