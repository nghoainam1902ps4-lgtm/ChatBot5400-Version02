import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ocrApi } from '@/lib/api/ocr'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import type { OcrEngineId, OcrEnginesResponse } from '@/lib/types/api'

const ACTIVE_STATES = new Set(['pending', 'downloading', 'installing'])

/** True while any engine has an install job in flight (drives polling). */
export function hasActiveOcrJob(data?: OcrEnginesResponse): boolean {
  return !!data?.engines.some((e) => ACTIVE_STATES.has(e.state) || !!e.readiness_job)
}

export function useOcrEngines() {
  return useQuery({
    queryKey: QUERY_KEYS.ocrEngines,
    queryFn: () => ocrApi.list(),
    // Poll only while a download/install runs, so progress is real, not simulated.
    refetchInterval: (query) => (hasActiveOcrJob(query.state.data) ? 2000 : false),
  })
}

function useOcrMutation<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  successKey?: string,
) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.ocrEngines })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settings })
      if (successKey) toast({ title: t('common.success'), description: t(successKey) })
    },
    onError: (error: unknown) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.ocrEngines })
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), 'common.error'),
        variant: 'destructive',
      })
    },
  })
}

export const useInstallOcrEngine = () =>
  useOcrMutation((id: OcrEngineId) => ocrApi.install(id), 'ocr.installQueued')
export const useActivateOcrEngine = () =>
  useOcrMutation((id: OcrEngineId) => ocrApi.activate(id), 'ocr.activated')
export const useRemoveOcrModel = () =>
  useOcrMutation((id: OcrEngineId) => ocrApi.removeModel(id), 'ocr.modelRemoved')
export const usePrepareOcrEngine = () =>
  useOcrMutation((id: OcrEngineId) => ocrApi.prepare(id), 'ocr.readiness.prepareQueued')
export const useOcrReadinessCheck = () =>
  useOcrMutation((id: OcrEngineId) => ocrApi.readinessCheck(id), 'ocr.readiness.checkQueued')
export const useTestOcrEngine = () => useOcrMutation((id: OcrEngineId) => ocrApi.test(id))
export const useUpdateOcrConfig = () =>
  useOcrMutation((data: Parameters<typeof ocrApi.updateConfig>[0]) => ocrApi.updateConfig(data), 'common.saveSuccess')

/** Poll an OCR job until it finishes. */
export function useOcrJob(jobId: string | null) {
  return useQuery({
    queryKey: ['ocr', 'job', jobId],
    queryFn: () => ocrApi.job(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'completed' || s === 'failed' || s === 'canceled' ? false : 2000
    },
  })
}
