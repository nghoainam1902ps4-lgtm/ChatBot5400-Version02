'use client'

import { useEffect, useState } from 'react'
import { BellRing } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/lib/hooks/use-translation'
import { APP_VERSION } from '@/lib/constants/app'
import { compareVersions, fetchLatestVersion } from '@/lib/utils/version'

type UpdateStatus = 'checking' | 'upToDate' | 'updateAvailable' | 'error'

export function SystemInfo() {
  const { t } = useTranslation()
  const currentVersion = APP_VERSION
  const [latestVersion, setLatestVersion] = useState<string | null>(null)
  const [status, setStatus] = useState<UpdateStatus>('checking')

  useEffect(() => {
    let cancelled = false

    fetchLatestVersion()
      .then((latest) => {
        if (cancelled) return
        setLatestVersion(latest)
        setStatus(compareVersions(latest, currentVersion) > 0 ? 'updateAvailable' : 'upToDate')
      })
      .catch((error) => {
        if (cancelled) return
        console.error('Failed to check latest version:', error)
        setLatestVersion(null)
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [currentVersion])

  return (
    <Card className="p-6">
      <div className="space-y-4">
        <h2 className="font-display text-xl font-semibold tracking-tight">{t('advanced.systemInfo')}</h2>

        <div className="space-y-3">
          {/* Current Version (from frontend/package.json) */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('advanced.currentVersion')}</span>
            <Badge variant="outline" className="font-mono text-[11px]">{currentVersion}</Badge>
          </div>

          {/* Latest Version (latest GitHub release) */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('advanced.latestVersion')}</span>
            {status === 'checking' ? (
              <span className="text-xs text-muted-foreground">{t('advanced.checkingVersion')}</span>
            ) : status === 'error' ? (
              <Badge variant="outline" className="text-muted-foreground">
                {t('advanced.cannotCheckVersion')}
              </Badge>
            ) : (
              <Badge
                variant="outline"
                className={
                  status === 'updateAvailable'
                    ? 'font-mono text-[11px] border-transparent bg-warn-tint text-warn'
                    : 'font-mono text-[11px]'
                }
              >
                {latestVersion}
              </Badge>
            )}
          </div>

          {/* Update Status */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('advanced.status')}</span>
            {status === 'checking' ? (
              <span className="text-xs text-muted-foreground">{t('advanced.checkingVersion')}</span>
            ) : status === 'updateAvailable' ? (
              <Badge variant="outline" className="border-transparent bg-warn-tint text-warn">
                <BellRing />
                {t('advanced.updateAvailable')}
              </Badge>
            ) : status === 'error' ? (
              <Badge variant="outline" className="text-destructive border-destructive/30">
                {t('advanced.connectionError')}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-fern border-fern/30">
                {t('advanced.upToDate')}
              </Badge>
            )}
          </div>
        </div>
      </div>
    </Card>
  )
}
