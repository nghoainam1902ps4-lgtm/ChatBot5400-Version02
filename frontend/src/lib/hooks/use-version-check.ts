import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { APP_VERSION } from '@/lib/constants/app'
import { useTranslation } from '@/lib/hooks/use-translation'
import { compareVersions, fetchLatestVersion } from '@/lib/utils/version'

/** sessionStorage flag: the update toast was already shown in this tab session. */
export const UPDATE_NOTIFIED_KEY = 'update_notified'

/**
 * Background update check: once per browser session, fetch the latest GitHub
 * release and show a bottom-right toast if it is newer than APP_VERSION.
 * Mounted in the dashboard layout; pass `enabled = false` to skip the check.
 */
export function useVersionCheck(enabled = true) {
  const { t } = useTranslation()
  const router = useRouter()

  useEffect(() => {
    if (!enabled) return
    if (sessionStorage.getItem(UPDATE_NOTIFIED_KEY)) return

    let cancelled = false

    fetchLatestVersion()
      .then((latestVersion) => {
        if (cancelled || sessionStorage.getItem(UPDATE_NOTIFIED_KEY)) return
        if (compareVersions(latestVersion, APP_VERSION) <= 0) return

        toast.info(t('advanced.updateToast', { version: latestVersion }), {
          position: 'bottom-right',
          duration: 15000,
          closeButton: true,
          action: {
            label: t('navigation.advanced'),
            onClick: () => router.push('/advanced'),
          },
        })
        sessionStorage.setItem(UPDATE_NOTIFIED_KEY, 'true')
      })
      .catch(() => {
        // Silently ignore: the update check is non-critical (offline, rate limit...)
      })

    return () => {
      cancelled = true
    }
  }, [enabled, t, router])
}
