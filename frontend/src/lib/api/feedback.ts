import apiClient from './client'
import {
  AdminFeedbackListParams,
  AdminFeedbackListResponse,
  AdminFeedbackStats,
  FeedbackState,
  ReportMessageRequest,
  SetReactionRequest,
} from '@/lib/types/api'

export const feedbackApi = {
  // Batch feedback state for every AI message in a session (owner only).
  getSessionFeedback: async (sessionId: string) => {
    const response = await apiClient.get<FeedbackState[]>(
      `/feedback/sessions/${sessionId}`
    )
    return response.data
  },

  // Set or clear a like/dislike (reaction=null clears it).
  setReaction: async (messageId: string, data: SetReactionRequest) => {
    const response = await apiClient.put<FeedbackState>(
      `/feedback/messages/${messageId}/reaction`,
      data
    )
    return response.data
  },

  // Report an AI answer (reason required).
  reportMessage: async (messageId: string, data: ReportMessageRequest) => {
    const response = await apiClient.post<FeedbackState>(
      `/feedback/messages/${messageId}/report`,
      data
    )
    return response.data
  },

  // Admin: aggregate stats.
  getAdminStats: async () => {
    const response = await apiClient.get<AdminFeedbackStats>(
      `/feedback/admin/stats`
    )
    return response.data
  },

  // Admin: paginated/filtered list.
  getAdminList: async (params: AdminFeedbackListParams) => {
    const response = await apiClient.get<AdminFeedbackListResponse>(
      `/feedback/admin`,
      { params }
    )
    return response.data
  },
}

export default feedbackApi
