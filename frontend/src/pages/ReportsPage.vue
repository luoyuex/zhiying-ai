<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { reportsApi, type ReportStats, type ReportSummary } from '@/api/reports'
import { watchlistApi, type PortfolioDiagnosisSummary } from '@/api/watchlist'
import AppShell from '@/components/layout/AppShell.vue'
import ReportListItem from '@/components/report/ReportListItem.vue'
import ReportListSkeleton from '@/components/report/ReportListSkeleton.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getErrorMessage } from '@/utils/errors'
import { dayLabel, formatFullDateTime } from '@/utils/report'

type ReportTab = 'stock' | 'portfolio'

const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()
const activeTab = ref<ReportTab>(route.query.tab === 'portfolio' ? 'portfolio' : 'stock')
const reports = ref<ReportSummary[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const moreError = ref('')
const hasMore = ref(false)
const stats = ref<ReportStats | null>(null)
const keyword = ref('')
const activeQuery = ref('')
const sentinelRef = ref<HTMLElement | null>(null)
const selectMode = ref(false)
const selected = ref<ReportSummary[]>([])

let requestSeq = 0
let searchTimer: ReturnType<typeof setTimeout> | null = null
let observer: IntersectionObserver | null = null

const portfolioReports = ref<PortfolioDiagnosisSummary[]>([])
const portfolioLoading = ref(false)
const portfolioError = ref('')
const portfolioLoaded = ref(false)

const selectedIds = computed(() => new Set(selected.value.map((item) => item.id)))

function setTab(tab: ReportTab): void {
  activeTab.value = tab
  void router.replace({ query: tab === 'portfolio' ? { tab: 'portfolio' } : {} })
}

async function loadPortfolio(): Promise<void> {
  if (portfolioLoading.value) return
  portfolioLoading.value = true
  portfolioError.value = ''
  try {
    const { data } = await watchlistApi.portfolioHistory(50)
    portfolioReports.value = data
    portfolioLoaded.value = true
  } catch (err) {
    portfolioError.value = getErrorMessage(err, '组合诊断记录加载失败')
  } finally {
    portfolioLoading.value = false
  }
}

watch(
  activeTab,
  (tab) => {
    if (tab === 'portfolio' && !portfolioLoaded.value) void loadPortfolio()
  },
  { immediate: true },
)

watch(
  () => route.query.tab,
  (value) => {
    const tab: ReportTab = value === 'portfolio' ? 'portfolio' : 'stock'
    if (tab !== activeTab.value) activeTab.value = tab
  },
)

function toggleSelect(item: ReportSummary): void {
  const index = selected.value.findIndex((entry) => entry.id === item.id)
  if (index >= 0) {
    selected.value.splice(index, 1)
    return
  }
  // 对比只支持同一只股票；切换股票时重置选择
  if (selected.value.length && selected.value[0].symbol !== item.symbol) {
    selected.value = [item]
    return
  }
  if (selected.value.length >= 2) {
    selected.value = [selected.value[1], item]
    return
  }
  selected.value.push(item)
}

function exitSelect(): void {
  selectMode.value = false
  selected.value = []
}

function openCompare(): void {
  if (selected.value.length !== 2) return
  void router.push({
    path: '/reports/compare',
    query: { ids: selected.value.map((item) => item.id).join(',') },
  })
}

const stockCount = computed(() => new Set(reports.value.map((item) => item.symbol)).size)
const totalReports = computed(() => stats.value?.total ?? reports.value.length)
const totalStocks = computed(() => stats.value?.stock_count ?? stockCount.value)

const groups = computed(() => {
  const result: { key: string; label: string; items: ReportSummary[] }[] = []
  for (const item of reports.value) {
    const date = new Date(item.created_at)
    const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
    let group = result.find((entry) => entry.key === key)
    if (!group) {
      group = { key, label: dayLabel(date), items: [] }
      result.push(group)
    }
    group.items.push(item)
  }
  return result
})

async function loadStats(seq: number, query: string): Promise<void> {
  try {
    const { data } = await reportsApi.stats(query || undefined)
    if (seq !== requestSeq) return
    stats.value = data
  } catch {
    // 统计失败不影响列表
  }
}

async function load(reset = true): Promise<void> {
  if (!reset && (loading.value || loadingMore.value || !hasMore.value)) return

  const seq = ++requestSeq
  const query = reset ? keyword.value.trim() : activeQuery.value

  if (reset) {
    activeQuery.value = query
    loading.value = true
    loadingMore.value = false
    error.value = ''
    moreError.value = ''
    hasMore.value = false
    selected.value = []
  } else {
    loadingMore.value = true
    moreError.value = ''
  }

  const offset = reset ? 0 : reports.value.length

  try {
    const { data } = await reportsApi.list(
      undefined,
      PAGE_SIZE + 1,
      offset,
      query || undefined,
    )
    if (seq !== requestSeq) return

    const page = data.slice(0, PAGE_SIZE)
    reports.value = reset ? page : [...reports.value, ...page]
    hasMore.value = data.length > PAGE_SIZE

    if (reset) void loadStats(seq, query)
  } catch (err) {
    if (seq !== requestSeq) return
    if (reset) {
      reports.value = []
      hasMore.value = false
      error.value = getErrorMessage(err, '历史报告加载失败')
    } else {
      moreError.value = getErrorMessage(err, '加载更多失败')
    }
  } finally {
    if (seq === requestSeq) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function loadMore(): void {
  if (activeTab.value !== 'stock') return
  void load(false)
}

watch(keyword, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (activeTab.value !== 'stock') return
    void load(true)
  }, 300)
})

