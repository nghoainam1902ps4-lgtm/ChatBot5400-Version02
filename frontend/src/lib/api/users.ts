import apiClient from './client'
import type { User, UserRole } from '@/lib/types/auth'

export interface CreateUserRequest {
  username: string
  password: string
  role: UserRole
  name?: string | null
}

export interface UpdateUserRequest {
  username?: string
  role?: UserRole
  name?: string | null
}

export const usersApi = {
  list: async () => {
    const response = await apiClient.get<User[]>('/users')
    return response.data
  },

  create: async (data: CreateUserRequest) => {
    const response = await apiClient.post<User>('/users', data)
    return response.data
  },

  update: async (id: string, data: UpdateUserRequest) => {
    const response = await apiClient.put<User>(`/users/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await apiClient.delete(`/users/${id}`)
  },

  resetPassword: async (id: string, newPassword: string) => {
    await apiClient.post(`/users/${id}/reset-password`, {
      new_password: newPassword,
    })
  },
}

export const accountApi = {
  changePassword: async (currentPassword: string, newPassword: string) => {
    await apiClient.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  },
}
