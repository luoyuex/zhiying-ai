<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { adminApi } from '@/api/admin'
import DataTable from '@/components/admin/DataTable.vue'
import Pagination from '@/components/admin/Pagination.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import MarkdownBlock from '@/components/ui/MarkdownBlock.vue'
import Select from '@/components/ui/Select.vue'
import type {
  AdminContentPortfolioDetail,
  AdminContentReportDetail,
  AdminContentScreenerDetail,
} from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime, ratingTone } from '@/utils/report'

type TabId = 'reports' | 'screener' | 'portfolio' | 'watchlist'

const route = useRoute()
const router = useRouter()

const tabs: { id: TabId; label: string }[] = [
  { id: 'reports', label: '个股报告' },
  { id: 'screener', label: '选股记录' },
  { id: 'portfolio', label: '组合诊断' },
  { id: 'watchlist', label: '自选股' },
]

const STRATEGY_LABELS: Record<string, string> = {
  main_force: '主力追踪',
  low_price_bull: '低价寻宝',
  small_cap: '小盘精选',
  profit_growth: '业绩高增',
  value_stock: '价值洼地',
}

const strategyOptions = [
  { label: '全部策略', value: '' },
  ...Object.entries(STRATEGY_LABELS).map(([value, label]) => ({ label, value })),
]

function initialTab(): TabId {
  const raw = String(route.query.tab || '')
  return tabs.some((tab) => tab.id === raw) ? (raw as TabId) : 'reports'
}

const activeTab = ref<TabId>(initialTab())
const q = ref('')
const strategy = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const items = ref<Record<string, any>[]>([])
const loading = ref(true)
const error = ref('')

const reportColumns = [
  { key: 'time', label: '时间' },
  { key: 'user', label: '用户' },
  { key: 'stock', label: '股票' },
  { key: 'rating', label: '评级' },
  { key: 'confidence', label: '置信度', align: 'right' as const },
  { key: 'source', label: '来源' },
]
const screenerColumns = [
  { key: 'time', label: '时间' },
  { key: 'user', label: '用户' },
  { key: 'strategy', label: '策略' },
  { key: 'candidates', label: '候选', align: 'right' as const },
  { key: 'picks', label: '精选' },
]
const portfolioColumns = [
  { key: 'time', label: '时间' },
  { key: 'user', label: '用户' },
  { key: 'health', label: '健康度', align: 'right' as const },
  { key: 'positions', label: '持仓数', align: 'right' as const },
  { key: 'summary', label: '摘要' },
]
const watchlistColumns = [
  { key: 'time', label: '加入时间' },
  { key: 'user', label: '用户' },
  { key: 'stock', label: '股票' },
  { key: 'position', label: '成本 / 数量' },
  { key: 'note', label: '备注' },
]

const columns = computed(() => {
  if (activeTab.value === 'reports') return reportColumns
  if (activeTab.value === 'screener') return screenerColumns
  if (activeTab.value === 'portfolio') return portfolioColumns
  return watchlistColumns
})

const emptyText = computed(() => {
  if (activeTab.value === 'reports') return '没有匹配的报告。'
  if (activeTab.value === 'screener') return '没有匹配的选股记录。'
  if (activeTab.value === 'portfolio') return '没有匹配的组合诊断。'
  return '没有匹配的自选股。'
})

const detailOpen = ref(false)
const detailType = ref<'report' | 'screener' | 'portfolio'>('report')
const detail = ref<
  AdminContentReportDetail | AdminContentScreenerDetail | AdminContentPortfolioDetail | null
>(null)
const detailLoading = ref(false)
const detailError = ref('')

const reportDetail = computed(() =>
  detailType.value === 'report' ? (detail.value as AdminContentReportDetail | null) : null,
)
const screenerDetail = computed(() =>
  detailType.value === 'screener' ? (detail.value as AdminContentScreenerDetail | null) : null,
)
const portfolioDetail = computed(() =>
  detailType.value === 'portfolio'
    ? (detail.value as AdminContentPortfolioDetail | null)
    : null,
)