onMounted(() => {
  void load()
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMore()
    },
    { rootMargin: '240px 0px' },
  )
  if (sentinelRef.value) observer.observe(sentinelRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <AppShell>
    <RouterLink
      to="/"
      class="inline-flex items-center gap-1 text-xs text-ink-3 transition-colors hover:text-ink"
    >
      <span aria-hidden="true">←</span>
      返回首页
    </RouterLink>

    <section class="mt-4 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">
          {{ activeTab === 'stock' ? '所有个股的 AI 分析记录' : '自选组合的 AI 诊断记录' }}
        </p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">历史报告</h1>
      </div>
      <div
        v-if="activeTab === 'stock' ? totalReports : portfolioReports.length"
        class="flex gap-5 text-right text-[11px] text-ink-3"
      >
        <template v-if="activeTab === 'stock'">
          <div>
            <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
              {{ totalReports }}
            </div>
            <div class="mt-1">份报告</div>
          </div>
          <div>
            <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
              {{ totalStocks }}
            </div>
            <div class="mt-1">只股票</div>
          </div>
        </template>
        <div v-else>
          <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
            {{ portfolioReports.length }}
          </div>
          <div class="mt-1">次诊断</div>
        </div>
      </div>
    </section>

    <section class="mt-6 rounded-lg border border-line bg-canvas">
      <div
        class="flex flex-col gap-3 border-b border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <div class="flex flex-wrap items-center gap-2">
          <div class="flex h-8 items-center rounded-md bg-surface p-0.5 text-xs">
            <button
              type="button"
              class="rounded px-2.5 py-1 transition-colors"
              :class="activeTab === 'stock' ? 'bg-canvas text-ink shadow-sm' : 'text-ink-3 hover:text-ink'"
              @click="setTab('stock')"
            >
              个股分析
            </button>
            <button
              type="button"
              class="rounded px-2.5 py-1 transition-colors"
              :class="activeTab === 'portfolio' ? 'bg-canvas text-ink shadow-sm' : 'text-ink-3 hover:text-ink'"
              @click="setTab('portfolio')"
            >
              组合诊断
            </button>
          </div>
          <span
            v-if="activeTab === 'stock' && totalReports"
            class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-3"
          >
            {{ totalReports }} 条
          </span>
          <span
            v-else-if="activeTab === 'portfolio' && portfolioReports.length"
            class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-3"
          >
            {{ portfolioReports.length }} 条
          </span>
        </div>
        <div
          v-if="activeTab === 'stock'"
          class="flex w-full flex-wrap items-center gap-2 sm:w-auto"
        >
          <Input
            v-model="keyword"
            size="sm"
            class="min-w-0 flex-1 sm:w-64 sm:flex-none"
            placeholder="筛选股票代码或名称"
            aria-label="筛选历史报告"
            autocomplete="off"
            maxlength="30"
          />
          <template v-if="selectMode">
            <span class="text-[11px] tabular-nums text-ink-3">已选 {{ selected.length }}/2</span>
            <Button size="sm" :disabled="selected.length !== 2" @click="openCompare">
              对比选中
            </Button>
            <Button variant="secondary" size="sm" @click="exitSelect">取消</Button>
          </template>
          <Button v-else variant="secondary" size="sm" @click="selectMode = true">
            对比报告
          </Button>
        </div>
      </div>

      <p
        v-if="selectMode && activeTab === 'stock'"
        class="border-b border-line bg-surface/60 px-4 py-2 text-[11px] text-ink-3"
      >
        点击报告进行选择，需选择同一只股票的两份报告；切换股票会重置选择。
      </p>

      <template v-if="activeTab === 'stock'">
        <ReportListSkeleton v-if="loading" />

        <div v-else-if="error" class="px-4 py-10 text-center">
          <p class="text-sm text-danger">{{ error }}</p>
          <Button variant="secondary" size="sm" class="mt-3" @click="load(true)">重新加载</Button>
        </div>

        <div
          v-else-if="!reports.length"
          class="px-4 py-14 text-center"
        >
          <template v-if="keyword.trim()">
            <div class="text-sm font-medium text-ink">没有匹配的报告</div>
            <p class="mt-1 text-xs text-ink-3">
              没有找到包含「{{ keyword.trim() }}」的股票代码或名称。
            </p>
          </template>
          <template v-else>
            <div class="text-sm font-medium text-ink">还没有分析报告</div>
            <p class="mt-1 text-xs text-ink-3">
              在个股详情页完成一次 AI 分析后，报告会自动保存在这里。
            </p>
            <Button variant="secondary" size="sm" class="mt-4" @click="router.push('/')">
              去查询股票
            </Button>
          </template>
        </div>

        <div v-else>
          <div v-for="group in groups" :key="group.key">
            <div
              class="border-b border-line bg-surface/60 px-4 py-2 text-[11px] font-medium text-ink-3"
            >
              {{ group.label }}
            </div>
            <ReportListItem
              v-for="item in group.items"
              :key="item.id"
              :item="item"
              from="reports"
              :selectable="selectMode"
              :selected="selectedIds.has(item.id)"
              @toggle="toggleSelect(item)"
            />
          </div>
        </div>
      </template>

      <template v-else>
        <div v-if="portfolioLoading" class="divide-y divide-line">
          <div v-for="index in 3" :key="index" class="px-4 py-4">
            <div class="h-4 w-40 animate-pulse rounded bg-surface-2" />
            <div class="mt-2 h-3 w-full max-w-xl animate-pulse rounded bg-surface-2" />
            <div class="mt-2 h-3 w-24 animate-pulse rounded bg-surface-2" />
          </div>
        </div>

        <div v-else-if="portfolioError" class="px-4 py-10 text-center">
          <p class="text-sm text-danger">{{ portfolioError }}</p>
          <Button variant="secondary" size="sm" class="mt-3" @click="loadPortfolio">
            重新加载
          </Button>
        </div>

        <div v-else-if="!portfolioReports.length" class="px-4 py-14 text-center">
          <div class="text-sm font-medium text-ink">还没有组合诊断记录</div>
          <p class="mt-1 text-xs text-ink-3">
            在自选股页运行一次 AI 组合诊断，结果会自动保存在这里。
          </p>
          <Button variant="secondary" size="sm" class="mt-4" @click="router.push('/watchlist')">
            去自选股
          </Button>
        </div>

        <div v-else>
          <RouterLink
            v-for="item in portfolioReports"
            :key="item.id"
            :to="`/reports/portfolio/${item.id}`"
            class="flex items-start gap-4 border-b border-line px-4 py-3.5 transition-colors last:border-b-0 hover:bg-surface/60"
          >
            <div class="w-14 shrink-0">
              <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
                {{ item.health_score }}
              </div>
              <div class="mt-1 text-[10px] text-ink-3">健康度</div>
            </div>
            <div class="min-w-0 flex-1">
              <p class="line-clamp-2 text-xs leading-relaxed text-ink-2">{{ item.summary }}</p>
              <div class="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-ink-3">
                <span>{{ formatFullDateTime(item.created_at) }}</span>
                <span>{{ item.position_count }} 只持仓</span>
              </div>
            </div>
            <span class="mt-1 shrink-0 text-xs text-ink-3">查看 →</span>
          </RouterLink>
        </div>
      </template>

      <div
        v-show="activeTab === 'stock' && reports.length > 0 && !loading && !error"
        ref="sentinelRef"
        class="flex items-center justify-center px-4 py-3 text-[11px] text-ink-3"
        aria-live="polite"
      >
        <span v-if="loadingMore">正在加载更多…</span>
        <button
          v-else-if="moreError"
          type="button"
          class="text-danger underline underline-offset-2"
          @click="loadMore"
        >
          加载失败，点击重试
        </button>
        <button
          v-else-if="hasMore"
          type="button"
          class="transition-colors hover:text-ink"
          @click="loadMore"
        >
          加载更多
        </button>
        <span v-else>已显示全部 {{ reports.length }} 条</span>
      </div>
    </section>
  </AppShell>
</template>
