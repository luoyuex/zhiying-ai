<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  companyApi,
  type FundFlowData,
  type FundFlowMetric,
} from '@/api/company'
import FundFlowChart from '@/components/market/FundFlowChart.vue'
import { getErrorMessage } from '@/utils/errors'
import {
  formatBig,
  formatPercent,
  formatQuoteTime,
  sourceLabel,
} from '@/utils/market'

const props = defineProps<{
  symbol: string
}>()

const METRICS: { value: FundFlowMetric; label: string }[] = [
  { value: 'main_net', label: '主力' },
  { value: 'super_large_net', label: '超大单' },
  { value: 'large_net', label: '大单' },
  { value: 'medium_net', label: '中单' },
  { value: 'small_net', label: '小单' },
]

const data = ref<FundFlowData | null>(null)
const metric = ref<FundFlowMetric>('main_net')
const loading = ref(false)
const error = ref('')

const fallbackSource = computed(() => data.value?.source === 'sina_fundflow')
const metrics = computed(() => (fallbackSource.value ? METRICS.slice(0, 2) : METRICS))

const latest = computed(() => {
  const days = data.value?.days ?? []
  return days.length ? days[days.length - 1] : null
})

const latestValue = computed(() => latest.value?.[metric.value] ?? null)

function metricLabel(): string {
  return METRICS.find((item) => item.value === metric.value)?.label ?? ''
}

async function load(): Promise<void> {
  const symbol = props.symbol
  if (!/^\d{6}$/.test(symbol)) {
    data.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data: result } = await companyApi.fundFlow(symbol)
    if (props.symbol === symbol) {
      data.value = result
      if (result.source === 'sina_fundflow' && !['main_net', 'super_large_net'].includes(metric.value)) {
        metric.value = 'main_net'
      }
    }
  } catch (err) {
    if (props.symbol === symbol) {
      data.value = null
      error.value = getErrorMessage(err, '资金流加载失败')
    }
  } finally {
    if (props.symbol === symbol) loading.value = false
  }
}

watch(
  () => props.symbol,
  () => {
    data.value = null
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-sm font-semibold text-ink">资金流</h2>
          <span class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-3">
            近 30 个交易日
          </span>
        </div>
        <p class="mt-1 text-[11px] text-ink-3">
          按净流入绘制，红柱为净流入、绿柱为净流出；单位随数值自动切换。
        </p>
        <p v-if="fallbackSource" class="mt-1 text-[11px] text-warn">
          东财资金流暂不可用，已切换新浪备用源；仅提供主力净流入与超大单。
        </p>
      </div>

      <div class="flex flex-wrap gap-1">
        <button
          v-for="item in metrics"
          :key="item.value"
          type="button"
          class="h-7 rounded-sm px-2.5 text-xs transition-colors duration-150"
          :class="
            metric === item.value
              ? 'bg-primary-soft font-medium text-primary'
              : 'text-ink-2 hover:text-ink'
          "
          @click="metric = item.value"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <div v-if="loading && !data" class="mt-4 animate-pulse">
      <div class="h-[180px] rounded-md bg-surface-2" />
      <div class="mt-3 grid grid-cols-3 gap-3">
        <div v-for="index in 3" :key="index" class="h-12 rounded bg-surface-2" />
      </div>
    </div>

    <div
      v-else-if="error"
      class="mt-4 flex h-[180px] items-center justify-center rounded-md border border-line bg-surface px-4 text-center text-xs text-ink-3"
    >
      {{ error }}
      <button
        type="button"
        class="ml-2 font-medium text-primary hover:text-primary-hover"
        @click="load"
      >
        重试
      </button>
    </div>

    <template v-else-if="data && data.days.length">
      <div class="mt-4">
        <FundFlowChart :days="data.days" :metric="metric" />
      </div>

      <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div class="rounded-md bg-surface px-3 py-2.5">
          <div class="text-[11px] text-ink-3">最新{{ metricLabel() }}净额</div>
          <div
            class="mt-1 text-[14px] font-semibold tabular-nums"
            :class="
              latestValue == null || latestValue === 0
                ? 'text-ink'
                : latestValue > 0
                  ? 'text-up'
                  : 'text-down'
            "
          >
            {{ formatBig(latestValue) }}
          </div>
        </div>
        <div class="rounded-md bg-surface px-3 py-2.5">
          <div class="text-[11px] text-ink-3">主力净占比</div>
          <div class="mt-1 text-[14px] font-semibold tabular-nums text-ink">
            {{ formatPercent(latest?.main_pct ?? null) }}
          </div>
        </div>
        <div class="rounded-md bg-surface px-3 py-2.5">
          <div class="text-[11px] text-ink-3">最新交易日</div>
          <div class="mt-1 text-[14px] font-semibold tabular-nums text-ink">
            {{ latest?.date ?? '—' }}
          </div>
        </div>
      </div>

      <div class="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-3">
        <span>区间 {{ data.days[0].date }} → {{ data.days[data.days.length - 1].date }}</span>
        <span class="tabular-nums">
          来源 {{ sourceLabel(data.source) }} · {{ formatQuoteTime(data.fetched_at) }}
        </span>
      </div>
    </template>

    <div
      v-else
      class="mt-4 flex h-[180px] items-center justify-center rounded-md border border-dashed border-line bg-surface text-xs text-ink-3"
    >
      暂无资金流数据
    </div>
  </section>
</template>
