'use client'

import { useMemo, useState } from 'react'
import { AlertTriangle } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { EpisodesTab } from '@/components/podcasts/EpisodesTab'
import { TemplatesTab } from '@/components/podcasts/TemplatesTab'
import { Mic, LayoutTemplate } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useEpisodeProfiles, useSpeakerProfiles } from '@/lib/hooks/use-podcasts'
import { useSettings } from '@/lib/hooks/use-settings'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { needsModelSetup } from '@/lib/types/podcasts'

export default function PodcastsPage() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<'episodes' | 'templates'>('episodes')

  // The Podcast feature can be turned off by an admin in Settings. When off,
  // the whole page is unavailable (navigation + quick actions are hidden too,
  // but guard the route in case someone reaches it by direct URL).
  const { data: settings, isLoading: settingsLoading } = useSettings()
  const podcastEnabled = settings?.podcast_enabled !== false

  const { episodeProfiles } = useEpisodeProfiles()
  const { speakerProfiles } = useSpeakerProfiles(episodeProfiles)

  const hasUnconfiguredProfiles = useMemo(() => {
    return episodeProfiles.some(needsModelSetup) || speakerProfiles.some(needsModelSetup)
  }, [episodeProfiles, speakerProfiles])

  if (!settingsLoading && !podcastEnabled) {
    return (
      <AppShell>
        <div className="flex-1 overflow-y-auto">
          <PageShell width="wide" className="space-y-6">
            <PageHeader title={t('podcasts.listTitle')} description={t('podcasts.listDesc')} />
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('podcasts.featureDisabled')}</AlertTitle>
              <AlertDescription>{t('podcasts.featureDisabledDesc')}</AlertDescription>
            </Alert>
          </PageShell>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="wide" className="space-y-6">
          <PageHeader title={t('podcasts.listTitle')} description={t('podcasts.listDesc')} />

          {settingsLoading ? (
            <LoadingSkeleton variant="card" items={2} lines={3} aria-label={t('common.loading')} />
          ) : (
            <>
              {hasUnconfiguredProfiles ? (
                <Alert className="bg-warn-tint text-warn border-warn/30">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>{t('podcasts.setupRequired')}</AlertTitle>
                  <AlertDescription>
                    {t('podcasts.setupRequiredDesc')}
                  </AlertDescription>
                </Alert>
              ) : null}

              <Tabs
                value={activeTab}
                onValueChange={(value) => setActiveTab(value as 'episodes' | 'templates')}
                className="space-y-6"
              >
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('podcasts.chooseAView')}</p>
                  <TabsList aria-label={t('common.accessibility.podcastViews')} className="w-full max-w-md">
                    <TabsTrigger value="episodes">
                      <Mic className="h-4 w-4" />
                      {t('podcasts.episodesTab')}
                    </TabsTrigger>
                    <TabsTrigger value="templates">
                      <LayoutTemplate className="h-4 w-4" />
                      {t('podcasts.templatesTab')}
                    </TabsTrigger>
                  </TabsList>
                </div>

                <TabsContent value="episodes">
                  <EpisodesTab />
                </TabsContent>

                <TabsContent value="templates">
                  <TemplatesTab />
                </TabsContent>
              </Tabs>
            </>
          )}
        </PageShell>
      </div>
    </AppShell>
  )
}
