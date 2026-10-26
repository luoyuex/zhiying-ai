<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { AIJobState } from '@/api/ai'
import { watchlistApi, type WatchlistEntry } from '@/api/watchlist'
import AppShell from '@/components/layout/AppShell.vue'
import PortfolioDiagnosis from '@/components/watchlist/PortfolioDiagnosis.vue'
import PriceAlertsOverview from '@/components/watchlist/PriceAlertsOverview.vue'
import WatchlistCard from '@/components/watchlist/WatchlistCard.vue'
import { useAIBatch } from '@/composables/useAIBatch'
import { useAuthStore } from '@/stores/auth'
import { getErrorMessage } from '@/utils/errors'

const MAX_BATCH = 20
const PENDING_STORAGE_PREFIX = 'zhiying:watchlist-pending:'

const auth = useAuthStore()

const watchlist = ref<WatchlistEntry[]>([])
const loading = ref(true)
const error = ref('')
const removingSymbol = ref('')
const selectedSymbols = ref<string[]>([])

const count = computed(() => watchlist.value.length)
const selectedCount = computed(() => selectedSymbols.value.length)
const allSelected = computed(
  () => count.value > 0 && count.value <= MAX_BATCH && selectedCount.value === count.value,
)

const batch = useAIBatch({
  storageKey: () => `${PENDING_STORAGE_PREFIX}${auth.user?.id ?? 'anonymous'}`,
  onSucceeded: applyJobResult,
  onAllDone: () => load(true),
})
const jobStates = batch.jobStates
const pendingCount = batch.pendingCount
const batchSubmitting = batch.submitting
const batchError = batch.error

async function load(silent = false): Promise<void> {
  if (!silent) {
    loading.value = true
    error.value = ''
  }
  try {
    const { data } = await watchlistApi.list()
    watchlist.value = data
    selectedSymbols.value = selectedSymbols.value.filter((symbol) =>
      data.some((item) => item.symbol === symbol),
    )
  } catch (err) {
    if (!silent) {
      watchlist.value = []
      error.value = getErrorMessage(err, '自选股加载失败')
    }
  } finally {
    if (!silent) loading.value = false
  }
}

async function remove(symbol: string): Promise<void> {
  if (removingSymbol.value) return
  removingSymbol.value = symbol
  const backup = watchlist.value
  // 立即从列表移除，不重新拉取
  watchlist.value = watchlist.value.filter((item) => item.symbol !== symbol)
  selectedSymbols.value = selectedSymbols.value.filter((item) => item !== symbol)
  batch.clearSymbol(symbol)
  try {
    await watchlistApi.remove(symbol)
  } catch (err) {
    watchlist.value = backup
    error.value = getErrorMessage(err, '移出自选失败')
  } finally {
    removingSymbol.value = ''
  }
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
  selectedSymbols.value = watchlist.value.slice(0, MAX_BATCH).map((item) => item.symbol)
  batchError.value =
    count.value > MAX_BATCH ? `一次最多分析 ${MAX_BATCH} 只，已选择前 ${MAX_BATCH} 只` : ''
}

function onMetaUpdated(
  symbol: string,
  payload: { note: string; cost_price: number | null; quantity: number | null },
): void {
  const target = watchlist.value.find((item) => item.symbol === symbol)
  if (target) Object.assign(target, payload)
}

function applyJobResult(symbol: string, job: AIJobState): void {
  if (!job.result) return
  const target = watchlist.value.find((item) => item.symbol === symbol)
  if (!target) return
  const decision = job.result.decision
  target.latest = {
    report_id: job.result.report_id ?? '',
    rating: decision?.rating ?? job.result.analysis.rating,
    confidence: decision?.confidence ?? job.result.analysis.confidence,
    decision_source: decision?.decision_source ?? '',
    position_action: decision?.position_action ?? null,
    summary: (decision?.summary ?? job.result.analysis.summary).slice(0, 200),
    rating_change: job.result.rating_change ?? null,
    prev_rating: job.result.prev_rating ?? null,
    created_at: job.result.generated_at,
  }
}

async function submitBatch(): Promise<void> {
  await batch.submit(selectedSymbols.value)
}

onMounted(async () => {
  await load()
  // 列表加载失败时保留存储，等下次刷新再恢复
  if (!error.value) batch.restore(watchlist.value.map((item) => item.symbol))
})
</script>

<template>
  <AppShell>
    <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">关注列表、持仓信息与最新 AI 结论</p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">自选股</h1>
      </div>
      <div v-if="count" class="flex flex-wrap items-center gap-3">
        <label class="flex cursor-pointer items-center gap-1.5 text-xs text-ink-3">
          <input
            type="checkbox"
            class="size-3.5 cursor-pointer accent-ink"
            :checked="allSelected"
            @change="toggleSelectAll"
          />
          全选
        </label>
        <span class="text-xs text-ink-3">
          {{ count }} 只 · 上限 50 只<template v-if="pendingCount">
            · {{ pendingCount }} 只分析中</template
          >
        </span>
        <button
          type="button"
          class="h-8 rounded-md border px-3 text-xs transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          :class="
            selectedCount
              ? 'border-ink bg-ink text-canvas hover:opacity-80'
              : 'border-line text-ink-2'
          "
          :disabled="!selectedCount || batchSubmitting"
          @click="submitBatch"
        >
          {{
            batchSubmitting
              ? '提交中…'
              : selectedCount
                ? `批量分析 (${selectedCount})`
                : '批量分析'
          }}
        </button>
      </div>
    </section>

    <p v-if="batchError" class="mt-3 text-xs text-danger">{{ batchError }}</p>

    <PortfolioDiagnosis v-if="!loading && !error && watchlist.length" class="mt-6" />
    <PriceAlertsOverview v-if="!loading && !error" />

    <div class="mt-6">
      <div v-if="loading" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="index in 3"
          :key="index"
          class="rounded-lg border border-line bg-canvas p-4"
        >
          <div class="h-4 w-24 animate-pulse rounded bg-surface-2" />
          <div class="mt-3 h-6 w-32 animate-pulse rounded bg-surface-2" />
          <div class="mt-2 h-3 w-20 animate-pulse rounded bg-surface-2" />
          <div class="mt-4 h-8 animate-pulse rounded bg-surface-2" />
        </div>
      </div>

      <div
        v-else-if="error"
        class="rounded-lg border border-line bg-canvas px-4 py-10 text-center"
      >
        <p class="text-xs text-danger">{{ error }}</p>
        <button
          type="button"
          class="mt-3 rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
          @click="load()"
        >
          重新加载
        </button>
      </div>

      <div
        v-else-if="!watchlist.length"
        class="rounded-lg border border-dashed border-line bg-canvas px-4 py-14 text-center"
      >
        <div class="text-sm font-medium text-ink">还没有自选股</div>
        <p class="mt-1 text-xs text-ink-3">
          查询一只股票，在个股页点「加入自选」即可固定在这里。
        </p>
        <RouterLink
          to="/"
          class="mt-4 inline-flex rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
        >
          去查询股票
        </RouterLink>
      </div>

      <div v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <WatchlistCard
          v-for="item in watchlist"
          :key="item.symbol"
          :item="item"
          :selected="selectedSymbols.includes(item.symbol)"
          :batch="jobStates[item.symbol] ?? null"
          @toggle="toggleSelect(item.symbol)"
          @remove="remove(item.symbol)"
          @updated="onMetaUpdated(item.symbol, $event)"
        />
      </div>
    </div>
  </AppShell>
</template>
