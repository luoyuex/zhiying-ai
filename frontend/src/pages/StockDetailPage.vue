<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  aiApi,
  streamJob,
  type AIAnalysisResponse,
  type AIConfig,
  type AIJobState,
} from '@/api/ai'
import { marketApi, type KlineSeries, type Quote, type TechnicalAnalysis } from '@/api/market'
import { reportsApi, type ReportSummary } from '@/api/reports'
import { watchlistApi } from '@/api/watchlist'
import AppShell from '@/components/layout/AppShell.vue'
import MiniKline from '@/components/market/MiniKline.vue'
import DiscussionTimeline from '@/components/report/DiscussionTimeline.vue'
import PublicInfoPanel from '@/components/report/PublicInfoPanel.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getErrorCode, getErrorMessage } from '@/utils/errors'
import {
  formatChange,
  formatQuoteTime,
  quoteMetrics,
  quoteToneClass,
  sourceLabel,
} from '@/utils/market'

const PERIODS = [
  { value: 'day', label: '日 K' },
  { value: 'week', label: '周 K' },
  { value: 'month', label: '月 K' },
] as const

const ADJUSTS = [
  { value: 'qfq', label: '前复权' },
  { value: 'hfq', label: '后复权' },
  { value: 'none', label: '不复权' },
] as const

type PeriodValue = (typeof PERIODS)[number]['value']
type AdjustValue = (typeof ADJUSTS)[number]['value']

const route = useRoute()
const router = useRouter()

const code = computed(() => String(route.params.symbol ?? '').trim())
const validCode = computed(() => /^\d{6}$/.test(code.value))

const searchSymbol = ref('')
const quote = ref<Quote | null>(null)
const kline = ref<KlineSeries | null>(null)
const analysis = ref<TechnicalAnalysis | null>(null)
const loadingQuote = ref(false)
const loadingKline = ref(false)
const loadingAnalysis = ref(false)
const error = ref('')
const chartError = ref('')
const analysisError = ref('')
const aiConfig = ref<AIConfig | null>(null)
const aiConfigLoading = ref(false)
const aiConfigError = ref('')
const aiReport = ref<AIAnalysisResponse | null>(null)
const aiLoading = ref(false)
const aiError = ref('')
const aiJobId = ref<string | null>(null)
const aiPhase = ref('')
const aiElapsed = ref(0)
const history = ref<ReportSummary[]>([])
const historyLoading = ref(false)
const historyError = ref('')
const watchlisted = ref(false)
const watchlistBusy = ref(false)
let aiPollTimer: ReturnType<typeof setTimeout> | null = null
let aiElapsedTimer: ReturnType<typeof setInterval> | null = null
let aiStreamAbort: AbortController | null = null
const period = ref<PeriodValue>('day')
const adjust = ref<AdjustValue>('qfq')
let quoteSeq = 0
let klineSeq = 0
let analysisSeq = 0
let aiRequestSeq = 0

const tone = computed(() => quoteToneClass(quote.value?.change_pct))
const changeText = computed(() => formatChange(quote.value))
const metrics = computed(() => (quote.value ? quoteMetrics(quote.value) : []))
const fetchedTime = computed(() => formatQuoteTime(quote.value?.fetched_at))
const periodLabel = computed(() => PERIODS.find((item) => item.value === period.value)?.label ?? '')
const adjustLabel = computed(() => ADJUSTS.find((item) => item.value === adjust.value)?.label ?? '')
const chartTitle = computed(() => {
  if (period.value === 'week') return '近 60 周'
  if (period.value === 'month') return '近 60 个月'
  return '近 60 个交易日'
})

const ratingTone = computed(() => {
  const rating = analysis.value?.rating
  if (rating === '强势' || rating === '偏强') return 'text-up'
  if (rating === '弱势' || rating === '偏弱') return 'text-down'
  return 'text-ink-2'
})

const ratingBadge = computed(() => {
  const rating = analysis.value?.rating
  if (rating === '强势' || rating === '偏强') return 'bg-up-soft text-up'
  if (rating === '弱势' || rating === '偏弱') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
})

const ratingBar = computed(() => {
  const rating = analysis.value?.rating
  if (rating === '强势' || rating === '偏强') return 'bg-up'
  if (rating === '弱势' || rating === '偏弱') return 'bg-down'
  return 'bg-flat'
})

const levelItems = computed(() => {
  const levels = analysis.value?.levels
  if (!levels) return []
  return [
    { label: '支撑位', value: levels.support.toFixed(2), tone: 'text-ink' },
    { label: '压力位', value: levels.resistance.toFixed(2), tone: 'text-ink' },
    { label: '建议入场', value: levels.entry.toFixed(2), tone: 'text-primary' },
    { label: '止盈', value: levels.take_profit.toFixed(2), tone: 'text-up' },
    { label: '止损', value: levels.stop_loss.toFixed(2), tone: 'text-down' },
    { label: '盈亏比', value: `${levels.risk_reward.toFixed(2)} : 1`, tone: 'text-ink' },
  ]
})

const indicatorItems = computed(() => {
  const indicators = analysis.value?.indicators
  if (!indicators) return []
  const value = (value: number | null, digits: number): string =>
    value == null ? '—' : value.toFixed(digits)
  return [
    { label: 'MA5', value: value(indicators.ma5, 2) },
    { label: 'MA10', value: value(indicators.ma10, 2) },
    { label: 'MA20', value: value(indicators.ma20, 2) },
    { label: 'MA60', value: value(indicators.ma60, 2) },
    { label: 'RSI14', value: value(indicators.rsi14, 1) },
    { label: 'MACD 柱', value: value(indicators.macd_hist, 3) },
    { label: 'ATR14', value: value(indicators.atr14, 2) },
    { label: '量比', value: value(indicators.volume_ratio, 2) },
  ]
})

