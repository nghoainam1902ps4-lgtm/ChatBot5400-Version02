import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi } from '@/lib/api/settings'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { SettingsResponse } from '@/lib/types/api'

export function useSettings() {
  return useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: () => settingsApi.get(),
  })
}

/**
 * Whether the Podcast feature is enabled by the admin. Drives the visibility of
 * the Podcast navigation entry, the "Create podcast" action and the podcast
 * quick-action (Ctrl+K) for every user. Defaults to enabled (true) — both while
 * the setting is loading and when it is unset — so existing deployments and the
 * initial render are unaffected; only an explicit `false` hides podcasts.
 */
export function usePodcastEnabled(): boolean {
  const { data } = useSettings()
  return data?.podcast_enabled !== false
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: Partial<SettingsResponse>) => settingsApi.update(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settings })
      toast({
        title: t('common.success'),
        description: t('common.saveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), 'common.error'),
        variant: 'destructive',
      })
    },
  })
}