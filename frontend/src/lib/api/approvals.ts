import apiClient from './client'

export interface ApprovalNotebookRef {
  id: string
  name: string
}

export interface ApprovalItem {
  id: string
  title?: string | null
  type?: string | null
  approval_status: string
  submitted_by_id?: string | null
  submitted_by_name?: string | null
  submitted_at?: string | null
  notebooks: ApprovalNotebookRef[]
}

export interface PendingApprovalCount {
  count: number
}

export interface ReviewActionResponse {
  success: boolean
  source_id: string
  approval_status: string
  message: string
}

export interface Reviewer {
  id: string
  username: string
  name?: string | null
}

export const approvalsApi = {
  listPending: async () => {
    const response = await apiClient.get<ApprovalItem[]>('/approvals/pending')
    return response.data
  },

  count: async () => {
    const response = await apiClient.get<PendingApprovalCount>('/approvals/count')
    return response.data
  },

  approve: async (sourceId: string) => {
    const response = await apiClient.post<ReviewActionResponse>(
      `/approvals/sources/${sourceId}/approve`
    )
    return response.data
  },

  reject: async (sourceId: string, reason?: string) => {
    const response = await apiClient.post<ReviewActionResponse>(
      `/approvals/sources/${sourceId}/reject`,
      { reason: reason ?? null }
    )
    return response.data
  },

  reviewers: async (notebookIds: string[]) => {
    const params = new URLSearchParams()
    notebookIds.forEach((id) => params.append('notebook_id', id))
    const qs = params.toString()
    const response = await apiClient.get<Reviewer[]>(
      `/approvals/reviewers${qs ? `?${qs}` : ''}`
    )
    return response.data
  },
}
