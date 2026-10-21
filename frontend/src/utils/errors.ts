import axios from 'axios'

export function getErrorMessage(error: unknown, fallback = '操作失败，请稍后重试'): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { message?: string } | undefined
    if (data?.message) return data.message
    if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试'
    if (!error.response) return '无法连接服务器，请确认后端服务已启动'
  }
  return fallback
}

export function getErrorCode(error: unknown): string | undefined {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { code?: string } | undefined
    return data?.code
  }
  return undefined
}

export function getRetryAfter(error: unknown): number | undefined {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { detail?: { retry_after?: number } } | undefined
    return data?.detail?.retry_after
  }
  return undefined
}
