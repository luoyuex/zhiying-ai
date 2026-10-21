<script setup lang="ts">
import { ref } from 'vue'

import { screenerApi, type MainForceScreenResponse } from '@/api/screener'
import { getErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/report'
import ScreenerResults from './ScreenerResults.vue'
import type { ScreenerDisplayItem } from './types'

const topN = ref(10)
const maxChangePct = ref<string | number>('7')
const excludeST = ref(true)
const excludeGEM = ref(true)
const excludeSTAR = ref(true)

const loading = ref(false)
const error = ref('')
const result = ref<MainForceScreenResponse | null>(null)
const displayItems = ref<ScreenerDisplayItem[]>([])

function formatAmount(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`
  if (abs >= 1e4) return `${(value / 1e4).toFixed(0)} 万`
  return value.toFixed(0)
}

function netTone(value: number): string {
  if (value > 0) return 'text-up'
  if (value < 0) return 'text-down'
  return 'text-ink-2'
}

function toDisplay(data: MainForceScreenResponse): ScreenerDisplayItem[] {
  return data.items.map((item) => ({
    symbol: item.symbol,
    name: item.name,
    price: item.price,
    change_pct: item.change_pct,
    metrics: [
      {
        label: '主力净额',
        value: formatAmount(item.main_net),
        tone: netTone(item.main_net),
      },
      {
        label: '净占比',
        value:
          item.main_net_pct === null ? '—' : `${item.main_net_pct.toFixed(2)}%`,
        tone: netTone(item.main_net_pct ?? 0),
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
    const maxText = String(maxChangePct.value).trim()
    const { data } = await screenerApi.mainForce({
      top_n: topN.value,
      max_change_pct: maxText === '' ? null : Number(maxText),
      exclude_st: excludeST.value,
      exclude_gem: excludeGEM.value,
      exclude_star: excludeSTAR.value,
      exclude_bj: true,
    })
    result.value = data
    displayItems.value = toDisplay(data)
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
            <option :value="20">20 只</option>
          </select>
        </label>

        <label class="flex flex-col gap-1 text-[11px] text-ink-3">
          最大涨幅（%）
          <input
            v-model="maxChangePct"
            type="number"
            step="0.1"
            placeholder="不限制"
            class="h-9 w-24 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none"
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
      正在拉取资金流排行并筛选…
    </div>

    <section v-else-if="result" class="mt-6">
      <div class="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-sm font-semibold text-ink">
            候选标的 {{ result.items.length }}
            <span class="ml-1 text-[11px] font-normal text-ink-3">
              / 命中 {{ result.candidate_count }} · 扫描 {{ result.scanned_count }}
            </span>
          </h2>
          <p class="mt-1 text-[11px] text-ink-3">
            {{ result.source }} · {{ formatDateTime(result.fetched_at) }}
          </p>
        </div>
      </div>

      <ScreenerResults v-if="displayItems.length" :items="displayItems" />

      <div
        v-else
        class="rounded-lg border border-dashed border-line bg-canvas px-4 py-12 text-center text-xs text-ink-3"
      >
        当前条件下没有符合条件的标的，可放宽涨幅上限或减少排除项。
      </div>

      <p class="mt-3 text-[10px] leading-relaxed text-ink-3">{{ result.disclaimer }}</p>
    </section>

    <div
      v-else-if="!loading"
      class="mt-4 rounded-lg border border-dashed border-line bg-canvas px-4 py-12 text-center"
    >
      <div class="text-sm font-medium text-ink">按主力资金筛选</div>
      <p class="mt-1 text-xs text-ink-3">
        取超大单净流入排名前 300 只，过滤 ST / 创业板 / 科创板与涨幅过高的标的。
      </p>
    </div>
  </div>
</template>
