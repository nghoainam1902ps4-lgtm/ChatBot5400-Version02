'use client'

import { useCallback, useState } from 'react'
import { Loader2, Mic, RefreshCcw } from 'lucide-react'

import { useDeletePodcastEpisode, usePodcastEpisodes, useRetryPodcastEpisode } from '@/lib/hooks/use-podcasts'
import { EpisodeCard } from '@/components/podcasts/EpisodeCard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ErrorState } from '@/components/common/ErrorState'
import { EmptyState } from '@/components/common/EmptyState'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { GeneratePodcastDialog } from '@/components/podcasts/GeneratePodcastDialog'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { TFunction } from 'i18next'

// One order everywhere (summary badges after Total, then the sections):
// pending → processing → completed → failed. Unknown statuses stay in the
// pending group (see statusPendingNote).
const getSTATUS_ORDER = (t: TFunction): Array<{
  key: 'running' | 'completed' | 'failed' | 'pending'
  title: string
  badgeLabel: string
  description?: string
  note?: string
}> => [
  {
    key: 'pending',
    title: t('podcasts.statusPendingTitle'),
    badgeLabel: t('podcasts.pendingLabel'),
    description: t('podcasts.statusPendingDesc'),
    note: t('podcasts.statusPendingNote'),
  },
  {
    key: 'running',
    title: t('podcasts.statusRunningTitle'),
    badgeLabel: t('podcasts.processingLabel'),
    description: t('podcasts.statusRunningDesc'),
  },
  {
    key: 'completed',
    title: t('podcasts.statusCompletedTitle'),
    badgeLabel: t('podcasts.completedLabel'),
    description: t('podcasts.statusCompletedDesc'),
    note: t('podcasts.statusCompletedNote'),
  },
  {
    key: 'failed',
    title: t('podcasts.statusFailedTitle'),
    badgeLabel: t('podcasts.failedLabel'),
    description: t('podcasts.statusFailedDesc'),
  },
]

function SummaryBadge({ label, value }: { label: string; value: number }) {
  return (
    <Badge variant="outline" className="font-medium">
      <span className="text-muted-foreground mr-1.5">{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </Badge>
  )
}

export function EpisodesTab() {
  const { t } = useTranslation()
  const [showGenerateDialog, setShowGenerateDialog] = useState(false)
  const {
    episodes,
    statusGroups,
    statusCounts,
    isLoading,
    isError,
    refetch,
    isFetching,
  } = usePodcastEpisodes()
  const deleteEpisode = useDeletePodcastEpisode()
  const retryEpisode = useRetryPodcastEpisode()

  const handleRefresh = useCallback(() => {
    void refetch()
  }, [refetch])

  const handleDelete = useCallback(
    (episodeId: string) => deleteEpisode.mutateAsync(episodeId),
    [deleteEpisode]
  )

  const handleRetry = useCallback(
    async (episodeId: string) => { await retryEpisode.mutateAsync(episodeId) },
    [retryEpisode]
  )

  const emptyState = !isLoading && !isError && episodes.length === 0
  const statusOrder = getSTATUS_ORDER(t)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h2 className="font-display text-xl font-semibold tracking-tight">{t('podcasts.overviewTitle')}</h2>
          <p className="text-sm text-muted-foreground">
            {t('podcasts.overviewDesc')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setShowGenerateDialog(true)}>
            {t('podcasts.generateBtn')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isFetching}
          >
            {isFetching ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCcw className="mr-2 h-4 w-4" />
            )}
            {t('common.refresh')}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <SummaryBadge label={t('podcasts.total')} value={statusCounts.total} />
        {statusOrder.map(({ key, badgeLabel }) => (
          <SummaryBadge key={key} label={badgeLabel} value={statusCounts[key]} />
        ))}
      </div>

      {isError ? (
        <ErrorState
          title={t('podcasts.loadErrorTitle')}
          description={t('podcasts.loadErrorDesc')}
          onRetry={handleRefresh}
          className="rounded-md border"
        />
      ) : null}

      {isLoading ? (
        <LoadingSkeleton variant="card" items={3} aria-label={t('podcasts.loadingEpisodes')} />
      ) : null}

      {emptyState ? (
        <div className="rounded-md border border-dashed">
          <EmptyState icon={Mic} title={t('podcasts.noEpisodesYet')} />
        </div>
      ) : null}

      {statusOrder.map(({ key, title, description, note }) => {
        const data = statusGroups[key]
        if (!data || data.length === 0) {
          return null
        }

        return (
          <section key={key} data-status-group={key} className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold leading-tight">{title}</h3>
              {description ? (
                <p className="text-sm text-muted-foreground">{description}</p>
              ) : null}
              {note ? (
                <p className="mt-1 text-xs text-muted-foreground">{note}</p>
              ) : null}
            </div>
            <Separator />
            <div className="space-y-4">
              {data.map((episode) => (
                <EpisodeCard
                  key={episode.id}
                  episode={episode}
                  onDelete={handleDelete}
                  deleting={deleteEpisode.isPending}
                  onRetry={handleRetry}
                  retrying={retryEpisode.isPending}
                />
              ))}
            </div>
          </section>
        )
      })}

      <GeneratePodcastDialog
        open={showGenerateDialog}
        onOpenChange={setShowGenerateDialog}
      />
    </div>
  )
}
