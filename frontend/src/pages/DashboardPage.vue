<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { aiApi, type AIConfig } from '@/api/ai'
import { reportsApi, type ReportStats, type ReportSummary } from '@/api/reports'
import { watchlistApi, type PriceAlert, type WatchlistEntry } from '@/api/watchlist'
import AppShell from '@/components/layout/AppShell.vue'
import StockLookup from '@/components/market/StockLookup.vue'
import ReportListItem from '@/components/report/ReportListItem.vue'
import ReportListSkeleton from '@/components/report/ReportListSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { alertActionLabel, alertTargetText } from '@/utils/alerts'
import { getErrorMessage } from '@/utils/errors'
import { formatPrice, quoteToneClass } from '@/utils/market'
import { formatRecentDateTime } from '@/utils/report'

const REPORT_FETCH_LIMIT = 50
const RECENT_LIMIT = 5
const WATCH_TILE_LIMIT = 6
const ALERT_PREVIEW_LIMIT = 3

const auth = useAuthStore()

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const aiConfig = ref<AIConfig | null>(null)
const aiConfigLoading = ref(true)
const reports = ref<ReportSummary[]>([])
const reportsLoading = ref(true)
const reportsError = ref('')
const reportStats = ref<ReportStats | null>(null)
const watchlist = ref<WatchlistEntry[]>([])
const watchlistLoading = ref(true)
const watchlistError = ref('')
const alerts = ref<PriceAlert[]>([])
const alertsLoading = ref(true)

const quotaPct = computed(() => {
  const config = aiConfig.value
  if (!config || !config.daily_quota) return 0
  const used = Math.min(config.quota_used, config.daily_quota)
  return Math.max(used > 0 ? 6 : 0, Math.round((used / config.daily_quota) * 100))
})

const quotaExhausted = computed(
  () => !!aiConfig.value && aiConfig.value.quota_used >= aiConfig.value.daily_quota,
)

const triggeredAlerts = computed(() =>
  alerts.value
    .filter((alert) => alert.status === 'triggered')
    .sort(
      (a, b) =>
        Date.parse(b.triggered_at ?? b.created_at) - Date.parse(a.triggered_at ?? a.created_at),
    ),
)
const visibleAlerts = computed(() => triggeredAlerts.value.slice(0, ALERT_PREVIEW_LIMIT))

const myWatchlist = computed(() => watchlist.value.slice(0, WATCH_TILE_LIMIT))

const watchSummary = computed(() => {
  const total = watchlist.value.length
  if (!total) return ''
  let up = 0
  let down = 0
  for (const entry of watchlist.value) {
    if (entry.change_pct == null || entry.change_pct === 0) continue
    if (entry.change_pct > 0) up += 1
    else down += 1
  }
  if (!up && !down) return `${total} 只自选`
  return `${total} 只自选 · ${up} 涨 ${down} 跌`
})

const contextLine = computed(() => {
  if (watchSummary.value) return watchSummary.value
  if (watchlistLoading.value) return ''
  if (!watchlist.value.length) return '自选股为空，添加后可在这里看涨跌与最新结论'
  return ''
})

const stockCount = computed(() => new Set(reports.value.map((item) => item.symbol)).size)
const totalStocks = computed(() => reportStats.value?.stock_count ?? stockCount.value)
const totalReportsText = computed(() => {
  if (reportStats.value) return `${reportStats.value.total}`
  return reports.value.length >= REPORT_FETCH_LIMIT
    ? `${reports.value.length}+`
    : `${reports.value.length}`
})

const todayReports = computed(() => {
  const now = new Date()
  return reports.value.filter((item) => {
    const date = new Date(item.created_at)
    return (
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate()
    )
  }).length
})

/** 首页只保留每只股票最新一份，重复次数折叠成角标 */
const recentGroups = computed(() => {
  const map = new Map<string, { item: ReportSummary; count: number }>()
  for (const item of reports.value) {
    const hit = map.get(item.symbol)
    if (!hit) {
      map.set(item.symbol, { item, count: 1 })
      continue
    }
    hit.count += 1
    if (Date.parse(item.created_at) > Date.parse(hit.item.created_at)) hit.item = item
  }
  return [...map.values()]
    .sort((a, b) => Date.parse(b.item.created_at) - Date.parse(a.item.created_at))
    .slice(0, RECENT_LIMIT)
})

function watchHint(entry: WatchlistEntry): string {
  const latest = entry.latest
  if (!latest) return '尚未分析'
  const head = latest.position_action
    ? `建议 ${latest.position_action}`
    : `最新 ${latest.rating}`
  return `${head} · 置信度 ${latest.confidence}`
}

function signedPct(value: number | null): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function triggeredPriceText(alert: PriceAlert): string {
  return alert.triggered_price == null ? '—' : alert.triggered_price.toFixed(2)
}

