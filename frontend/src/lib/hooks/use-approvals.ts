import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '@/lib/api/approvals'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'

export const APPROVAL_QUERY_KEYS = {
  all: ['approvals'] as const,
  pending: ['approvals', 'pending'] as const,
  count: ['approvals', 'count'] as const,
}

/** Pending-approval badge count. Only enabled for reviewers (approver/admin). */
export function useApprovalCount(enabled = true) {
  return useQuery({
    queryKey: APPROVAL_QUERY_KEYS.count,
    queryFn: async () => (await approvalsApi.count()).count,
    enabled,
    // Keep the badge reasonably fresh without hammering the API.
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
}

/** The list of sources awaiting the current reviewer's action. */
export function usePendingApprovals(enabled = true) {
  return useQuery({
    queryKey: APPROVAL_QUERY_KEYS.pending,
    queryFn: () => approvalsApi.listPending(),
    enabled,
  })
}

export function useApproveSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (sourceId: string) => approvalsApi.approve(sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: APPROVAL_QUERY_KEYS.all })
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      toast({
        title: t('common.success'),
        description: t('approvals.approvedDone'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('approvals.actionError')),
        variant: 'destructive',
      })
    },
  })
}

export function useRejectSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ sourceId, reason }: { sourceId: string; reason?: string }) =>
      approvalsApi.reject(sourceId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: APPROVAL_QUERY_KEYS.all })
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      toast({
        title: t('common.success'),
        description: t('approvals.rejectedDone'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('approvals.actionError')),
        variant: 'destructive',
      })
    },
  })
}
