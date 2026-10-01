'use client'

import { AppShell } from '@/components/layout/AppShell'
import { SettingsForm } from './components/SettingsForm'
import { useSettings } from '@/lib/hooks/use-settings'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { AccessDenied } from '@/components/common/AccessDenied'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'

export default function SettingsPage() {
  const { t } = useTranslation()
  // Access is shown in place (AccessDenied), never by redirecting.
  const { isAdmin, isLoading: authLoading } = useAuth()
  const { refetch } = useSettings()

  const renderBody = () => {
    if (authLoading) {
      return <LoadingSkeleton variant="card" items={3} lines={3} aria-label={t('common.loading')} />
    }
    if (!isAdmin) {
      return <AccessDenied />
    }
    return <SettingsForm />
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="config" className="space-y-6">
          <PageHeader
            title={t('settings.pageTitle')}
            description={t('settings.pageDesc')}
            actions={
              isAdmin && !authLoading ? (
                <Button
                  variant="outline"
                  onClick={() => void refetch()}
                  aria-label={t('common.refresh')}
                  className="h-11 sm:h-10 lg:h-9"
                >
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