const signalTone = (direction: string): string => {
  if (direction === 'bullish') return 'bg-up'
  if (direction === 'bearish') return 'bg-down'
  return 'bg-flat'
}

const analysisSource = computed(() => {
  if (!analysis.value) return ''
  return analysis.value.source
    .split('/')
    .map((part) => sourceLabel(part.trim()))
    .join(' / ')
})

const aiBadgeClass = computed(() => {
  const rating = aiReport.value?.analysis.rating
  if (rating === '看多' || rating === '偏多') return 'bg-up-soft text-up'
  if (rating === '看空' || rating === '偏空') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
})

const aiBarClass = computed(() => {
  const rating = aiReport.value?.analysis.rating
  if (rating === '看多' || rating === '偏多') return 'bg-up'
  if (rating === '看空' || rating === '偏空') return 'bg-down'
  return 'bg-flat'
})

const aiQuotaLeft = computed(() => {
  const config = aiConfig.value
  if (!config) return null
  return Math.max(config.daily_quota - config.quota_used, 0)
})

const aiGeneratedTime = computed(() => formatQuoteTime(aiReport.value?.generated_at))

const dataGaps = computed(() => {
  const gaps = new Set<string>()
  for (const analyst of aiReport.value?.analysts ?? []) {
    for (const missing of analyst.missing) {
      gaps.add(missing)
    }
  }
  return Array.from(gaps)
})

const coverageLabels = computed(() => {
  const report = aiReport.value
  const labels = ['行情', '技术指标']
  if (!report?.analysts?.length) {
    if (report?.web_search_used) labels.push('公开网页')
    return labels
  }
  const missing = new Set(dataGaps.value)
  if (!missing.has('财务/季报')) labels.push('财务/季报')
  if (!missing.has('资金流')) labels.push('资金流')
  if (!missing.has('情绪')) labels.push('情绪')
  if (report.web_search_used) labels.push('公开网页')
  return labels
})

const decisionBadgeClass = computed(() => {
  const rating = aiReport.value?.decision?.rating
  if (rating === '买入') return 'bg-up-soft text-up'
  if (rating === '卖出') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
})

const webUsedBy = computed(() =>
  (aiReport.value?.analysts ?? [])
    .filter((analyst) => analyst.data_sources.includes('元宝搜索'))
    .map((analyst) => `${analyst.name}分析师`),
)

const decisionLevels = computed(() => {
  const levels = aiReport.value?.decision?.levels
  if (!levels) return []
  return [
    { label: '建议入场', value: levels.entry.toFixed(2), tone: 'text-primary' },
    { label: '止盈', value: levels.take_profit.toFixed(2), tone: 'text-up' },
    { label: '止损', value: levels.stop_loss.toFixed(2), tone: 'text-down' },
    { label: '盈亏比', value: `${levels.risk_reward.toFixed(2)} : 1`, tone: 'text-ink' },
  ]
})

function analystTone(score: number): string {
  if (score >= 65) return 'text-up'
  if (score < 45) return 'text-down'
  return 'text-ink-2'
}

function formatReportTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadHistory(value: string): Promise<void> {
  if (!/^\d{6}$/.test(value)) {
    history.value = []
    return
  }
  historyLoading.value = true
  try {
    const { data } = await reportsApi.list(value, 6)
    history.value = data
    historyError.value = ''
  } catch (err) {
    historyError.value = getErrorMessage(err, '历史报告加载失败')
  } finally {
    historyLoading.value = false
  }
}

async function loadWatchlistState(value: string): Promise<void> {
  try {
    const { data } = await watchlistApi.status(value)
    if (data.symbol === code.value) watchlisted.value = data.in_watchlist
  } catch {
    watchlisted.value = false
  }
}

async function toggleWatchlist(): Promise<void> {
  const value = code.value
  if (watchlistBusy.value || !quote.value || !/^\d{6}$/.test(value)) return

  watchlistBusy.value = true
  const next = !watchlisted.value
  watchlisted.value = next
  try {
    if (next) await watchlistApi.add(value)
    else await watchlistApi.remove(value)
  } catch (err) {
    watchlisted.value = !next
    error.value = getErrorMessage(err, next ? '加入自选失败' : '移出自选失败')
  } finally {
    watchlistBusy.value = false
  }
}

async function loadAIConfig(): Promise<void> {
  aiConfigLoading.value = true
  try {
    const { data } = await aiApi.config()
    aiConfig.value = data
    aiConfigError.value = ''
  } catch (err) {
    aiConfigError.value = getErrorMessage(err, '无法获取 AI 配置')
  } finally {
    aiConfigLoading.value = false
  }
}

async function runAIAnalysis(): Promise<void> {
  await submitAIAnalysis(false)
}

async function rerunAIAnalysis(): Promise<void> {
  await submitAIAnalysis(true)
}

