<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { ScreenerRecordDetail } from '@/api/screener'
import { formatFullDateTime } from '@/utils/report'
import { exportScreenerCsv } from './screenerExport'
import { strategyMeta } from './strategy'

const props = defineProps<{
  open: boolean
  record: ScreenerRecordDetail | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{ close: [] }>()

const closeButtonRef = ref<HTMLButtonElement | null>(null)

const FLOW_WINDOW_LABELS: Record<string, string> = {
  today: '今日',
  '3d': '近 3 日',
  '5d': '近 5 日',
  '10d': '近 10 日',
}

const reports = computed(() => {
  const data = props.record?.result
  if (!data) return []
  const meta = strategyMeta(props.record?.strategy ?? 'main_force')
  return [
    { title: meta.fundFlow, content: data.fund_flow },
    { title: meta.industry, content: data.industry },
    { title: meta.fundamental, content: data.fundamental },
  ]
})

const filterText = computed(() => {
  const filters = props.record?.filters
  if (!filters) return ''
  const parts: string[] = []
  const finalN = Number(filters.final_n)
  if (finalN) parts.push(`目标 ${finalN} 只`)
  const windowValue = filters.window
  if (typeof windowValue === 'string' && FLOW_WINDOW_LABELS[windowValue]) {
    parts.push(`区间 ${FLOW_WINDOW_LABELS[windowValue]}`)
  }
  const minMarketCap = filters.min_market_cap
  if (minMarketCap !== null && minMarketCap !== undefined) {
    parts.push(`总市值 ≥ ${String(minMarketCap)} 亿`)
  }
  const maxPrice = filters.max_price
  if (maxPrice !== null && maxPrice !== undefined) {
    parts.push(`股价上限 ${String(maxPrice)} 元`)
  }
  const maxMarketCap = filters.max_market_cap
  if (maxMarketCap !== null && maxMarketCap !== undefined) {
    parts.push(`总市值上限 ${String(maxMarketCap)} 亿`)
  }
  const minProfitGrowth = filters.min_profit_growth
  if (minProfitGrowth !== null && minProfitGrowth !== undefined) {
    parts.push(`净利同比 ≥ ${String(minProfitGrowth)}%`)
  }
  const minRevenueGrowth = filters.min_revenue_growth
  if (minRevenueGrowth !== null && minRevenueGrowth !== undefined) {
    parts.push(`营收同比 ≥ ${String(minRevenueGrowth)}%`)
  }
  const maxPe = filters.max_pe
  if (maxPe !== null && maxPe !== undefined) parts.push(`PE ≤ ${String(maxPe)}`)
  const maxPb = filters.max_pb
  if (maxPb !== null && maxPb !== undefined) parts.push(`PB ≤ ${String(maxPb)}`)
  const minDividend = filters.min_dividend_yield
  if (minDividend !== null && minDividend !== undefined) {
    parts.push(`股息率 ≥ ${String(minDividend)}%`)
  }
  const maxDebt = filters.max_debt_ratio
  if (maxDebt !== null && maxDebt !== undefined) {
    parts.push(`资产负债率 ≤ ${String(maxDebt)}%`)
  }
  const maxChange = filters.max_change_pct
  if (maxChange !== null && maxChange !== undefined) {
    const label = props.record?.strategy === 'main_force' ? '区间涨幅上限' : '涨幅上限'
    parts.push(`${label} ${String(maxChange)}%`)
  }
  const excludes: string[] = []
  if (filters.exclude_st) excludes.push('ST')
  if (filters.exclude_gem) excludes.push('创业板')
  if (filters.exclude_star) excludes.push('科创板')
  if (excludes.length) parts.push(`排除 ${excludes.join(' / ')}`)
  return parts.join(' · ')
})

function close(): void {
  emit('close')
}

function exportCsv(): void {
  if (!props.record) return
  exportScreenerCsv(
    props.record.result,
    strategyMeta(props.record.strategy).name,
  )
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && props.open) close()
}

