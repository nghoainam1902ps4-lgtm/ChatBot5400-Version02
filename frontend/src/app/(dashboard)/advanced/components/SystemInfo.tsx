'use client'

import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/lib/hooks/use-translation'
import { APP_VERSION } from '@/lib/constants/app'

export function SystemInfo() {
  const { t } = useTranslation()

  return (
    <Card className="p-6">
      <div className="space-y-4">
        <h2 className="font-display text-xl font-semibold tracking-tight">{t('advanced.systemInfo')}</h2>

        <div className="space-y-3">
          {/* Current Version (from frontend/package.json) */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('advanced.currentVersion')}</span>
            <Badge variant="outline" className="font-mono text-[11px]">{APP_VERSION}</Badge>
          </div>

          {/* Update Status: internal deployment, no external update check */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('advanced.status')}</span>
            <Badge variant="outline" className="text-fern border-fern/30">
              {t('advanced.upToDate')}
            </Badge>
          </div>
        </div>
      </div>
    </Card>
  )
}
