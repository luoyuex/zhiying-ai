import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

let accessToken: string | null = null
let refreshPromise: Promise<string | null> | null = null
let sessionExpiredHandler: (() => void) | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  sessionExpiredHandler = handler
}

export const http = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status
    const url = config?.url ?? ''

    // refresh 接口本身失败、或已重试过，直接抛出，避免死循环
    if (status !== 401 || !config || config._retry || url.includes('/auth/refresh')) {
      throw error
    }

    config._retry = true
    const token = await refreshAccessToken()
    if (!token) {
      sessionExpiredHandler?.()
      throw error
    }

    config.headers.Authorization = `Bearer ${token}`
    return http(config)
  },
)

/** 单飞刷新：并发请求共享同一次 refresh */
export function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post<{ access_token: string }>('/api/v1/auth/refresh', null, {
        withCredentials: true,
        timeout: 15000,
      })
      .then((response) => {
        const token = response.data.access_token
        setAccessToken(token)
        return token
      })
      .catch(() => {
        setAccessToken(null)
        return null
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}
