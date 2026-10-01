'use client'

import { useMemo, useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { AiProvidersGuideModal } from '@/components/settings/AiProvidersGuideModal'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { AccessDenied } from '@/components/common/AccessDenied'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Key, ShieldAlert } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'
import { useModels, useModelDefaults } from '@/lib/hooks/use-models'
import {
  useCredentials,
  useCredentialStatus,
  useEnvStatus,
} from '@/lib/hooks/use-credentials'
import { useProviders } from '@/lib/hooks/use-providers'
import { Credential } from '@/lib/api/credentials'
import {
  DefaultModelSelectors,
  MigrationBanner,
  ProviderSection,
} from '@/components/settings'

export default function ApiKeysPage() {
  const { t } = useTranslation()
  // Access is shown in place (AccessDenied), never by redirecting.
  const { isAdmin, isLoading: authLoading } = useAuth()
  const [guideOpen, setGuideOpen] = useState(false)

  // Data
  const { data: credentials, isLoading: credentialsLoading } = useCredentials()
  const { data: models, isLoading: modelsLoading } = useModels()
  const { data: defaults, isLoading: defaultsLoading } = useModelDefaults()
  const { data: credentialStatus } = useCredentialStatus()
  const { data: envStatus } = useEnvStatus()
  const {
    data: providers,
    isLoading: providersLoading,
    isError: providersError,
    refetch: refetchProviders,
  } = useProviders()

  const encryptionReady = credentialStatus?.encryption_configured ?? true

  // Group credentials by provider
  const credentialsByProvider = useMemo(() => {
    const grouped: Record<string, Credential[]> = {}
    for (const provider of providers ?? []) {
      grouped[provider.name] = []
    }
    if (credentials) {
      for (const cred of credentials) {
        if (!grouped[cred.provider]) grouped[cred.provider] = []
        grouped[cred.provider].push(cred)
      }
    }
    return grouped
  }, [credentials, providers])

  // Providers needing migration
  const providersToMigrate = useMemo(() => {
    if (!envStatus || !credentialStatus) return []
    const result: string[] = []
    for (const provider in envStatus) {
      if (envStatus[provider] && credentialStatus.source[provider] === 'environment') {
        result.push(provider)
      }
    }
    return result
  }, [envStatus, credentialStatus])

  // Sort: configured providers first (the backend registry owns the base order)
  const sortedProviders = useMemo(() => {
    return [...(providers ?? [])].sort((a, b) => {
      const aHas = (credentialsByProvider[a.name]?.length || 0) > 0 ? 1 : 0
      const bHas = (credentialsByProvider[b.name]?.length || 0) > 0 ? 1 : 0
      return bHas - aHas
    })
  }, [providers, credentialsByProvider])

  const isLoading = credentialsLoading || modelsLoading || defaultsLoading || providersLoading

  const renderBody = () => {
    // Auth still resolving, or admin data still loading: keep the geometry.
    if (authLoading || (isAdmin && isLoading)) {
      return <LoadingSkeleton variant="card" items={4} lines={3} aria-label={t('common.loading')} />
    }

    if (!isAdmin) {
      return <AccessDenied />
    }

    return (
      <>
        {/* Encryption required: blocks credential management (destructive) */}
        {!encryptionReady && (
          <Alert variant="destructive" className="bg-destructive-tint">
            <ShieldAlert className="h-4 w-4" />
            <AlertTitle>{t('apiKeys.encryptionRequired')}</AlertTitle>
            <AlertDescription>
              <code className="text-xs bg-destructive-tint px-1 py-0.5 rounded">
                {t('apiKeys.encryptionRequiredDescription')}
              </code>
            </AlertDescription>
          </Alert>
        )}

        {/* Migration banner */}
        {encryptionReady && <MigrationBanner providersToMigrate={providersToMigrate} />}

        {/* Default Model Selectors */}
        {models && defaults && (
          <DefaultModelSelectors models={models} defaults={defaults} />
        )}

        {/* Provider Cards */}
        {providersError ? (
          <ErrorState
            title={t('apiKeys.providersLoadFailed')}
            description={t('apiKeys.providersLoadFailedDescription')}
            onRetry={() => void refetchProviders()}
            className="rounded-lg border"
          />
        ) : (
          <div className="grid gap-4">
            {sortedProviders.map(provider => (
              <ProviderSection
                key={provider.name}
                provider={provider}
                credentials={credentialsByProvider[provider.name] || []}
                models={models || []}
                defaults={defaults || null}
                allCredentials={credentials || []}
                encryptionReady={encryptionReady}
              />
            ))}
          </div>
        )}

        {/* Help link — opens the in-app guide modal instead of GitHub */}
        <div className="border-t pt-4">
          <button
            type="button"
            onClick={() => setGuideOpen(true)}
            className="text-sm text-primary hover:underline"
          >
            {t('apiKeys.learnMore')}
          </button>
        </div>
      </>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="config" className="space-y-6">
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                <Key aria-hidden className="h-5 w-5 text-muted-foreground" />
                {t('apiKeys.title')}
              </span>
            }
            description={t('apiKeys.description')}
          />
          {renderBody()}
        </PageShell>
      </div>

      <AiProvidersGuideModal open={guideOpen} onOpenChange={setGuideOpen} />
    </AppShell>
  )
}
