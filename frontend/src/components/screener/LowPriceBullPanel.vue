<script setup lang="ts">
import { ref } from 'vue'

import { screenerApi, type LowPriceBullResponse } from '@/api/screener'
import { getErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/report'
import ScreenerResults from './ScreenerResults.vue'
import type { ScreenerDisplayItem } from './types'

const topN = ref(5)
const maxPrice = ref<string | number>(10)
const minProfitGrowth = ref<string | number>(100)
const excludeST = ref(true)
const excludeGEM = ref(true)
const excludeSTAR = ref(true)

const loading = ref(false)
const error = ref('')
const result = ref<LowPriceBullResponse | null>(null)
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

function toDisplay(data: LowPriceBullResponse): ScreenerDisplayItem[] {
  return data.items.map((item) => ({
    symbol: item.symbol,
    name: item.name,
    price: item.price,
    change_pct: item.change_pct,
    metrics: [
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
    const price = Number(String(maxPrice.value).trim())
    const growth = Number(String(minProfitGrowth.value).trim())
    const { data } = await screenerApi.lowPriceBull({
      top_n: topN.value,
      max_price: Number.isFinite(price) && price > 0 ? price : 10,
      min_profit_growth: Number.isFinite(growth) && growth >= 0 ? growth : 100,
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
          股价上限（元）
          <input
            v-model="maxPrice"
            type="number"
            step="0.1"
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
      正在读取最新业绩报表并匹配行情…
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
        当前条件下没有符合「低价 + 高净利增长」的标的，可放宽股价或净利增速。
      </div>

      <p class="mt-3 text-[10px] leading-relaxed text-ink-3">{{ result.disclaimer }}</p>
    </section>

    <div
      v-else-if="!loading"
      class="mt-4 rounded-lg border border-dashed border-line bg-canvas px-4 py-12 text-center"
    >
      <div class="text-sm font-medium text-ink">低价擒牛</div>
      <p class="mt-1 text-xs text-ink-3">
        取最新报告期净利润同比 ≥ 100% 的 A 股，要求股价低于上限，剔除 ST / 创业板 /
        科创板，按成交额由小到大排名。
      </p>
    </div>
  </div>
</template>
