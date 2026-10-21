<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { watchlistApi } from '@/api/watchlist'
import { useAIBatch } from '@/composables/useAIBatch'
import { getErrorMessage } from '@/utils/errors'
import type { ScreenerDisplayItem } from './types'

const props = defineProps<{
  items: ScreenerDisplayItem[]
}>()

const MAX_BATCH = 20

const watchlisted = ref<Set<string>>(new Set())
const addingSymbol = ref('')
const selectedSymbols = ref<string[]>([])
const addError = ref('')

const batch = useAIBatch()
const jobStates = batch.jobStates
const submitting = batch.submitting
const batchError = batch.error

const selectedCount = computed(() => selectedSymbols.value.length)
const allSelected = computed(
  () =>
    props.items.length > 0 &&
    selectedCount.value === Math.min(props.items.length, MAX_BATCH),
)

function changeTone(value: number | null): string {
  if (value === null || value === 0) return 'text-ink-2'
  return value > 0 ? 'text-up' : 'text-down'
}

function formatPrice(value: number | null): string {
  return value === null ? '—' : value.toFixed(2)
}

function formatPct(value: number | null): string {
  if (value === null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function jobText(symbol: string): string {
  const state = jobStates.value[symbol]
  if (!state) return ''
  if (state.status === 'queued') return '排队中'
  if (state.status === 'running') return state.phase || '分析中'
  if (state.status === 'succeeded') return '分析完成'
  return state.message || '分析失败'
}

function jobTone(symbol: string): string {
  const state = jobStates.value[symbol]
  if (!state) return 'text-ink-3'
  return state.status === 'failed' ? 'text-danger' : 'text-ink-3'
}

function toggleSelect(symbol: string): void {
  if (selectedSymbols.value.includes(symbol)) {
    selectedSymbols.value = selectedSymbols.value.filter((item) => item !== symbol)
    return
  }
  if (selectedSymbols.value.length >= MAX_BATCH) {
    batchError.value = `一次最多分析 ${MAX_BATCH} 只`
    return
  }
  batchError.value = ''
  selectedSymbols.value = [...selectedSymbols.value, symbol]
}

function toggleSelectAll(): void {
  if (allSelected.value) {
    selectedSymbols.value = []
    return
  }
  selectedSymbols.value = props.items.slice(0, MAX_BATCH).map((item) => item.symbol)
  batchError.value =
    props.items.length > MAX_BATCH
      ? `一次最多分析 ${MAX_BATCH} 只，已选择前 ${MAX_BATCH} 只`
      : ''
}

function isWatchlisted(symbol: string): boolean {
  return watchlisted.value.has(symbol)
}

async function addToWatchlist(item: ScreenerDisplayItem): Promise<void> {
  if (addingSymbol.value || isWatchlisted(item.symbol)) return
  addingSymbol.value = item.symbol
  addError.value = ''
  try {
    await watchlistApi.add(item.symbol)
    watchlisted.value = new Set([...watchlisted.value, item.symbol])
  } catch (err) {
    addError.value = getErrorMessage(err, '加入自选失败')
  } finally {
    addingSymbol.value = ''
  }
}

async function submitBatch(): Promise<void> {
  await batch.submit(selectedSymbols.value)
}

async function loadWatchlisted(): Promise<void> {
  try {
    const { data } = await watchlistApi.list()
    watchlisted.value = new Set(data.map((item) => item.symbol))
  } catch {
    watchlisted.value = new Set()
  }
}

onMounted(() => {
  void loadWatchlisted()
})
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-end gap-3">
      <label class="flex cursor-pointer items-center gap-1.5 text-xs text-ink-3">
        <input
          type="checkbox"
          class="size-3.5 cursor-pointer accent-ink"
          :checked="allSelected"
          @change="toggleSelectAll"
        />
        全选
      </label>
      <button
        type="button"
        class="h-8 rounded-md border px-3 text-xs transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        :class="
          selectedCount
            ? 'border-ink bg-ink text-canvas hover:opacity-80'
            : 'border-line text-ink-2'
        "
        :disabled="!selectedCount || submitting"
        @click="submitBatch"
      >
        {{
          submitting
            ? '提交中…'
            : `批量分析${selectedCount ? ` (${selectedCount})` : ''}`
        }}
      </button>
    </div>

    <p v-if="batchError" class="mt-2 text-xs text-danger">
      {{ batchError }}
    </p>
    <p v-if="addError" class="mt-2 text-xs text-danger">{{ addError }}</p>

    <div class="mt-3 overflow-hidden rounded-lg border border-line bg-canvas">
      <div
        v-for="item in items"
        :key="item.symbol"
        class="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 last:border-b-0"
      >
        <input
          type="checkbox"
          class="size-3.5 shrink-0 cursor-pointer accent-ink"
          :checked="selectedSymbols.includes(item.symbol)"
          :aria-label="`选择 ${item.name}`"
          @change="toggleSelect(item.symbol)"
        />

        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-baseline gap-x-2">
            <RouterLink
              :to="`/stock/${item.symbol}`"
              class="text-[13px] font-medium text-ink transition-colors hover:text-primary"
            >
              {{ item.name }}
            </RouterLink>
            <span class="text-[11px] tabular-nums text-ink-3">{{ item.symbol }}</span>
          </div>
          <div
            v-if="jobText(item.symbol)"
            class="mt-0.5 text-[11px]"
            :class="jobTone(item.symbol)"
          >
            {{ jobText(item.symbol) }}
          </div>
        </div>

        <div class="w-20 text-right">
          <div class="text-sm font-semibold tabular-nums text-ink">
            {{ formatPrice(item.price) }}
          </div>
          <div class="text-[11px] tabular-nums" :class="changeTone(item.change_pct)">
            {{ formatPct(item.change_pct) }}
          </div>
        </div>

        <div
          v-for="metric in item.metrics"
          :key="metric.label"
          class="w-20 text-right"
        >
          <div class="text-[10px] text-ink-3">{{ metric.label }}</div>
          <div class="text-xs tabular-nums" :class="metric.tone || 'text-ink-2'">
            {{ metric.value }}
          </div>
        </div>

        <div class="flex shrink-0 items-center gap-2">
          <button
            type="button"
            class="h-7 rounded-md border border-line px-2.5 text-[11px] transition-colors hover:border-line-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            :class="isWatchlisted(item.symbol) ? 'text-ink-3' : 'text-ink-2'"
            :disabled="isWatchlisted(item.symbol) || addingSymbol === item.symbol"
            @click="addToWatchlist(item)"
          >
            {{ isWatchlisted(item.symbol) ? '已自选' : '加入自选' }}
          </button>
          <RouterLink
            :to="`/stock/${item.symbol}`"
            class="text-[11px] text-ink-3 transition-colors hover:text-ink"
          >
            详情 →
          </RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>
