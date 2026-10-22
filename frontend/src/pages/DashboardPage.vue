<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { aiApi, type AIConfig } from '@/api/ai'
import { reportsApi, type ReportSummary } from '@/api/reports'
import AppShell from '@/components/layout/AppShell.vue'
import StockLookup from '@/components/market/StockLookup.vue'
import ReportListItem from '@/components/report/ReportListItem.vue'
import ReportListSkeleton from '@/components/report/ReportListSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { getErrorMessage } from '@/utils/errors'

const REPORT_FETCH_LIMIT = 50
const RECENT_LIMIT = 5

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

const recentReports = computed(() => reports.value.slice(0, RECENT_LIMIT))
const stockCount = computed(() => new Set(reports.value.map((item) => item.symbol)).size)

function quotaHint(): string {
  if (aiConfigLoading.value) return '加载中'
  if (!aiConfig.value) return 'AI 状态获取失败'
  return aiConfig.value.configured
    ? '每日 0 点重置'
    : 'LLM 未配置，AI 分析暂不可用'
}

const stats = computed(() => [
  {
    label: '今日分析额度',
    value:
      aiConfigLoading.value || !aiConfig.value
        ? '—'
        : `${aiConfig.value.quota_used} / ${aiConfig.value.daily_quota}`,
    hint: quotaHint(),
  },
  {
    label: '历史报告',
    value: reportsLoading.value
      ? '—'
      : reports.value.length >= REPORT_FETCH_LIMIT
        ? `${reports.value.length}+`
        : `${reports.value.length}`,
    hint: reportsLoading.value ? '加载中' : '最近 50 份分析记录',
  },
  {
    label: '覆盖股票',
    value: reportsLoading.value ? '—' : `${stockCount.value}`,
    hint: '按股票代码去重',
  },
  {
    label: '行情数据源',
    value: '3 家',
    hint: '腾讯 · 新浪 · 东方财富',
  },
])

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

async function loadAIConfig(): Promise<void> {
  try {
    const { data } = await aiApi.config()
    aiConfig.value = data
  } catch {
    aiConfig.value = null
  } finally {
    aiConfigLoading.value = false
  }
}

onMounted(() => {
  void loadReports()
  void loadAIConfig()
})
</script>

<template>
  <AppShell>
    <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">{{ greeting }}，{{ auth.user?.nickname }}</p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">首页</h1>
      </div>
      <div class="flex items-center gap-4">
        <RouterLink
          to="/watchlist"
          class="text-xs text-ink-3 transition-colors hover:text-ink"
        >
          自选股 →
        </RouterLink>
        <RouterLink
          to="/reports"
          class="text-xs text-ink-3 transition-colors hover:text-ink"
        >
          全部历史报告 →
        </RouterLink>
      </div>
    </section>

    <StockLookup class="mt-6" />

    <section class="mt-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
      <div
        v-for="item in stats"
        :key="item.label"
        class="rounded-lg border border-line bg-canvas p-5"
      >
        <div class="text-xs text-ink-3">{{ item.label }}</div>
        <div class="mt-2 text-[28px] font-semibold leading-none tracking-tight text-ink">
          {{ item.value }}
        </div>
        <div class="mt-2 text-[11px] text-ink-3">{{ item.hint }}</div>
      </div>
    </section>

    <section class="mt-8">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold text-ink">最近分析</h2>
          <p class="mt-1 text-xs text-ink-3">
            点击查看完整六分析师报告与首席决策
          </p>
        </div>
        <RouterLink
          v-if="reports.length > RECENT_LIMIT"
          to="/reports"
          class="text-xs text-ink-3 transition-colors hover:text-ink"
        >
          查看全部 {{ reports.length }} 份 →
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

        <div v-else-if="!recentReports.length" class="px-4 py-14 text-center">
          <div class="text-sm font-medium text-ink">还没有分析记录</div>
          <p class="mt-1 text-xs text-ink-3">
            查询一只股票，在个股详情页发起一次 AI 分析，报告会自动保存在这里。
          </p>
        </div>

        <template v-else>
          <ReportListItem
            v-for="item in recentReports"
            :key="item.id"
            :item="item"
            time-style="datetime"
            from="dashboard"
          />
        </template>
      </div>
    </section>
  </AppShell>
</template>
