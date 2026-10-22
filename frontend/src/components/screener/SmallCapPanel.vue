<script setup lang="ts">
import { ref } from 'vue'

import { screenerApi, type SmallCapResponse } from '@/api/screener'
import { getErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/report'
import ScreenerResults from './ScreenerResults.vue'
import type { ScreenerDisplayItem } from './types'

const topN = ref(5)
const maxMarketCap = ref<string | number>(50)
const minProfitGrowth = ref<string | number>(100)
const minRevenueGrowth = ref<string | number>(10)
const excludeST = ref(true)
const excludeGEM = ref(true)
const excludeSTAR = ref(true)

const loading = ref(false)
const error = ref('')
const result = ref<SmallCapResponse | null>(null)
const displayItems = ref<ScreenerDisplayItem[]>([])
const reportDate = ref('')

function growthTone(value: number | null): string {
  if (value === null || value === 0) return 'text-ink-2'
  return value > 0 ? 'text-up' : 'text-down'
}

function formatGrowth(value: number | null): string {
  if (value === null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatCap(value: number | null): string {
  if (value === null) return '—'
  return `${(value / 1e8).toFixed(1)} 亿`
}

function toDisplay(data: SmallCapResponse): ScreenerDisplayItem[] {
  return data.items.map((item) => ({
    symbol: item.symbol,
    name: item.name,
    price: item.price,
    change_pct: item.change_pct,
    metrics: [
      {
        label: '总市值',
        value: formatCap(item.total_market_cap),
        tone: 'text-ink-2',
      },
      {
        label: '净利同比',
        value: formatGrowth(item.profit_growth),
        tone: growthTone(item.profit_growth),
      },
      {
        label: '营收同比',
        value: formatGrowth(item.revenue_growth),
        tone: growthTone(item.revenue_growth),
      },
      {
        label: '报告期',
        value: item.report_date ? item.report_date.slice(5) : '—',
        tone: 'text-ink-3',
      },
    ],
  }))
}

async function run(): Promise<void> {
  if (loading.value) return
  loading.value = true
  error.value = ''
  result.value = null
  displayItems.value = []
  try {
    const cap = Number(String(maxMarketCap.value).trim())
    const profit = Number(String(minProfitGrowth.value).trim())
    const revenue = Number(String(minRevenueGrowth.value).trim())
    const { data } = await screenerApi.smallCap({
      top_n: topN.value,
      max_market_cap: Number.isFinite(cap) && cap > 0 ? cap : 50,
      min_profit_growth: Number.isFinite(profit) && profit >= 0 ? profit : 100,
      min_revenue_growth: Number.isFinite(revenue) && revenue >= 0 ? revenue : 10,
      exclude_st: excludeST.value,
      exclude_gem: excludeGEM.value,
      exclude_star: excludeSTAR.value,
      exclude_bj: true,
    })
    result.value = data
    displayItems.value = toDisplay(data)
    reportDate.value = String(data.filters.report_date ?? '')
  } catch (err) {
    error.value = getErrorMessage(err, '选股失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <form class="rounded-lg border border-line bg-canvas p-4" @submit.prevent="run">
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          精选数量
          <select
            v-model.number="topN"
            class="h-9 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none"
          >
            <option :value="5">5 只</option>
            <option :value="10">10 只</option>
          </select>
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          总市值上限（亿）
          <input
            v-model="maxMarketCap"
            type="number"
            step="5"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none"
          />
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          净利同比下限（%）
          <input
            v-model="minProfitGrowth"
            type="number"
            step="10"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none"
          />
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          营收同比下限（%）
          <input
            v-model="minRevenueGrowth"
            type="number"
            step="5"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none"
          />
        </label>

        <label class="flex h-9 cursor-pointer items-center gap-1.5 text-xs text-ink-2">
          <input v-model="excludeST" type="checkbox" class="size-3.5 accent-ink" />
          排除 ST
        </label>
        <label class="flex h-9 cursor-pointer items-center gap-1.5 text-xs text-ink-2">
          <input v-model="excludeGEM" type="checkbox" class="size-3.5 accent-ink" />
          排除创业板
        </label>
        <label class="flex h-9 cursor-pointer items-center gap-1.5 text-xs text-ink-2">
          <input v-model="excludeSTAR" type="checkbox" class="size-3.5 accent-ink" />
          排除科创板
        </label>

        <button
          type="submit"
          class="ml-auto h-9 rounded-md border border-ink bg-ink px-4 text-xs text-canvas transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="loading"
        >
          {{ loading ? '筛选中…' : '开始筛选' }}
        </button>
      </div>
    </form>

    <div
      v-if="error"
      class="mt-4 rounded-md border border-line bg-canvas px-4 py-3 text-xs text-danger"
    >
      {{ error }}
    </div>

    <div
      v-if="loading"
      class="mt-4 rounded-lg border border-line bg-canvas px-4 py-12 text-center text-xs text-ink-3"
    >
      <span
        class="mx-auto mb-3 block size-5 animate-spin rounded-full border-2 border-ink-3/25 border-t-ink-3"
      />
      正在读取最新业绩报表并匹配行情与市值…
    </div>

    <section v-else-if="result" class="mt-6">
      <div class="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-sm font-semibold text-ink">
            候选标的 {{ result.items.length }}
            <span class="ml-1 text-[11px] font-normal text-ink-3">
              / 命中 {{ result.candidate_count }} · 业绩记录 {{ result.scanned_count }}
            </span>
          </h2>
          <p class="mt-1 text-[11px] text-ink-3">
            报告期 {{ reportDate || '—' }} · {{ result.source }} ·
            {{ formatDateTime(result.fetched_at) }}
          </p>
        </div>
      </div>

      <ScreenerResults v-if="displayItems.length" :items="displayItems" />

      <div
        v-else
        class="rounded-lg border border-dashed border-line bg-canvas px-4 py-12 text-center text-xs text-ink-3"
      >
        当前条件下没有符合「小市值 + 高增长」的标的，可放宽市值或增速阈值。
      </div>

      <p class="mt-3 text-[10px] leading-relaxed text-ink-3">{{ result.disclaimer }}</p>
    </section>

    <div
      v-else-if="!loading"
      class="mt-4 rounded-lg border border-dashed border-line bg-canvas px-4 py-12 text-center"
    >
      <div class="text-sm font-medium text-ink">小市值成长</div>
      <p class="mt-1 text-xs text-ink-3">
        取最新报告期营收同比 ≥ 10%、净利同比 ≥ 100% 的 A 股，要求总市值不超过上限，
        剔除 ST / 创业板 / 科创板，按总市值由小到大排名。
      </p>
    </div>
  </div>
</template>
