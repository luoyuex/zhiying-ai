<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { AIAnalysisResponse } from '@/api/ai'
import { reportsApi } from '@/api/reports'
import { watchlistApi, type PriceAlertKind } from '@/api/watchlist'
import { notifyPriceAlertsChanged } from '@/composables/usePriceAlertsSync'
import AppShell from '@/components/layout/AppShell.vue'
import AnalystRadar from '@/components/report/AnalystRadar.vue'
import DiscussionTimeline from '@/components/report/DiscussionTimeline.vue'
import PublicInfoPanel from '@/components/report/PublicInfoPanel.vue'
import { getErrorMessage } from '@/utils/errors'
import { formatQuoteTime, formatSourceList } from '@/utils/market'
import { exportElementToPdf, pdfFilename } from '@/utils/pdf'
import { analystScoreTone, decisionLevels, ratingChangeBadge } from '@/utils/report'

const route = useRoute()
const router = useRouter()
const report = ref<AIAnalysisResponse | null>(null)
const createdAt = ref('')
const loading = ref(false)
const error = ref('')

type ReportOrigin = 'dashboard' | 'reports' | 'stock' | 'watchlist'

const origin = computed<ReportOrigin>(() => {
  const value = String(route.query.from ?? '')
  if (
    value === 'dashboard' ||
    value === 'reports' ||
    value === 'stock' ||
    value === 'watchlist'
  ) {
    return value
  }
  return 'stock'
})

const originSymbol = computed(
  () => String(route.query.symbol ?? '') || report.value?.symbol || '',
)

const backLink = computed(() => {
  if (origin.value === 'dashboard') return { to: '/', label: '返回首页' }
  if (origin.value === 'reports') return { to: '/reports', label: '返回全部历史报告' }
  if (origin.value === 'watchlist') return { to: '/watchlist', label: '返回自选股' }
  if (originSymbol.value) {
    return {
      to: `/stock/${originSymbol.value}`,
      label: report.value ? `返回 ${report.value.name} 行情` : '返回个股行情',
    }
  }
  return { to: '/', label: '返回首页' }
})

const decision = computed(() => report.value?.decision ?? null)
const priceTone = computed(() => {
  const value = report.value?.change_pct
  if (value == null || value === 0) return 'text-ink-2'
  return value > 0 ? 'text-up' : 'text-down'
})
const decisionBadgeClass = computed(() => {
  if (decision.value?.rating === '买入') return 'bg-up-soft text-up'
  if (decision.value?.rating === '卖出') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
})

const positionActionTone = computed(() => {
  const action = decision.value?.position_action
  if (action === '加仓' || action === '建仓') return 'bg-up-soft text-up'
  if (action === '减仓' || action === '清仓') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
})
const ratingChange = computed(() =>
  ratingChangeBadge(report.value?.rating_change, report.value?.prev_rating),
)
const decisionLevelItems = computed(() => decisionLevels(decision.value?.levels))
const coverageLabels = computed(() => {
  const analysts = report.value?.analysts ?? []
  const labels = ['行情', '技术指标']
  if (!analysts.length) {
    if (report.value?.web_search_used) labels.push('公开网页')
    return labels
  }
  const missing = new Set(analysts.flatMap((item) => item.missing))
  if (!missing.has('财务/季报')) labels.push('财务/季报')
  if (!missing.has('资金流')) labels.push('资金流')
  if (!missing.has('情绪')) labels.push('情绪')
  if (report.value?.web_search_used) labels.push('公开网页')
  return labels
})
const dataGaps = computed(() => {
  const gaps = new Set<string>()
  for (const analyst of report.value?.analysts ?? []) {
    for (const missing of analyst.missing) gaps.add(missing)
  }
  return Array.from(gaps)
})
const dataSourceText = computed(() => {
  const source = report.value?.data_source ?? ''
  return source ? formatSourceList([source]) : '—'
})
const webSearchLabel = computed(() => {
  if (!report.value?.web_search_used) return '本次未收录'
  const count = report.value.web_sources.length
  return count ? `已检索 ${count} 条` : '已检索，暂无来源'
})
const webUsedBy = computed(() =>
  (report.value?.analysts ?? [])
    .filter((analyst) => analyst.data_sources.includes('元宝搜索'))
    .map((analyst) => `${analyst.name}分析师`),
)

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const compareBusy = ref(false)
const compareError = ref('')
const reportRoot = ref<HTMLElement | null>(null)
const pdfBusy = ref(false)
const pdfError = ref('')
const alertSavingKind = ref<PriceAlertKind | ''>('')
const alertMessage = ref('')
const alertError = ref('')