const reportDecision = computed(() => reportDetail.value?.report?.decision || null)
const reportAnalysts = computed(() => reportDetail.value?.report?.analysts || [])
const screenerRecommendations = computed(
  () => screenerDetail.value?.result?.recommendations || [],
)
const portfolioReport = computed(() => portfolioDetail.value?.report || null)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      q: q.value.trim() || undefined,
      strategy: activeTab.value === 'screener' ? strategy.value || undefined : undefined,
    }
    if (activeTab.value === 'reports') {
      const { data } = await adminApi.contentReports(params)
      items.value = data.items
      total.value = data.total
    } else if (activeTab.value === 'screener') {
      const { data } = await adminApi.contentScreenerRecords(params)
      items.value = data.items
      total.value = data.total
    } else if (activeTab.value === 'portfolio') {
      const { data } = await adminApi.contentPortfolios(params)
      items.value = data.items
      total.value = data.total
    } else {
      const { data } = await adminApi.contentWatchlist(params)
      items.value = data.items
      total.value = data.total
    }
  } catch (err) {
    error.value = getErrorMessage(err, '内容库加载失败')
  } finally {
    loading.value = false
  }
}

function setTab(tab: TabId): void {
  if (activeTab.value === tab) return
  activeTab.value = tab
  page.value = 1
  q.value = ''
  strategy.value = ''
  void router.replace({ query: { ...route.query, tab } })
  void load()
}

function applyFilters(): void {
  page.value = 1
  void load()
}

function onPageChange(value: number): void {
  if (value === page.value) return
  page.value = value
  void load()
}

function onPageSizeChange(value: number): void {
  pageSize.value = value
  page.value = 1
  void load()
}

