export type UserRole = 'admin' | 'user'

export interface User {
  id: string
  username: string
  role: UserRole
  name?: string | null
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
