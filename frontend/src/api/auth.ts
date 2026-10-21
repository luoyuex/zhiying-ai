import { http } from './client'
import type { AuthResponse, OtpPurpose, SendCodeResponse, User } from '@/types/auth'

export const authApi = {
  sendCode(email: string, purpose: OtpPurpose) {
    return http.post<SendCodeResponse>('/auth/email/send-code', { email, purpose })
  },

  register(payload: { email: string; code: string; password: string; nickname: string }) {
    return http.post<AuthResponse>('/auth/register', payload)
  },

  login(payload: { email: string; password: string }) {
    return http.post<AuthResponse>('/auth/login', payload)
  },

  loginByCode(payload: { email: string; code: string }) {
    return http.post<AuthResponse>('/auth/login/code', payload)
  },

  resetPassword(payload: { email: string; code: string; new_password: string }) {
    return http.post<{ ok: boolean; message: string }>('/auth/password/reset', payload)
  },

  refresh() {
    return http.post<AuthResponse>('/auth/refresh')
  },

  logout() {
    return http.post<{ ok: boolean; message: string }>('/auth/logout')
  },

  me() {
    return http.get<User>('/auth/me')
  },
}
