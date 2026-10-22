import { onBeforeUnmount, onMounted, ref } from 'vue'

import {
  screenerApi,
  type ScreenerAnalysisRequest,
  type ScreenerAnalysisResponse,
  type ScreenerJobState,
  type ScreenerRecordDetail,
  type ScreenerRecordSummary,
  type ScreenerStrategyId,
} from '@/api/screener'
import { getErrorMessage } from '@/utils/errors'

interface Options {
  strategy: ScreenerStrategyId
  applyFilters: (filters: Record<string, unknown>) => void
}

export function useScreenerAI(options: Options) {
  const loading = ref(false)
  const restoring = ref(false)
  const error = ref('')
  const analysis = ref<ScreenerAnalysisResponse | null>(null)
  const job = ref<ScreenerJobState | null>(null)

  // 本地平滑计时：轮询间隔 2s，直接绑定 job.elapsed_seconds 会出现跳秒，
  // 这里每秒 +1，轮询返回时用服务端值做单调校准（只增不减）。
  const displayElapsed = ref(0)
  let elapsedTimer: ReturnType<typeof setInterval> | null = null

  function syncElapsed(value: number): void {
    displayElapsed.value = Math.max(displayElapsed.value, value)
  }

  function startElapsedTimer(): void {
    if (elapsedTimer === null) {
      elapsedTimer = setInterval(() => {
        if (loading.value) displayElapsed.value += 1
      }, 1000)
    }
  }

  function stopElapsedTimer(): void {
    if (elapsedTimer !== null) {
      clearInterval(elapsedTimer)
      elapsedTimer = null
    }
  }

  const records = ref<ScreenerRecordSummary[]>([])
  const recordsLoading = ref(false)
  const recordsError = ref('')
  const activeRecordId = ref<string | null>(null)

  const detailOpen = ref(false)
  const detailLoading = ref(false)
  const detailError = ref('')
  const detailRecord = ref<ScreenerRecordDetail | null>(null)
  const detailRecordId = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let pollFailures = 0
  let disposed = false
  let detailToken = 0

  async function loadRecords(): Promise<void> {
    recordsLoading.value = true
    recordsError.value = ''
    try {
      const { data } = await screenerApi.records(options.strategy, 10)
      records.value = data
    } catch (err) {
      records.value = []
      recordsError.value = getErrorMessage(err, '历史记录加载失败')
    } finally {
      recordsLoading.value = false
    }
  }

  async function loadRecord(recordId: string): Promise<void> {
    if (loading.value || restoring.value) return
    restoring.value = true
    error.value = ''
    try {
      const { data } = await screenerApi.record(recordId)
      analysis.value = data.result
      options.applyFilters(data.filters)
      activeRecordId.value = data.id
    } catch (err) {
      error.value = getErrorMessage(err, '选股记录加载失败')
    } finally {
      restoring.value = false
    }
  }

  async function openRecordDetail(recordId: string): Promise<void> {
    const token = ++detailToken
    detailOpen.value = true
    detailRecordId.value = recordId
    detailRecord.value = null
    detailError.value = ''
    detailLoading.value = true
    try {
      const { data } = await screenerApi.record(recordId)
      if (token !== detailToken) return
      detailRecord.value = data
    } catch (err) {
      if (token !== detailToken) return
      detailError.value = getErrorMessage(err, '选股记录加载失败')
    } finally {
      if (token === detailToken) detailLoading.value = false
    }
  }

  function closeRecordDetail(): void {
    detailToken += 1
    detailOpen.value = false
    detailRecordId.value = null
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function schedulePoll(delay = 2000): void {
    if (disposed) return
    stopPolling()
    pollTimer = setTimeout(() => {
      void pollJob()
    }, delay)
  }

  async function onJobSucceeded(state: ScreenerJobState): Promise<void> {
    await loadRecords()
    if (!state.record_id) {
      error.value = '选股完成但没有生成记录，请重新发起'
      return
    }
    await loadRecord(state.record_id)
  }

  async function pollJob(): Promise<void> {
    if (disposed) return
    const current = job.value
    if (!current) return
    try {
      const { data } = await screenerApi.jobState(current.job_id)
      pollFailures = 0
      job.value = data
      syncElapsed(data.elapsed_seconds)
      if (data.status === 'succeeded') {
        stopPolling()
        loading.value = false
        await onJobSucceeded(data)
        return
      }
      if (data.status === 'failed') {
        stopPolling()
        loading.value = false
        error.value = data.error_message || 'AI 选股失败，请稍后重试'
        return
      }
      schedulePoll()
    } catch (err) {
      pollFailures += 1
      if (pollFailures >= 3) {
        stopPolling()
        loading.value = false
        error.value = getErrorMessage(err, '选股任务状态获取失败，请刷新页面重试')
        return
      }
      schedulePoll()
    }
  }

  async function init(): Promise<void> {
    await loadRecords()
    try {
      const { data } = await screenerApi.activeJob(options.strategy)
      if (data) {
        job.value = data
        syncElapsed(data.elapsed_seconds)
        if (data.status === 'queued' || data.status === 'running') {
          loading.value = true
          schedulePoll(0)
          return
        }
        if (data.status === 'succeeded' && data.record_id) {
          await loadRecord(data.record_id)
          return
        }
        if (data.status === 'failed') {
          error.value = data.error_message || '上次 AI 选股失败，请重新发起'
          return
        }
      }
    } catch {
      // 活跃任务查询失败时退回最近一次记录
    }
    if (records.value.length) await loadRecord(records.value[0].id)
  }

  async function run(payload: ScreenerAnalysisRequest): Promise<void> {
    if (loading.value || restoring.value) return
    loading.value = true
    error.value = ''
    analysis.value = null
    activeRecordId.value = null
    job.value = null
    displayElapsed.value = 0
    try {
      const { data } = await screenerApi.startJob(options.strategy, payload)
      job.value = data
      syncElapsed(data.elapsed_seconds)
      if (data.status === 'succeeded') {
        loading.value = false
        await onJobSucceeded(data)
        return
      }
      if (data.status === 'failed') {
        loading.value = false
        error.value = data.error_message || 'AI 选股失败，请稍后重试'
        return
      }
      schedulePoll()
    } catch (err) {
      loading.value = false
      error.value = getErrorMessage(err, 'AI 选股发起失败，请稍后重试')
    }
  }

  onMounted(() => {
    startElapsedTimer()
    void init()
  })

  onBeforeUnmount(() => {
    disposed = true
    stopPolling()
    stopElapsedTimer()
  })

  return {
    loading,
    restoring,
    error,
    analysis,
    job,
    displayElapsed,
    records,
    recordsLoading,
    recordsError,
    activeRecordId,
    detailOpen,
    detailLoading,
    detailError,
    detailRecord,
    detailRecordId,
    run,
    openRecordDetail,
    closeRecordDetail,
  }
}
