<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import type { AIAnalysisResponse } from '@/api/ai'
import { reportsApi } from '@/api/reports'
import AppShell from '@/components/layout/AppShell.vue'
import PublicInfoPanel from '@/components/report/PublicInfoPanel.vue'
import { getErrorMessage } from '@/utils/errors'
import { formatQuoteTime, formatSourceList } from '@/utils/market'

const route = useRoute()
const report = ref<AIAnalysisResponse | null>(null)
const createdAt = ref('')
const loading = ref(false)
const error = ref('')

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
const levels = computed(() => {
  const data = decision.value?.levels
  if (!data) return []
  return [
    { label: '支撑位', value: data.support.toFixed(2), tone: 'text-ink' },
    { label: '压力位', value: data.resistance.toFixed(2), tone: 'text-ink' },
    { label: '建议入场', value: data.entry.toFixed(2), tone: 'text-primary' },
    { label: '止盈', value: data.take_profit.toFixed(2), tone: 'text-up' },
    { label: '止损', value: data.stop_loss.toFixed(2), tone: 'text-down' },
    { label: '盈亏比', value: `${data.risk_reward.toFixed(2)} : 1`, tone: 'text-ink' },
  ]
})
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

function analystTone(score: number): string {
  if (score >= 65) return 'text-up'
  if (score < 45) return 'text-down'
  return 'text-ink-2'
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
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
        v-if="report"
        :to="`/stock/${report.symbol}`"
        class="inline-flex items-center gap-1 transition-colors hover:text-ink"
      >
        <span aria-hidden="true">←</span>
        返回 {{ report.name }} 行情
      </RouterLink>
      <RouterLink
        v-else
        to="/"
        class="inline-flex items-center gap-1 transition-colors hover:text-ink"
      >
        <span aria-hidden="true">←</span>
        返回工作台
      </RouterLink>
      <RouterLink to="/reports" class="transition-colors hover:text-ink">全部历史报告</RouterLink>
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
      <section class="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="text-[24px] font-semibold tracking-tight text-ink">{{ report.name }}</h1>
            <span class="text-xs tabular-nums text-ink-3">{{ report.symbol }}</span>
            <span v-if="decision" class="rounded-md px-2.5 py-1 text-sm font-semibold" :class="decisionBadgeClass">
              {{ decision.rating }}
            </span>
          </div>
          <div class="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span class="text-[28px] font-semibold leading-none tabular-nums" :class="priceTone">
              {{ report.price == null ? '—' : report.price.toFixed(2) }}
            </span>
            <span class="text-sm font-medium tabular-nums" :class="priceTone">
              {{ report.change_pct == null ? '—' : `${report.change_pct > 0 ? '+' : ''}${report.change_pct.toFixed(2)}%` }}
            </span>
            <span class="text-xs text-ink-3">生成于 {{ formatTime(createdAt) }}</span>
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
        <div class="text-right text-[11px] leading-relaxed text-ink-3">
          <div>{{ report.model }}</div>
          <div>{{ report.prompt_version }}</div>
          <div>报价时间 {{ formatQuoteTime(report.data_as_of) }}</div>
          <div>数据源 {{ dataSourceText }}</div>
        </div>
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

        <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <div v-for="item in levels" :key="item.label" class="rounded-md bg-surface px-3 py-2">
            <div class="text-[11px] text-ink-3">{{ item.label }}</div>
            <div class="mt-1 text-[14px] font-semibold tabular-nums" :class="item.tone">
              {{ item.value }}
            </div>
          </div>
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
              <h3 class="text-[13px] font-medium text-ink">{{ analyst.name }}分析师</h3>
              <div class="flex items-center gap-2">
                <span class="text-[11px] text-ink-3">{{ analyst.rating }}</span>
                <span class="text-[18px] font-semibold tabular-nums" :class="analystTone(analyst.score)">
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

      <section class="mt-4 rounded-lg border border-line bg-surface p-4 text-[11px] leading-relaxed text-ink-3">
        <div>数据覆盖：{{ coverageLabels.join('、') }}<template v-if="dataGaps.length">；数据缺口：{{ dataGaps.join('、') }}</template>。</div>
        <div class="mt-1">{{ report.disclaimer }}</div>
      </section>
    </template>
  </AppShell>
</template>