async function submitAIAnalysis(force: boolean): Promise<void> {
  if (aiLoading.value || !aiConfig.value?.configured || !quote.value) return
  stopAIPolling()
  const seq = ++aiRequestSeq
  aiLoading.value = true
  aiError.value = ''
  if (!force) {
    // 首次分析清空旧结果；重新诊断时保留当前报告，直到新结果返回
    aiReport.value = null
    aiJobId.value = null
  }
  aiPhase.value = force ? '提交重新诊断' : '提交任务'
  aiElapsed.value = 0
  startAIElapsedTimer()

  try {
    const { data } = await aiApi.startAnalysis(code.value, force)
    if (seq !== aiRequestSeq) return
    aiJobId.value = data.job_id
    if (applyAIJob(data)) return
    void openAIStream(data.job_id, seq)
  } catch (err) {
    if (seq !== aiRequestSeq) return
    aiError.value = getErrorMessage(err, '提交 AI 分析任务失败')
    aiLoading.value = false
    if (getErrorCode(err) === 'LLM_NOT_CONFIGURED') {
      void loadAIConfig()
    }
  }
}

function startAIElapsedTimer(): void {
  if (aiElapsedTimer === null) {
    aiElapsedTimer = setInterval(() => {
      if (aiLoading.value) aiElapsed.value += 1
    }, 1000)
  }
}

/** 进入详情页时接上该股票正在运行的分析（例如自选股批量分析发起的任务） */
async function resumeActiveAIJob(value: string): Promise<void> {
  const seq = aiRequestSeq
  try {
    const { data } = await aiApi.activeJob(value)
    if (!data || seq !== aiRequestSeq || value !== code.value) return
    // 用户已经手动发起任务时不覆盖当前状态
    if (aiLoading.value || aiJobId.value) return
    aiLoading.value = true
    aiError.value = ''
    aiJobId.value = data.job_id
    aiPhase.value = data.phase || '排队中'
    aiElapsed.value = data.elapsed_seconds
    startAIElapsedTimer()
    if (!applyAIJob(data)) void openAIStream(data.job_id, seq)
  } catch {
    // 没有活跃任务或接口暂不可用时保持空闲状态
  }
}

function stopAIPolling(): void {
  if (aiPollTimer !== null) {
    clearTimeout(aiPollTimer)
    aiPollTimer = null
  }
  if (aiElapsedTimer !== null) {
    clearInterval(aiElapsedTimer)
    aiElapsedTimer = null
  }
  if (aiStreamAbort !== null) {
    aiStreamAbort.abort()
    aiStreamAbort = null
  }
}

function schedulePollingFallback(): void {
  if (aiPollTimer !== null) clearTimeout(aiPollTimer)
  aiPollTimer = setTimeout(() => {
    void pollAIJob()
  }, 1500)
}

async function openAIStream(jobId: string, seq: number): Promise<void> {
  aiStreamAbort?.abort()
  const controller = new AbortController()
  aiStreamAbort = controller

  try {
    await streamJob(
      jobId,
      (event) => {
        if (seq !== aiRequestSeq || jobId !== aiJobId.value) return
        if (event.type === 'error') {
          schedulePollingFallback()
          return
        }
        if (event.job && applyAIJob(event.job)) {
          controller.abort()
        }
      },
      controller.signal,
    )

    // 流结束但任务未到终态（代理缓冲/服务重启），退回轮询
    if (seq === aiRequestSeq && jobId === aiJobId.value && aiLoading.value) {
      schedulePollingFallback()
    }
  } catch {
    if (controller.signal.aborted) return
    if (seq !== aiRequestSeq || jobId !== aiJobId.value) return
    schedulePollingFallback()
  }
}

function applyAIJob(job: AIJobState): boolean {
  aiPhase.value = job.phase
  aiElapsed.value = job.elapsed_seconds

  if (job.status === 'succeeded') {
    if (job.result) {
      aiReport.value = job.result
      if (aiConfig.value) {
        aiConfig.value = { ...aiConfig.value, quota_used: job.result.quota_used }
      }
      void loadHistory(job.result.symbol)
    }
    aiLoading.value = false
    stopAIPolling()
    return true
  }

  if (job.status === 'failed') {
    aiLoading.value = false
    aiError.value = job.error_message || 'AI 分析失败，请稍后重试'
    if (job.error_code === 'LLM_NOT_CONFIGURED') {
      void loadAIConfig()
    }
    if (job.error_code === 'ANALYSIS_QUOTA_EXCEEDED' && aiConfig.value) {
      aiConfig.value = { ...aiConfig.value, quota_used: aiConfig.value.daily_quota }
    }
    stopAIPolling()
    return true
  }

  aiLoading.value = true
  return false
}

async function pollAIJob(): Promise<void> {
  const jobId = aiJobId.value
  if (!jobId) return
  try {
    const { data } = await aiApi.job(jobId)
    if (jobId !== aiJobId.value) return
    if (applyAIJob(data)) return
  } catch (err) {
    if (jobId !== aiJobId.value) return
    aiError.value = getErrorMessage(err, '查询 AI 分析进度失败')
    aiLoading.value = false
    stopAIPolling()
    return
  }
  aiPollTimer = setTimeout(() => {
    void pollAIJob()
  }, 2000)
}

async function loadQuote(value: string): Promise<void> {
  const seq = ++quoteSeq
  loadingQuote.value = true
  try {
    const { data } = await marketApi.quote(value)
    if (seq === quoteSeq) quote.value = data
  } catch (err) {
    if (seq === quoteSeq) {
      quote.value = null
      error.value = getErrorMessage(err, '行情查询失败')
    }
  } finally {
    if (seq === quoteSeq) loadingQuote.value = false
  }
}

