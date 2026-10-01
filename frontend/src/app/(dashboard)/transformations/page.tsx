'use client'

import { useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { AccessDenied } from '@/components/common/AccessDenied'
import { DefaultPromptEditor } from './components/DefaultPromptEditor'
import { TransformationsList } from './components/TransformationsList'
import { TransformationPlayground } from './components/TransformationPlayground'
import { useTransformations } from '@/lib/hooks/use-transformations'
import { Transformation } from '@/lib/types/transformations'
import { Wand2, Play, RefreshCw } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'

export default function TransformationsPage() {
  const { t } = useTranslation()
  // Access is shown in place (AccessDenied), never by redirecting.
  const { isAdmin, isLoading: authLoading } = useAuth()
  const [activeTab, setActiveTab] = useState('transformations')
  const [selectedTransformation, setSelectedTransformation] = useState<Transformation | undefined>()
  const { data: transformations, isLoading, isError, refetch } = useTransformations()

  const handlePlayground = (transformation: Transformation) => {
    setSelectedTransformation(transformation)
    setActiveTab('playground')
  }

  const renderBody = () => {
    if (authLoading) {
      return <LoadingSkeleton variant="card" items={3} aria-label={t('common.loading')} />
    }

    if (!isAdmin) {
      return <AccessDenied />
    }

    return (
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('transformations.workspace')}</p>
          <TabsList aria-label={t('common.accessibility.transformationViews')} className="w-full max-w-xl">
            <TabsTrigger value="transformations" className="flex items-center gap-2">
              <Wand2 className="h-4 w-4" />
              {t('transformations.title')}
            </TabsTrigger>
            <TabsTrigger value="playground" className="flex items-center gap-2">
              <Play className="h-4 w-4" />
              {t('transformations.playground')}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="transformations" className="space-y-6">
          <DefaultPromptEditor />
          {isError ? (
            <ErrorState
              title={t('transformations.loadErrorTitle')}
              description={t('transformations.loadErrorDesc')}
              onRetry={() => void refetch()}
              className="rounded-lg border"
            />
          ) : (
            <TransformationsList
              transformations={transformations}
              isLoading={isLoading}
              onPlayground={handlePlayground}
            />
          )}
        </TabsContent>

        <TabsContent value="playground">
          <TransformationPlayground
            transformations={transformations}
            selectedTransformation={selectedTransformation}
          />
        </TabsContent>
      </Tabs>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="config" className="space-y-6">
          <PageHeader
            title={t('transformations.title')}
            description={t('transformations.desc')}
            actions={
              isAdmin && !authLoading ? (
                <Button variant="outline" onClick={() => void refetch()} aria-label={t('common.refresh')} className="h-11 sm:h-10 lg:h-9">
                  <RefreshCw aria-hidden className="h-4 w-4" />
                  {t('common.refresh')}
                </Button>
              ) : undefined
            }
          />
          {renderBody()}
        </PageShell>
      </div>
    </AppShell>
  )
}