async function loadReports(): Promise<void> {
  reportsLoading.value = true
  reportsError.value = ''
  try {
    const { data } = await reportsApi.list(undefined, REPORT_FETCH_LIMIT)
    reports.value = data
  } catch (err) {
    reports.value = []
    reportsError.value = getErrorMessage(err, '历史报告加载失败')
  } finally {
    reportsLoading.value = false
  }
}

async function loadReportStats(): Promise<void> {
  try {
    const { data } = await reportsApi.stats()
    reportStats.value = data
  } catch {
    reportStats.value = null
  }
}

async function loadAIConfig(): Promise<void> {
  aiConfigLoading.value = true
  try {
    const { data } = await aiApi.config()
    aiConfig.value = data
  } catch {
    aiConfig.value = null
  } finally {
    aiConfigLoading.value = false
  }
}

async function loadWatchlist(): Promise<void> {
  watchlistLoading.value = true
  watchlistError.value = ''
  try {
    const { data } = await watchlistApi.list()
    watchlist.value = data
  } catch (err) {
    watchlist.value = []
    watchlistError.value = getErrorMessage(err, '自选股加载失败')
  } finally {
    watchlistLoading.value = false
  }
}

async function loadAlerts(): Promise<void> {
  alertsLoading.value = true
  try {
    const { data } = await watchlistApi.alerts()
    alerts.value = data
  } catch {
    alerts.value = []
  } finally {
    alertsLoading.value = false
  }
}

onMounted(() => {
  void loadReports()
  void loadReportStats()
  void loadAIConfig()
  void loadWatchlist()
  void loadAlerts()
})
</script>