async function openRow(item: Record<string, any>): Promise<void> {
  if (activeTab.value === 'watchlist') return
  detailType.value =
    activeTab.value === 'reports'
      ? 'report'
      : activeTab.value === 'screener'
        ? 'screener'
        : 'portfolio'
  detailOpen.value = true
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    if (detailType.value === 'report') {
      const { data } = await adminApi.contentReport(item.id)
      detail.value = data
    } else if (detailType.value === 'screener') {
      const { data } = await adminApi.contentScreenerRecord(item.id)
      detail.value = data
    } else {
      const { data } = await adminApi.contentPortfolio(item.id)
      detail.value = data
    }
  } catch (err) {
    detailError.value = getErrorMessage(err, '详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function closeDetail(): void {
  detailOpen.value = false
  detail.value = null
}

function strategyLabel(value: string): string {
  return STRATEGY_LABELS[value] || value
}

function ratingChangeLabel(change: string | null): string {
  if (change === 'up') return '评级上调'
  if (change === 'down') return '评级下调'
  return ''
}

function positionText(item: Record<string, any>): string {
  const cost = item.cost_price === null ? '—' : Number(item.cost_price).toFixed(2)
  const qty = item.quantity === null ? '—' : item.quantity
  return `${cost} / ${qty} 股`
}

function decisionLevels(): { label: string; value: string }[] {
  const levels = reportDecision.value?.levels
  if (!levels) return []
  return [
    { label: '建议入场', value: Number(levels.entry).toFixed(2) },
    { label: '止盈', value: Number(levels.take_profit).toFixed(2) },
    { label: '止损', value: Number(levels.stop_loss).toFixed(2) },
    { label: '盈亏比', value: `${Number(levels.risk_reward).toFixed(2)} : 1` },
  ]
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && detailOpen.value) closeDetail()
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <section class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <p class="text-[13px] text-ink-3">跨用户只读查看，用于定位用户反馈的问题</p>
      <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">内容库</h1>
    </div>
    <div class="text-right text-[11px] text-ink-3">
      <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
        {{ total }}
      </div>
      <div class="mt-1">条记录</div>
    </div>
  </section>

  <div class="mt-5 flex flex-wrap gap-5 border-b border-line text-[13px]">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="-mb-px border-b-[1.5px] pb-2 transition-colors"
      :class="
        activeTab === tab.id
          ? 'border-ink font-medium text-ink'
          : 'border-transparent text-ink-3 hover:text-ink'
      "
      @click="setTab(tab.id)"
    >
      {{ tab.label }}
    </button>
  </div>

  <section class="mt-4 rounded-lg border border-line bg-canvas">
    <div class="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
      <Input
        v-model="q"
        class="w-full sm:w-64"
        placeholder="搜索用户邮箱 / 股票名称或代码"
        aria-label="搜索内容"
        @keyup.enter="applyFilters"
      />
      <div v-if="activeTab === 'screener'" class="w-36">
        <Select v-model="strategy" :options="strategyOptions" size="lg" />
      </div>
      <Button @click="applyFilters">筛选</Button>
    </div>

    <div v-if="error" class="border-b border-line px-4 py-3">
      <p class="text-xs text-danger">{{ error }}</p>
      <button
        type="button"
        class="mt-2 text-xs text-ink-2 underline underline-offset-2"
        @click="load"
      >
        重新加载
      </button>
    </div>

    <DataTable :columns="columns">
      <tr v-if="loading">
        <td :colspan="columns.length" class="px-4 py-12 text-center text-xs text-ink-3">
          加载中…
        </td>
      </tr>
      <tr v-else-if="!items.length">
        <td :colspan="columns.length" class="px-4 py-12 text-center text-xs text-ink-3">
          {{ emptyText }}
        </td>
      </tr>
      <template v-else-if="activeTab === 'reports'">
        <tr
          v-for="item in items"
          :key="item.id"
          class="cursor-pointer transition-colors hover:bg-surface/60"
          tabindex="0"
          @click="openRow(item)"
          @keydown.enter="openRow(item)"
        >
          <td class="whitespace-nowrap px-4 py-2.5 text-[11px] text-ink-3">
            {{ formatFullDateTime(item.created_at) }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[200px] truncate text-ink-2">{{ item.user_email }}</div>
          </td>
          <td class="px-4 py-2.5 text-ink">
            {{ item.name }} <span class="text-[11px] text-ink-3">{{ item.symbol }}</span>
          </td>
          <td class="px-4 py-2.5">
            <span
              class="rounded px-1.5 py-0.5 text-[11px] font-medium"
              :class="ratingTone(item.rating)"
            >
              {{ item.rating }}
            </span>
            <span v-if="item.rating_change === 'up' || item.rating_change === 'down'" class="ml-1 text-[10px] text-ink-3">
              {{ ratingChangeLabel(item.rating_change) }}
            </span>
          </td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-2">
            {{ item.confidence }}
          </td>
          <td class="px-4 py-2.5 text-[11px] text-ink-3">
            {{ item.decision_source === 'llm' ? 'LLM' : item.decision_source || '—' }}
          </td>
        </tr>
      </template>
      <template v-else-if="activeTab === 'screener'">
        <tr
          v-for="item in items"
          :key="item.id"
          class="cursor-pointer transition-colors hover:bg-surface/60"
          tabindex="0"
          @click="openRow(item)"
          @keydown.enter="openRow(item)"
        >
          <td class="whitespace-nowrap px-4 py-2.5 text-[11px] text-ink-3">
            {{ formatFullDateTime(item.created_at) }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[200px] truncate text-ink-2">{{ item.user_email }}</div>
          </td>
          <td class="px-4 py-2.5 text-ink">{{ strategyLabel(item.strategy) }}</td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-2">
            {{ item.analyzed_count }}
          </td>
          <td class="px-4 py-2.5">
            <span class="text-[11px] text-ink-2">
              {{ item.picks.map((pick: any) => `${pick.name}${pick.symbol}`).join('、') || '—' }}
            </span>
          </td>
        </tr>
      </template>
      <template v-else-if="activeTab === 'portfolio'">
        <tr
          v-for="item in items"
          :key="item.id"
          class="cursor-pointer transition-colors hover:bg-surface/60"
          tabindex="0"
          @click="openRow(item)"
          @keydown.enter="openRow(item)"
        >
          <td class="whitespace-nowrap px-4 py-2.5 text-[11px] text-ink-3">
            {{ formatFullDateTime(item.created_at) }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[200px] truncate text-ink-2">{{ item.user_email }}</div>
          </td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink">
            {{ item.health_score }}
          </td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-2">
            {{ item.position_count }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[360px] truncate text-[11px] text-ink-2">
              {{ item.summary }}
            </div>
          </td>
        </tr>
      </template>
      <template v-else>
        <tr v-for="item in items" :key="item.id">
          <td class="whitespace-nowrap px-4 py-2.5 text-[11px] text-ink-3">
            {{ formatFullDateTime(item.created_at) }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[200px] truncate text-ink-2">{{ item.user_email }}</div>
          </td>
          <td class="px-4 py-2.5 text-ink">
            {{ item.name }} <span class="text-[11px] text-ink-3">{{ item.symbol }}</span>
          </td>
          <td class="px-4 py-2.5 text-[11px] tabular-nums text-ink-2">
            {{ positionText(item) }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[280px] truncate text-[11px] text-ink-3">
              {{ item.note || '—' }}
            </div>
          </td>
        </tr>
      </template>
    </DataTable>

    <Pagination
      :page="page"
      :page-size="pageSize"
      :total="total"
      @update:page="onPageChange"
      @update:page-size="onPageSizeChange"
    />
  </section>

  <div v-if="detailOpen" class="fixed inset-0 z-50 flex justify-end">
    <button
      type="button"
      class="absolute inset-0 bg-ink/20"
      aria-label="关闭详情"
      @click="closeDetail"
    />
    <aside
      class="relative flex h-full w-full max-w-[560px] flex-col overflow-y-auto border-l border-line bg-canvas shadow-pop"
    >
      <header class="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div class="min-w-0">
          <p class="text-[10px] font-medium tracking-[0.14em] text-ink-3">READ ONLY</p>
          <h2 class="mt-1 text-[16px] font-semibold text-ink">
            <template v-if="reportDetail">
              {{ reportDetail.name }}
              <span class="text-xs font-normal text-ink-3">{{ reportDetail.symbol }}</span>
            </template>
            <template v-else-if="screenerDetail">
              {{ strategyLabel(screenerDetail.strategy) }}
            </template>
            <template v-else-if="portfolioDetail">组合诊断</template>
          </h2>
          <p class="mt-0.5 truncate text-[11px] text-ink-3">
            {{ detail?.user_email }} ·
            {{ detail ? formatFullDateTime(detail.created_at) : '' }}
          </p>
        </div>
        <button
          type="button"
          class="text-sm text-ink-3 transition-colors hover:text-ink"
          aria-label="关闭"
          @click="closeDetail"
        >
          ✕
        </button>
      </header>

      <div class="flex-1 px-5 py-4">
        <p v-if="detailLoading" class="text-xs text-ink-3">加载中…</p>
        <p v-else-if="detailError" class="text-xs text-danger">{{ detailError }}</p>

        <template v-else-if="reportDetail">
          <div class="flex flex-wrap items-center gap-2">
            <span
              class="rounded-md px-2 py-0.5 text-xs font-semibold"
              :class="ratingTone(reportDetail.rating)"
            >
              {{ reportDetail.rating }}
            </span>
            <span
              v-if="reportDetail.rating_change === 'up' || reportDetail.rating_change === 'down'"
              class="rounded px-2 py-0.5 text-[11px]"
              :class="
                reportDetail.rating_change === 'up'
                  ? 'bg-up-soft text-up'
                  : 'bg-down-soft text-down'
              "
            >
              {{ ratingChangeLabel(reportDetail.rating_change) }}
            </span>
            <span class="text-[11px] text-ink-3">
              置信度 {{ reportDetail.confidence }} / 100
            </span>
          </div>

          <p v-if="reportDecision?.summary" class="mt-3 text-[12px] leading-relaxed text-ink-2">
            {{ reportDecision.summary }}
          </p>

          <div v-if="decisionLevels().length" class="mt-3 grid grid-cols-4 gap-2">
            <div
              v-for="level in decisionLevels()"
              :key="level.label"
              class="rounded-md bg-surface px-2.5 py-2"
            >
              <div class="text-[10px] text-ink-3">{{ level.label }}</div>
              <div class="mt-1 text-[13px] font-medium tabular-nums text-ink">
                {{ level.value }}
              </div>
            </div>
          </div>

          <div v-if="reportDecision?.risks?.length" class="mt-4">
            <h3 class="text-[11px] font-medium text-ink-3">风险提示</h3>
            <ul class="mt-1.5 space-y-1">
              <li
                v-for="(risk, index) in reportDecision.risks"
                :key="index"
                class="text-[12px] leading-relaxed text-ink-2"
              >
                · {{ risk }}
              </li>
            </ul>
          </div>

          <div class="mt-4">
            <h3 class="text-[11px] font-medium text-ink-3">六位分析师</h3>
            <div class="mt-2 space-y-2">
              <article
                v-for="analyst in reportAnalysts"
                :key="analyst.name"
                class="rounded-md border border-line p-3"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-[12px] font-medium text-ink">{{ analyst.name }}</span>
                  <span class="text-[11px] text-ink-3">
                    {{ analyst.rating }} · {{ analyst.score }}
                  </span>
                </div>
                <p class="mt-1 line-clamp-3 text-[11px] leading-relaxed text-ink-2">
                  {{ analyst.summary }}
                </p>
              </article>
            </div>
          </div>
        </template>

        <template v-else-if="screenerDetail">
          <div class="text-[11px] text-ink-3">
            候选 {{ screenerDetail.analyzed_count }} 只 · 精选
            {{ screenerDetail.recommendation_count }} 只
          </div>

          <div class="mt-3 space-y-3">
            <section v-if="screenerDetail.result?.fund_flow">
              <h3 class="text-[11px] font-medium text-ink-3">资金面</h3>
              <MarkdownBlock class="mt-1" size="sm" :content="screenerDetail.result.fund_flow" />
            </section>
            <section v-if="screenerDetail.result?.industry">
              <h3 class="text-[11px] font-medium text-ink-3">行业板块</h3>
              <MarkdownBlock class="mt-1" size="sm" :content="screenerDetail.result.industry" />
            </section>
            <section v-if="screenerDetail.result?.fundamental">
              <h3 class="text-[11px] font-medium text-ink-3">基本面</h3>
              <MarkdownBlock
                class="mt-1"
                size="sm"
                :content="screenerDetail.result.fundamental"
              />
            </section>
          </div>

          <div class="mt-4">
            <h3 class="text-[11px] font-medium text-ink-3">精选标的</h3>
            <div class="mt-2 space-y-2">
              <article
                v-for="rec in screenerRecommendations"
                :key="rec.symbol"
                class="rounded-md border border-line p-3"
              >
                <div class="flex items-baseline justify-between gap-2">
                  <span class="text-[13px] font-medium text-ink">
                    {{ rec.rank }}. {{ rec.name }}
                    <span class="text-[11px] text-ink-3">{{ rec.symbol }}</span>
                  </span>
                  <span class="text-[11px] text-ink-3">{{ rec.position }}</span>
                </div>
                <p v-if="rec.reasons?.length" class="mt-1.5 text-[11px] leading-relaxed text-ink-2">
                  {{ rec.reasons.join('；') }}
                </p>
                <p v-if="rec.risks" class="mt-1 text-[11px] leading-relaxed text-warn">
                  风险：{{ rec.risks }}
                </p>
              </article>
            </div>
          </div>

          <details class="mt-4">
            <summary class="cursor-pointer text-[11px] text-ink-3">筛选参数</summary>
            <pre class="mt-2 overflow-auto rounded-md bg-surface p-3 text-[11px] text-ink-2">{{
              JSON.stringify(screenerDetail.filters, null, 2)
            }}</pre>
          </details>
        </template>

        <template v-else-if="portfolioDetail && portfolioReport">
          <div class="flex items-center gap-3">
            <div>
              <div class="text-[10px] text-ink-3">健康度</div>
              <div class="text-[24px] font-semibold tabular-nums text-ink">
                {{ portfolioDetail.health_score }}
              </div>
            </div>
            <div class="text-[11px] text-ink-3">
              持仓 {{ portfolioDetail.position_count }} 只
            </div>
          </div>
          <p class="mt-3 text-[12px] leading-relaxed text-ink-2">
            {{ portfolioReport.summary }}
          </p>
          <div v-if="portfolioReport.allocation_advice" class="mt-3">
            <h3 class="text-[11px] font-medium text-ink-3">仓位建议</h3>
            <p class="mt-1 text-[12px] leading-relaxed text-ink-2">
              {{ portfolioReport.allocation_advice }}
            </p>
          </div>
          <div v-if="portfolioReport.risk_notes?.length" class="mt-3">
            <h3 class="text-[11px] font-medium text-ink-3">风险提示</h3>
            <ul class="mt-1 space-y-1">
              <li
                v-for="(note, index) in portfolioReport.risk_notes"
                :key="index"
                class="text-[12px] leading-relaxed text-ink-2"
              >
                · {{ note }}
              </li>
            </ul>
          </div>
          <div class="mt-3">
            <h3 class="text-[11px] font-medium text-ink-3">逐只建议</h3>
            <div class="mt-1.5 divide-y divide-line">
              <div
                v-for="position in portfolioReport.positions || []"
                :key="position.symbol"
                class="py-2 text-[12px]"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="font-medium text-ink">
                    {{ position.name }}
                    <span class="text-[11px] font-normal text-ink-3">{{ position.symbol }}</span>
                  </span>
                  <span class="text-[11px] text-ink-2">{{ position.action }}</span>
                </div>
                <p class="mt-0.5 text-[11px] leading-relaxed text-ink-2">
                  {{ position.reason }}
                </p>
              </div>
            </div>
          </div>
        </template>
      </div>
    </aside>
  </div>
</template>