async function createLevelAlert(kind: Exclude<PriceAlertKind, 'custom'>): Promise<void> {
  if (!report.value || alertSavingKind.value) return
  alertSavingKind.value = kind
  alertMessage.value = ''
  alertError.value = ''
  try {
    const { data } = await watchlistApi.createReportAlert(
      report.value.symbol,
      kind,
      String(route.params.id ?? ''),
    )
    const label =
      kind === 'entry' ? '入场' : kind === 'take_profit' ? '止盈' : '止损'
    alertMessage.value = `${label}提醒已设置：${data.target_price.toFixed(2)} 元，触发一次后自动结束`
    notifyPriceAlertsChanged()
  } catch (err) {
    alertError.value = getErrorMessage(err, '提醒设置失败，请稍后重试')
  } finally {
    alertSavingKind.value = ''
  }
}

async function exportPdf(): Promise<void> {
  if (!reportRoot.value || !report.value || pdfBusy.value) return
  pdfBusy.value = true
  pdfError.value = ''
  try {
    await exportElementToPdf(
      reportRoot.value,
      pdfFilename(report.value.name, report.value.symbol, createdAt.value),
    )
  } catch (err) {
    pdfError.value = getErrorMessage(err, 'PDF 导出失败，请稍后重试')
  } finally {
    pdfBusy.value = false
  }
}

async function comparePrevious(): Promise<void> {
  const currentId = String(route.params.id ?? '')
  if (!report.value || !currentId || compareBusy.value) return

  compareBusy.value = true
  compareError.value = ''
  try {
    const { data } = await reportsApi.list(report.value.symbol, 50)
    const index = data.findIndex((item) => item.id === currentId)
    const previous = index >= 0 ? data[index + 1] : undefined
    if (!previous) {
      compareError.value = '没有更早的同股报告可对比'
      return
    }
    await router.push({
      path: '/reports/compare',
      query: { ids: `${currentId},${previous.id}` },
    })
  } catch (err) {
    compareError.value = getErrorMessage(err, '读取上一份报告失败')
  } finally {
    compareBusy.value = false
  }
}