async function loadKline(value: string): Promise<void> {
  const seq = ++klineSeq
  loadingKline.value = true
  chartError.value = ''
  try {
    const { data } = await marketApi.kline(value, {
      period: period.value,
      adjust: adjust.value,
      limit: 90,
    })
    if (seq === klineSeq) kline.value = data
  } catch (err) {
    if (seq === klineSeq) {
      kline.value = null
      chartError.value = getErrorMessage(err, 'K 线加载失败')
    }
  } finally {
    if (seq === klineSeq) loadingKline.value = false
  }
}

async function loadAnalysis(value: string): Promise<void> {
  const seq = ++analysisSeq
  loadingAnalysis.value = true
  analysisError.value = ''
  try {
    const { data } = await marketApi.analysis(value)
    if (seq === analysisSeq) analysis.value = data
  } catch (err) {
    if (seq === analysisSeq) {
      analysis.value = null
      analysisError.value = getErrorMessage(err, '技术诊断生成失败')
    }
  } finally {
    if (seq === analysisSeq) loadingAnalysis.value = false
  }
}

async function loadAll(value: string): Promise<void> {
  stopAIPolling()
  aiRequestSeq += 1
  aiJobId.value = null
  aiPhase.value = ''
  aiElapsed.value = 0
  aiLoading.value = false
  aiReport.value = null
  aiError.value = ''

  if (!/^\d{6}$/.test(value)) {
    error.value = '股票代码必须是 6 位数字'
    quote.value = null
    kline.value = null
    analysisSeq += 1
    analysis.value = null
    history.value = []
    watchlisted.value = false
    return
  }
  quoteSeq += 1
  klineSeq += 1
  analysisSeq += 1
  quote.value = null
  kline.value = null
  analysis.value = null
  error.value = ''
  chartError.value = ''
  analysisError.value = ''
  watchlisted.value = false
  void loadWatchlistState(value)
  void loadHistory(value)
  void resumeActiveAIJob(value)
  await Promise.all([loadQuote(value), loadKline(value)])
  if (!error.value) void loadAnalysis(value)
}

function submitSearch(): void {
  const value = searchSymbol.value.trim()
  if (!/^\d{6}$/.test(value)) {
    error.value = '请输入 6 位股票代码'
    return
  }
  if (value === code.value) {
    void loadAll(value)
    return
  }
  void router.push({ name: 'stock', params: { symbol: value } })
}

watch(
  code,
  (value) => {
    searchSymbol.value = value
    if (!/^\d{6}$/.test(value)) {
      error.value = '股票代码必须是 6 位数字'
      quote.value = null
      kline.value = null
      analysisSeq += 1
      analysis.value = null
      return
    }
    void loadAll(value)
  },
  { immediate: true },
)

watch([period, adjust], () => {
  if (validCode.value) void loadKline(code.value)
})

onMounted(() => {
  void loadAIConfig()
})

onBeforeUnmount(() => {
  stopAIPolling()
})
</script>

