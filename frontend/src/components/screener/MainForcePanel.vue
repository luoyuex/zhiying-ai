<script setup lang="ts">
import { ref } from 'vue'

import { type FundFlowWindow, type MainForceAnalysisRequest } from '@/api/screener'
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

const WINDOW_OPTIONS: { label: string; value: FundFlowWindow }[] = [
  { label: '今日', value: 'today' },
  { label: '近 3 日', value: '3d' },
  { label: '近 5 日', value: '5d' },
  { label: '近 10 日', value: '10d' },
]

const finalN = ref(5)
const window = ref<FundFlowWindow>('10d')
const maxChangePct = ref<string | number>('30')
const minMarketCap = ref<string | number>('50')
const maxMarketCap = ref<string | number>('5000')
const excludeST = ref(true)
const excludeGEM = ref(true)
const excludeSTAR = ref(true)

function applyFilters(filters: Record<string, unknown>): void {
  const finalNValue = Number(filters.final_n)
  if (FINAL_N_OPTIONS.some((option) => option.value === finalNValue)) {
    finalN.value = finalNValue
  }
  // 旧记录没有 window 字段，不把旧口径（7% 涨幅、无市值区间）带回新表单
  if (WINDOW_OPTIONS.some((option) => option.value === filters.window)) {
    window.value = filters.window as FundFlowWindow
    if ('max_change_pct' in filters) {
      const value = filters.max_change_pct
      maxChangePct.value = value === null || value === undefined ? '' : String(value)
    }
    if (filters.min_market_cap !== null && filters.min_market_cap !== undefined) {
      minMarketCap.value = String(filters.min_market_cap)
    }
    if (filters.max_market_cap !== null && filters.max_market_cap !== undefined) {
      maxMarketCap.value = String(filters.max_market_cap)
    }
  }
  if (typeof filters.exclude_st === 'boolean') excludeST.value = filters.exclude_st
  if (typeof filters.exclude_gem === 'boolean') excludeGEM.value = filters.exclude_gem
  if (typeof filters.exclude_star === 'boolean') excludeSTAR.value = filters.exclude_star
}

function numberOr(value: string | number, fallback: number): number {
  const parsed = Number(String(value).trim())
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
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
} = useScreenerAI({ strategy: 'main_force', applyFilters })

function runSelection(): void {
  const maxText = String(maxChangePct.value).trim()
  const payload: MainForceAnalysisRequest = {
    final_n: finalN.value,
    window: window.value,
    max_change_pct: maxText === '' ? null : Number(maxText),
    min_market_cap: numberOr(minMarketCap.value, 50),
    max_market_cap: numberOr(maxMarketCap.value, 5000),
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

        <div class="flex flex-col gap-1 text-[11px] text-ink-3">
          统计区间
          <Select
            v-model="window"
            :options="WINDOW_OPTIONS"
            :disabled="loading || restoring"
          />
        </div>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          区间涨幅上限（%）
          <input
            v-model="maxChangePct"
            type="number"
            step="0.1"
            placeholder="不限制"
            :disabled="loading || restoring"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
          />
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          总市值下限（亿）
          <input
            v-model="minMarketCap"
            type="number"
            step="10"
            :disabled="loading || restoring"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
          />
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          总市值上限（亿）
          <input
            v-model="maxMarketCap"
            type="number"
            step="100"
            :disabled="loading || restoring"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
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
      strategy="main_force"
    />

    <div
      v-else
      class="mt-4 rounded-lg border border-dashed border-line bg-canvas px-4 py-12 text-center"
    >
      <div class="text-sm font-medium text-ink">AI 主力追踪</div>
      <p class="mx-auto mt-1 max-w-xl text-xs leading-relaxed text-ink-3">
        系统按所选区间的主力资金净流入排行、结合市值与区间涨幅圈定前 100 只候选，再由资金流向、行业板块、财务基本面三位分析师整体分析，最后交给资深研究员精选，只呈现 AI 认可的标的。
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