async function load(id: string): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await reportsApi.get(id)
    report.value = data.report
    createdAt.value = data.created_at
  } catch (err) {
    report.value = null
    error.value = getErrorMessage(err, '分析报告加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => String(route.params.id ?? ''),
  (id) => {
    if (id) void load(id)
  },
  { immediate: true },
)
</script>

<template>
  <AppShell>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-3">
      <RouterLink
        :to="backLink.to"
        class="inline-flex items-center gap-1 transition-colors hover:text-ink"
      >
        <span aria-hidden="true">←</span>
        {{ backLink.label }}
      </RouterLink>
      <RouterLink
        v-if="origin !== 'reports'"
        to="/reports"
        class="transition-colors hover:text-ink"
      >
        全部历史报告
      </RouterLink>
    </div>

    <div v-if="loading" class="mt-6 animate-pulse rounded-lg border border-line bg-canvas p-5">
      <div class="h-6 w-40 rounded bg-surface-2" />
      <div class="mt-3 h-10 w-60 rounded bg-surface-2" />
      <div class="mt-5 h-40 rounded bg-surface-2" />
    </div>

    <div
      v-else-if="error || !report"
      class="mt-6 rounded-lg border border-line bg-canvas px-5 py-10 text-center text-sm text-danger"
    >
      {{ error || '分析报告不存在' }}
    </div>

    <template v-else>
      <div ref="reportRoot">
      <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-[24px] font-semibold tracking-tight text-ink">{{ report.name }}</h1>
              <span class="text-xs tabular-nums text-ink-3">{{ report.symbol }}</span>
              <span v-if="decision" class="rounded-md px-2.5 py-1 text-sm font-semibold" :class="decisionBadgeClass">
                {{ decision.rating }}
              </span>
              <span
                v-if="ratingChange"
                class="rounded-md px-2 py-1 text-[11px] font-medium"
                :class="ratingChange.tone"
              >
                较上次{{ ratingChange.label }}
              </span>
            </div>

            <div class="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span class="text-[32px] font-semibold leading-none tracking-tight tabular-nums" :class="priceTone">
                {{ report.price == null ? '—' : report.price.toFixed(2) }}
              </span>
              <span class="text-sm font-medium tabular-nums" :class="priceTone">
                {{ report.change_pct == null ? '—' : `${report.change_pct > 0 ? '+' : ''}${report.change_pct.toFixed(2)}%` }}
              </span>
            </div>

            <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] text-ink-3">
              <span>生成于 {{ formatTime(createdAt) }}</span>
              <span
                class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium"
                :class="
                  report.web_search_used
                    ? 'border-primary/20 bg-primary-soft text-primary'
                    : 'border-line bg-surface text-ink-3'
                "
              >
                <svg
                  class="size-3 shrink-0"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  aria-hidden="true"
                >
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" stroke-linecap="round" />
                </svg>
                元宝搜索 · {{ webSearchLabel }}
              </span>
            </div>
          </div>

          <div class="flex flex-wrap gap-2" data-pdf-hide>
            <button
              type="button"
              class="inline-flex h-8 items-center rounded-md border border-line-strong bg-canvas px-3 text-xs font-medium text-ink-2 transition-colors hover:border-ink-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="compareBusy"
              @click="comparePrevious"
            >
              {{ compareBusy ? '读取中…' : '对比上一次' }}
            </button>
            <button
              type="button"
              class="inline-flex h-8 items-center rounded-md border border-line-strong bg-canvas px-3 text-xs font-medium text-ink-2 transition-colors hover:border-ink-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="pdfBusy"
              @click="exportPdf"
            >
              {{ pdfBusy ? '导出中…' : '导出 PDF' }}
            </button>
          </div>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line pt-3 text-[11px] leading-relaxed text-ink-3">
          <span class="tabular-nums">报价时间 {{ formatQuoteTime(report.data_as_of) }}</span>
          <span class="min-w-0">数据源 {{ dataSourceText }}</span>
        </div>
        <p v-if="compareError" class="mt-1 text-[11px] text-warn" data-pdf-hide>{{ compareError }}</p>
        <p v-if="pdfError" class="mt-1 text-[11px] text-warn" data-pdf-hide>{{ pdfError }}</p>
      </section>

      <section v-if="decision" class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-sm font-semibold text-ink">首席策略官</h2>
          <span class="rounded-md px-2 py-0.5 text-xs font-semibold" :class="decisionBadgeClass">
            {{ decision.rating }}
          </span>
          <span class="text-[11px] text-ink-3">
            置信度 {{ decision.confidence }} / 100
            <span v-if="decision.decision_source === 'rule_fallback'">· 规则兜底</span>
          </span>
        </div>

        <p class="mt-3 text-[13px] leading-relaxed text-ink-2">{{ decision.summary }}</p>

        <div class="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <div class="text-[11px] text-ink-3">操作建议</div>
            <p class="mt-0.5 text-xs leading-relaxed text-ink-2">{{ decision.operation_advice }}</p>
          </div>
          <div>
            <div class="text-[11px] text-ink-3">持有周期</div>
            <p class="mt-0.5 text-xs text-ink-2">{{ decision.holding_period }}</p>
          </div>
          <div>
            <div class="text-[11px] text-ink-3">仓位建议</div>
            <p class="mt-0.5 text-xs text-ink-2">{{ decision.position_size }}</p>
          </div>
        </div>

        <div
          v-if="decision.position_advice"
          class="mt-4 rounded-md border border-line bg-surface px-4 py-3"
        >
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs font-medium text-ink">我的持仓建议</span>
            <span
              v-if="decision.position_action"
              class="rounded px-1.5 py-0.5 text-[11px] font-semibold"
              :class="positionActionTone"
            >
              {{ decision.position_action }}
            </span>
          </div>
          <p class="mt-1 text-xs leading-relaxed text-ink-2">{{ decision.position_advice }}</p>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <div v-for="item in decisionLevelItems" :key="item.label" class="rounded-md bg-surface px-3 py-2">
            <div class="text-[11px] text-ink-3">{{ item.label }}</div>
            <div class="mt-1 text-[14px] font-semibold tabular-nums" :class="item.tone">
              {{ item.value }}
            </div>
          </div>
        </div>

        <div
          v-if="decision.levels"
          class="mt-3 flex flex-wrap items-center gap-2 text-[11px]"
          data-pdf-hide
        >
          <span class="text-ink-3">关键价位提醒</span>
          <button
            type="button"
            class="rounded-md border border-line-strong bg-canvas px-2.5 py-1 text-ink-2 transition-colors hover:border-ink-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!!alertSavingKind"
            @click="createLevelAlert('entry')"
          >
            {{ alertSavingKind === 'entry' ? '设置中…' : `入场 ≤ ${decision.levels.entry.toFixed(2)}` }}
          </button>
          <button
            type="button"
            class="rounded-md border border-line-strong bg-canvas px-2.5 py-1 text-ink-2 transition-colors hover:border-ink-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!!alertSavingKind"
            @click="createLevelAlert('take_profit')"
          >
            {{
              alertSavingKind === 'take_profit'
                ? '设置中…'
                : `止盈 ≥ ${decision.levels.take_profit.toFixed(2)}`
            }}
          </button>
          <button
            type="button"
            class="rounded-md border border-line-strong bg-canvas px-2.5 py-1 text-ink-2 transition-colors hover:border-ink-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!!alertSavingKind"
            @click="createLevelAlert('stop_loss')"
          >
            {{
              alertSavingKind === 'stop_loss'
                ? '设置中…'
                : `止损 ≤ ${decision.levels.stop_loss.toFixed(2)}`
            }}
          </button>
          <span v-if="alertMessage" class="text-down">{{ alertMessage }}</span>
          <span v-if="alertError" class="text-danger">{{ alertError }}</span>
        </div>

        <div class="mt-4 grid gap-5 lg:grid-cols-2">
          <div>
            <h3 class="text-xs font-medium text-ink">核心理由</h3>
            <ul class="mt-2 space-y-2">
              <li
                v-for="(item, index) in decision.key_reasons"
                :key="index"
                class="flex gap-2 text-xs leading-relaxed text-ink-2"
              >
                <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
                {{ item }}
              </li>
            </ul>
          </div>
          <div>
            <h3 class="text-xs font-medium text-ink">风险提示</h3>
            <ul class="mt-2 space-y-2">
              <li
                v-for="(item, index) in decision.risks"
                :key="index"
                class="flex gap-2 text-xs leading-relaxed text-ink-2"
              >
                <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-warn" />
                {{ item }}
              </li>
            </ul>
          </div>
        </div>

        <p v-if="decision.risk_warning" class="mt-4 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn">
          风险提示：{{ decision.risk_warning }}
        </p>

        <div
          v-if="decision.consensus.length || decision.dissent.length"
          class="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-ink-3"
        >
          <span v-if="decision.consensus.length">共识：{{ decision.consensus.join('；') }}</span>
          <span v-if="decision.dissent.length">分歧：{{ decision.dissent.join('；') }}</span>
        </div>
      </section>

      <PublicInfoPanel
        class="mt-4"
        :used="report.web_search_used"
        :sources="report.web_sources"
        :used-by="webUsedBy"
      />

      <section
        v-if="report.analysts.length"
        class="mt-4 rounded-lg border border-line bg-canvas p-5"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-ink">评分概览</h2>
          <span class="text-[11px] text-ink-3">0–100；风险维度分数越高表示风险越低</span>
        </div>

        <div class="mt-4 grid items-center gap-6 lg:grid-cols-[300px_1fr]">
          <AnalystRadar
            :series="[{ label: '本次分析', analysts: report.analysts }]"
            :size="300"
          />

          <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div
              v-for="analyst in report.analysts"
              :key="analyst.key"
              class="rounded-md bg-surface px-3 py-2.5"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-[11px] text-ink-3">{{ analyst.name }}</span>
                <span
                  class="text-[13px] font-semibold tabular-nums"
                  :class="analystScoreTone(analyst.score)"
                >
                  {{ analyst.score }}
                </span>
              </div>
              <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-2">
                <div
                  class="h-full rounded-full"
                  :class="
                    analyst.score >= 65
                      ? 'bg-up'
                      : analyst.score < 45
                        ? 'bg-down'
                        : 'bg-flat'
                  "
                  :style="{ width: `${Math.max(0, Math.min(100, analyst.score))}%` }"
                />
              </div>
              <div class="mt-1 text-[10px] text-ink-3">{{ analyst.rating }}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="mt-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-ink">六位分析师</h2>
          <span class="text-[11px] text-ink-3">完整依据、风险与数据来源</span>
        </div>
        <div class="mt-3 grid gap-4 lg:grid-cols-2">
          <div
            v-for="analyst in report.analysts"
            :key="analyst.key"
            class="rounded-lg border border-line bg-canvas p-4"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <h3 class="text-[13px] font-medium text-ink">{{ analyst.name }}分析师</h3>
                <span
                  v-if="analyst.engine === 'llm'"
                  class="rounded-full bg-primary-soft px-1.5 py-0.5 text-[10px] font-medium text-primary"
                >
                  LLM
                </span>
                <span
                  v-else
                  class="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-3"
                >
                  规则
                </span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-[11px] text-ink-3">{{ analyst.rating }}</span>
                <span class="text-[18px] font-semibold tabular-nums" :class="analystScoreTone(analyst.score)">
                  {{ analyst.score }}
                </span>
              </div>
            </div>
            <p class="mt-2 text-xs leading-relaxed text-ink-2">{{ analyst.summary }}</p>

            <div v-if="analyst.points.length" class="mt-3">
              <h4 class="text-[11px] font-medium text-ink-3">依据</h4>
              <ul class="mt-1 space-y-1">
                <li
                  v-for="(point, index) in analyst.points"
                  :key="index"
                  class="flex gap-2 text-xs leading-relaxed text-ink-2"
                >
                  <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
                  {{ point }}
                </li>
              </ul>
            </div>

            <div v-if="analyst.risks.length" class="mt-3">
              <h4 class="text-[11px] font-medium text-ink-3">风险</h4>
              <ul class="mt-1 space-y-1">
                <li
                  v-for="(risk, index) in analyst.risks"
                  :key="index"
                  class="flex gap-2 text-xs leading-relaxed text-ink-2"
                >
                  <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-warn" />
                  {{ risk }}
                </li>
              </ul>
            </div>

            <div class="mt-3 flex flex-wrap gap-2 text-[11px] text-ink-3">
              <span v-if="analyst.data_sources.length">
                来源：{{ formatSourceList(analyst.data_sources) }}
              </span>
              <span v-if="analyst.missing.length" class="text-warn">
                缺口：{{ analyst.missing.join('、') }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <DiscussionTimeline
        v-if="report.discussion && report.discussion.turns.length"
        class="mt-4"
        :discussion="report.discussion"
      />

      <section class="mt-4 rounded-lg border border-line bg-surface p-4 text-[11px] leading-relaxed text-ink-3">
        <div>数据覆盖：{{ coverageLabels.join('、') }}<template v-if="dataGaps.length">；数据缺口：{{ dataGaps.join('、') }}</template>。</div>
        <div class="mt-1">{{ report.disclaimer }}</div>
      </section>
      </div>
    </template>
  </AppShell>
</template>
