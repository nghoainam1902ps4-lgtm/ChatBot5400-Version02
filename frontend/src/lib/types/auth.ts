export type UserRole = 'admin' | 'approver' | 'contributor' | 'user'

// Roles allowed to submit sources/văn bản into the system.
export const SUBMITTER_ROLES: UserRole[] = ['admin', 'approver', 'contributor']
// Roles allowed to review pending submissions and manage categories.
export const APPROVER_ROLES: UserRole[] = ['admin', 'approver']

export interface User {
  id: string
  username: string
  role: UserRole
  name?: string | null
  language?: string | null
  theme?: string | null
  created?: string | null
  updated?: string | null
}

export interface AuthState {
  isAuthenticated: boolean
  token: string | null
  user: User | null
  isLoading: boolean
  error: string | null
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}
