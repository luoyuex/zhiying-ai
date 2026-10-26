export interface User {
  id: string
  email: string
  nickname: string
  role: string
  status: string
  email_verified_at: string | null
  daily_analysis_quota: number
  avatar_url: string | null
  created_at: string
}

export type OtpPurpose = 'register' | 'login' | 'reset'

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface SendCodeResponse {
  sent: boolean
  expires_in: number
  cooldown: number
  message: string
}

export interface ApiErrorBody {
  code: string
  message: string
  detail?: unknown
}
