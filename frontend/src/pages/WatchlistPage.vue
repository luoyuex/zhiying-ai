<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { aiApi, type AIJobState } from '@/api/ai'
import {
  watchlistApi,
  type WatchlistEntry,
  type WatchlistJobState,
} from '@/api/watchlist'
import AppShell from '@/components/layout/AppShell.vue'
import WatchlistCard from '@/components/watchlist/WatchlistCard.vue'
import { useAuthStore } from '@/stores/auth'
import { getErrorMessage } from '@/utils/errors'

const POLL_INTERVAL = 2500
const POLL_MAX_FAILURES = 5
const MAX_BATCH = 20
const PENDING_STORAGE_PREFIX = 'zhiying:watchlist-pending:'

const auth = useAuthStore()

const watchlist = ref<WatchlistEntry[]>([])
const loading = ref(true)
const error = ref('')

const removingSymbol = ref('')
const selectedSymbols = ref<string[]>([])
const jobStates = ref<Record<string, WatchlistJobState>>({})
const pendingJobs = ref<Record<string, string>>({})
const batchSubmitting = ref(false)
const batchError = ref('')
const pollFailures: Record<string, number> = {}
let pollTimer: ReturnType<typeof setTimeout> | null = null

const count = computed(() => watchlist.value.length)
const selectedCount = computed(() => selectedSymbols.value.length)
const allSelected = computed(
  () => count.value > 0 && count.value <= MAX_BATCH && selectedCount.value === count.value,
)
const pendingCount = computed(() => Object.keys(pendingJobs.value).length)
const pendingStorageKey = computed(
  () => `${PENDING_STORAGE_PREFIX}${auth.user?.id ?? 'anonymous'}`,
)

// 把排队中的任务写入 sessionStorage，刷新页面后可重新接上进度
watch(
  pendingJobs,
  (value) => {
    try {
      if (Object.keys(value).length) {
        sessionStorage.setItem(pendingStorageKey.value, JSON.stringify(value))
      } else {
        sessionStorage.removeItem(pendingStorageKey.value)
      }
    } catch {
      // 隐私模式等场景下 sessionStorage 不可用，忽略即可
    }
  },
  { deep: true },
)

function restorePendingJobs(): void {
  try {
    const raw = sessionStorage.getItem(pendingStorageKey.value)
    if (!raw) return
    const saved = JSON.parse(raw) as Record<string, unknown>
    const entries = Object.entries(saved).filter(
      ([symbol, jobId]) =>
        typeof jobId === 'string' &&
        jobId.length > 0 &&
        watchlist.value.some((item) => item.symbol === symbol),
    )
    if (!entries.length) {
      sessionStorage.removeItem(pendingStorageKey.value)
      return
    }
    for (const [symbol, jobId] of entries) {
      pendingJobs.value[symbol] = jobId as string
      jobStates.value[symbol] = { status: 'queued' }
    }
    schedulePoll(0)
  } catch {
    // 存储内容损坏时直接忽略，不阻塞页面
  }
}

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
  delete pendingJobs.value[symbol]
  delete jobStates.value[symbol]
  delete pollFailures[symbol]
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

function schedulePoll(delay = POLL_INTERVAL): void {
  if (pollTimer !== null) return
  pollTimer = setTimeout(() => {
    pollTimer = null
    void pollJobs()
  }, delay)
}

async function pollJobs(): Promise<void> {
  const pending = Object.entries(pendingJobs.value)
  if (!pending.length) return

  await Promise.all(
    pending.map(async ([symbol, jobId]) => {
      try {
        const { data } = await aiApi.job(jobId)
        if (pendingJobs.value[symbol] !== jobId) return
        delete pollFailures[symbol]

        if (data.status === 'succeeded') {
          delete pendingJobs.value[symbol]
          jobStates.value[symbol] = { status: 'succeeded' }
          applyJobResult(symbol, data)
        } else if (data.status === 'failed') {
          delete pendingJobs.value[symbol]
          jobStates.value[symbol] = {
            status: 'failed',
            message: data.error_message || '分析失败',
          }
        } else {
          jobStates.value[symbol] = { status: data.status, phase: data.phase }
        }
      } catch {
        if (pendingJobs.value[symbol] !== jobId) return
        pollFailures[symbol] = (pollFailures[symbol] ?? 0) + 1
        if (pollFailures[symbol] >= POLL_MAX_FAILURES) {
          delete pendingJobs.value[symbol]
          jobStates.value[symbol] = {
            status: 'failed',
            message: '任务状态查询失败',
          }
        }
      }
    }),
  )

  if (Object.keys(pendingJobs.value).length) {
    schedulePoll()
  } else {
    // 全部结束后静默同步一次，以数据库里的最新报告为准
    await load(true)
  }
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
    created_at: job.result.generated_at,
  }
}

async function submitBatch(): Promise<void> {
  if (!selectedCount.value || batchSubmitting.value) return
  batchSubmitting.value = true
  batchError.value = ''
  try {
    const { data } = await watchlistApi.batchAnalysis(selectedSymbols.value)
    for (const result of data) {
      if (result.status === 'failed') {
        jobStates.value[result.symbol] = {
          status: 'failed',
          message: result.error_message || result.error_code || '提交分析失败',
        }
      } else if (result.job_id) {
        jobStates.value[result.symbol] = { status: 'queued' }
        pendingJobs.value[result.symbol] = result.job_id
      }
    }
    if (pendingCount.value) schedulePoll(0)
  } catch (err) {
    batchError.value = getErrorMessage(err, '批量分析提交失败')
  } finally {
    batchSubmitting.value = false
  }
}

onMounted(async () => {
  await load()
  // 列表加载失败时保留存储，等下次刷新再恢复
  if (!error.value) restorePendingJobs()
})

onBeforeUnmount(() => {
  if (pollTimer !== null) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
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
