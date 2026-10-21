import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { authApi } from '@/api/auth'
import { setAccessToken, setSessionExpiredHandler } from '@/api/client'
import type { AuthResponse, User } from '@/types/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const bootstrapped = ref(false)

  const isAuthenticated = computed(() => user.value !== null)

  setSessionExpiredHandler(() => {
    setAccessToken(null)
    user.value = null
  })

  function applySession(payload: AuthResponse): void {
    setAccessToken(payload.access_token)
    user.value = payload.user
  }

  function clearSession(): void {
    setAccessToken(null)
    user.value = null
  }

  /** 首次进入应用时尝试用 httpOnly Cookie 恢复会话 */
  async function bootstrap(): Promise<void> {
    if (bootstrapped.value) return
    bootstrapped.value = true
    try {
      const { data } = await authApi.refresh()
      applySession(data)
    } catch {
      clearSession()
    }
  }

  async function loginWithPassword(email: string, password: string): Promise<void> {
    const { data } = await authApi.login({ email, password })
    applySession(data)
  }

  async function loginWithCode(email: string, code: string): Promise<void> {
    const { data } = await authApi.loginByCode({ email, code })
    applySession(data)
  }

  async function register(payload: {
    email: string
    code: string
    password: string
    nickname: string
  }): Promise<void> {
    const { data } = await authApi.register(payload)
    applySession(data)
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } finally {
      clearSession()
    }
  }

  return {
    user,
    bootstrapped,
    isAuthenticated,
    bootstrap,
    loginWithPassword,
    loginWithCode,
    register,
    logout,
    clearSession,
  }
})