<template>
  <AppShell>
    <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <RouterLink
          to="/"
          class="inline-flex items-center gap-1 text-xs text-ink-3 transition-colors hover:text-ink"
        >
          <span aria-hidden="true">←</span>
          返回工作台
        </RouterLink>
        <h1 class="mt-2 text-[24px] font-semibold tracking-tight text-ink">
          {{ quote?.name ?? '个股行情' }}
        </h1>
        <p class="mt-1 text-xs tabular-nums text-ink-3">
          {{ code || '—' }} · A 股
          <span v-if="quote" class="ml-2">
            {{ quote.delayed ? '延迟数据' : '最新行情' }}
          </span>
        </p>
      </div>

      <div class="flex w-full flex-wrap items-center gap-2 sm:w-auto">
        <button
          type="button"
          class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border px-3 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          :class="
            watchlisted
              ? 'border-primary/30 bg-primary-soft text-primary'
              : 'border-line-strong bg-canvas text-ink-2 hover:border-ink-3 hover:text-ink'
          "
          :disabled="watchlistBusy || !quote"
          @click="toggleWatchlist"
        >
          {{ watchlisted ? '已自选' : '加入自选' }}
        </button>

        <form class="flex min-w-0 flex-1 gap-2 sm:flex-none" @submit.prevent="submitSearch">
          <Input
            v-model="searchSymbol"
            class="min-w-0 flex-1 sm:w-56 sm:flex-none"
            placeholder="切换股票代码"
            aria-label="股票代码"
            inputmode="numeric"
            autocomplete="off"
            maxlength="6"
          />
          <Button type="submit" class="shrink-0">查询</Button>
        </form>
      </div>
    </section>

    <div
      v-if="!validCode"
      class="mt-6 rounded-lg border border-line bg-canvas px-5 py-10 text-center text-sm text-ink-2"
    >
      股票代码必须是 6 位数字。
      <RouterLink to="/" class="ml-1 font-medium text-primary hover:text-primary-hover">
        返回工作台
      </RouterLink>
    </div>

    <div
      v-else-if="error && !quote"
      class="mt-6 rounded-lg border border-line bg-canvas px-5 py-10 text-center text-sm text-danger"
    >
      {{ error }}
      <button
        type="button"
        class="ml-2 font-medium text-primary hover:text-primary-hover"
        @click="loadAll(code)"
      >
        重试
      </button>
    </div>

    <template v-else>
      <section class="mt-6 rounded-lg border border-line bg-canvas p-5">
        <div v-if="loadingQuote && !quote" class="animate-pulse space-y-3">
          <div class="h-5 w-32 rounded bg-surface-2" />
          <div class="h-10 w-48 rounded bg-surface-2" />
          <div class="grid grid-cols-4 gap-3">
            <div v-for="index in 12" :key="index" class="h-9 rounded bg-surface-2" />
          </div>
        </div>

        <template v-else-if="quote">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-xs tabular-nums text-ink-3">{{ quote.symbol }}</span>
                <span
                  v-if="quote.delayed"
                  class="rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn"
                >
                  延迟数据
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 rounded-full bg-down-soft px-2 py-0.5 text-[11px] font-medium text-down"
                >
                  <span class="size-1.5 rounded-full bg-down" />
                  最新
                </span>
              </div>
              <div class="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span
                  class="text-[36px] font-semibold leading-none tracking-tight tabular-nums"
                  :class="tone"
                >
                  {{ quote.price.toFixed(2) }}
                </span>
                <span class="text-sm font-medium tabular-nums" :class="tone">{{ changeText }}</span>
              </div>
            </div>
            <div class="text-right text-[11px] leading-relaxed text-ink-3">
              <div>{{ sourceLabel(quote.source) }}</div>
              <div class="tabular-nums">{{ fetchedTime }}</div>
            </div>
          </div>

          <div class="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4 xl:grid-cols-6">
            <div v-for="item in metrics" :key="item.label">
              <div class="text-[11px] text-ink-3">{{ item.label }}</div>
              <div class="mt-1 text-[13px] font-medium tabular-nums text-ink">{{ item.value }}</div>
            </div>
          </div>

          <p class="mt-4 text-[11px] leading-relaxed text-ink-3">
            行情来源 {{ sourceLabel(quote.source) }}，报价时间 {{ fetchedTime }}；数据仅供参考，不构成投资建议。
          </p>
        </template>
      </section>

      <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="text-sm font-semibold text-ink">AI 多分析师研判</h2>
              <span
                class="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary"
              >
                6 分析师 + 首席策略官
              </span>
              <span
                v-if="aiReport?.cached"
                class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-3"
              >
                6 小时内复用
              </span>
            </div>
            <p class="mt-1 text-xs leading-relaxed text-ink-3">
              六维数据与分析师报告由代码生成，首席策略官由 LLM 汇总；价位由代码计算，数据缺口会明确标注。
            </p>
          </div>
          <div
            v-if="aiConfig"
            class="flex shrink-0 flex-col items-end gap-1.5 text-right text-[11px] leading-relaxed text-ink-3"
          >
            <div>{{ aiConfig.model }} · 今日额度 {{ aiConfig.quota_used }} / {{ aiConfig.daily_quota }}</div>
            <div class="flex flex-wrap items-center justify-end gap-2">
              <RouterLink
                v-if="aiReport?.report_id"
                :to="{
                  path: `/reports/${aiReport.report_id}`,
                  query: { from: 'stock', symbol: code },
                }"
                class="font-medium text-primary transition-colors hover:text-primary-hover"
              >
                查看完整报告 →
              </RouterLink>
              <button
                v-if="aiReport"
                type="button"
                class="inline-flex h-7 items-center gap-1 rounded-md border border-line-strong bg-canvas px-2.5 text-xs font-medium text-ink-2 transition-colors hover:border-ink-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="aiLoading || !aiConfig?.configured"
                title="跳过 6 小时缓存重新生成，消耗 1 次额度"
                @click="rerunAIAnalysis"
              >
                <svg
                  class="size-3.5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  aria-hidden="true"
                >
                  <path d="M4 4v5h5" stroke-linecap="round" stroke-linejoin="round" />
                  <path
                    d="M4.6 9A8 8 0 1 1 4 13"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
                {{ aiLoading ? '诊断中…' : '重新诊断' }}
              </button>
            </div>
          </div>
        </div>

        <div
          v-if="aiConfigLoading && !aiConfig"
          class="mt-4 flex items-center gap-2 text-xs text-ink-3"
        >
          <span class="size-3.5 animate-spin rounded-full border-2 border-line-strong border-t-primary" />
          读取 AI 配置…
        </div>

        <div
          v-else-if="aiConfigError && !aiConfig"
          class="mt-4 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn"
        >
          {{ aiConfigError }}
        </div>

        <div v-else-if="!aiConfig?.configured" class="mt-4 rounded-md bg-warn-soft px-4 py-3">
          <p class="text-[13px] font-medium text-warn">尚未配置 LLM</p>
          <p class="mt-1 text-xs leading-relaxed text-ink-2">
            在根目录
            <code class="rounded bg-canvas px-1 py-0.5 font-mono text-[11px]">.env</code>
            填写
            <code class="rounded bg-canvas px-1 py-0.5 font-mono text-[11px]">LLM_BASE_URL</code>、
            <code class="rounded bg-canvas px-1 py-0.5 font-mono text-[11px]">LLM_API_KEY</code>、
            <code class="rounded bg-canvas px-1 py-0.5 font-mono text-[11px]">LLM_MODEL</code>
            后重启后端即可启用。支持任意 OpenAI 兼容的
            <code class="rounded bg-canvas px-1 py-0.5 font-mono text-[11px]">/chat/completions</code>
            服务。
          </p>
        </div>

        <template v-else>
          <div v-if="!aiReport" class="mt-4">
            <div class="flex flex-wrap items-center gap-3">
              <Button
                :loading="aiLoading"
                :disabled="aiLoading || !quote"
                @click="runAIAnalysis"
              >
                {{ aiLoading ? '分析中…' : '开始 AI 分析' }}
              </Button>
              <span v-if="aiQuotaLeft !== null" class="text-[11px] text-ink-3">
                今日剩余 {{ aiQuotaLeft }} 次
              </span>
            </div>
            <div
              v-if="aiLoading"
              class="mt-3 flex items-center gap-2 rounded-md bg-primary-soft px-3 py-2 text-xs text-primary-hover"
            >
              <span class="size-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
              <span>{{ aiPhase || '排队中' }} · 已等待 {{ aiElapsed }} 秒</span>
            </div>
            <p class="mt-2 text-[11px] leading-relaxed text-ink-3">
              任务在后台执行，通常需要 1–3 分钟，页面会自动更新进度；每次消耗 1 次额度。
              同股同交易日 + 同模型 6 小时内复用，不重复消耗。
            </p>
            <div
              v-if="aiError"
              class="mt-3 rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger"
            >
              {{ aiError }}
            </div>
          </div>

          <div v-else class="mt-4">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div class="flex flex-wrap items-center gap-2">
                <span
                  class="rounded-md px-2.5 py-1 text-sm font-semibold"
                  :class="aiBadgeClass"
                >
                  {{ aiReport.analysis.rating }}
                </span>
                <span class="text-xs text-ink-3">
                  {{ aiReport.analysis.trend }} · 置信度 {{ aiReport.analysis.confidence }}
                </span>
              </div>
              <div class="w-full max-w-[220px]">
                <div class="flex items-center justify-between text-[11px] text-ink-3">
                  <span>置信度</span>
                  <span class="tabular-nums">{{ aiReport.analysis.confidence }} / 100</span>
                </div>
                <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div
                    class="h-full rounded-full"
                    :class="aiBarClass"
                    :style="{ width: `${aiReport.analysis.confidence}%` }"
                  />
                </div>
              </div>
            </div>

            <p class="mt-4 text-[13px] leading-relaxed text-ink-2">
              {{ aiReport.analysis.summary }}
            </p>

            <div
              v-if="aiReport.decision"
              class="mt-4 rounded-md border border-line bg-surface/60 p-4"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-xs font-medium text-ink">首席策略官</span>
                <span
                  class="rounded-md px-2 py-0.5 text-xs font-semibold"
                  :class="decisionBadgeClass"
                >
                  {{ aiReport.decision.rating }}
                </span>
                <span class="text-[11px] text-ink-3">
                  决策置信度 {{ aiReport.decision.confidence }} / 100
                  <span v-if="aiReport.decision.decision_source === 'rule_fallback'">
                    · 规则兜底
                  </span>
                </span>
              </div>

              <div class="mt-3 grid gap-3 sm:grid-cols-3">
                <div>
                  <div class="text-[11px] text-ink-3">操作建议</div>
                  <p class="mt-0.5 text-xs leading-relaxed text-ink-2">
                    {{ aiReport.decision.operation_advice }}
                  </p>
                </div>
                <div>
                  <div class="text-[11px] text-ink-3">持有周期</div>
                  <p class="mt-0.5 text-xs text-ink-2">{{ aiReport.decision.holding_period }}</p>
                </div>
                <div>
                  <div class="text-[11px] text-ink-3">仓位建议</div>
                  <p class="mt-0.5 text-xs text-ink-2">{{ aiReport.decision.position_size }}</p>
                </div>
              </div>

              <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div
                  v-for="item in decisionLevels"
                  :key="item.label"
                  class="rounded-md bg-canvas px-2.5 py-2"
                >
                  <div class="text-[10px] text-ink-3">{{ item.label }}</div>
                  <div class="mt-0.5 text-[12px] font-semibold tabular-nums" :class="item.tone">
                    {{ item.value }}
                  </div>
                </div>
              </div>

              <p v-if="aiReport.decision.risk_warning" class="mt-3 text-[11px] text-warn">
                风险提示：{{ aiReport.decision.risk_warning }}
              </p>

              <div
                v-if="aiReport.decision.consensus.length || aiReport.decision.dissent.length"
                class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-3"
              >
                <span v-if="aiReport.decision.consensus.length">
                  共识：{{ aiReport.decision.consensus.join('；') }}
                </span>
                <span v-if="aiReport.decision.dissent.length">
                  分歧：{{ aiReport.decision.dissent.join('；') }}
                </span>
              </div>
            </div>

            <div v-if="aiReport.analysts?.length" class="mt-5">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <h3 class="text-xs font-medium text-ink">六位分析师</h3>
                <span class="text-[11px] text-ink-3">评分越高越偏积极</span>
              </div>
              <div class="mt-2 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                <div
                  v-for="analyst in aiReport.analysts"
                  :key="analyst.key"
                  class="rounded-md border border-line bg-surface/40 p-3"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="flex items-center gap-1.5">
                      <span class="text-xs font-medium text-ink">{{ analyst.name }}</span>
                      <span
                        v-if="analyst.engine === 'llm'"
                        class="rounded-full bg-primary-soft px-1.5 py-0.5 text-[10px] font-medium text-primary"
                      >
                        LLM
                      </span>
                      <span
                        v-else
                        class="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-3"
                      >
                        规则
                      </span>
                    </span>
                    <div class="flex items-center gap-2">
                      <span class="text-[11px] text-ink-3">{{ analyst.rating }}</span>
                      <span
                        class="text-sm font-semibold tabular-nums"
                        :class="analystTone(analyst.score)"
                      >
                        {{ analyst.score }}
                      </span>
                    </div>
                  </div>
                  <p class="mt-1.5 text-[11px] leading-relaxed text-ink-2">
                    {{ analyst.summary }}
                  </p>
                  <ul v-if="analyst.points.length" class="mt-1.5 space-y-1">
                    <li
                      v-for="(point, index) in analyst.points.slice(0, 2)"
                      :key="index"
                      class="text-[11px] leading-relaxed text-ink-2"
                    >
                      · {{ point }}
                    </li>
                  </ul>
                  <p v-if="analyst.risks.length" class="mt-1.5 text-[11px] text-down">
                    风险：{{ analyst.risks[0] }}
                  </p>
                  <p v-if="analyst.missing.length" class="mt-1 text-[11px] text-warn">
                    缺口：{{ analyst.missing.join('、') }}
                  </p>
                </div>
              </div>
            </div>

            <DiscussionTimeline
              v-if="aiReport.discussion && aiReport.discussion.turns.length"
              class="mt-4"
              variant="flat"
              :discussion="aiReport.discussion"
            />

            <div class="mt-4 grid gap-5 lg:grid-cols-2">
              <div>
                <h3 class="text-xs font-medium text-ink">核心依据</h3>
                <ul class="mt-2 space-y-2">
                  <li
                    v-for="(point, index) in aiReport.analysis.key_points"
                    :key="index"
                    class="flex gap-2 text-xs leading-relaxed text-ink-2"
                  >
                    <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
                    {{ point }}
                  </li>
                </ul>
              </div>
              <div>
                <h3 class="text-xs font-medium text-ink">风险提示</h3>
                <ul class="mt-2 space-y-2">
                  <li
                    v-for="(risk, index) in aiReport.analysis.risks"
                    :key="index"
                    class="flex gap-2 text-xs leading-relaxed text-ink-2"
                  >
                    <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-warn" />
                    {{ risk }}
                  </li>
                </ul>
              </div>
            </div>

            <p
              v-if="aiReport.analysis.watch"
              class="mt-4 rounded-md bg-surface px-3 py-2 text-xs text-ink-2"
            >
              下一交易日观察：{{ aiReport.analysis.watch }}
            </p>

            <PublicInfoPanel
              class="mt-4"
              variant="flat"
              :used="aiReport.web_search_used"
              :sources="aiReport.web_sources"
              :used-by="webUsedBy"
            />

            <div
              class="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-[11px] text-ink-3"
            >
              <span>{{ aiReport.model }} · {{ aiReport.prompt_version }}</span>
              <span class="tabular-nums">
                {{ aiGeneratedTime }} · 额度 {{ aiReport.quota_used }} / {{ aiReport.quota_limit }}
              </span>
            </div>
            <p class="mt-2 text-[11px] leading-relaxed text-ink-3">
              数据覆盖：{{ coverageLabels.join('、') }}<template v-if="aiReport.analysts?.length">；{{
                dataGaps.length ? `数据缺口：${dataGaps.join('、')}` : '六维数据齐全'
              }}</template>。
            </p>
            <p class="mt-2 text-[11px] leading-relaxed text-ink-3">{{ aiReport.disclaimer }}</p>
          </div>
        </template>
      </section>

      <section
        v-if="history.length || historyLoading || historyError"
        class="mt-4 rounded-lg border border-line bg-canvas p-5"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <h2 class="text-sm font-semibold text-ink">历史分析</h2>
            <span class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-3">
              {{ history.length }} 条
            </span>
          </div>
          <span v-if="historyLoading" class="text-[11px] text-ink-3">加载中…</span>
          <span v-else class="text-[11px] text-ink-3">点击查看完整历史报告</span>
        </div>

        <p v-if="historyError" class="mt-2 text-xs text-warn">{{ historyError }}</p>
        <div v-else class="mt-3 flex flex-wrap gap-2">
          <RouterLink
            v-for="item in history"
            :key="item.id"
            :to="{ path: `/reports/${item.id}`, query: { from: 'stock', symbol: code } }"
            class="rounded-md border border-line bg-surface/40 px-3 py-2 text-left transition-colors hover:border-line-strong hover:bg-surface"
          >
            <div class="text-[11px] text-ink-3">{{ formatReportTime(item.created_at) }}</div>
            <div class="mt-0.5 flex items-center gap-2">
              <span
                class="text-xs font-medium"
                :class="
                  item.rating === '买入'
                    ? 'text-up'
                    : item.rating === '卖出'
                      ? 'text-down'
                      : 'text-ink-2'
                "
              >
                {{ item.rating }}
              </span>
              <span class="text-[11px] text-ink-3">置信度 {{ item.confidence }}</span>
              <span class="text-[10px] text-ink-3">
                {{ item.decision_source === 'rule_fallback' ? '规则' : 'LLM' }}
              </span>
            </div>
          </RouterLink>
        </div>
      </section>

      <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-sm font-semibold text-ink">技术面诊断</h2>
            <span
              class="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary"
            >
              技术面分析师 · 规则版
            </span>
          </div>
          <span v-if="analysis" class="text-[11px] text-ink-3">
            {{ analysis.trend }} · {{ formatQuoteTime(analysis.as_of) }}
          </span>
        </div>

        <div v-if="loadingAnalysis" class="mt-4 animate-pulse space-y-3">
          <div class="h-4 w-3/4 rounded bg-surface-2" />
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div v-for="index in 6" :key="index" class="h-14 rounded bg-surface-2" />
          </div>
        </div>

        <div v-else-if="analysis" class="mt-4">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <p class="max-w-3xl text-xs leading-relaxed text-ink-2">{{ analysis.summary }}</p>
            <div class="flex shrink-0 items-center gap-3">
              <div class="text-right">
                <div class="text-[11px] text-ink-3">技术评分</div>
                <div
                  class="text-[30px] font-semibold leading-none tabular-nums"
                  :class="ratingTone"
                >
                  {{ analysis.score }}
                </div>
              </div>
              <span class="rounded-md px-2.5 py-1 text-xs font-medium" :class="ratingBadge">
                {{ analysis.rating }}
              </span>
            </div>
          </div>

          <div class="mt-3 h-1 w-full max-w-[320px] overflow-hidden rounded-full bg-surface-2">
            <div
              class="h-full rounded-full transition-all duration-300"
              :class="ratingBar"
              :style="{ width: `${analysis.score}%` }"
            />
          </div>

          <div class="mt-5 grid gap-6 lg:grid-cols-2">
            <div>
              <h3 class="text-xs font-medium text-ink">关键价位</h3>
              <div class="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div
                  v-for="item in levelItems"
                  :key="item.label"
                  class="rounded-md bg-surface px-3 py-2.5"
                >
                  <div class="text-[11px] text-ink-3">{{ item.label }}</div>
                  <div class="mt-1 text-[14px] font-semibold tabular-nums" :class="item.tone">
                    {{ item.value }}
                  </div>
                </div>
              </div>

              <h3 class="mt-5 text-xs font-medium text-ink">指标快照</h3>
              <div class="mt-2 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
                <div v-for="item in indicatorItems" :key="item.label">
                  <div class="text-[11px] text-ink-3">{{ item.label }}</div>
                  <div class="mt-0.5 text-[12px] font-medium tabular-nums text-ink">
                    {{ item.value }}
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h3 class="text-xs font-medium text-ink">信号</h3>
              <ul class="mt-2 space-y-2.5">
                <li
                  v-for="signal in analysis.signals"
                  :key="signal.name"
                  class="flex gap-2.5 text-xs leading-relaxed"
                >
                  <span
                    class="mt-1.5 size-1.5 shrink-0 rounded-full"
                    :class="signalTone(signal.direction)"
                  />
                  <p class="text-ink-2">
                    <span class="font-medium text-ink">{{ signal.name }}</span>
                    {{ signal.detail }}
                  </p>
                </li>
              </ul>
            </div>
          </div>

          <p class="mt-4 border-t border-line pt-3 text-[11px] leading-relaxed text-ink-3">
            {{ analysis.disclaimer }} 基于日 K · 前复权 90 根，行情源 {{ analysisSource }}。
          </p>
        </div>

        <div
          v-else-if="analysisError"
          class="mt-4 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn"
        >
          {{ analysisError }}
        </div>
        <div v-else class="mt-4 text-xs text-ink-3">行情加载完成后生成诊断。</div>
      </section>

      <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-sm font-semibold text-ink">K 线</h2>
            <div class="flex rounded-md border border-line bg-surface p-0.5">
              <button
                v-for="item in PERIODS"
                :key="item.value"
                type="button"
                class="h-7 rounded-sm px-3 text-xs font-medium transition-colors duration-150"
                :class="
                  period === item.value
                    ? 'bg-canvas text-ink shadow-card'
                    : 'text-ink-2 hover:text-ink'
                "
                @click="period = item.value"
              >
                {{ item.label }}
              </button>
            </div>
          </div>

          <div class="flex items-center gap-1">
            <button
              v-for="item in ADJUSTS"
              :key="item.value"
              type="button"
              class="h-7 rounded-sm px-2.5 text-xs transition-colors duration-150"
              :class="
                adjust === item.value
                  ? 'bg-primary-soft font-medium text-primary'
                  : 'text-ink-2 hover:text-ink'
              "
              @click="adjust = item.value"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div class="relative mt-4">
          <MiniKline
            v-if="kline && kline.bars.length"
            :bars="kline.bars"
            :title="chartTitle"
            large
            :class="loadingKline ? 'opacity-60' : ''"
          />
          <div
            v-else-if="loadingKline"
            class="h-[320px] animate-pulse rounded-md bg-surface sm:h-[430px]"
          />
          <div
            v-else-if="chartError"
            class="flex h-[320px] items-center justify-center rounded-md border border-line bg-surface px-4 text-center text-xs text-ink-3 sm:h-[430px]"
          >
            {{ chartError }}
          </div>
          <div
            v-else
            class="flex h-[320px] items-center justify-center rounded-md border border-dashed border-line bg-surface text-xs text-ink-3 sm:h-[430px]"
          >
            暂无 K 线数据
          </div>

          <div
            v-if="loadingKline && kline && kline.bars.length"
            class="absolute inset-0 flex items-center justify-center"
          >
            <span class="rounded-full bg-canvas px-3 py-1 text-xs text-ink-2 shadow-card">
              更新中…
            </span>
          </div>
        </div>

        <div class="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-3">
          <span>{{ periodLabel }} · {{ adjustLabel }}</span>
          <span v-if="kline" class="tabular-nums">
            K 线来源 {{ sourceLabel(kline.source) }} · {{ formatQuoteTime(kline.fetched_at) }}
          </span>
        </div>
      </section>
    </template>
  </AppShell>
</template>
