import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { APP_VERSION } from '@/lib/constants/app'
import { useTranslation } from '@/lib/hooks/use-translation'
import { compareVersions, fetchLatestVersion } from '@/lib/utils/version'

// Module-level flag: lives for one app load. Client-side navigation keeps it
// (no repeat toast when switching pages); opening or reloading the app resets
// it, so the toast shows again on every new visit until the app is updated.
let checkedThisLoad = false

/** Test helper: reset the once-per-load guard. */
export function resetVersionCheck() {
  checkedThisLoad = false
}

/**
 * Background update check: once per app load, fetch the latest GitHub release
 * and show a bottom-right toast if it is newer than APP_VERSION.
 * Mounted in the dashboard layout; pass `enabled = false` to skip the check.
 */
export function useVersionCheck(enabled = true) {
  const { t } = useTranslation()
  const router = useRouter()

  useEffect(() => {
    if (!enabled || checkedThisLoad) return
    checkedThisLoad = true

    fetchLatestVersion()
      .then((latestVersion) => {
        if (compareVersions(latestVersion, APP_VERSION) <= 0) return

        toast.info(t('advanced.updateToastTitle', { version: latestVersion }), {
          description: t('advanced.updateToastDesc'),
          position: 'bottom-right',
          duration: 15000,
          action: {
            label: t('navigation.advanced'),
            onClick: () => router.push('/advanced'),
          },
          actionButtonStyle: { background: '#ffffff', color: '#8B1538' },
        })
      })
      .catch(() => {
        // Silently ignore: the update check is non-critical (offline, rate limit...)
        // Allow a retry on the next app load only.
      })
  }, [enabled, t, router])
}
