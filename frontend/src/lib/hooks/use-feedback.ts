'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { feedbackApi } from '@/lib/api/feedback'
import { useAuth } from '@/lib/hooks/use-auth'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  AdminFeedbackListParams,
  FeedbackReaction,
  FeedbackState,
} from '@/lib/types/api'

// Per-user, per-session cache key so one account's feedback state can never be
// served to another from React Query's cache (defense in depth, mirroring the
// chat hooks' userId scoping).
export const sessionFeedbackKey = (sessionId: string | null, userId: string) =>
  ['feedback', 'session', sessionId, userId] as const

/** Batch feedback state for every AI message in a session (one request). */
export function useSessionFeedback(sessionId: string | null, enabled: boolean) {
  const { user } = useAuth()
  const userId = user?.id ?? 'anon'
  return useQuery<FeedbackState[]>({
    queryKey: sessionFeedbackKey(sessionId, userId),
    queryFn: () => feedbackApi.getSessionFeedback(sessionId as string),
    enabled: Boolean(sessionId) && enabled,
  })
}

interface ReactionVars {
  messageId: string
  reaction: FeedbackReaction
}

/** Set/clear a like or dislike with optimistic UI + rollback on failure. */
export function useSetReaction(sessionId: string | null) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { t } = useTranslation()
  const userId = user?.id ?? 'anon'
  const key = sessionFeedbackKey(sessionId, userId)

  return useMutation({
    mutationFn: ({ messageId, reaction }: ReactionVars) =>
      feedbackApi.setReaction(messageId, {
        session_id: sessionId as string,
        reaction,
      }),
    onMutate: async ({ messageId, reaction }: ReactionVars) => {
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<FeedbackState[]>(key)
      const hadPrevious = previous !== undefined
      queryClient.setQueryData<FeedbackState[]>(key, (old) => {
        const list = old ? [...old] : []
        const idx = list.findIndex((f) => f.message_id === messageId)
        if (idx >= 0) {
          list[idx] = { ...list[idx], reaction }
        } else {
          list.push({ message_id: messageId, reaction, reported: false })
        }
        return list
      })
      return { previous, hadPrevious }
    },
    onError: (_err, _vars, context) => {
      // Roll back to the exact pre-mutation state. If the cache held nothing
      // before (hadPrevious === false), drop the optimistic data entirely so no
      // ghost entry survives a failed mutation.
      if (context?.hadPrevious) {
        queryClient.setQueryData(key, context.previous)
      } else {
        queryClient.removeQueries({ queryKey: key, exact: true })
      }
      toast.error(t('feedback.failed'))
    },
    onSuccess: (data) => {
      // Reconcile with server truth. When the server reports no reaction AND no
      // report, the row was deleted server-side — remove the entry instead of
      // keeping a {reaction:null, reported:false} ghost.
      const deleted = data.reaction === null && data.reported === false
      queryClient.setQueryData<FeedbackState[]>(key, (old) => {
        const list = old ? [...old] : []
        const idx = list.findIndex((f) => f.message_id === data.message_id)
        if (deleted) {
          return idx >= 0 ? list.filter((f) => f.message_id !== data.message_id) : list
        }
        if (idx >= 0) list[idx] = data
        else list.push(data)
        return list
      })
      toast.success(t('feedback.saved'))
    },
  })
}

interface ReportVars {
  messageId: string
  reason: string
}

/** Report an AI answer. Independent of the reaction. */
export function useReportMessage(sessionId: string | null) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { t } = useTranslation()
  const userId = user?.id ?? 'anon'
  const key = sessionFeedbackKey(sessionId, userId)

  return useMutation({
    mutationFn: ({ messageId, reason }: ReportVars) =>
      feedbackApi.reportMessage(messageId, {
        session_id: sessionId as string,
        reason,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData<FeedbackState[]>(key, (old) => {
        const list = old ? [...old] : []
        const idx = list.findIndex((f) => f.message_id === data.message_id)
        if (idx >= 0) list[idx] = data
        else list.push(data)
        return list
      })
      toast.success(t('feedback.reportSubmitted'))
    },
    onError: () => {
      toast.error(t('feedback.failed'))
    },
  })
}

// --- admin ----------------------------------------------------------------
export const FEEDBACK_ADMIN_KEYS = {
  stats: ['feedback', 'admin', 'stats'] as const,
  list: (params: AdminFeedbackListParams) =>
    ['feedback', 'admin', 'list', params] as const,
}

export function useAdminFeedbackStats(enabled = true) {
  return useQuery({
    queryKey: FEEDBACK_ADMIN_KEYS.stats,
    queryFn: () => feedbackApi.getAdminStats(),
    enabled,
  })
}

export function useAdminFeedbackList(
  params: AdminFeedbackListParams,
  enabled = true
) {
  return useQuery({
    queryKey: FEEDBACK_ADMIN_KEYS.list(params),
    queryFn: () => feedbackApi.getAdminList(params),
    enabled,
  })
}
