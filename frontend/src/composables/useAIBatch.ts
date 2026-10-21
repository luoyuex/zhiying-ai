import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { aiApi, type AIJobState } from '@/api/ai'
import { watchlistApi, type WatchlistJobState } from '@/api/watchlist'
import { getErrorMessage } from '@/utils/errors'

const POLL_INTERVAL = 2500
const POLL_MAX_FAILURES = 5

export interface AIBatchOptions {
  /** 提供后会把待轮询 job 写入 sessionStorage，刷新后可恢复 */
  storageKey?: () => string
  /** 单只任务成功时回调，用于把结果写回列表 */
  onSucceeded?: (symbol: string, job: AIJobState) => void
  /** 所有任务结束后回调（成功或失败） */
  onAllDone?: () => void | Promise<void>
}

/** 批量 AI 分析：提交、逐只轮询、失败重试与状态回收。 */
export function useAIBatch(options: AIBatchOptions = {}) {
  const jobStates = ref<Record<string, WatchlistJobState>>({})
  const pendingJobs = ref<Record<string, string>>({})
  const submitting = ref(false)
  const error = ref('')
  const pendingCount = computed(() => Object.keys(pendingJobs.value).length)
  const pollFailures: Record<string, number> = {}
  let pollTimer: ReturnType<typeof setTimeout> | null = null

  if (options.storageKey) {
    const storageKey = options.storageKey
    watch(
      pendingJobs,
      (value) => {
        try {
          if (Object.keys(value).length) {
            sessionStorage.setItem(storageKey(), JSON.stringify(value))
          } else {
            sessionStorage.removeItem(storageKey())
          }
        } catch {
          // 隐私模式等场景下 sessionStorage 不可用，忽略即可
        }
      },
      { deep: true },
    )
  }

  function schedulePoll(delay = POLL_INTERVAL): void {
    if (pollTimer !== null) return
    pollTimer = setTimeout(() => {
      pollTimer = null
      void pollJobs()
    }, delay)
  }

  async function pollJobs(): Promise<void> {
    const pending = Object.entries(pendingJobs.value)
    if (!pending.length) return

    await Promise.all(
      pending.map(async ([symbol, jobId]) => {
        try {
          const { data } = await aiApi.job(jobId)
          if (pendingJobs.value[symbol] !== jobId) return
          delete pollFailures[symbol]

          if (data.status === 'succeeded') {
            delete pendingJobs.value[symbol]
            jobStates.value[symbol] = { status: 'succeeded' }
            options.onSucceeded?.(symbol, data)
          } else if (data.status === 'failed') {
            delete pendingJobs.value[symbol]
            jobStates.value[symbol] = {
              status: 'failed',
              message: data.error_message || '分析失败',
            }
          } else {
            jobStates.value[symbol] = { status: data.status, phase: data.phase }
          }
        } catch {
          if (pendingJobs.value[symbol] !== jobId) return
          pollFailures[symbol] = (pollFailures[symbol] ?? 0) + 1
          if (pollFailures[symbol] >= POLL_MAX_FAILURES) {
            delete pendingJobs.value[symbol]
            jobStates.value[symbol] = {
              status: 'failed',
              message: '任务状态查询失败',
            }
          }
        }
      }),
    )

    if (Object.keys(pendingJobs.value).length) {
      schedulePoll()
    } else {
      await options.onAllDone?.()
    }
  }

  async function submit(symbols: string[], force = false): Promise<void> {
    if (!symbols.length || submitting.value) return
    submitting.value = true
    error.value = ''
    try {
      const { data } = await watchlistApi.batchAnalysis(symbols, force)
      for (const result of data) {
        if (result.status === 'failed') {
          jobStates.value[result.symbol] = {
            status: 'failed',
            message: result.error_message || result.error_code || '提交分析失败',
          }
        } else if (result.job_id) {
          jobStates.value[result.symbol] = { status: 'queued' }
          pendingJobs.value[result.symbol] = result.job_id
        }
      }
      if (pendingCount.value) schedulePoll(0)
    } catch (err) {
      error.value = getErrorMessage(err, '批量分析提交失败')
    } finally {
      submitting.value = false
    }
  }

  /** 从 sessionStorage 恢复待轮询任务；只保留仍在列表中的股票 */
  function restore(symbols: string[]): void {
    if (!options.storageKey) return
    try {
      const raw = sessionStorage.getItem(options.storageKey())
      if (!raw) return
      const saved = JSON.parse(raw) as Record<string, unknown>
      const entries = Object.entries(saved).filter(
        ([symbol, jobId]) =>
          typeof jobId === 'string' && jobId.length > 0 && symbols.includes(symbol),
      )
      if (!entries.length) {
        sessionStorage.removeItem(options.storageKey())
        return
      }
      for (const [symbol, jobId] of entries) {
        pendingJobs.value[symbol] = jobId as string
        jobStates.value[symbol] = { status: 'queued' }
      }
      schedulePoll(0)
    } catch {
      // 存储内容损坏时直接忽略，不阻塞页面
    }
  }

  function clearSymbol(symbol: string): void {
    delete pendingJobs.value[symbol]
    delete jobStates.value[symbol]
    delete pollFailures[symbol]
  }

  function stop(): void {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  onBeforeUnmount(stop)

  return {
    jobStates,
    pendingJobs,
    pendingCount,
    submitting,
    error,
    submit,
    restore,
    clearSymbol,
    stop,
  }
}