<template>
  <AppShell>
    <section class="flex flex-wrap items-start justify-between gap-x-8 gap-y-5">
      <div class="min-w-0">
        <h1 class="text-[24px] font-semibold tracking-tight text-ink">
          {{ greeting }}，{{ auth.user?.nickname }}
        </h1>
        <p v-if="contextLine" class="mt-1.5 text-[13px] text-ink-2">{{ contextLine }}</p>
      </div>

      <div class="w-full sm:w-auto sm:text-right">
        <div class="text-[12px] text-ink-3">今日分析额度</div>
        <template v-if="aiConfig">
          <div class="mt-1 flex items-baseline gap-1 sm:justify-end">
            <span class="text-[20px] font-semibold leading-none tabular-nums text-ink">
              {{ aiConfig.quota_used }}
            </span>
            <span class="text-[12px] tabular-nums text-ink-3">/ {{ aiConfig.daily_quota }}</span>
          </div>
          <div class="mt-2 h-1 w-[120px] overflow-hidden rounded-full bg-surface-2 sm:ml-auto sm:w-[150px]">
            <div
              class="h-full rounded-full transition-[width] duration-300"
              :class="quotaExhausted ? 'bg-warn' : 'bg-primary'"
              :style="{ width: `${quotaPct}%` }"
            />
          </div>
          <p
            class="mt-1.5 text-[11px]"
            :class="aiConfig.configured ? 'text-ink-3' : 'text-warn'"
          >
            {{ aiConfig.configured ? '每日 0 点重置' : 'LLM 未配置，AI 分析暂不可用' }}
          </p>
        </template>
        <template v-else-if="aiConfigLoading">
          <div class="mt-2 h-5 w-16 animate-pulse rounded bg-surface-2 sm:ml-auto" />
        </template>
        <template v-else>
          <button
            type="button"
            class="mt-2 text-[12px] text-ink-2 underline-offset-2 transition-colors hover:text-ink hover:underline"
            @click="loadAIConfig"
          >
            额度获取失败 · 重试
          </button>
        </template>
      </div>
    </section>

    <section
      v-if="visibleAlerts.length"
      class="mt-5 rounded-lg border border-line bg-canvas px-4 py-3"
    >
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span class="size-1.5 rounded-full bg-warn" aria-hidden="true" />
        <h2 class="text-[13px] font-semibold text-ink">价位提醒已触发</h2>
        <span class="text-[11px] text-ink-3">{{ triggeredAlerts.length }} 条 · 触发一次后自动结束</span>
        <RouterLink
          to="/watchlist"
          class="ml-auto text-[11px] text-ink-3 transition-colors hover:text-ink"
        >
          去自选股页 →
        </RouterLink>
      </div>
      <div class="mt-2 divide-y divide-line">
        <RouterLink
          v-for="alert in visibleAlerts"
          :key="alert.id"
          :to="`/stock/${alert.symbol}`"
          class="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5 text-[12px] transition-colors hover:text-primary"
        >
          <span class="font-medium text-ink">{{ alert.name || alert.symbol }}</span>
          <span class="tabular-nums text-ink-3">{{ alert.symbol }}</span>
          <span class="text-ink-2">{{ alertActionLabel(alert) }} {{ alertTargetText(alert) }}</span>
          <span class="tabular-nums text-ink-3">触发价 {{ triggeredPriceText(alert) }}</span>
          <span class="tabular-nums text-ink-3 sm:ml-auto">
            {{ alert.triggered_at ? formatRecentDateTime(alert.triggered_at) : '' }}
          </span>
        </RouterLink>
        <p
          v-if="triggeredAlerts.length > visibleAlerts.length"
          class="pt-1.5 text-[11px] text-ink-3"
        >
          还有 {{ triggeredAlerts.length - visibleAlerts.length }} 条，去自选股页查看。
        </p>
      </div>
    </section>

    <StockLookup class="mt-5" />

    <section class="mt-7">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-sm font-semibold text-ink">我的自选</h2>
          <p class="mt-1 text-[12px] text-ink-3">
            <template v-if="watchlistLoading">正在加载自选股…</template>
            <template v-else-if="!watchlist.length">
              添加自选后，这里显示今日涨跌与最新结论
            </template>
            <template v-else>最新报价与每只股票最近一次的 AI 结论</template>
          </p>
        </div>
        <RouterLink
          to="/watchlist"
          class="text-[12px] text-ink-3 transition-colors hover:text-ink"
        >
          自选股页 →
        </RouterLink>
      </div>

      <div
        v-if="watchlistLoading"
        class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6"
      >
        <div
          v-for="entry in WATCH_TILE_LIMIT"
          :key="entry"
          class="h-[96px] animate-pulse rounded-lg bg-surface-2"
        />
      </div>

      <div
        v-else-if="watchlistError"
        class="mt-3 rounded-lg border border-line bg-canvas px-4 py-3 text-[12px] text-ink-2"
      >
        {{ watchlistError }}
        <button
          type="button"
          class="ml-1 text-ink underline-offset-2 hover:underline"
          @click="loadWatchlist"
        >
          重试
        </button>
      </div>

      <div
        v-else-if="!watchlist.length"
        class="mt-3 rounded-lg border border-line bg-canvas px-4 py-4 text-[12px] text-ink-2"
      >
        还没有自选股。在个股页点「加入自选」，或去
        <RouterLink to="/screener" class="text-ink underline-offset-2 hover:underline">选股</RouterLink>
        挑几只。
      </div>

      <div v-else class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <RouterLink
          v-for="entry in myWatchlist"
          :key="entry.symbol"
          :to="`/stock/${entry.symbol}`"
          class="rounded-lg border border-line bg-canvas px-3.5 py-3 transition-colors hover:border-line-strong"
        >
          <div class="flex items-baseline justify-between gap-2">
            <span class="truncate text-[13px] font-medium text-ink">{{ entry.name }}</span>
            <span class="shrink-0 text-[11px] tabular-nums text-ink-3">{{ entry.symbol }}</span>
          </div>
          <div class="mt-2 flex items-baseline gap-2">
            <span
              class="text-[18px] font-semibold leading-none tabular-nums"
              :class="quoteToneClass(entry.change_pct)"
            >
              {{ formatPrice(entry.price) }}
            </span>
            <span class="text-[12px] tabular-nums" :class="quoteToneClass(entry.change_pct)">
              {{ signedPct(entry.change_pct) }}
            </span>
          </div>
          <div class="mt-2 truncate text-[11px] text-ink-2" :title="watchHint(entry)">
            {{ watchHint(entry) }}
          </div>
        </RouterLink>
      </div>
    </section>

    <section class="mt-8">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-sm font-semibold text-ink">最近分析</h2>
          <p class="mt-1 text-[12px] text-ink-3">
            每只股票只保留最新一份 · 覆盖 {{ totalStocks }} 只<template v-if="todayReports">
              · 今天 {{ todayReports }} 份</template>
          </p>
        </div>
        <RouterLink
          to="/reports"
          class="text-[12px] text-ink-3 transition-colors hover:text-ink"
        >
          全部 {{ totalReportsText }} 份 →
        </RouterLink>
      </div>

      <div class="mt-3 overflow-hidden rounded-lg border border-line bg-canvas">
        <ReportListSkeleton v-if="reportsLoading" />

        <div v-else-if="reportsError" class="px-4 py-10 text-center">
          <p class="text-sm text-danger">{{ reportsError }}</p>
          <button
            type="button"
            class="mt-3 rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
            @click="loadReports"
          >
            重新加载
          </button>
        </div>

        <div v-else-if="!recentGroups.length" class="px-4 py-14 text-center">
          <div class="text-sm font-medium text-ink">还没有分析记录</div>
          <p class="mt-1 text-xs text-ink-3">
            查询一只股票，在个股详情页发起一次 AI 分析，报告会自动保存在这里。
          </p>
        </div>

        <template v-else>
          <ReportListItem
            v-for="group in recentGroups"
            :key="group.item.id"
            :item="group.item"
            time-style="recent"
            source-mode="fallback-only"
            :show-confidence-label="false"
            :repeats="group.count - 1"
            from="dashboard"
          />
        </template>
      </div>
    </section>
  </AppShell>
</template>