watch(
  () => props.open,
  async (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
    if (open) {
      await nextTick()
      closeButtonRef.value?.focus()
    }
  },
)

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-ink/35" @click="close" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="选股记录详情"
        class="relative flex h-full w-full max-w-3xl flex-col border-l border-line bg-canvas shadow-pop"
      >
        <header
          class="flex items-start justify-between gap-3 border-b border-line px-5 py-4"
        >
          <div class="min-w-0">
            <h2 class="text-base font-semibold text-ink">
              选股记录详情
              <span v-if="record" class="ml-1 text-xs font-normal text-ink-3">
                {{ strategyMeta(record.strategy).name }}
              </span>
            </h2>
            <p
              v-if="record"
              class="mt-1 flex items-center gap-1.5 text-[11px] text-ink-2"
            >
              <svg
                class="size-3.5 shrink-0 text-ink-3"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" stroke-linecap="round" />
              </svg>
              选股时间 {{ formatFullDateTime(record.created_at) }}
            </p>
          </div>
          <button
            v-if="record"
            type="button"
            class="h-8 shrink-0 rounded-md border border-line-strong bg-canvas px-2.5 text-[11px] text-ink-2 transition-colors hover:border-ink-3 hover:text-ink"
            @click="exportCsv"
          >
            导出 CSV
          </button>
          <button
            ref="closeButtonRef"
            type="button"
            class="flex size-8 shrink-0 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
            aria-label="关闭详情"
            @click="close"
          >
            <svg
              class="size-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
            </svg>
          </button>
        </header>

        <div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          <div v-if="loading" class="py-20 text-center">
            <span
              class="mx-auto mb-3 block size-5 animate-spin rounded-full border-2 border-ink-3/25 border-t-ink-3"
            />
            <div class="text-xs text-ink-3">正在加载选股详情…</div>
          </div>

          <div
            v-else-if="error"
            class="rounded-md bg-danger-soft px-4 py-3 text-xs text-danger"
          >
            {{ error }}
          </div>

          <template v-else-if="record">
            <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h3 class="text-sm font-semibold text-ink">
                AI 精选 {{ record.result.recommendations.length }} 只
              </h3>
              <span class="text-[11px] text-ink-3">
                分析候选 {{ record.result.analyzed_count }} 只
              </span>
              <span class="text-[11px] text-ink-3">
                额度 {{ record.result.quota_used }} / {{ record.result.quota_limit }}
              </span>
            </div>
            <p v-if="filterText" class="mt-1 text-[11px] text-ink-3">
              {{ filterText }}
            </p>

            <div v-if="record.result.recommendations.length" class="mt-4 space-y-2">
              <div
                v-for="recommendation in record.result.recommendations"
                :key="recommendation.symbol"
                class="rounded-md border border-line px-3.5 py-3"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span
                    class="flex size-5 items-center justify-center rounded bg-ink text-[11px] text-canvas"
                  >
                    {{ recommendation.rank }}
                  </span>
                  <RouterLink
                    :to="`/stock/${recommendation.symbol}`"
                    class="text-[13px] font-medium text-ink transition-colors hover:text-primary"
                  >
                    {{ recommendation.name }}
                  </RouterLink>
                  <span class="text-[11px] tabular-nums text-ink-3">
                    {{ recommendation.symbol }}
                  </span>
                  <span
                    v-if="recommendation.position || recommendation.investment_period"
                    class="ml-auto text-[11px] text-ink-3"
                  >
                    {{
                      [recommendation.position, recommendation.investment_period]
                        .filter(Boolean)
                        .join(' · ')
                    }}
                  </span>
                </div>
                <ul class="mt-1.5 space-y-1">
                  <li
                    v-for="(reason, index) in recommendation.reasons"
                    :key="index"
                    class="flex gap-2 text-[11px] leading-relaxed text-ink-2"
                  >
                    <span class="mt-1.5 size-1 shrink-0 rounded-full bg-ink-3" />
                    {{ reason }}
                  </li>
                </ul>
                <div class="mt-1.5 grid gap-1 text-[11px] leading-relaxed sm:grid-cols-2">
                  <p v-if="recommendation.highlights" class="text-ink-2">
                    <span class="text-ink-3">亮点：</span>{{ recommendation.highlights }}
                  </p>
                  <p v-if="recommendation.risks" class="text-ink-2">
                    <span class="text-ink-3">风险：</span>{{ recommendation.risks }}
                  </p>
                </div>
              </div>
            </div>
            <div
              v-else
              class="mt-4 rounded-md border border-dashed border-line px-4 py-10 text-center text-xs text-ink-3"
            >
              这次没有产生 AI 精选结果。
            </div>

            <div class="mt-5 space-y-2">
              <details
                v-for="report in reports"
                :key="report.title"
                class="rounded-md border border-line bg-surface"
              >
                <summary
                  class="cursor-pointer px-3.5 py-2.5 text-[12px] font-medium text-ink transition-colors hover:text-primary"
                >
                  {{ report.title }}
                </summary>
                <p
                  class="max-h-80 overflow-y-auto whitespace-pre-line border-t border-line px-3.5 py-3 text-[11px] leading-relaxed text-ink-2"
                >
                  {{ report.content || '暂无内容' }}
                </p>
              </details>
            </div>

            <p class="mt-4 text-[10px] leading-relaxed text-ink-3">
              {{ record.result.disclaimer }}
            </p>
          </template>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
