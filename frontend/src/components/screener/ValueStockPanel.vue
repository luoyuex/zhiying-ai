<script setup lang="ts">
import { ref } from 'vue'

import { type ValueStockAnalysisRequest } from '@/api/screener'
import Select from '@/components/ui/Select.vue'
import ScreenerAIResult from './ScreenerAIResult.vue'
import ScreenerHistory from './ScreenerHistory.vue'
import ScreenerJobLoading from './ScreenerJobLoading.vue'
import ScreenerRecordDrawer from './ScreenerRecordDrawer.vue'
import { useScreenerAI } from './useScreenerAI'

const FINAL_N_OPTIONS = [
  { label: '3 只', value: 3 },
  { label: '5 只', value: 5 },
  { label: '10 只', value: 10 },
]

const finalN = ref(5)
const maxPe = ref<string | number>(20)
const maxPb = ref<string | number>(1.5)
const minDividendYield = ref<string | number>(1)
const maxDebtRatio = ref<string | number>(30)
const excludeST = ref(true)
const excludeGEM = ref(true)
const excludeSTAR = ref(true)

function applyFilters(filters: Record<string, unknown>): void {
  const finalNValue = Number(filters.final_n)
  if (FINAL_N_OPTIONS.some((option) => option.value === finalNValue)) {
    finalN.value = finalNValue
  }
  const numericFields: Array<[unknown, typeof maxPe]> = [
    [filters.max_pe, maxPe],
    [filters.max_pb, maxPb],
    [filters.min_dividend_yield, minDividendYield],
    [filters.max_debt_ratio, maxDebtRatio],
  ]
  for (const [value, target] of numericFields) {
    if (value !== undefined && value !== null) target.value = String(value)
  }
  if (typeof filters.exclude_st === 'boolean') excludeST.value = filters.exclude_st
  if (typeof filters.exclude_gem === 'boolean') excludeGEM.value = filters.exclude_gem
  if (typeof filters.exclude_star === 'boolean') excludeSTAR.value = filters.exclude_star
}

const {
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
} = useScreenerAI({ strategy: 'value_stock', applyFilters })

function toNumber(value: string | number, fallback: number): number {
  const parsed = Number(String(value).trim())
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function runSelection(): void {
  const payload: ValueStockAnalysisRequest = {
    final_n: finalN.value,
    max_pe: toNumber(maxPe.value, 20),
    max_pb: toNumber(maxPb.value, 1.5),
    min_dividend_yield: Math.max(0, Number(String(minDividendYield.value).trim()) || 0),
    max_debt_ratio: Math.min(100, Math.max(0, Number(String(maxDebtRatio.value).trim()) || 0)),
    exclude_st: excludeST.value,
    exclude_gem: excludeGEM.value,
    exclude_star: excludeSTAR.value,
    exclude_bj: true,
  }
  void run(payload)
}
</script>

<template>
  <div>
    <form class="rounded-lg border border-line bg-canvas p-4" @submit.prevent="runSelection">
      <div class="flex flex-wrap items-end gap-3">
        <div class="flex flex-col gap-1 text-[11px] text-ink-3">
          最终精选数量
          <Select
            v-model="finalN"
            :options="FINAL_N_OPTIONS"
            :disabled="loading || restoring"
          />
        </div>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          PE 上限
          <input
            v-model="maxPe"
            type="number"
            step="1"
            :disabled="loading || restoring"
            class="h-9 w-20 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
          />
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          PB 上限
          <input
            v-model="maxPb"
            type="number"
            step="0.1"
            :disabled="loading || restoring"
            class="h-9 w-20 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
          />
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          股息率下限（%）
          <input
            v-model="minDividendYield"
            type="number"
            step="0.5"
            :disabled="loading || restoring"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
          />
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          资产负债率上限（%）
          <input
            v-model="maxDebtRatio"
            type="number"
            step="5"
            :disabled="loading || restoring"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
          />
        </label>

        <label class="flex h-9 cursor-pointer items-center gap-1.5 text-xs text-ink-2">
          <input
            v-model="excludeST"
            type="checkbox"
            :disabled="loading || restoring"
            class="size-3.5 accent-ink"
          />
          排除 ST
        </label>
        <label class="flex h-9 cursor-pointer items-center gap-1.5 text-xs text-ink-2">
          <input
            v-model="excludeGEM"
            type="checkbox"
            :disabled="loading || restoring"
            class="size-3.5 accent-ink"
          />
          排除创业板
        </label>
        <label class="flex h-9 cursor-pointer items-center gap-1.5 text-xs text-ink-2">
          <input
            v-model="excludeSTAR"
            type="checkbox"
            :disabled="loading || restoring"
            class="size-3.5 accent-ink"
          />
          排除科创板
        </label>

        <button
          type="submit"
          class="ml-auto h-9 rounded-md border border-ink bg-ink px-4 text-xs text-canvas transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="loading || restoring"
        >
          {{ loading ? 'AI 选股中…' : '开始 AI 选股' }}
        </button>
      </div>
    </form>

    <div
      v-if="error"
      class="mt-4 rounded-md border border-line bg-canvas px-4 py-3 text-xs text-danger"
    >
      {{ error }}
    </div>

    <ScreenerJobLoading
      v-if="loading || restoring"
      class="mt-4"
      :restoring="restoring"
      :phase="job?.phase || ''"
      :elapsed="displayElapsed"
    />

    <ScreenerAIResult
      v-else-if="analysis"
      class="mt-6"
      :analysis="analysis"
      strategy="value_stock"
    />

    <div
      v-else
      class="mt-4 rounded-lg border border-dashed border-line bg-canvas px-4 py-12 text-center"
    >
      <div class="text-sm font-medium text-ink">AI 价值洼地</div>
      <p class="mx-auto mt-1 max-w-xl text-xs leading-relaxed text-ink-3">
        系统先按 PE/PB、近 12 个月股息率、最新报告期资产负债率圈定低估值候选，再由资金与流动性、行业板块、估值质量三位分析师整体分析，最后交给资深研究员精选，只呈现 AI 认可的标的。
      </p>
    </div>

    <ScreenerHistory
      class="mt-4"
      :records="records"
      :loading="recordsLoading"
      :error="recordsError"
      :active-record-id="activeRecordId"
      :detail-record-id="detailRecordId"
      @view="openRecordDetail"
    />

    <ScreenerRecordDrawer
      :open="detailOpen"
      :record="detailRecord"
      :loading="detailLoading"
      :error="detailError"
      @close="closeRecordDetail"
    />
  </div>
</template>
