'use client'

import { AppShell } from '@/components/layout/AppShell'
import { RebuildEmbeddings } from './components/RebuildEmbeddings'
import { SystemInfo } from './components/SystemInfo'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { AccessDenied } from '@/components/common/AccessDenied'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'

export default function AdvancedPage() {
  const { t } = useTranslation()
  // Access is shown in place (AccessDenied), never by redirecting.
  const { isAdmin, isLoading: authLoading } = useAuth()

  const renderBody = () => {
    if (authLoading) {
      return <LoadingSkeleton variant="card" items={2} lines={3} aria-label={t('common.loading')} />
    }
    if (!isAdmin) {
      return <AccessDenied />
    }
    return (
      <>
        <SystemInfo />
        <RebuildEmbeddings />
      </>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="config" className="space-y-6">
          <PageHeader title={t('advanced.title')} description={t('advanced.desc')} />
          {renderBody()}
        </PageShell>
      </div>
    </AppShell>
  )
}
